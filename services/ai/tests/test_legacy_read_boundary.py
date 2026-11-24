from dataclasses import replace
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

import fitz
from fastapi.testclient import TestClient

from app.app_factory import create_app
from app.core.settings import Settings
from app.models.domain import DocumentDebugRecord, DocumentRecord, StudySessionRecord
from app.persistence.document_repository import (
    DocumentLegacyImportConflict,
    DocumentRepository,
)
from app.persistence.migrate_local_data import migrate_from_legacy_store
from app.persistence.models import DocumentDebugRow
from app.persistence.study_session_repository import (
    StudySessionLegacyImportConflict,
    StudySessionRepository,
)
from app.services.local_store import LegacyLocalJsonStore, LocalJsonStore
from app.services.token_usage import TokenUsageService

STAMP = "2025-01-01T00:00:00+00:00"
DOCUMENT = {
    "id": "doc-legacy",
    "title": "Legacy fixture",
    "original_filename": "fixture.pdf",
    "stored_path": "/unused/fixture.pdf",
    "status": "uploaded",
    "ocr_status": "pending",
    "created_at": STAMP,
    "updated_at": STAMP,
}
SESSION = {
    "id": "session-legacy",
    "document_id": "doc-legacy",
    "persona_id": "persona-fixture",
    "section_id": "section-legacy",
    "status": "active",
    "turns": [],
    "created_at": STAMP,
    "updated_at": STAMP,
}


class LegacyReadBoundaryTests(TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(TemporaryDirectory()))

    def seed(self, root):
        root.mkdir(exist_ok=True)
        for name, item in (("documents", DOCUMENT), ("sessions", SESSION)):
            (root / f"{name}.json").write_text(json.dumps([item]), encoding="utf-8")

    def settings(self, *, desktop=False, auto_migrate=False):
        return Settings(
            database_url=f"sqlite:///{self.root / 'fixture.db'}",
            storage_root=str(self.root),
            desktop_mode=desktop,
            auto_migrate_local_data=auto_migrate,
            plan_provider="mock",
            ocr_engine="disabled",
        )

    def assert_legacy_bytes_unchanged(self):
        self.assertEqual(
            (self.root / "documents.json").read_text(), json.dumps([DOCUMENT])
        )
        self.assertEqual(
            (self.root / "sessions.json").read_text(), json.dumps([SESSION])
        )

    def assert_visible(self, client):
        document = client.get("/documents/doc-legacy/status")
        session = client.get("/study-sessions/session-legacy")
        self.assertEqual(document.status_code, 200, document.text)
        self.assertEqual(session.status_code, 200, session.text)
        self.assertEqual(document.json()["title"], DOCUMENT["title"])
        self.assertEqual(session.json()["study_unit_id"], SESSION["section_id"])

    def test_standalone_without_opt_in_does_not_import_at_start_or_on_read(self):
        self.seed(self.root)
        legacy_reads = []
        original_load_list = LegacyLocalJsonStore.load_list

        def track(store, name, model):
            if name in {"documents", "sessions"}:
                legacy_reads.append(name)
            return original_load_list(store, name, model)

        with patch.object(LegacyLocalJsonStore, "load_list", track):
            with TestClient(create_app(settings=self.settings())) as client:
                for path in (
                    "/documents/doc-legacy/status",
                    "/study-sessions/session-legacy",
                ):
                    response = client.get(path)
                    self.assertEqual(response.status_code, 404, response.text)
                for path in ("/documents", "/study-sessions"):
                    response = client.get(path)
                    self.assertEqual(response.status_code, 200, response.text)
                    self.assertEqual(response.json()["items"], [])
                container = client.app.state.container
                self.assertEqual(container.store.count_bucket("documents"), 0)
                self.assertEqual(container.store.count_bucket("sessions"), 0)
        self.assertEqual(legacy_reads, [])
        self.assert_legacy_bytes_unchanged()

    def test_packaged_desktop_imports_old_lists_at_start_without_touching_sources(self):
        self.seed(self.root)
        for _ in range(2):
            with TestClient(create_app(settings=self.settings(desktop=True))) as client:
                store = client.app.state.container.store
                self.assertEqual(store.count_bucket("documents"), 1)
                self.assertEqual(store.count_bucket("sessions"), 1)
                self.assert_visible(client)
        self.assert_legacy_bytes_unchanged()

    def test_packaged_desktop_skips_nonempty_bucket_but_imports_other_bucket(self):
        self.seed(self.root)
        with TestClient(create_app(settings=self.settings())) as client:
            container = client.app.state.container
            edited = DocumentRecord.model_validate(
                {**DOCUMENT, "title": "Database", "revision": 2}
            )
            DocumentRepository(container.database).insert(edited)
        with TestClient(create_app(settings=self.settings(desktop=True))) as client:
            store = client.app.state.container.store
            self.assertEqual(store.load_list("documents", DocumentRecord), [edited])
            self.assertEqual(store.count_bucket("sessions"), 1)
        self.assert_legacy_bytes_unchanged()

    def processed_legacy_fixture(self):
        # Generate the exact old mirror shape using normal document processing.
        source = replace(
            self.settings(), database_url=f"sqlite:///{self.root / 'source.db'}"
        )
        with fitz.open() as pdf:
            page = pdf.new_page()
            for index in range(8):
                page.insert_text(
                    (50, 50 + index * 20), "Vector spaces and linear transformations."
                )
            content = pdf.tobytes()
        with TestClient(create_app(settings=source)) as client:
            uploaded = client.post(
                "/documents",
                files={"file": ("vectors.pdf", content, "application/pdf")},
            )
            self.assertEqual(uploaded.status_code, 200, uploaded.text)
            doc_id = uploaded.json()["id"]
            processed = client.post(f"/documents/{doc_id}/process", json={})
            self.assertEqual(processed.status_code, 200, processed.text)
            document = DocumentRecord.model_validate(processed.json())
            self.assertTrue(document.debug_ready)
            self.assertGreater(document.chunk_count, 0)
            return document

    def test_desktop_restores_paired_legacy_debug_before_mock_planning(self):
        legacy_document = self.processed_legacy_fixture()
        legacy_files = LegacyLocalJsonStore(self.root)
        legacy_debug = legacy_files.load_item(
            "document_debug", legacy_document.id, DocumentDebugRecord
        )
        self.assertIsNotNone(legacy_debug)
        debug_path = self.root / "document_debug" / f"{legacy_document.id}.json"
        original_debug_bytes = debug_path.read_bytes()
        with TestClient(create_app(settings=self.settings(desktop=True))) as client:
            container = client.app.state.container
            # Do not call a public debug endpoint first: check DB, not fallback.
            pair = DocumentRepository(container.database).get_with_debug(
                legacy_document.id
            )
            self.assertEqual(pair, (legacy_document, legacy_debug))
            self.assertEqual(debug_path.read_bytes(), original_debug_bytes)
            response = client.post(
                "/learning-plans",
                json={
                    "document_id": legacy_document.id,
                    "persona_id": container.persona_engine.list_personas()[0].id,
                    "objective": "Learn linear transformations",
                    "expected_document_updated_at": legacy_document.updated_at,
                    "client_request_id": "legacy-document-fixture",
                },
            )
            self.assertEqual(response.status_code, 200, response.text)

    def test_desktop_leaves_debug_absent_when_document_version_differs(self):
        legacy_document = self.processed_legacy_fixture()
        debug_path = self.root / "document_debug" / f"{legacy_document.id}.json"
        original_debug_bytes = debug_path.read_bytes()
        with TestClient(create_app(settings=self.settings())) as client:
            db = client.app.state.container.database
            changed = legacy_document.model_copy(
                update={"revision": legacy_document.revision + 1}
            )
            DocumentRepository(db).insert(changed)
        with TestClient(create_app(settings=self.settings(desktop=True))) as client:
            db = client.app.state.container.database
            self.assertEqual(
                DocumentRepository(db).get_with_debug(changed.id), (changed, None)
            )
        self.assertEqual(debug_path.read_bytes(), original_debug_bytes)

    def test_desktop_never_overwrites_existing_debug(self):
        legacy_document = self.processed_legacy_fixture()
        debug_path = self.root / "document_debug" / f"{legacy_document.id}.json"
        original_debug_bytes = debug_path.read_bytes()
        with TestClient(create_app(settings=self.settings(desktop=True))) as client:
            container = client.app.state.container
            snapshot = DocumentRepository(container.database).get_with_debug(
                legacy_document.id
            )
            self.assertIsNotNone(snapshot)
            _, original_debug = snapshot
            self.assertIsNotNone(original_debug)
            # The authoritative row diverges; leave the compatibility file old.
            edited_debug = original_debug.model_copy(
                update={"parser_name": "database-parser"}
            )
            with container.database.session() as session:
                row = session.get(DocumentDebugRow, legacy_document.id)
                self.assertIsNotNone(row)
                row.payload = edited_debug.model_dump(mode="json")
        with TestClient(create_app(settings=self.settings(desktop=True))) as client:
            db = client.app.state.container.database
            self.assertEqual(
                DocumentRepository(db).get_with_debug(legacy_document.id),
                (legacy_document, edited_debug),
            )
        self.assertEqual(debug_path.read_bytes(), original_debug_bytes)

    def test_explicit_startup_opt_in_remains_available_on_standalone_service(self):
        self.seed(self.root)
        with TestClient(
            create_app(settings=self.settings(auto_migrate=True))
        ) as client:
            store = client.app.state.container.store
            self.assertEqual(store.count_bucket("documents"), 1)
            self.assertEqual(store.count_bucket("sessions"), 1)
            self.assert_visible(client)

    def test_explicit_import_repeats_safely_for_lists_and_never_overwrites_rows(self):
        self.seed(self.root)
        store = LocalJsonStore(self.root / "target")
        self.addCleanup(store.close)
        legacy = LegacyLocalJsonStore(self.root)
        usage = TokenUsageService(store.database)
        original_doc = DocumentRecord.model_validate(DOCUMENT)
        original_session = StudySessionRecord.model_validate(dict(SESSION))
        docs = DocumentRepository(store.database)
        sessions = StudySessionRepository(store.database)
        for _ in range(2):
            migrate_from_legacy_store(legacy, store, usage, self.root)
        self.assertEqual(docs.list(), [original_doc])
        self.assertEqual(sessions.list(), [original_session])

        (self.root / "documents.json").write_text(
            json.dumps([{**DOCUMENT, "title": "Changed fixture"}])
        )
        with self.assertRaises(DocumentLegacyImportConflict):
            migrate_from_legacy_store(legacy, store, usage, self.root)
        self.assertEqual(docs.list(), [original_doc])
        (self.root / "documents.json").write_text(json.dumps([DOCUMENT]))
        (self.root / "sessions.json").write_text(
            json.dumps([{**SESSION, "section_id": "changed"}])
        )
        with self.assertRaises(StudySessionLegacyImportConflict):
            migrate_from_legacy_store(legacy, store, usage, self.root)
        self.assertEqual(sessions.list(), [original_session])
