"""Commit-time domain validation for managed database sessions.

The connection observer sees ORM flushes and Core DML alike. Maintenance code
using the engine directly remains an explicit audit/migration boundary.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import event, literal, select
from sqlalchemy.orm import Session
from sqlalchemy.sql import visitors
from sqlalchemy.sql.elements import BindParameter, TextClause
from sqlalchemy.sql.dml import Delete, Insert, Update

from app.persistence.models import TavernMessageRow, TavernRunRow
from app.persistence.tavern_invariant_scanner import (
    TavernReferenceWriteSet,
    require_tavern_reference_integrity,
)


@dataclass
class TransactionWriteSet:
    room_ids: set[str] = field(default_factory=set)
    run_ids: set[str] = field(default_factory=set)
    message_ids: set[str] = field(default_factory=set)

    def record(self, table: str, values) -> None:
        if table == "tavern_rooms":
            self.room_ids.update(filter(None, [values.get("id")]))
        else:
            self.room_ids.update(filter(None, [values.get("room_id")]))
        if table == "tavern_runs":
            self.run_ids.update(filter(None, [values.get("id")]))
        elif table == "tavern_messages":
            self.message_ids.update(filter(None, [values.get("id")]))
        elif table == "tavern_run_steps":
            self.run_ids.update(filter(None, [values.get("run_id")]))

    def freeze(self) -> TavernReferenceWriteSet:
        return TavernReferenceWriteSet(
            frozenset(self.room_ids), frozenset(self.run_ids), frozenset(self.message_ids)
        )


_KEY = "domain_transaction_write_set"
_TABLES = {"tavern_rooms", "tavern_runs", "tavern_messages", "tavern_run_steps", "tavern_participants"}


def install_transaction_validation(engine, session_factory) -> None:
    event.listen(engine, "before_cursor_execute", _observe_write)
    event.listen(engine, "commit", _validate_connection)
    event.listen(engine, "savepoint", _ensure_outer_transaction)
    event.listen(session_factory, "after_begin", _begin)
    event.listen(session_factory, "before_commit", _validate)
    event.listen(session_factory, "after_transaction_end", _end)


def _ensure_outer_transaction(connection, name) -> None:
    # sqlite3 legacy transaction mode does not BEGIN for SELECT/SAVEPOINT.
    # Without this, RELEASE of the first savepoint commits data before the
    # outer domain validator runs, and its later rollback cannot undo it.
    if connection.dialect.name != "sqlite" or _KEY not in connection.info:
        return
    driver = connection.connection.driver_connection
    if not driver.in_transaction:
        cursor = driver.cursor()
        try:
            cursor.execute("BEGIN")
        finally:
            cursor.close()


def _begin(session, transaction, connection) -> None:
    write_set = session.info.setdefault(_KEY, TransactionWriteSet())
    connection.info[_KEY] = write_set
    session.info.setdefault("domain_connection_infos", []).append(connection.info)


def _end(session, transaction) -> None:
    if transaction.parent is not None:
        return
    for info in session.info.pop("domain_connection_infos", []):
        info.pop(_KEY, None)
    session.info.pop(_KEY, None)


def _validate(session) -> None:
    # A savepoint may be an intentionally incomplete aggregate. Validate only
    # the outer transaction; its write set survives flush and savepoint rollback.
    if session.in_nested_transaction():
        return
    session.flush()


def _validate_connection(connection) -> None:
    write_set = connection.info.get(_KEY)
    if write_set is None:
        return
    # Separate identity map, same database transaction: Core DML cannot leave
    # a stale ORM value in the commit proof. This also covers connection.commit.
    with Session(bind=connection) as reader:
        require_tavern_reference_integrity(reader, write_set=write_set.freeze())


def _observe_write(connection, cursor, sql, parameters, context, executemany) -> None:
    write_set = connection.info.get(_KEY)
    if write_set is None:
        return
    compiled = context.compiled
    statement = compiled.statement if compiled is not None else None
    if statement is not None and any(
        isinstance(node, (Insert, Update, Delete)) and node is not statement
        for node in visitors.iterate(statement)
    ):
        raise ValueError("transaction_nested_dml_requires_separate_statement")
    if not isinstance(statement, (Insert, Update, Delete)):
        # Opaque SQL cannot declare a reliable write set. Reads are permitted;
        # mutations use SQLAlchemy DML in managed sessions (engine maintenance
        # is intentionally outside this interface).
        if compiled is None or isinstance(statement, TextClause):
            if not sql.lstrip().upper().startswith("SELECT "):
                raise ValueError("transaction_opaque_sql_requires_structured_dml")
        return
    table = statement.table
    if table.name not in _TABLES:
        return
    if isinstance(statement, Insert) and (statement.select is not None or statement._multi_values):
        raise ValueError("tavern_insert_requires_parameter_rows")
    for bound in context.compiled_parameters:
        def resolve(element):
            if isinstance(element, BindParameter):
                key = compiled.bind_names.get(element, element.key)
                if key is not None and key in bound:
                    return literal(bound[key], type_=element.type)
            return None

        if isinstance(statement, (Update, Delete)):
            query = select(*(table.c[name] for name in ("id", "room_id", "run_id") if name in table.c))
            if statement.whereclause is not None:
                query = query.where(visitors.replacement_traverse(statement.whereclause, {}, resolve))
            for row in connection.execute(query).mappings():
                write_set.record(table.name, row)
                # Cascading deletes can remove referenced children before the
                # commit scanner sees them, so retain those identities too.
                if table.name == "tavern_rooms" and isinstance(statement, Delete):
                    _record_room_children(connection, write_set, row["id"])
        if not isinstance(statement, Delete):
            values = dict(bound)
            for column, value in (getattr(statement, "_values", None) or {}).items():
                name = getattr(column, "name", column)
                if name in {"id", "room_id", "run_id"}:
                    resolved = resolve(value)
                    if resolved is None:
                        raise ValueError("tavern_scope_identity_requires_literal")
                    values[name] = resolved.value
            if isinstance(statement, Insert):
                required = {
                    "tavern_rooms": {"id"},
                    "tavern_runs": {"id", "room_id"},
                    "tavern_messages": {"id", "room_id"},
                    "tavern_run_steps": {"run_id"},
                    "tavern_participants": {"room_id"},
                }[table.name]
                if not required <= values.keys():
                    raise ValueError("tavern_insert_requires_literal_scope")
            write_set.record(table.name, values)


def _record_room_children(connection, write_set, room_id) -> None:
    for model in (TavernRunRow, TavernMessageRow):
        table = model.__table__
        for row in connection.execute(select(table.c.id, table.c.room_id).where(table.c.room_id == room_id)).mappings():
            write_set.record(table.name, row)
