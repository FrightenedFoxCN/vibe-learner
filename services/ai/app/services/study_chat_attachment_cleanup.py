from __future__ import annotations

from collections.abc import Callable
from errno import EEXIST, ENOTEMPTY
from pathlib import Path
import re
from stat import S_ISDIR, S_ISREG

from sqlalchemy import select

from app.models.domain import StudySessionRecord
from app.models.study_chat_operation import StudyChatOperationStatus
from app.persistence.models import StudyChatOperationRow
from app.services.local_store import LocalJsonStore


_SESSION_DIRECTORY = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
_OPERATION_DIRECTORY = re.compile(r"study-chat-op-[0-9a-f]{16}")
# Fencing rules out a later commit, but these transitions can be made by an
# observer while the original worker still holds/uses staged files.
_UNPROVEN_QUIESCENCE = {
    "study_chat_execution_deadline_expired",
    "study_chat_harness_operation_legacy_unbound",
}


def validate_chat_attachment_cleanup_scope(session_id: str) -> None:
    if session_id and not _SESSION_DIRECTORY.fullmatch(session_id):
        raise ValueError("study_chat_session_id_invalid")


def cleanup_study_chat_attachment_residue(
    store: LocalJsonStore,
    *,
    session_id: str,
) -> int:
    root = store.chat_attachment_root
    if not _is_real_directory(root):
        return 0
    root = root.resolve()
    session_dirs = [root / session_id] if session_id else _entries(root)
    # Capture only operation directories/files that already exist. The writer
    # publishes its admission and claim in the DB before creating them; taking
    # a DB snapshot first could miss a new operation that stages during discovery.
    candidates = {
        operation_dir: tuple(
            path for path in _entries(operation_dir) if _has_mode(path, S_ISREG)
        )
        for session_dir in session_dirs
        if _SESSION_DIRECTORY.fullmatch(session_dir.name)
        and _is_real_directory(session_dir)
        for operation_dir in _entries(session_dir)
        if _OPERATION_DIRECTORY.fullmatch(operation_dir.name)
        and _is_real_directory(operation_dir)
    }
    if not candidates:
        return 0

    operations = _load_candidate_operations(store, {path.name for path in candidates})
    candidates = {
        directory: files
        for directory, files in candidates.items()
        if _is_reclaimable(directory, operations.get(directory.name))
    }
    if not candidates:
        return 0
    # Protect persisted references independently of operation metadata, including
    # legacy projections. Flat and unrecognised layouts are never swept: absence
    # from the current database is not proof of ownership for those files.
    referenced_paths = {
        Path(attachment.stored_path).resolve()
        for session in store.load_list("sessions", StudySessionRecord)
        for turn in session.turns
        for attachment in turn.learner_attachments
        if attachment.stored_path
    }

    removed = 0
    for directory, files in candidates.items():
        if not _is_real_directory(directory) or directory.resolve() != directory:
            continue
        for path in files:
            if path not in referenced_paths and _has_mode(path, S_ISREG):
                try:
                    path.unlink()
                except FileNotFoundError:
                    continue  # concurrent cleanup or terminal compensation
                removed += 1
        try:
            directory.rmdir()
        except FileNotFoundError:
            pass
        except OSError as exc:
            if exc.errno not in (ENOTEMPTY, EEXIST):
                raise
    return removed


def _is_reclaimable(directory: Path, owner: tuple[str, str, str] | None) -> bool:
    # No admission means no writer. A recognized directory in the wrong session
    # is inconsistent, not an orphan; leave it untouched for diagnosis.
    if owner is None:
        return True
    owner_session, status, error_code = owner
    return (
        owner_session == directory.parent.name
        and status
        in {
            StudyChatOperationStatus.NOT_COMMITTED.value,
            StudyChatOperationStatus.UNCERTAIN.value,
        }
        and error_code not in _UNPROVEN_QUIESCENCE
    )


def _load_candidate_operations(
    store: LocalJsonStore,
    operation_ids: set[str],
) -> dict[str, tuple[str, str, str]]:
    ids = sorted(operation_ids)
    owners = {}
    with store.database.session() as session:
        for start in range(0, len(ids), 500):
            rows = session.execute(
                select(
                    StudyChatOperationRow.operation_id,
                    StudyChatOperationRow.session_id,
                    StudyChatOperationRow.status,
                    StudyChatOperationRow.error_code,
                ).where(
                    StudyChatOperationRow.operation_id.in_(ids[start : start + 500])
                )
            )
            for operation_id, session_id, status, error_code in rows:
                owners[operation_id] = (session_id, status, error_code)
    return owners


def _entries(directory: Path) -> list[Path]:
    try:
        return list(directory.iterdir())
    except FileNotFoundError:
        return []


def _is_real_directory(path: Path) -> bool:
    return _has_mode(path, S_ISDIR) and not path.is_junction()


def _has_mode(path: Path, test: Callable[[int], bool]) -> bool:
    try:
        return test(path.lstat().st_mode)
    except FileNotFoundError:
        return False
