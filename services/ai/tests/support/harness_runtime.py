from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import ClassVar

from pydantic import BaseModel, ConfigDict

from app.models.harness import (
    HarnessCheckStatus,
    HarnessCheckV2,
    HarnessContractRef,
    HarnessSafeManifest,
    HarnessStage,
    HarnessWorkflow,
)
from app.models.harness_operation import (
    HarnessDomainOperationKind,
    HarnessOperationBindingV1,
)
from app.persistence.database import Database
from app.persistence.harness_runtime_repository import HarnessRuntimeRepository
from app.persistence.models import HarnessOperationBindingRow
from app.services.harness_context import build_harness_context
from app.services.harness_runtime import (
    HarnessRuntimeRequest,
    HarnessRuntimeStageAdapter,
    HarnessRuntimeValidationResult,
)


ADAPTER_CONTRACT = HarnessContractRef(
    name="TavernActorWorkflowAdapter",
    version="tavern-actor-workflow-adapter-v1",
)
TRACE_CONTRACT = HarnessContractRef(
    name="TavernActorReply",
    version="tavern-actor-reply-v1",
)
INPUT_CONTRACT = HarnessContractRef(
    name="TavernActorInputManifest",
    version="tavern-actor-input-manifest-v1",
)
PROMPT_CONTRACT = HarnessContractRef(
    name="TavernActorPrompt",
    version="tavern-actor-v1",
)
POLICY_CONTRACT = HarnessContractRef(
    name="TavernHarnessPolicy",
    version="tavern-harness-v1",
)


class RuntimeInputManifest(HarnessSafeManifest):
    trace_safe_fields: ClassVar[frozenset[str]] = frozenset(
        {"mode", "room_revision", "target_ids"}
    )

    mode: str
    room_revision: int
    target_ids: list[str]


class RuntimeOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    value: str


class HarnessRuntimeFixture:
    def __init__(self) -> None:
        self.temp = TemporaryDirectory()
        self.database = Database(
            f"sqlite:///{Path(self.temp.name) / 'runtime.sqlite3'}"
        )
        self.database.create_schema()
        self.repository = HarnessRuntimeRepository(self.database)
        self.binding = HarnessOperationBindingV1(
            harness_operation_id="harness-operation-0123456789abcdef0123456789abcdef",
            domain_operation_kind=HarnessDomainOperationKind.TAVERN_RUN,
            domain_operation_id="tavern-runtime-test-run",
            workflow=HarnessWorkflow.TAVERN,
            entry_stage=HarnessStage.TAVERN_ACTOR_REPLY,
            admitted_at=datetime(2026, 9, 3, tzinfo=UTC),
        )
        with self.database.session() as session:
            session.add(
                HarnessOperationBindingRow(
                    **self.binding.model_dump(mode="json", exclude_none=False)
                )
            )
        self.context = build_harness_context(
            workflow=HarnessWorkflow.TAVERN,
            stage=HarnessStage.TAVERN_ACTOR_REPLY,
            operation_binding=self.binding,
            input_contract=INPUT_CONTRACT,
            input_manifest=RuntimeInputManifest(
                mode="direct",
                room_revision=0,
                target_ids=["persona-a"],
            ),
            subject_refs=[],
            prompt_contract=PROMPT_CONTRACT,
            policy_contract=POLICY_CONTRACT,
        )
        self.request = HarnessRuntimeRequest(
            operation_binding=self.binding,
            stage=HarnessStage.TAVERN_ACTOR_REPLY,
            trace_slot=0,
            context=self.context,
        )

    def close(self) -> None:
        self.database.dispose()
        self.temp.cleanup()

    def adapter(self, calls: dict[str, int] | None = None):
        counts = calls if calls is not None else {}

        def generate(_context, _artifacts):
            counts["generate"] = counts.get("generate", 0) + 1
            return {"value": "valid"}

        def decode(raw):
            counts["decode"] = counts.get("decode", 0) + 1
            if not isinstance(raw, dict) or raw.get("value") != "valid":
                raise ValueError("fixture_decode_failed")
            return RuntimeOutput.model_validate(raw)

        def validate(output):
            counts["validate"] = counts.get("validate", 0) + 1
            return HarnessRuntimeValidationResult(
                output=output,
                checks=(
                    HarnessCheckV2(
                        name="fixture_value",
                        status=HarnessCheckStatus.PASSED,
                        code="",
                        message="fixture output is valid",
                    ),
                ),
            )

        return HarnessRuntimeStageAdapter(
            adapter_contract=ADAPTER_CONTRACT,
            trace_contract=TRACE_CONTRACT,
            generate=generate,
            decode=decode,
            validate=validate,
        )

