from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Barrier, Event
import unittest
from unittest.mock import patch

from fastapi import HTTPException

from app.models.domain import DocumentDebugRecord
from app.persistence.document_repository import (
    DocumentLegacyImportConflict,
    DocumentRepository,
    DocumentRevisionConflict,
    replace_document_in_session,
)
from app.services.documents import DocumentService
from app.services.local_store import LocalJsonStore
from tests.support.document_operations import FakeDocumentParser, FakeStudyArrangement, create_document
from tests.support.planning_operations import planning_debug, planning_document


class DocumentRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.store = LocalJsonStore(self.root)
        self.service = DocumentService(self.store, FakeDocumentParser(), FakeStudyArrangement())

    def tearDown(self) -> None:
        self.store.close()
        self.temp.cleanup()

    def seed(self, document_id: str = "doc-cas"):
        document = planning_document(document_id=document_id)
        self.service.repository.insert(document)
        self.store.save_item("document_debug", document.id, planning_debug(document))
        return document

    def rename(self, document, title: str):
        return self.service.update_study_unit_title(
            document_id=document.id,
            study_unit_id=document.study_units[0].id,
            title=title,
            expected_revision=document.revision,
        )

    def test_interleaved_uploads_keep_both_rows(self) -> None:
        paused, resume = Event(), Event()
        insert = self.service.repository.insert

        def delayed_insert(document):
            if document.original_filename == "first.pdf":
                paused.set()
                if not resume.wait(5):
                    raise TimeoutError("upload_not_resumed")
            insert(document)

        with patch.object(self.service.repository, "insert", side_effect=delayed_insert):
            with ThreadPoolExecutor(max_workers=2) as executor:
                first = executor.submit(create_document, self.service, "first.pdf")
                try:
                    self.assertTrue(paused.wait(5))
                    second = create_document(self.service, "second.pdf")
                finally:
                    resume.set()
                first = first.result(timeout=5)
        self.assertEqual({item.id for item in self.service.list_documents()}, {first.id, second.id})

    def test_legacy_list_cannot_delete_or_overwrite_runtime_rows(self) -> None:
        first = self.seed("doc-first")
        second = self.seed("doc-second")
        self.store.save_list("documents", [first])
        self.assertEqual(len(self.service.list_documents()), 2)
        renamed = self.rename(first, "New title")
        with self.assertRaises(DocumentLegacyImportConflict):
            self.store.save_list("documents", [second, first])
        self.assertEqual(self.service.require_document(first.id), renamed)
        self.assertEqual(self.service.require_document(second.id), second)

    def test_titles_on_different_documents_survive_concurrent_writes(self) -> None:
        documents = [self.seed("doc-one"), self.seed("doc-two")]
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda doc: self.rename(doc, doc.id), documents))
        for updated in results:
            self.assertEqual(updated.revision, 1)
            self.assertEqual(self.service.require_document(updated.id), updated)
            self.assertEqual(self.service.require_debug_report(updated.id).study_units[0].title, updated.id)

    def test_same_revision_writers_have_one_winner_after_both_reads(self) -> None:
        document = self.seed()
        ready = Barrier(2)

        def race(session, candidate, *, expected_revision):
            ready.wait(timeout=5)
            replace_document_in_session(session, candidate, expected_revision=expected_revision)

        def rename(title):
            try:
                return self.rename(document, title)
            except HTTPException as exc:
                self.assertEqual((exc.status_code, exc.detail), (409, "document_revision_conflict"))
                return None

        with patch("app.persistence.document_repository.replace_document_in_session", side_effect=race):
            with ThreadPoolExecutor(max_workers=2) as executor:
                results = list(executor.map(rename, ["One", "Two"]))
        winners = [result for result in results if result is not None]
        self.assertEqual(len(winners), 1)
        winner = winners[0]
        self.assertEqual(self.service.require_document(document.id), winner)
        self.assertEqual(self.service.require_debug_report(document.id).study_units[0].title, winner.study_units[0].title)

    def test_debug_failure_rolls_back_title_and_revision(self) -> None:
        document = self.seed()
        debug = self.service.require_debug_report(document.id)
        with patch(
            "app.persistence.document_repository.DocumentDebugRecord.model_validate",
            side_effect=RuntimeError("debug_unreadable"),
        ):
            with self.assertRaisesRegex(RuntimeError, "debug_unreadable"):
                self.rename(document, "Rejected")
        self.assertEqual(self.service.require_document(document.id), document)
        self.assertEqual(self.service.require_debug_report(document.id), debug)

    def test_title_rejects_processing_and_stale_revision_then_reads_back_after_restart(self) -> None:
        document = self.seed()
        operation, processing = self.service.process_repository.admit(document_id=document.id, force_ocr=False)
        for candidate, detail in (
            (document, "document_revision_conflict"),
            (processing, "document_processing_already_active"),
        ):
            with self.assertRaises(HTTPException) as error:
                self.rename(candidate, "Rejected")
            self.assertEqual((error.exception.status_code, error.exception.detail), (409, detail))
        self.service.process_repository.mark_interrupted(operation_id=operation.operation_id, error_code="test")
        restored = self.service.require_document(document.id)
        renamed = self.rename(restored, "Persisted")
        self.store.close()
        reopened = LocalJsonStore(self.root)
        try:
            self.assertEqual(DocumentRepository(reopened.database).get(document.id), renamed)
            debug = reopened.load_item("document_debug", document.id, DocumentDebugRecord)
            self.assertEqual(debug.study_units[0].title, "Persisted")
        finally:
            reopened.close()

    def test_parse_commit_and_cleanup_do_not_overwrite_a_newer_projection(self) -> None:
        document = create_document(self.service, "parse-race.pdf")
        commit = self.service.process_repository.commit_success

        def advance_then_commit(**kwargs):
            current = self.service.require_document(document.id)
            current.title = "Newer projection"
            current.status = "processed"
            current.revision += 1
            with self.store.database.session() as session:
                replace_document_in_session(session, current, expected_revision=current.revision - 1)
            return commit(**kwargs)

        with patch.object(self.service.process_repository, "commit_success", side_effect=advance_then_commit):
            with self.assertRaises(DocumentRevisionConflict):
                self.service.process_document(document.id)
        current = self.service.require_document(document.id)
        self.assertEqual((current.title, current.status, current.revision), ("Newer projection", "processed", 2))
        self.assertFalse(current.debug_ready)
        self.assertEqual(self.service.process_repository.latest(document_id=document.id).status.value, "failed")

    def test_competing_terminal_transitions_restore_the_processing_revision_once(self) -> None:
        document = create_document(self.service, "terminal-race.pdf")
        repository = self.service.process_repository
        operation, _ = repository.admit(document_id=document.id, force_ocr=False)
        ready = Barrier(2)

        def finish(method):
            ready.wait(timeout=5)
            return method(operation_id=operation.operation_id, error_code="terminal_race")

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(finish, [repository.mark_failed, repository.mark_interrupted]))
        self.assertEqual(results[0].status, results[1].status)
        self.assertEqual(self.service.require_document(document.id).revision, 2)
