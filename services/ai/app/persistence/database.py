from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.persistence.models import Base


class Database:
    def __init__(self, url: str) -> None:
        engine_kwargs: dict[str, object] = {
            "future": True,
            "pool_pre_ping": True,
        }
        if url.startswith("sqlite"):
            engine_kwargs["connect_args"] = {"check_same_thread": False}
        self.url = url
        self.engine: Engine = create_engine(url, **engine_kwargs)
        if url.startswith("sqlite"):
            event.listen(self.engine, "connect", _enable_sqlite_foreign_keys)
        self._session_factory = sessionmaker(
            bind=self.engine,
            autoflush=False,
            expire_on_commit=False,
            future=True,
        )

        from app.persistence.transaction_validation import install_transaction_validation

        install_transaction_validation(self.engine, self._session_factory)

    def create_schema(self) -> None:
        self._repair_sqlite_harness_operation_binding_route()
        self._repair_sqlite_harness_artifact_audit_schema()
        self._migrate_sqlite_schema()
        Base.metadata.create_all(self.engine)
        if self.url.startswith("sqlite"):
            with self.engine.begin() as connection:
                self._ensure_sqlite_study_session_indexes(connection)
                self._ensure_sqlite_tavern_room_indexes(connection)
                self._ensure_sqlite_harness_operation_guards(connection)
                self._ensure_sqlite_harness_artifact_guards(connection)
                self._ensure_sqlite_harness_effect_guards(connection)
                self._ensure_sqlite_harness_runtime_guards(connection)

    def dispose(self) -> None:
        self.engine.dispose()

    @contextmanager
    def session(self) -> Iterator[Session]:
        session = self._session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def _migrate_sqlite_schema(self) -> None:
        if not self.url.startswith("sqlite"):
            return

        self._repair_sqlite_tavern_run_foreign_key()
        with self.engine.begin() as connection:
            table_names = {
                str(row[0])
                for row in connection.exec_driver_sql(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }

            if "learning_plans" in table_names:
                plan_columns = self._sqlite_column_names(connection, "learning_plans")
                for column in ("revision", "deleted"):
                    if column not in plan_columns:
                        connection.exec_driver_sql(
                            f"ALTER TABLE learning_plans ADD COLUMN {column} INTEGER NOT NULL DEFAULT 0"
                        )

            if "tavern_rooms" in table_names:
                tavern_columns = self._sqlite_column_names(connection, "tavern_rooms")
                if "creation_key" not in tavern_columns:
                    connection.exec_driver_sql(
                        "ALTER TABLE tavern_rooms ADD COLUMN creation_key VARCHAR(80)"
                    )
                if "creation_input_digest" not in tavern_columns:
                    connection.exec_driver_sql(
                        "ALTER TABLE tavern_rooms ADD COLUMN "
                        "creation_input_digest VARCHAR(64) NOT NULL DEFAULT ''"
                    )
                connection.exec_driver_sql(
                    "CREATE UNIQUE INDEX IF NOT EXISTS uq_tavern_rooms_creation_key "
                    "ON tavern_rooms (creation_key) WHERE creation_key IS NOT NULL"
                )

            if "tavern_run_steps" in table_names:
                step_columns = self._sqlite_column_names(connection, "tavern_run_steps")
                if "lease_owner" not in step_columns:
                    connection.exec_driver_sql(
                        "ALTER TABLE tavern_run_steps ADD COLUMN "
                        "lease_owner VARCHAR(64) NOT NULL DEFAULT ''"
                    )
                if "lease_expires_at" not in step_columns:
                    connection.exec_driver_sql(
                        "ALTER TABLE tavern_run_steps ADD COLUMN "
                        "lease_expires_at VARCHAR(64) NOT NULL DEFAULT ''"
                    )
                if "claim_count" not in step_columns:
                    connection.exec_driver_sql(
                        "ALTER TABLE tavern_run_steps ADD COLUMN "
                        "claim_count INTEGER NOT NULL DEFAULT 0"
                    )

            if "learning_plan_operations" in table_names:
                plan_operation_columns = self._sqlite_column_names(
                    connection,
                    "learning_plan_operations",
                )
                if "base_debug_digest" not in plan_operation_columns:
                    connection.exec_driver_sql(
                        "ALTER TABLE learning_plan_operations ADD COLUMN "
                        "base_debug_digest VARCHAR(64) NOT NULL DEFAULT ''"
                    )

            if "harness_artifacts" in table_names:
                artifact_columns = self._sqlite_column_names(
                    connection, "harness_artifacts"
                )
                if "deleted_at" not in artifact_columns:
                    connection.exec_driver_sql(
                        "ALTER TABLE harness_artifacts ADD COLUMN "
                        "deleted_at VARCHAR(64)"
                    )

            if "harness_artifact_access_audits" in table_names:
                audit_columns = self._sqlite_column_names(
                    connection, "harness_artifact_access_audits"
                )
                audit_additions = {
                    "authorization_outcome": "VARCHAR(32)",
                    "resolution_status": "VARCHAR(32) NOT NULL DEFAULT 'forbidden'",
                    "schema_name": "VARCHAR(64) NOT NULL DEFAULT 'HarnessArtifactResolutionAuditV1'",
                    "schema_version": "VARCHAR(64) NOT NULL DEFAULT 'harness-artifact-resolution-audit-v1'",
                }
                for column_name, declaration in audit_additions.items():
                    if column_name not in audit_columns:
                        connection.exec_driver_sql(
                            "ALTER TABLE harness_artifact_access_audits ADD COLUMN "
                            f"{column_name} {declaration}"
                        )

            for operation_table in (
                "document_process_operations",
                "learning_plan_operations",
                "study_chat_operations",
                "tavern_runs",
            ):
                if operation_table not in table_names:
                    continue
                operation_columns = self._sqlite_column_names(
                    connection,
                    operation_table,
                )
                if "harness_operation_id" not in operation_columns:
                    connection.exec_driver_sql(
                        f"ALTER TABLE {operation_table} ADD COLUMN "
                        "harness_operation_id VARCHAR(64)"
                    )
                if operation_table == "study_chat_operations" and "harness_trace" not in operation_columns:
                    connection.exec_driver_sql(
                        "ALTER TABLE study_chat_operations ADD COLUMN harness_trace JSON"
                    )

            for scene_table in ("scene_setup_states", "scene_library_entries"):
                if scene_table not in table_names:
                    continue
                scene_columns = self._sqlite_column_names(connection, scene_table)
                if "revision" not in scene_columns:
                    connection.exec_driver_sql(
                        f"ALTER TABLE {scene_table} ADD COLUMN "
                        "revision INTEGER NOT NULL DEFAULT 0"
                    )

            # Recover partially applied migrations that left a duplicate legacy table behind.
            if "study_sessions_legacy" in table_names and "study_sessions" not in table_names:
                connection.exec_driver_sql("ALTER TABLE study_sessions_legacy RENAME TO study_sessions")
                table_names.remove("study_sessions_legacy")
                table_names.add("study_sessions")

            if "study_sessions_legacy" in table_names and "study_sessions" in table_names:
                current_columns = self._sqlite_column_names(connection, "study_sessions")
                legacy_columns = self._sqlite_column_names(connection, "study_sessions_legacy")
                if "study_unit_id" in current_columns and "section_id" in legacy_columns:
                    connection.exec_driver_sql(
                        """
                        INSERT OR IGNORE INTO study_sessions (
                            id,
                            document_id,
                            persona_id,
                            plan_id,
                            study_unit_id,
                            status,
                            created_at,
                            updated_at,
                            payload
                        )
                        SELECT
                            id,
                            document_id,
                            persona_id,
                            plan_id,
                            section_id,
                            status,
                            created_at,
                            updated_at,
                            payload
                        FROM study_sessions_legacy
                        """
                    )
                    connection.exec_driver_sql("DROP TABLE study_sessions_legacy")
                    table_names.remove("study_sessions_legacy")

            if "study_sessions" not in table_names:
                return

            columns = self._sqlite_column_names(connection, "study_sessions")
            if "study_unit_id" not in columns and "section_id" in columns:
                self._rebuild_legacy_study_sessions_table(connection, source_table="study_sessions")
                columns = self._sqlite_column_names(connection, "study_sessions")
            if "revision" not in columns:
                connection.exec_driver_sql(
                    "ALTER TABLE study_sessions ADD COLUMN "
                    "revision INTEGER NOT NULL DEFAULT 0"
                )
            if "last_turn_sequence" not in columns:
                connection.exec_driver_sql(
                    "ALTER TABLE study_sessions ADD COLUMN "
                    "last_turn_sequence INTEGER NOT NULL DEFAULT 0"
                )

    def _repair_sqlite_tavern_run_foreign_key(self) -> None:
        with self.engine.connect() as connection:
            table_names = {
                str(row[0])
                for row in connection.exec_driver_sql(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }
            if "tavern_runs" not in table_names:
                return
            columns = self._sqlite_column_names(connection, "tavern_runs")
            foreign_keys = connection.exec_driver_sql(
                "PRAGMA foreign_key_list(tavern_runs)"
            ).all()
            has_parent_foreign_key = any(
                str(row[2]) == "tavern_runs"
                and str(row[3]) == "parent_run_id"
                and str(row[4]) == "id"
                for row in foreign_keys
            )
            if "parent_run_id" in columns and has_parent_foreign_key:
                return

            connection.commit()
            connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
            connection.commit()
            try:
                with connection.begin():
                    self._rebuild_legacy_tavern_runs_table(
                        connection,
                        has_parent_column="parent_run_id" in columns,
                        has_step_table="tavern_run_steps" in table_names,
                    )
            finally:
                if connection.in_transaction():
                    connection.rollback()
                connection.exec_driver_sql("PRAGMA foreign_keys=ON")
                connection.commit()

            violations = connection.exec_driver_sql("PRAGMA foreign_key_check").all()
            if violations:
                raise RuntimeError("sqlite_foreign_key_repair_failed")

    def _repair_sqlite_harness_operation_binding_route(self) -> None:
        """Preserve existing admissions while widening the closed route catalog."""
        if not self.url.startswith("sqlite"):
            return
        with self.engine.connect() as connection:
            rebuild = []
            for table in ("harness_operation_bindings", "harness_workflow_operations"):
                ddl = connection.exec_driver_sql(
                    "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)
                ).scalar_one_or_none()
                if ddl and ("frontend_decode" not in str(ddl) or (table == "harness_operation_bindings" and "learning_plan_revision" not in str(ddl))):
                    rebuild.append(table)
            if not rebuild:
                return
            triggers = connection.exec_driver_sql(
                "SELECT name, sql FROM sqlite_master WHERE type='trigger' AND "
                "(sql LIKE '%harness_operation_bindings%' OR tbl_name='harness_workflow_operations')"
            ).all()
            connection.commit()
            connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
            connection.exec_driver_sql("PRAGMA legacy_alter_table=ON")
            connection.commit()
            try:
                with connection.begin():
                    for name, _ in triggers:
                        connection.exec_driver_sql('DROP TRIGGER "' + name.replace('"', '""') + '"')
                    for table in rebuild:
                        indexes = connection.exec_driver_sql(
                            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name=? AND sql IS NOT NULL", (table,)
                        ).all()
                        for (name,) in indexes:
                            connection.exec_driver_sql('DROP INDEX "' + name.replace('"', '""') + '"')
                        connection.exec_driver_sql(f"ALTER TABLE {table} RENAME TO {table}_old_routes")
                        metadata = Base.metadata.tables[table]
                        metadata.create(connection, checkfirst=False)
                        columns = ", ".join(column.name for column in metadata.columns)
                        connection.exec_driver_sql(f"INSERT INTO {table} ({columns}) SELECT {columns} FROM {table}_old_routes")
                        connection.exec_driver_sql(f"DROP TABLE {table}_old_routes")
                    for _, sql in triggers:
                        connection.exec_driver_sql(sql)
                    if connection.exec_driver_sql("PRAGMA foreign_key_check").all():
                        raise RuntimeError("sqlite_harness_operation_route_repair_failed")
            finally:
                if connection.in_transaction():
                    connection.rollback()
                connection.exec_driver_sql("PRAGMA legacy_alter_table=OFF")
                connection.exec_driver_sql("PRAGMA foreign_keys=ON")
                connection.commit()

    def _repair_sqlite_harness_artifact_audit_schema(self) -> None:
        """Replace the pre-resolver audit table while preserving content-free rows."""

        if not self.url.startswith("sqlite"):
            return
        with self.engine.begin() as connection:
            table_names = {
                str(row[0])
                for row in connection.exec_driver_sql(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }
            if "harness_artifact_access_audits" not in table_names:
                return
            columns = self._sqlite_column_names(
                connection, "harness_artifact_access_audits"
            )
            if "outcome" not in columns:
                return
            connection.exec_driver_sql(
                "DROP TRIGGER IF EXISTS "
                "trg_harness_artifact_access_audits_no_update"
            )
            connection.exec_driver_sql(
                "DROP TRIGGER IF EXISTS "
                "trg_harness_artifact_access_audits_no_delete"
            )
            for index_name in (
                "ix_harness_artifact_access_audits_grant_id",
                "ix_harness_artifact_access_audits_harness_operation_id",
                "ix_harness_artifact_access_audits_artifact_id",
                "ix_harness_artifact_access_audits_authorization_outcome",
                "ix_harness_artifact_access_audits_resolution_status",
                "ix_harness_artifact_access_audits_evaluated_at",
            ):
                connection.exec_driver_sql(f"DROP INDEX IF EXISTS {index_name}")
            connection.exec_driver_sql(
                "ALTER TABLE harness_artifact_access_audits "
                "RENAME TO harness_artifact_access_audits_legacy"
            )
            Base.metadata.tables["harness_artifact_access_audits"].create(
                connection, checkfirst=False
            )
            connection.exec_driver_sql(
                """
                INSERT INTO harness_artifact_access_audits (
                    audit_id, grant_id, harness_operation_id,
                    grant_harness_operation_id, presented_principal_id,
                    grant_subject_id, artifact_id, artifact_type,
                    contract_name, contract_version, permission,
                    authorization_outcome, resolution_status,
                    schema_name, schema_version, evaluated_at
                )
                SELECT
                    audit_id, grant_id, harness_operation_id,
                    grant_harness_operation_id, presented_principal_id,
                    grant_subject_id, artifact_id, artifact_type,
                    contract_name, contract_version, permission,
                    outcome,
                    CASE
                        WHEN outcome = 'allowed' THEN 'resolved'
                        WHEN outcome = 'expired' THEN 'expired'
                        ELSE 'forbidden'
                    END,
                    'HarnessArtifactResolutionAuditV1',
                    'harness-artifact-resolution-audit-v1',
                    evaluated_at
                FROM harness_artifact_access_audits_legacy
                """
            )
            connection.exec_driver_sql(
                "DROP TABLE harness_artifact_access_audits_legacy"
            )

    @staticmethod
    def _drop_tavern_run_indexes(connection) -> None:
        for index_name in (
            "ix_tavern_runs_room_id",
            "ix_tavern_runs_status",
            "uq_tavern_runs_parent_run_id",
        ):
            connection.exec_driver_sql(f"DROP INDEX IF EXISTS {index_name}")

    @staticmethod
    def _drop_tavern_run_step_indexes(connection) -> None:
        for index_name in (
            "ix_tavern_run_steps_persona_id",
            "ix_tavern_run_steps_status",
        ):
            connection.exec_driver_sql(f"DROP INDEX IF EXISTS {index_name}")

    def _rebuild_legacy_tavern_runs_table(
        self,
        connection,
        *,
        has_parent_column: bool,
        has_step_table: bool,
    ) -> None:
        legacy_runs = "tavern_runs_legacy_migration"
        legacy_steps = "tavern_run_steps_legacy_migration"
        if has_step_table:
            connection.exec_driver_sql(
                f"ALTER TABLE tavern_run_steps RENAME TO {legacy_steps}"
            )
            self._drop_tavern_run_step_indexes(connection)
        connection.exec_driver_sql(f"ALTER TABLE tavern_runs RENAME TO {legacy_runs}")
        self._drop_tavern_run_indexes(connection)
        Base.metadata.tables["tavern_runs"].create(connection, checkfirst=True)

        parent_expression = (
            f"CASE WHEN source.parent_run_id IS NULL OR EXISTS ("
            f"SELECT 1 FROM {legacy_runs} AS parent WHERE parent.id = source.parent_run_id"
            ") THEN source.parent_run_id ELSE NULL END"
            if has_parent_column
            else "NULL"
        )
        connection.exec_driver_sql(
            f"""
            INSERT INTO tavern_runs (
                id,
                room_id,
                idempotency_key,
                parent_run_id,
                status,
                mode,
                input_message_id,
                expected_room_revision,
                error_code,
                created_at,
                completed_at,
                payload
            )
            SELECT
                source.id,
                source.room_id,
                source.idempotency_key,
                {parent_expression},
                source.status,
                source.mode,
                source.input_message_id,
                source.expected_room_revision,
                source.error_code,
                source.created_at,
                source.completed_at,
                source.payload
            FROM {legacy_runs} AS source
            """
        )

        if has_step_table:
            Base.metadata.tables["tavern_run_steps"].create(connection, checkfirst=True)
            connection.exec_driver_sql(
                f"""
                INSERT INTO tavern_run_steps (
                    run_id,
                    step_index,
                    persona_id,
                    participant_prompt_hash,
                    status,
                    message_id,
                    reply_to_message_id,
                    error_code,
                    started_at,
                    completed_at,
                    lease_owner,
                    lease_expires_at,
                    claim_count,
                    payload
                )
                SELECT
                    run_id,
                    step_index,
                    persona_id,
                    participant_prompt_hash,
                    status,
                    message_id,
                    reply_to_message_id,
                    error_code,
                    started_at,
                    completed_at,
                    '',
                    '',
                    0,
                    payload
                FROM {legacy_steps}
                """
            )
            connection.exec_driver_sql(f"DROP TABLE {legacy_steps}")
        connection.exec_driver_sql(f"DROP TABLE {legacy_runs}")

    @staticmethod
    def _sqlite_column_names(connection, table_name: str) -> set[str]:
        return {
            str(row[1])
            for row in connection.exec_driver_sql(f"PRAGMA table_info({table_name})")
        }

    @staticmethod
    def _drop_study_session_indexes(connection) -> None:
        for index_name in (
            "ix_study_sessions_document_id",
            "ix_study_sessions_persona_id",
            "ix_study_sessions_plan_id",
        ):
            connection.exec_driver_sql(f"DROP INDEX IF EXISTS {index_name}")

    @staticmethod
    def _ensure_sqlite_study_session_indexes(connection) -> None:
        table = Base.metadata.tables.get("study_sessions")
        if table is None:
            return
        for index in table.indexes:
            index.create(connection, checkfirst=True)

    @staticmethod
    def _ensure_sqlite_tavern_room_indexes(connection) -> None:
        connection.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_tavern_rooms_updated_at_id "
            "ON tavern_rooms (updated_at DESC, id DESC)"
        )

    @staticmethod
    def _ensure_sqlite_harness_operation_guards(connection) -> None:
        domain_tables = (
            ("plan_revision_operations", "uq_plan_revision_harness_operation", "learning_plan_revision", "operation_id"),
            (
                "document_process_operations",
                "uq_document_process_operation_harness_operation",
                "document_process",
                "operation_id",
            ),
            (
                "learning_plan_operations",
                "uq_learning_plan_operation_harness_operation",
                "learning_plan_generation",
                "operation_id",
            ),
            (
                "study_chat_operations",
                "uq_study_chat_operation_harness_operation",
                "study_chat",
                "operation_id",
            ),
            (
                "tavern_runs",
                "uq_tavern_run_harness_operation",
                "tavern_run",
                "id",
            ),
            (
                "harness_workflow_operations",
                "uq_harness_workflow_operation_harness_operation",
                None,
                "operation_id",
            ),
        )
        connection.exec_driver_sql(
            """
            CREATE TRIGGER IF NOT EXISTS trg_harness_operation_bindings_no_update
            BEFORE UPDATE ON harness_operation_bindings
            BEGIN
                SELECT RAISE(ABORT, 'harness_operation_binding_update_forbidden');
            END
            """
        )
        connection.exec_driver_sql(
            """
            CREATE TRIGGER IF NOT EXISTS trg_harness_operation_bindings_no_delete
            BEFORE DELETE ON harness_operation_bindings
            BEGIN
                SELECT RAISE(ABORT, 'harness_operation_binding_delete_forbidden');
            END
            """
        )
        for table_name, unique_name, domain_kind, identity_column in domain_tables:
            # Fresh metadata/Alembic schemas already carry a table-level unique
            # constraint. Only legacy SQLite tables upgraded by ADD COLUMN need
            # a supplemental index; creating both makes runtime and Alembic
            # schemas diverge and provides no additional invariant.
            indexes = connection.exec_driver_sql(
                f"PRAGMA index_list({table_name})"
            ).all()
            has_unique_harness_identity = False
            for index in indexes:
                if not bool(index[2]):
                    continue
                columns = connection.exec_driver_sql(
                    f"PRAGMA index_info({index[1]})"
                ).all()
                if [str(column[2]) for column in columns] == [
                    "harness_operation_id"
                ]:
                    has_unique_harness_identity = True
                    break
            if not has_unique_harness_identity:
                connection.exec_driver_sql(
                    f"CREATE UNIQUE INDEX IF NOT EXISTS {unique_name} "
                    f"ON {table_name} (harness_operation_id)"
                )
            connection.exec_driver_sql(
                f"""
                CREATE TRIGGER IF NOT EXISTS
                    trg_{table_name}_harness_operation_immutable
                BEFORE UPDATE OF harness_operation_id ON {table_name}
                WHEN NEW.harness_operation_id IS NOT OLD.harness_operation_id
                BEGIN
                    SELECT RAISE(ABORT, 'harness_operation_rebinding_forbidden');
                END
                """
            )
            kind_predicate = (
                "binding.domain_operation_kind = NEW.domain_operation_kind"
                if domain_kind is None
                else f"binding.domain_operation_kind = '{domain_kind}'"
            )
            connection.exec_driver_sql(
                f"""
                CREATE TRIGGER IF NOT EXISTS
                    trg_{table_name}_harness_operation_validate_insert
                BEFORE INSERT ON {table_name}
                WHEN NEW.harness_operation_id IS NOT NULL
                    AND NOT EXISTS (
                        SELECT 1
                        FROM harness_operation_bindings AS binding
                        WHERE binding.harness_operation_id = NEW.harness_operation_id
                            AND {kind_predicate}
                            AND binding.domain_operation_id = NEW.{identity_column}
                    )
                BEGIN
                    SELECT RAISE(
                        ABORT,
                        'harness_operation_domain_binding_mismatch'
                    );
                END
                """
            )

    @staticmethod
    def _ensure_sqlite_harness_artifact_guards(connection) -> None:
        table_names = {
            str(row[0])
            for row in connection.exec_driver_sql(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        if "harness_artifacts" in table_names:
            connection.exec_driver_sql(
                """
                CREATE TRIGGER IF NOT EXISTS trg_harness_artifacts_immutable_update
                BEFORE UPDATE ON harness_artifacts
                WHEN NOT (
                    OLD.deleted_at IS NULL
                    AND NEW.deleted_at IS NOT NULL
                    AND length(NEW.payload) = 0
                    AND NEW.artifact_id IS OLD.artifact_id
                    AND NEW.artifact_type IS OLD.artifact_type
                    AND NEW.contract_name IS OLD.contract_name
                    AND NEW.contract_version IS OLD.contract_version
                    AND NEW.digest_algorithm IS OLD.digest_algorithm
                    AND NEW.payload_digest IS OLD.payload_digest
                    AND NEW.expires_at IS OLD.expires_at
                    AND NEW.registered_principal_id IS OLD.registered_principal_id
                    AND NEW.schema_name IS OLD.schema_name
                    AND NEW.schema_version IS OLD.schema_version
                    AND NEW.registered_at IS OLD.registered_at
                )
                BEGIN
                    SELECT RAISE(ABORT, 'harness_artifact_mutation_forbidden');
                END
                """
            )
            connection.exec_driver_sql(
                """
                CREATE TRIGGER IF NOT EXISTS trg_harness_artifacts_no_delete
                BEFORE DELETE ON harness_artifacts
                BEGIN
                    SELECT RAISE(ABORT, 'harness_artifact_harness_artifacts_delete_forbidden');
                END
                """
            )
        for table_name in (
            "harness_artifact_principals",
            "harness_artifact_contracts",
            "harness_artifact_grant_scopes",
            "harness_artifact_access_audits",
        ):
            if table_name not in table_names:
                continue
            for operation in ("UPDATE", "DELETE"):
                connection.exec_driver_sql(
                    f"""
                    CREATE TRIGGER IF NOT EXISTS trg_{table_name}_no_{operation.lower()}
                    BEFORE {operation} ON {table_name}
                    BEGIN
                        SELECT RAISE(
                            ABORT,
                            'harness_artifact_{table_name}_{operation.lower()}_forbidden'
                        );
                    END
                    """
                )
        if "harness_artifact_grants" in table_names:
            connection.exec_driver_sql(
                """
                CREATE TRIGGER IF NOT EXISTS trg_harness_artifact_grants_revocation_only
                BEFORE UPDATE ON harness_artifact_grants
                WHEN NOT (
                    OLD.revoked_at IS NULL
                    AND NEW.revoked_at IS NOT NULL
                    AND NEW.grant_id IS OLD.grant_id
                    AND NEW.harness_operation_id IS OLD.harness_operation_id
                    AND NEW.principal_id IS OLD.principal_id
                    AND NEW.issued_at IS OLD.issued_at
                    AND NEW.expires_at IS OLD.expires_at
                    AND NEW.schema_name IS OLD.schema_name
                    AND NEW.schema_version IS OLD.schema_version
                )
                BEGIN
                    SELECT RAISE(ABORT, 'harness_artifact_grant_mutation_forbidden');
                END
                """
            )
            connection.exec_driver_sql(
                """
                CREATE TRIGGER IF NOT EXISTS trg_harness_artifact_grants_no_delete
                BEFORE DELETE ON harness_artifact_grants
                BEGIN
                    SELECT RAISE(ABORT, 'harness_artifact_harness_artifact_grants_delete_forbidden');
                END
                """
            )

    @staticmethod
    def _ensure_sqlite_harness_effect_guards(connection) -> None:
        table_names = {
            str(row[0])
            for row in connection.exec_driver_sql(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        if "harness_effect_batches" in table_names:
            connection.exec_driver_sql(
                """
                CREATE TRIGGER IF NOT EXISTS trg_harness_effect_batches_identity_immutable
                BEFORE UPDATE ON harness_effect_batches
                WHEN NOT (
                    NEW.effect_batch_id IS OLD.effect_batch_id
                    AND NEW.harness_operation_id IS OLD.harness_operation_id
                    AND NEW.max_slots IS OLD.max_slots
                    AND NEW.schema_name IS OLD.schema_name
                    AND NEW.schema_version IS OLD.schema_version
                    AND NEW.created_at IS OLD.created_at
                    AND (
                        NEW.sealed_at IS OLD.sealed_at
                        OR (OLD.sealed_at = '' AND NEW.sealed_at <> '')
                    )
                )
                BEGIN
                    SELECT RAISE(ABORT, 'harness_effect_batch_mutation_forbidden');
                END
                """
            )

            connection.exec_driver_sql(
                """
                CREATE TRIGGER IF NOT EXISTS trg_harness_effect_batches_no_delete
                BEFORE DELETE ON harness_effect_batches
                BEGIN
                    SELECT RAISE(ABORT, 'harness_effect_batch_delete_forbidden');
                END
                """
            )
        if "harness_effect_journal" in table_names:
            connection.exec_driver_sql(
                """
                CREATE TRIGGER IF NOT EXISTS trg_harness_effect_journal_identity_immutable
                BEFORE UPDATE ON harness_effect_journal
                WHEN NOT (
                    NEW.effect_id IS OLD.effect_id
                    AND NEW.effect_batch_id IS OLD.effect_batch_id
                    AND NEW.harness_operation_id IS OLD.harness_operation_id
                    AND NEW.slot IS OLD.slot
                    AND NEW.adapter_name IS OLD.adapter_name
                    AND NEW.adapter_version IS OLD.adapter_version
                    AND NEW.boundary_kind IS OLD.boundary_kind
                    AND NEW.prepare_policy IS OLD.prepare_policy
                    AND NEW.commit_policy IS OLD.commit_policy
                    AND NEW.compensation_policy IS OLD.compensation_policy
                    AND NEW.read_back_policy IS OLD.read_back_policy
                    AND NEW.proposal_contract_name IS OLD.proposal_contract_name
                    AND NEW.proposal_contract_version IS OLD.proposal_contract_version
                    AND NEW.proposal_digest IS OLD.proposal_digest
                    AND NEW.target_refs IS OLD.target_refs
                    AND NEW.schema_name IS OLD.schema_name
                    AND NEW.schema_version IS OLD.schema_version
                    AND NEW.prepared_at IS OLD.prepared_at
                    AND OLD.state <> 'terminal'
                )
                BEGIN
                    SELECT RAISE(ABORT, 'harness_effect_journal_mutation_forbidden');
                END
                """
            )
            connection.exec_driver_sql(
                """
                CREATE TRIGGER IF NOT EXISTS trg_harness_effect_journal_no_delete
                BEFORE DELETE ON harness_effect_journal
                BEGIN
                    SELECT RAISE(ABORT, 'harness_effect_journal_delete_forbidden');
                END
                """
            )

    @staticmethod
    def _ensure_sqlite_harness_runtime_guards(connection) -> None:
        """Keep runtime identity immutable and terminal executions append-only."""
        table_names = {
            str(row[0]) for row in connection.exec_driver_sql(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        if "harness_runtime_executions" not in table_names:
            return
        connection.exec_driver_sql(
            """
            CREATE TRIGGER IF NOT EXISTS trg_harness_runtime_identity_immutable
            BEFORE UPDATE ON harness_runtime_executions
            WHEN NOT (
                NEW.trace_id IS OLD.trace_id AND NEW.trace_slot IS OLD.trace_slot
                AND NEW.harness_operation_id IS OLD.harness_operation_id
                AND NEW.parent_trace_id IS OLD.parent_trace_id
                AND NEW.workflow IS OLD.workflow AND NEW.stage IS OLD.stage
                AND NEW.adapter_contract_name IS OLD.adapter_contract_name
                AND NEW.adapter_contract_version IS OLD.adapter_contract_version
                AND NEW.trace_contract_name IS OLD.trace_contract_name
                AND NEW.trace_contract_version IS OLD.trace_contract_version
                AND NEW.context_payload IS OLD.context_payload
                AND NEW.context_digest IS OLD.context_digest
                AND NEW.schema_name IS OLD.schema_name
                AND NEW.schema_version IS OLD.schema_version
                AND NEW.created_at IS OLD.created_at
                AND OLD.state <> 'terminal'
            )
            BEGIN
                SELECT RAISE(ABORT, 'harness_runtime_identity_mutation_forbidden');
            END
            """
        )
        connection.exec_driver_sql(
            """
            CREATE TRIGGER IF NOT EXISTS trg_harness_runtime_no_delete
            BEFORE DELETE ON harness_runtime_executions
            BEGIN
                SELECT RAISE(ABORT, 'harness_runtime_delete_forbidden');
            END
            """
        )

    def _rebuild_legacy_study_sessions_table(self, connection, *, source_table: str) -> None:
        legacy_table = "study_sessions_legacy_migration"
        connection.exec_driver_sql(f"DROP TABLE IF EXISTS {legacy_table}")
        connection.exec_driver_sql(f"ALTER TABLE {source_table} RENAME TO {legacy_table}")
        self._drop_study_session_indexes(connection)
        Base.metadata.tables["study_sessions"].create(connection, checkfirst=True)
        connection.exec_driver_sql(
            f"""
            INSERT INTO study_sessions (
                id,
                document_id,
                persona_id,
                plan_id,
                study_unit_id,
                status,
                revision,
                last_turn_sequence,
                created_at,
                updated_at,
                payload
            )
            SELECT
                id,
                document_id,
                persona_id,
                plan_id,
                section_id,
                status,
                0,
                0,
                created_at,
                updated_at,
                payload
            FROM {legacy_table}
            """
        )
        connection.exec_driver_sql(f"DROP TABLE {legacy_table}")


def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
    finally:
        cursor.close()
