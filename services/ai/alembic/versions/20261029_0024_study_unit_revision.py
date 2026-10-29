"""Durable, independently confirmed Study Unit revision proposals."""

import sqlalchemy as sa
from alembic import context, op
from sqlalchemy.dialects.postgresql import JSONB

revision = "20261029_0024"
down_revision = "20261029_0023"
branch_labels = None
depends_on = None

_ROUTES = (
    ("document_process", "document_parse", "document_parse"),
    ("document_ocr", "ocr", "ocr_page"),
    ("study_unit_cleanup", "study_unit_cleanup", "study_unit_cleanup"),
    ("learning_plan_generation", "planning", "plan_generation"),
    ("learning_plan_revision", "planning", "plan_revision"),
    ("study_unit_revision", "planning", "study_unit_revision"),
    ("persona_generation", "persona", "persona_generation"),
    ("scene_generation", "scene", "scene_generation"),
    ("study_chat", "study_chat", "study_chat_reply"),
    ("tavern_run", "tavern", "actor_reply"),
    ("frontend_decode", "frontend_decode", "response_decode"),
)
_ROUTE_SQL = " OR ".join(
    f"(domain_operation_kind = '{kind}' AND workflow = '{workflow}' AND entry_stage = '{stage}')"
    for kind, workflow, stage in _ROUTES
)


def upgrade() -> None:
    connection = op.get_bind()
    offline = context.is_offline_mode()
    existing = (
        None
        if offline
        else next(
            item
            for item in sa.inspect(connection).get_check_constraints(
                "harness_operation_bindings"
            )
            if item["name"] == "ck_harness_operation_binding_route"
        )
    )
    if offline or "study_unit_revision" not in existing["sqltext"]:
        triggers = []
        if connection.dialect.name == "sqlite":
            triggers = connection.execute(
                sa.text(
                    "SELECT name, sql FROM sqlite_master WHERE type='trigger' "
                    "AND sql LIKE '%harness_operation_bindings%'"
                )
            ).all()
            for name, _ in triggers:
                connection.exec_driver_sql(
                    'DROP TRIGGER "' + name.replace('"', '""') + '"'
                )
        with op.batch_alter_table("harness_operation_bindings") as batch:
            batch.drop_constraint("ck_harness_operation_binding_route", type_="check")
            batch.create_check_constraint(
                "ck_harness_operation_binding_route", _ROUTE_SQL
            )
        for _, sql in triggers:
            connection.exec_driver_sql(sql)
    if offline or not sa.inspect(connection).has_table(
        "study_unit_revision_operations"
    ):
        payload = sa.JSON().with_variant(JSONB(), "postgresql")
        op.create_table(
            "study_unit_revision_operations",
            sa.Column("operation_id", sa.String(80), primary_key=True),
            sa.Column(
                "harness_operation_id",
                sa.String(64),
                sa.ForeignKey("harness_operation_bindings.harness_operation_id"),
                nullable=False,
                unique=True,
            ),
            sa.Column("plan_id", sa.String(64), nullable=False, unique=True),
            sa.Column("document_id", sa.String(64), nullable=False, index=True),
            sa.Column("parent_operation_id", sa.String(64), nullable=False),
            sa.Column("preview", payload, nullable=False),
            sa.Column("base_debug_report", payload, nullable=False),
            sa.Column("status", sa.String(24), nullable=False),
            sa.Column("decision_receipt", payload, nullable=True),
            sa.Column("error_code", sa.String(160), nullable=False, server_default=""),
            sa.Column("updated_at", sa.String(64), nullable=False),
            sa.CheckConstraint(
                "status IN ('ready', 'applying', 'accepted', 'rejected', 'conflict', 'failed')",
                name="ck_study_unit_revision_status",
            ),
        )


def downgrade() -> None:
    connection = op.get_bind()
    if connection.execute(
        sa.text(
            "SELECT count(*) FROM harness_operation_bindings WHERE domain_operation_kind='study_unit_revision'"
        )
    ).scalar_one():
        raise RuntimeError("study_unit_revision_admission_tombstones_prevent_downgrade")
    op.drop_table("study_unit_revision_operations")
    # The widened, empty route remains read-compatible with the earlier schema.
