"""Admit Frontend Decode operations without borrowing a producer identity.

Revision ID: 20260909_0019
Revises: 20260903_0018
"""

import sqlalchemy as sa
from alembic import op

revision = "20260909_0019"
down_revision = "20260903_0018"
branch_labels = None
depends_on = None

_FRONTEND_ROUTE = "(domain_operation_kind = 'frontend_decode' AND workflow = 'frontend_decode' AND entry_stage = 'response_decode')"

_OLD_ROUTE = "(domain_operation_kind = 'document_process' AND workflow = 'document_parse' AND entry_stage = 'document_parse') OR (domain_operation_kind = 'document_ocr' AND workflow = 'ocr' AND entry_stage = 'ocr_page') OR (domain_operation_kind = 'study_unit_cleanup' AND workflow = 'study_unit_cleanup' AND entry_stage = 'study_unit_cleanup') OR (domain_operation_kind = 'learning_plan_generation' AND workflow = 'planning' AND entry_stage = 'plan_generation') OR (domain_operation_kind = 'persona_generation' AND workflow = 'persona' AND entry_stage = 'persona_generation') OR (domain_operation_kind = 'scene_generation' AND workflow = 'scene' AND entry_stage = 'scene_generation') OR (domain_operation_kind = 'study_chat' AND workflow = 'study_chat' AND entry_stage = 'study_chat_reply') OR (domain_operation_kind = 'tavern_run' AND workflow = 'tavern' AND entry_stage = 'actor_reply')"
_OLD_KIND = "domain_operation_kind IN ('document_ocr', 'study_unit_cleanup', 'persona_generation', 'scene_generation')"


def _alter(add: bool) -> None:
    connection = op.get_bind()
    route = _OLD_ROUTE + (" OR " + _FRONTEND_ROUTE if add else "")
    kind = (
        _OLD_KIND.replace("'scene_generation'", "'scene_generation', 'frontend_decode'")
        if add
        else _OLD_KIND
    )
    triggers = []
    if connection.dialect.name == "sqlite":
        # Batch table rebuilds must not leave cross-table validation triggers
        # referencing a temporarily absent table. Restore their exact SQL.
        triggers = connection.execute(
            sa.text(
                "SELECT name, sql FROM sqlite_master WHERE type='trigger' AND (sql LIKE '%harness_operation_bindings%' OR tbl_name='harness_workflow_operations')"
            )
        ).all()
        for name, _ in triggers:
            connection.exec_driver_sql('DROP TRIGGER "' + name.replace('"', '""') + '"')
    for table, name, expression in (
        ("harness_operation_bindings", "ck_harness_operation_binding_route", route),
        ("harness_workflow_operations", "ck_harness_workflow_operation_kind", kind),
    ):
        with op.batch_alter_table(table) as batch:
            batch.drop_constraint(name, type_="check")
            batch.create_check_constraint(name, expression)
    for _, sql in triggers:
        connection.exec_driver_sql(sql)


def upgrade() -> None:
    _alter(True)


def downgrade() -> None:
    if (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT count(*) FROM harness_operation_bindings WHERE domain_operation_kind='frontend_decode'"
            )
        )
        .scalar_one()
    ):
        raise RuntimeError("frontend_decode_admission_tombstones_prevent_downgrade")
    _alter(False)
