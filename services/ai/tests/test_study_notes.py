from contextlib import ExitStack
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from fastapi.testclient import TestClient

from app.app_factory import create_app
from app.core.settings import Settings
from app.models.domain import SessionMemoryRecord


ARCHIVE_VERSION = "study-note-archive-v1"
NOTE_FIELDS = {
    "id",
    "session_id",
    "title",
    "content",
    "revision",
    "created_at",
    "updated_at",
}
SUMMARY_FIELDS = {"id", "title", "excerpt", "revision", "created_at", "updated_at"}


class StudyNotesTests(TestCase):
    def setUp(self):
        root = Path(self.enterContext(TemporaryDirectory()))
        self.settings = Settings(
            database_url=f"sqlite:///{root / 'study-notes.db'}",
            storage_root=str(root / "storage"),
            auto_migrate_local_data=False,
            plan_provider="mock",
            ocr_engine="disabled",
        )
        self.clients = self.enterContext(ExitStack())
        self.restart_client()

    def restart_client(self, *, raise_server_exceptions=True):
        self.clients.close()
        self.client = self.clients.enter_context(
            TestClient(
                create_app(settings=self.settings),
                raise_server_exceptions=raise_server_exceptions,
            )
        )

    @property
    def container(self):
        return self.client.app.state.container

    def assert_status(self, response, status):
        self.assertEqual(response.status_code, status, response.text)

    def new_session(self):
        response = self.client.post(
            "/study-sessions",
            json={
                "document_id": "",
                "persona_id": self.container.persona_engine.list_personas()[0].id,
                "study_unit_id": "notes-fixture",
            },
        )
        self.assert_status(response, 200)
        return response.json()

    def session(self, session_id):
        response = self.client.get(f"/study-sessions/{session_id}")
        self.assert_status(response, 200)
        return response.json()

    def notes_path(self, session_id):
        return f"/study-sessions/{session_id}/notes"

    def create_note(self, path, title, content):
        response = self.client.post(path, json={"title": title, "content": content})
        self.assert_status(response, 201)
        note = response.json()
        self.assert_note(note, path.split("/")[2], title, content, revision=1)
        return note

    def assert_note(self, note, session_id, title, content, *, revision):
        self.assertEqual(set(note), NOTE_FIELDS)
        self.assertIsInstance(note["id"], str)
        self.assertTrue(note["id"])
        self.assertEqual(note["session_id"], session_id)
        self.assertEqual(note["title"], title)
        self.assertEqual(note["content"], content)
        self.assertEqual(note["revision"], revision)
        self.assertGreaterEqual(
            datetime.fromisoformat(note["updated_at"]),
            datetime.fromisoformat(note["created_at"]),
        )

    def get_note(self, path, note_id):
        response = self.client.get(f"{path}/{note_id}")
        self.assert_status(response, 200)
        return response.json()

    def list_notes(self, path, **params):
        response = self.client.get(path, params=params)
        self.assert_status(response, 200)
        page = response.json()
        self.assertEqual(set(page), {"items", "next_offset"})
        for item in page["items"]:
            self.assertEqual(set(item), SUMMARY_FIELDS)
            self.assertIsInstance(item["excerpt"], str)
        return page

    def assert_empty(self, path):
        self.assertEqual(self.list_notes(path), {"items": [], "next_offset": None})

    def note_ids(self, path, **params):
        return [item["id"] for item in self.list_notes(path, **params)["items"]]

    def export_notes(self, path, **params):
        response = self.client.get(f"{path}/export", params=params)
        self.assert_status(response, 200)
        self.assertEqual(
            response.headers["content-type"].split(";", 1)[0], "application/json"
        )
        self.assertEqual(
            response.headers["content-disposition"].split(";", 1)[0].lower(),
            "attachment",
        )
        document = response.json()
        self.assertEqual(set(document), {"schema_version", "notes", "next_after"})
        self.assertEqual(document["schema_version"], ARCHIVE_VERSION)
        return document

    def archive(self, notes):
        return {"schema_version": ARCHIVE_VERSION, "notes": notes, "next_after": None}

    def import_archive(self, path, document):
        response = self.client.post(f"{path}/import", json=document)
        self.assert_status(response, 201)
        result = response.json()
        self.assertEqual(set(result), {"note_ids"})
        ids = result["note_ids"]
        self.assertEqual(len(ids), len(document["notes"]))
        self.assertEqual(len(set(ids)), len(ids))
        return ids

    def seed_memory(self, session_id, entries):
        records = [
            SessionMemoryRecord(
                id=f"legacy-memory-{index}",
                key=key,
                content=content,
                created_at="2025-01-01T00:00:00+00:00",
                updated_at="2025-01-01T00:00:00+00:00",
            )
            for index, (key, content) in enumerate(entries.items())
        ]

        def replace_memory(record):
            record.session_memory = records

        self.container.study_session_service.repository.mutate(
            session_id=session_id, mutation=replace_memory
        )
        return self.session(session_id)

    def assert_session_unchanged(self, baseline):
        after = self.session(baseline["id"])
        for key in ("revision", "session_memory"):
            self.assertEqual(after[key], baseline[key])

    def test_crud_revision_conflicts_and_persistence_across_app_restarts(self):
        session_id = self.new_session()["id"]
        baseline = self.seed_memory(session_id, {"original memory": "Keep me"})
        path = self.notes_path(session_id)
        before = self.create_note(path, "  Draft  ", "\n  Original text\t\n")
        note_path = f"{path}/{before['id']}"
        self.assertEqual(self.get_note(path, before["id"]), before)

        replacement = {"title": "\t Revised 标题 ", "content": "\n  全部替换\n\n"}
        updated = self.client.patch(
            note_path, json={**replacement, "expected_revision": 1}
        )
        self.assert_status(updated, 200)
        after = updated.json()
        self.assert_note(after, session_id, **replacement, revision=2)
        self.assertEqual(after["id"], before["id"])
        self.assertEqual(after["created_at"], before["created_at"])
        self.assertGreaterEqual(
            datetime.fromisoformat(after["updated_at"]),
            datetime.fromisoformat(before["updated_at"]),
        )

        stale_patch = self.client.patch(
            note_path,
            json={"title": "Stale", "content": "Do not save", "expected_revision": 1},
        )
        stale_delete = self.client.delete(note_path, params={"expected_revision": 1})
        for response in (stale_patch, stale_delete):
            self.assert_status(response, 409)
            self.assertEqual(
                response.json()["detail"],
                {"code": "study_note_revision_conflict", "current_revision": 2},
            )
        self.assertEqual(self.get_note(path, after["id"]), after)
        self.assert_session_unchanged(baseline)

        # A StudySession revision change must not invalidate or rewrite the note.
        changed_session = self.client.patch(
            f"/study-sessions/{session_id}", json={"study_unit_id": "another-unit"}
        )
        self.assert_status(changed_session, 200)
        self.assertGreater(changed_session.json()["revision"], baseline["revision"])
        self.assertEqual(self.get_note(path, after["id"]), after)

        self.restart_client()
        self.assertEqual(self.get_note(path, after["id"]), after)
        self.assertEqual(self.note_ids(path), [after["id"]])
        response = self.client.delete(note_path, params={"expected_revision": 2})
        self.assert_status(response, 204)
        self.assertEqual(response.content, b"")
        self.assert_session_unchanged(changed_session.json())

        self.restart_client()
        self.assert_status(self.client.get(note_path), 404)
        self.assert_empty(path)

    def test_missing_and_cross_session_notes_are_404_without_mutation(self):
        owner = self.notes_path(self.new_session()["id"])
        other = self.notes_path(self.new_session()["id"])
        missing = self.notes_path("nonexistent-session")
        note = self.create_note(owner, "Private note", "Session scoped")
        removed = self.create_note(owner, "Removed", "No longer exists")
        removed_path = f"{owner}/{removed['id']}"
        self.assert_status(
            self.client.delete(removed_path, params={"expected_revision": 1}), 204
        )
        content = {"title": "Don't write", "content": "Still don't write"}
        for path in (
            f"{other}/{note['id']}",
            f"{missing}/{note['id']}",
            removed_path,
        ):
            with self.subTest(path=path):
                # A wrong revision must not reveal information about a foreign note.
                self.assert_status(self.client.get(path), 404)
                self.assert_status(
                    self.client.patch(path, json={**content, "expected_revision": 99}),
                    404,
                )
                self.assert_status(
                    self.client.delete(path, params={"expected_revision": 99}), 404
                )

        for method, url, body in (
            ("GET", missing, None),
            ("POST", missing, content),
            ("GET", f"{missing}/export", None),
            ("POST", f"{missing}/import", self.archive([content])),
            ("POST", f"{missing}/import-memory", {"keys": ["memory"]}),
        ):
            with self.subTest(method=method, url=url):
                self.assert_status(self.client.request(method, url, json=body), 404)
        self.assert_empty(other)
        self.assertEqual(self.get_note(owner, note["id"]), note)

    def test_search_casefolds_title_and_content_without_sql_wildcards(self):
        path = self.notes_path(self.new_session()["id"])
        other = self.notes_path(self.new_session()["id"])
        matches_title = self.create_note(path, "Straße 代数", "Title match only")
        matches_content = self.create_note(path, "Review", "重读 STRASSE 与代数")
        literal = self.create_note(path, "Progress 100%_done", "普通笔记")
        self.create_note(path, "Progress 100XYdone", "Not a wildcard match")
        self.create_note(other, "Straße 代数", "Progress 100%_done")
        edited = self.client.patch(
            f"{path}/{matches_title['id']}",
            json={
                "title": matches_title["title"],
                "content": "Edited, still only a title match",
                "expected_revision": 1,
            },
        )
        self.assert_status(edited, 200)
        matches_title = edited.json()
        expected_notes = {note["id"]: note for note in (matches_title, matches_content)}

        for query in ("sTrAsSe", "STRAẞE", "代数"):
            with self.subTest(query=query):
                expected = set(expected_notes)
                self.assertEqual(set(self.note_ids(path, q=query)), expected)
                first = self.list_notes(path, q=query, limit=1, offset=0)
                self.assertEqual(len(first["items"]), 1)
                self.assertEqual(first["next_offset"], 1)
                second = self.list_notes(path, q=query, limit=1, offset=1)
                self.assertEqual(len(second["items"]), 1)
                self.assertIsNone(second["next_offset"])
                items = first["items"] + second["items"]
                self.assertEqual({item["id"] for item in items}, expected)
                for item in items:
                    for key in SUMMARY_FIELDS - {"excerpt"}:
                        self.assertEqual(item[key], expected_notes[item["id"]][key])
                self.assertGreaterEqual(
                    datetime.fromisoformat(items[0]["updated_at"]),
                    datetime.fromisoformat(items[1]["updated_at"]),
                )
                self.assertEqual(
                    self.list_notes(path, q=query, limit=1, offset=0), first
                )
                self.assertEqual(
                    self.list_notes(path, q=query, limit=1, offset=1), second
                )
                self.assertEqual(
                    self.list_notes(path, q=query, offset=2),
                    {"items": [], "next_offset": None},
                )

        for query in ("100%_dOnE", "%", "_"):
            with self.subTest(query=query):
                self.assertEqual(self.note_ids(path, q=query), [literal["id"]])

    def test_input_length_nonblank_and_full_patch_validation(self):
        path = self.notes_path(self.new_session()["id"])
        title = " " + "题" * 158 + "\t"
        content = "\n" + "文" * 3998 + " "
        note = self.create_note(path, title, content)
        note_path = f"{path}/{note['id']}"

        for label, payload in (
            ("blank title", {"title": "\t \u3000", "content": content}),
            ("blank content", {"title": title, "content": " \t\n"}),
            ("long title", {"title": "题" + title, "content": content}),
            ("long content", {"title": title, "content": content + "文"}),
            ("missing title", {"content": content}),
            ("missing content", {"title": title}),
        ):
            with self.subTest(label=label):
                self.assert_status(self.client.post(path, json=payload), 422)
                self.assert_status(
                    self.client.patch(
                        note_path, json={**payload, "expected_revision": 1}
                    ),
                    422,
                )
        self.assert_status(
            self.client.patch(note_path, json={"title": title, "content": content}), 422
        )
        self.assert_status(self.client.delete(note_path), 422)

        response = self.client.post(
            path,
            content=rb'{"title":"private-note-marker \ud800","content":"Valid"}',
            headers={"Content-Type": "application/json"},
        )
        self.assert_status(response, 422)
        self.assertNotIn("private-note-marker", response.text)
        self.assertNotIn(r"\ud800", response.text.lower())
        self.assertEqual(response.json()["detail"][0]["loc"], ["body", "title"])
        self.assertEqual(self.note_ids(path), [note["id"]])
        self.assertEqual(self.get_note(path, note["id"]), note)

    def test_oversized_chunked_create_body_is_rejected_without_saving(self):
        path = self.notes_path(self.new_session()["id"])
        # A syntactically valid note padded past the raw body limit, without a
        # Content-Length header. Field validation alone would permit this note.
        response = self.client.post(
            path,
            content=iter([b'{"title":"Sized","content":"Valid"}', b" " * (256 * 1024)]),
            headers={"Content-Type": "application/json"},
        )
        self.assertNotIn("content-length", response.request.headers)
        self.assertEqual(response.request.headers["transfer-encoding"], "chunked")
        self.assert_status(response, 413)
        self.assert_empty(path)

    def test_downloadable_archive_id_pagination_and_round_trip_append(self):
        source = self.notes_path(self.new_session()["id"])
        destination_session = self.new_session()
        destination = self.notes_path(destination_session["id"])
        existing = self.create_note(destination, "Existing", "Keep alongside imports")
        created = [
            self.create_note(source, title, content)
            for title, content in (
                ("  标题一  ", "\n第一条\t\n"),
                ("Title two", "Second\n\nparagraph"),
                ("Title two", "Different content for the same title"),
            )
        ]
        first = self.export_notes(source, limit=2)
        self.assertEqual(len(first["notes"]), 2)
        self.assertIsInstance(first["next_after"], str)
        self.assertTrue(first["next_after"])
        last = self.export_notes(source, limit=2, after=first["next_after"])
        self.assertEqual(len(last["notes"]), 1)
        self.assertIsNone(last["next_after"])
        selected = first["notes"] + last["notes"]
        self.assertEqual(
            selected,
            [
                {"title": note["title"], "content": note["content"]}
                for note in sorted(created, key=lambda note: note["id"])
            ],
        )

        # Import the actual export documents, including the nonterminal cursor.
        imported = self.import_archive(destination, first) + self.import_archive(
            destination, last
        )
        self.assertEqual(len(set(imported)), len(created))
        self.assertTrue(set(imported).isdisjoint({note["id"] for note in created}))
        self.assertEqual(set(self.note_ids(destination)), {existing["id"], *imported})
        self.assertEqual(self.get_note(destination, existing["id"]), existing)
        self.assertEqual(set(self.note_ids(source)), {note["id"] for note in created})
        for note_id, payload in zip(imported, selected, strict=True):
            self.assert_note(
                self.get_note(destination, note_id),
                destination_session["id"],
                **payload,
                revision=1,
            )
        self.assert_session_unchanged(destination_session)

    def test_archive_validation_rejects_entire_batch_and_accepts_200(self):
        path = self.notes_path(self.new_session()["id"])
        original = self.create_note(path, "Existing", "Do not alter")
        valid = {"title": "Valid first member", "content": "Would otherwise append"}
        for label, document in (
            ("version", {**self.archive([valid]), "schema_version": "unknown-v1"}),
            ("top-level extra", {**self.archive([valid]), "unexpected": True}),
            ("member extra", self.archive([valid, {**valid, "id": "client-id"}])),
            ("member missing content", self.archive([valid, {"title": "Incomplete"}])),
            ("member wrong type", self.archive([valid, {**valid, "title": 101}])),
            ("member blank", self.archive([valid, {**valid, "content": " \n"}])),
            (
                "member oversized",
                self.archive([valid, {**valid, "content": "x" * 4001}]),
            ),
            ("201 items", self.archive([valid] * 201)),
        ):
            with self.subTest(label=label):
                response = self.client.post(f"{path}/import", json=document)
                self.assert_status(response, 422)
                self.assertEqual(self.note_ids(path), [original["id"]])
                self.assertEqual(self.get_note(path, original["id"]), original)

        # Equal entries are appended, not deduplicated, even at the size limit.
        ids = self.import_archive(path, self.archive([valid] * 200))
        for note_id in (ids[0], ids[-1]):
            self.assert_note(
                self.get_note(path, note_id),
                original["session_id"],
                **valid,
                revision=1,
            )
        self.assertNotIn(original["id"], ids)

    def test_archive_rolls_back_when_sqlite_rejects_a_later_insert(self):
        self.restart_client(raise_server_exceptions=False)
        path = self.notes_path(self.new_session()["id"])
        existing = self.create_note(path, "Existing", "Keep this note")
        database = self.container.database
        with database.engine.begin() as connection:
            connection.exec_driver_sql("""
                CREATE TRIGGER fixture_fail_study_note_insert
                BEFORE INSERT ON study_notes WHEN NEW.title = 'Abort this insert'
                BEGIN SELECT RAISE(ABORT, 'fixture note insert failure'); END
                """)
        document = self.archive(
            [
                {"title": "First insert", "content": "Must not escape rollback"},
                {"title": "Abort this insert", "content": "Trigger aborts this insert"},
            ]
        )
        response = self.client.post(f"{path}/import", json=document)
        self.assertTrue(response.is_error, response.text)
        self.assertEqual(self.note_ids(path), [existing["id"]])
        self.assertEqual(self.get_note(path, existing["id"]), existing)

        with database.engine.begin() as connection:
            connection.exec_driver_sql("DROP TRIGGER fixture_fail_study_note_insert")
        imported = self.import_archive(path, document)
        self.assertEqual(set(self.note_ids(path)), {existing["id"], *imported})

    def test_legacy_memory_requires_explicit_copy_and_missing_key_is_atomic(self):
        session_id = self.new_session()["id"]
        other_id = self.new_session()["id"]
        path = self.notes_path(session_id)
        other_path = self.notes_path(other_id)
        selected = {"旧笔记": "\n  保留这些空白 \t\n", "Key B": "Second legacy note"}
        baseline = self.seed_memory(session_id, {**selected, "Omit": "Not selected"})
        foreign = self.seed_memory(other_id, {"Other only": "Foreign memory"})
        self.assert_empty(path)
        self.assert_empty(other_path)
        self.assertEqual(self.export_notes(path), self.archive([]))
        self.restart_client()
        self.assert_empty(path)

        for missing_key in ("missing", "Other only"):
            with self.subTest(missing_key=missing_key):
                response = self.client.post(
                    f"{path}/import-memory", json={"keys": ["旧笔记", missing_key]}
                )
                self.assert_status(response, 422)
                self.assert_empty(path)
                self.assert_session_unchanged(baseline)

        response = self.client.post(
            f"{path}/import-memory", json={"keys": list(selected)}
        )
        self.assert_status(response, 201)
        result = response.json()
        self.assertEqual(set(result), {"note_ids"})
        ids = result["note_ids"]
        self.assertEqual(len(ids), len(selected))
        self.assertEqual(set(self.note_ids(path)), set(ids))
        copied = {note["title"]: note for note in (self.get_note(path, i) for i in ids)}
        self.assertEqual(set(copied), set(selected))
        for key, content in selected.items():
            self.assert_note(copied[key], session_id, key, content, revision=1)
        self.assert_empty(other_path)
        self.assert_session_unchanged(baseline)
        self.assert_session_unchanged(foreign)
