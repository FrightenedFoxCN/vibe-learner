"""Private retained stage membership; keep the public v1 link projection stable."""

import sqlite3

from pydantic import BaseModel, ConfigDict, Field

from app.models.diagnostic import DiagnosticEventV1, DiagnosticOperationLinkV1
from app.models.harness import HarnessStage, HarnessWorkflow


class _StageObservation(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    workflow: HarnessWorkflow
    stage: HarnessStage


class _RetainedLink(DiagnosticOperationLinkV1):
    # Both enums are closed. Repeated diagnostic attempts do not grow this list.
    observed_stages: list[_StageObservation] = Field(
        default_factory=list, max_length=len(HarnessWorkflow) * len(HarnessStage)
    )

    def observations(self) -> list[_StageObservation]:
        values = self.observed_stages.copy()
        # A legacy row only proves the last stage it retained.
        if self.workflow is not None and self.stage is not None:
            current = _StageObservation(workflow=self.workflow, stage=self.stage)
            if current not in values:
                values.append(current)
        return values


def remember_operation_link(db: sqlite3.Connection, event: DiagnosticEventV1) -> None:
    if event.source != "server" or event.harness is None or event.request_id is None:
        return
    harness = event.harness
    key = (harness.operation_id, event.request_id)
    row = db.execute(
        "SELECT payload FROM operation_links WHERE operation_id=? AND request_id=?", key
    ).fetchone()
    observations = (
        _RetainedLink.model_validate_json(row[0]).observations() if row else []
    )
    current = _StageObservation(workflow=harness.workflow, stage=harness.stage)
    if current not in observations:
        observations.append(current)
    link = _RetainedLink(
        operation_id=harness.operation_id,
        request_id=event.request_id,
        client_instance_id=event.client_instance_id,
        page_view_id=event.page_view_id,
        flow_id=event.flow_id,
        action_id=event.action_id,
        workflow=harness.workflow,
        stage=harness.stage,
        observed_stages=observations,
    )
    db.execute(
        "INSERT INTO operation_links(operation_id,request_id,payload) VALUES (?,?,?) "
        "ON CONFLICT(operation_id,request_id) DO UPDATE SET payload=excluded.payload",
        (*key, link.model_dump_json()),
    )


def link_stage_predicate(filters: dict, *, payload: str) -> tuple[str, list]:
    fields = [
        (key, filters[key])
        for key in ("workflow", "stage")
        if filters.get(key) is not None
    ]
    if not fields:
        return "1", []
    legacy = " AND ".join(f"json_extract({payload}, '$.{key}')=?" for key, _ in fields)
    observed = " AND ".join(f"json_extract(s.value, '$.{key}')=?" for key, _ in fields)
    return (
        f"(({legacy}) OR EXISTS (SELECT 1 FROM json_each({payload}, '$.observed_stages') s WHERE {observed}))",
        [value for _, value in fields] * 2,
    )


def public_operation_link(
    payload: str, *, filters: dict | None = None
) -> DiagnosticOperationLinkV1:
    row = _RetainedLink.model_validate_json(payload)
    wire = row.model_dump(exclude_unset=True, exclude={"observed_stages"})
    if filters and any(
        filters.get(key) is not None and filters[key] != wire.get(key)
        for key in ("workflow", "stage")
    ):
        for observation in reversed(row.observations()):
            if all(
                filters.get(key) is None or filters[key] == getattr(observation, key)
                for key in ("workflow", "stage")
            ):
                wire.update(workflow=observation.workflow, stage=observation.stage)
                break
        else:
            raise ValueError("diagnostic_link_stage_mismatch")
    return DiagnosticOperationLinkV1.model_validate(wire)
