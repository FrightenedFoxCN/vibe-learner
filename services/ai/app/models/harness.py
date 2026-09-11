from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
import hashlib
import json
import re
from types import MappingProxyType
from typing import TYPE_CHECKING, ClassVar, Generic, Literal, Mapping, NamedTuple, TypeVar

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    TypeAdapter,
    field_validator,
    model_validator,
)

from app.core.harness_component_versions import (
    DOCUMENT_CHUNK_BUILDER_CONTRACT_VERSION,
    DOCUMENT_PAGE_EXTRACTOR_CONTRACT_VERSION,
    DOCUMENT_PARSER_CONTRACT_VERSION,
    DOCUMENT_SECTION_DETECTOR_CONTRACT_VERSION,
    FRONTEND_DECODER_CONTRACT_VERSION,
    OCR_ENGINE_CONTRACT_VERSION,
    PERSONA_COMPILER_CONTRACT_VERSION,
    PLANNING_PROMPT_CONTRACT_VERSION,
    PLANNING_TOOL_RUNTIME_CONTRACT_VERSION,
    PLANNING_TOOLSET_CONTRACT_VERSION,
    SCENE_COMPILER_CONTRACT_VERSION,
    STUDY_UNIT_CLEANER_CONTRACT_VERSION,
    TAVERN_ACTOR_PROMPT_CONTRACT_VERSION,
    TAVERN_ACTOR_REPLY_COMMIT_CONTRACT_VERSION,
    TAVERN_ACTOR_REPLY_CONTRACT_NAME,
    TAVERN_ACTOR_REPLY_CONTRACT_VERSION,
    TAVERN_MESSAGE_COMMIT_BINDING_CONTRACT_NAME,
    TAVERN_MESSAGE_COMMIT_BINDING_CONTRACT_VERSION,
    TAVERN_MESSAGE_COMMITTED_PROJECTION_CONTRACT_NAME,
    TAVERN_MESSAGE_COMMITTED_PROJECTION_CONTRACT_VERSION,
    TAVERN_PERSONA_COMPILER_CONTRACT_VERSION,
    TAVERN_SCHEDULER_CONTRACT_VERSION,
    STUDY_CHAT_PROMPT_CONTRACT_VERSION,
    STUDY_CHAT_TOOLSET_CONTRACT_VERSION,
    STUDY_CHAT_TRACE_CONTRACT_VERSION,
    STUDY_CHAT_COMMIT_CONTRACT_VERSION,
    STUDY_CHAT_COMMITTED_PROJECTION_CONTRACT_VERSION,
)
from app.models.tavern_commit import (
    TavernPersonaMessageCommitBindingV1,
    TavernPersonaMessageCommittedProjectionV1,
    revalidate_tavern_message_commit_binding,
    revalidate_tavern_message_committed_projection,
)

if TYPE_CHECKING:
    from app.models.tavern import (
        TavernMessageRecord,
        TavernParticipantRecord,
        TavernRunRecord,
        TavernSpeakerStepRecord,
    )


class HarnessStatus(StrEnum):
    PASSED = "passed"
    REPAIRED = "repaired"
    FAILED = "failed"
    SKIPPED = "skipped"


class HarnessCheckStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    WARNING = "warning"
    SKIPPED = "skipped"


class HarnessCheckRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    status: HarnessCheckStatus
    code: str = ""
    message: str = ""


class HarnessTraceRecord(BaseModel):
    """Legacy v1 validation summary kept for existing Tavern records."""

    model_config = ConfigDict(extra="forbid")

    version: str
    workflow: str
    stage: str
    status: HarnessStatus
    schema_name: str
    input_digest: str = ""
    context_digest: str = ""
    checks: list[HarnessCheckRecord] = Field(default_factory=list)
    attempts: int = Field(default=1, ge=1, le=3)
    recovery_strategy: str = "none"
    duration_ms: int = Field(default=0, ge=0)

    @field_validator("version")
    @classmethod
    def reject_reserved_schema_version_prefix(cls, value: str) -> str:
        if value.startswith("harness-trace-"):
            raise ValueError("harness_trace_schema_version_discriminator_required")
        return value


# Existing persisted Tavern payloads have no discriminator. Keep their exact model
# and ambiguous ``version`` semantics intact instead of fabricating v2 evidence.
HarnessTraceV1 = HarnessTraceRecord


HARNESS_TRACE_SCHEMA_V2 = "harness-trace-v2"
HARNESS_TRACE_SCHEMA_V3 = "harness-trace-v3"


class HarnessWorkflow(StrEnum):
    DOCUMENT_PARSE = "document_parse"
    OCR = "ocr"
    STUDY_UNIT_CLEANUP = "study_unit_cleanup"
    PLANNING = "planning"
    PERSONA = "persona"
    SCENE = "scene"
    STUDY_CHAT = "study_chat"
    TAVERN = "tavern"
    FRONTEND_DECODE = "frontend_decode"


class HarnessStage(StrEnum):
    DOCUMENT_PARSE = "document_parse"
    PAGE_EXTRACTION = "page_extraction"
    SECTION_DETECTION = "section_detection"
    CHUNK_BUILDING = "chunk_building"
    OCR_PAGE = "ocr_page"
    STUDY_UNIT_CLEANUP = "study_unit_cleanup"
    PLAN_REVISION = "plan_revision"
    PLAN_GENERATION = "plan_generation"
    PLANNING_TOOL_EXECUTION = "planning_tool_execution"
    PERSONA_GENERATION = "persona_generation"
    SCENE_GENERATION = "scene_generation"
    STUDY_CHAT_REPLY = "study_chat_reply"
    TAVERN_ACTOR_REPLY = "actor_reply"
    FRONTEND_RESPONSE_DECODE = "response_decode"


class HarnessComponentName(StrEnum):
    DOCUMENT_PARSER = "document_parser"
    DOCUMENT_PAGE_EXTRACTOR = "document_page_extractor"
    DOCUMENT_SECTION_DETECTOR = "document_section_detector"
    DOCUMENT_CHUNK_BUILDER = "document_chunk_builder"
    OCR_ENGINE = "ocr_engine"
    STUDY_UNIT_CLEANER = "study_unit_cleaner"
    PLAN_REVISION_PATCH = "plan_revision_patch"
    PLANNING_PROMPT = "planning_prompt"
    PLANNING_TOOLSET = "planning_toolset"
    PLANNING_TOOL_RUNTIME = "planning_tool_runtime"
    PERSONA_COMPILER = "persona_compiler"
    SCENE_COMPILER = "scene_compiler"
    STUDY_CHAT_PROMPT = "study_chat_prompt"
    STUDY_CHAT_TOOLSET = "study_chat_toolset"
    TAVERN_PERSONA_COMPILER = "tavern_persona_compiler"
    TAVERN_ACTOR_PROMPT = "tavern_actor_prompt"
    TAVERN_SCHEDULER = "tavern_scheduler"
    FRONTEND_DECODER = "frontend_decoder"


class HarnessDigestAlgorithm(StrEnum):
    SHA256 = "sha256"


class HarnessAttemptPhase(StrEnum):
    GENERATE = "generate"
    DECODE = "decode"
    VALIDATE = "validate"
    REPAIR = "repair"
    COMMIT = "commit"
    ROLLBACK = "rollback"


class HarnessAttemptStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"


class HarnessCommitStatus(StrEnum):
    NOT_APPLICABLE = "not_applicable"
    NOT_COMMITTED = "not_committed"
    COMMITTED = "committed"
    ROLLED_BACK = "rolled_back"


class HarnessDigestScope(StrEnum):
    COMMITTED_PROJECTION = "committed_projection"
    COMMITTED_BATCH = "committed_batch"


class HarnessArtifactType(StrEnum):
    DOCUMENT_UPLOAD = "document_upload"
    DOCUMENT_DEBUG = "document_debug"
    OCR_PAGE = "ocr_page"
    STUDY_UNIT_INPUT = "study_unit_input"
    PLANNING_CONTEXT = "planning_context"
    PERSONA_SNAPSHOT = "persona_snapshot"
    SCENE_SNAPSHOT = "scene_snapshot"
    STUDY_SESSION_SNAPSHOT = "study_session_snapshot"
    TAVERN_ROOM_SNAPSHOT = "tavern_room_snapshot"
    TAVERN_TRANSCRIPT = "tavern_transcript"
    FRONTEND_RESPONSE_FIXTURE = "frontend_response_fixture"


class HarnessResourceType(StrEnum):
    DOCUMENT = "document"
    DOCUMENT_PAGE = "document_page"
    DOCUMENT_DEBUG = "document_debug"
    STUDY_UNIT = "study_unit"
    PLAN_REVISION = "plan_revision"
    LEARNING_PLAN = "learning_plan"
    PLANNING_TRACE = "planning_trace"
    PERSONA = "persona"
    SCENE = "scene"
    STUDY_SESSION = "study_session"
    TAVERN_ROOM = "tavern_room"
    TAVERN_RUN = "tavern_run"
    TAVERN_MESSAGE = "tavern_message"
    FRONTEND_REQUEST = "frontend_request"


class HarnessResourceSemantics(StrEnum):
    REVISIONED_CONTROL_AGGREGATE = "revisioned_control_aggregate"
    APPEND_ONLY = "append_only"
    IMMUTABLE = "immutable"
    PARENT_BOUND = "parent_bound"
    UNVERSIONED_MUTABLE = "unversioned_mutable"
    OPERATION_IDENTITY = "operation_identity"


class HarnessContextEvidencePolicy(StrEnum):
    AUTHORITATIVE_REVISION = "authoritative_revision"
    PROTECTED_SNAPSHOT = "protected_snapshot"
    OPERATION_IDENTITY = "operation_identity"
    UNSUPPORTED = "unsupported"


class HarnessCommitEvidencePolicy(StrEnum):
    REVISION = "revision"
    SEQUENCE = "sequence"
    DIGEST = "digest"
    UNSUPPORTED = "unsupported"


class HarnessRollbackEvidencePolicy(StrEnum):
    READ_BACK = "read_back"
    COMPENSATION = "compensation"
    UNSUPPORTED = "unsupported"


class HarnessOperationEvidenceScope(StrEnum):
    """How much of a real transaction a registered policy proves."""

    PRIMARY_OUTPUT_ONLY = "primary_output_only"
    COMPLETE_TRANSACTION = "complete_transaction"


class HarnessOperationCommitPolicyKey(NamedTuple):
    workflow: HarnessWorkflow
    stage: HarnessStage
    trace_contract_name: str
    trace_contract_version: str
    payload_contract_name: str
    payload_contract_version: str


class HarnessOperationCommitStatusRule(NamedTuple):
    trace_status: HarnessStatus
    commit_status: HarnessCommitStatus


class HarnessOperationCommitResourceRule(NamedTuple):
    resource_type: HarnessResourceType
    committed_attempted_count: int
    committed_resource_count: int
    not_committed_attempted_min: int
    not_committed_attempted_max: int


class HarnessOperationCommitPolicy(NamedTuple):
    key: HarnessOperationCommitPolicyKey
    projection_contract: HarnessRegisteredContract
    binding_contract: HarnessRegisteredContract
    digest_scope: HarnessDigestScope
    evidence_scope: HarnessOperationEvidenceScope
    subject_resource_type: HarnessResourceType
    subject_resource_count: int
    status_rules: tuple[HarnessOperationCommitStatusRule, ...]
    resource_rules: tuple[HarnessOperationCommitResourceRule, ...]


@dataclass(frozen=True, slots=True)
class HarnessResourceEvidencePolicy:
    semantics: HarnessResourceSemantics
    context_evidence: HarnessContextEvidencePolicy
    commit_evidence: HarnessCommitEvidencePolicy
    rollback_evidence: HarnessRollbackEvidencePolicy


class HarnessV2Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class HarnessSafeManifest(HarnessV2Model):
    """Marker base for explicitly reviewed, non-secret digest manifests."""

    trace_safe_fields: ClassVar[frozenset[str]] = frozenset()


class HarnessContractRef(HarnessV2Model):
    name: str = Field(min_length=1, max_length=160)
    version: str = Field(min_length=1, max_length=160)


class HarnessRegisteredContract(NamedTuple):
    name: str
    version: str

    def to_ref(self) -> HarnessContractRef:
        return HarnessContractRef(name=self.name, version=self.version)


class HarnessComponentRegistration(NamedTuple):
    component_name: HarnessComponentName
    owner_module: str
    contract: HarnessRegisteredContract | None


class HarnessOperationStageRegistration(NamedTuple):
    workflow: HarnessWorkflow
    stage: HarnessStage
    owner_module: str
    component_names: tuple[HarnessComponentName, ...]
    eval_route: str


HARNESS_COMPONENT_REGISTRATIONS = MappingProxyType(
    {
        HarnessComponentName.DOCUMENT_PARSER: HarnessComponentRegistration(
            HarnessComponentName.DOCUMENT_PARSER,
            "app.services.document_parser",
            HarnessRegisteredContract(
                name="document_parser",
                version=DOCUMENT_PARSER_CONTRACT_VERSION,
            ),
        ),
        HarnessComponentName.DOCUMENT_PAGE_EXTRACTOR: HarnessComponentRegistration(
            HarnessComponentName.DOCUMENT_PAGE_EXTRACTOR,
            "app.services.document_parser",
            HarnessRegisteredContract(
                name="document_page_extractor",
                version=DOCUMENT_PAGE_EXTRACTOR_CONTRACT_VERSION,
            ),
        ),
        HarnessComponentName.DOCUMENT_SECTION_DETECTOR: HarnessComponentRegistration(
            HarnessComponentName.DOCUMENT_SECTION_DETECTOR,
            "app.services.document_parser",
            HarnessRegisteredContract(
                name="document_section_detector",
                version=DOCUMENT_SECTION_DETECTOR_CONTRACT_VERSION,
            ),
        ),
        HarnessComponentName.DOCUMENT_CHUNK_BUILDER: HarnessComponentRegistration(
            HarnessComponentName.DOCUMENT_CHUNK_BUILDER,
            "app.services.document_parser",
            HarnessRegisteredContract(
                name="document_chunk_builder",
                version=DOCUMENT_CHUNK_BUILDER_CONTRACT_VERSION,
            ),
        ),
        HarnessComponentName.OCR_ENGINE: HarnessComponentRegistration(
            HarnessComponentName.OCR_ENGINE,
            "app.services.ocr_engine",
            HarnessRegisteredContract(
                name="ocr_engine",
                version=OCR_ENGINE_CONTRACT_VERSION,
            ),
        ),
        HarnessComponentName.STUDY_UNIT_CLEANER: HarnessComponentRegistration(
            HarnessComponentName.STUDY_UNIT_CLEANER,
            "app.services.study_arrangement",
            HarnessRegisteredContract(
                name="study_unit_cleaner",
                version=STUDY_UNIT_CLEANER_CONTRACT_VERSION,
            ),
        ),
        HarnessComponentName.PLAN_REVISION_PATCH: HarnessComponentRegistration(
            HarnessComponentName.PLAN_REVISION_PATCH,
            "app.models.plan_revision",
            HarnessRegisteredContract(name="plan_revision_patch", version="plan-revision-patch-v1"),
        ),
        HarnessComponentName.PLANNING_PROMPT: HarnessComponentRegistration(
            HarnessComponentName.PLANNING_PROMPT,
            "app.services.plan_prompt",
            HarnessRegisteredContract(
                name="planning_prompt",
                version=PLANNING_PROMPT_CONTRACT_VERSION,
            ),
        ),
        HarnessComponentName.PLANNING_TOOLSET: HarnessComponentRegistration(
            HarnessComponentName.PLANNING_TOOLSET,
            "app.services.plan_tool_runtime",
            HarnessRegisteredContract(
                name="planning_toolset",
                version=PLANNING_TOOLSET_CONTRACT_VERSION,
            ),
        ),
        HarnessComponentName.PLANNING_TOOL_RUNTIME: HarnessComponentRegistration(
            HarnessComponentName.PLANNING_TOOL_RUNTIME,
            "app.services.plan_tool_runtime",
            HarnessRegisteredContract(
                name="planning_tool_runtime",
                version=PLANNING_TOOL_RUNTIME_CONTRACT_VERSION,
            ),
        ),
        HarnessComponentName.PERSONA_COMPILER: HarnessComponentRegistration(
            HarnessComponentName.PERSONA_COMPILER,
            "app.services.persona_cards",
            HarnessRegisteredContract(
                name="persona_compiler",
                version=PERSONA_COMPILER_CONTRACT_VERSION,
            ),
        ),
        HarnessComponentName.SCENE_COMPILER: HarnessComponentRegistration(
            HarnessComponentName.SCENE_COMPILER,
            "app.services.scene_setup",
            HarnessRegisteredContract(
                name="scene_compiler",
                version=SCENE_COMPILER_CONTRACT_VERSION,
            ),
        ),
        HarnessComponentName.STUDY_CHAT_PROMPT: HarnessComponentRegistration(
            HarnessComponentName.STUDY_CHAT_PROMPT,
            "app.services.study_session_prompt",
            HarnessRegisteredContract(
                name="study_chat_prompt", version=STUDY_CHAT_PROMPT_CONTRACT_VERSION
            ),
        ),
        HarnessComponentName.STUDY_CHAT_TOOLSET: HarnessComponentRegistration(
            HarnessComponentName.STUDY_CHAT_TOOLSET,
            "app.services.study_session_chat_runtime",
            HarnessRegisteredContract(
                name="study_chat_toolset", version=STUDY_CHAT_TOOLSET_CONTRACT_VERSION
            ),
        ),
        HarnessComponentName.TAVERN_PERSONA_COMPILER: HarnessComponentRegistration(
            HarnessComponentName.TAVERN_PERSONA_COMPILER,
            "app.services.persona_runtime",
            HarnessRegisteredContract(
                name="tavern_persona_compiler",
                version=TAVERN_PERSONA_COMPILER_CONTRACT_VERSION,
            ),
        ),
        HarnessComponentName.TAVERN_ACTOR_PROMPT: HarnessComponentRegistration(
            HarnessComponentName.TAVERN_ACTOR_PROMPT,
            "app.services.tavern_prompt",
            HarnessRegisteredContract(
                name="tavern_actor_prompt",
                version=TAVERN_ACTOR_PROMPT_CONTRACT_VERSION,
            ),
        ),
        HarnessComponentName.TAVERN_SCHEDULER: HarnessComponentRegistration(
            HarnessComponentName.TAVERN_SCHEDULER,
            "app.services.tavern",
            HarnessRegisteredContract(
                name="tavern_scheduler",
                version=TAVERN_SCHEDULER_CONTRACT_VERSION,
            ),
        ),
        HarnessComponentName.FRONTEND_DECODER: HarnessComponentRegistration(
            HarnessComponentName.FRONTEND_DECODER,
            "apps.web.lib.api",
            HarnessRegisteredContract(
                name="frontend_decoder",
                version=FRONTEND_DECODER_CONTRACT_VERSION,
            ),
        ),
    }
)

HARNESS_COMPONENT_OWNERS = MappingProxyType(
    {
        HarnessComponentName.DOCUMENT_PARSER: "app.services.document_parser",
        HarnessComponentName.DOCUMENT_PAGE_EXTRACTOR: "app.services.document_parser",
        HarnessComponentName.DOCUMENT_SECTION_DETECTOR: "app.services.document_parser",
        HarnessComponentName.DOCUMENT_CHUNK_BUILDER: "app.services.document_parser",
        HarnessComponentName.OCR_ENGINE: "app.services.ocr_engine",
        HarnessComponentName.STUDY_UNIT_CLEANER: "app.services.study_arrangement",
        HarnessComponentName.PLAN_REVISION_PATCH: "app.models.plan_revision",
        HarnessComponentName.PLANNING_PROMPT: "app.services.plan_prompt",
        HarnessComponentName.PLANNING_TOOLSET: "app.services.plan_tool_runtime",
        HarnessComponentName.PLANNING_TOOL_RUNTIME: "app.services.plan_tool_runtime",
        HarnessComponentName.PERSONA_COMPILER: "app.services.persona_cards",
        HarnessComponentName.SCENE_COMPILER: "app.services.scene_setup",
        HarnessComponentName.STUDY_CHAT_PROMPT: "app.services.study_session_prompt",
        HarnessComponentName.STUDY_CHAT_TOOLSET: "app.services.study_session_chat_runtime",
        HarnessComponentName.TAVERN_PERSONA_COMPILER: "app.services.persona_runtime",
        HarnessComponentName.TAVERN_ACTOR_PROMPT: "app.services.tavern_prompt",
        HarnessComponentName.TAVERN_SCHEDULER: "app.services.tavern",
        HarnessComponentName.FRONTEND_DECODER: "apps.web.lib.api",
    }
)


HARNESS_OPERATION_STAGE_REGISTRATIONS = MappingProxyType(
    {
        (HarnessWorkflow.DOCUMENT_PARSE, HarnessStage.DOCUMENT_PARSE): HarnessOperationStageRegistration(
            HarnessWorkflow.DOCUMENT_PARSE,
            HarnessStage.DOCUMENT_PARSE,
            "app.services.document_parser",
            (HarnessComponentName.DOCUMENT_PARSER,),
            "document.parse",
        ),
        (HarnessWorkflow.DOCUMENT_PARSE, HarnessStage.PAGE_EXTRACTION): HarnessOperationStageRegistration(
            HarnessWorkflow.DOCUMENT_PARSE,
            HarnessStage.PAGE_EXTRACTION,
            "app.services.document_parser",
            (HarnessComponentName.DOCUMENT_PAGE_EXTRACTOR,),
            "document.page_extraction",
        ),
        (HarnessWorkflow.DOCUMENT_PARSE, HarnessStage.SECTION_DETECTION): HarnessOperationStageRegistration(
            HarnessWorkflow.DOCUMENT_PARSE,
            HarnessStage.SECTION_DETECTION,
            "app.services.document_parser",
            (HarnessComponentName.DOCUMENT_SECTION_DETECTOR,),
            "document.section_detection",
        ),
        (HarnessWorkflow.DOCUMENT_PARSE, HarnessStage.CHUNK_BUILDING): HarnessOperationStageRegistration(
            HarnessWorkflow.DOCUMENT_PARSE,
            HarnessStage.CHUNK_BUILDING,
            "app.services.document_parser",
            (HarnessComponentName.DOCUMENT_CHUNK_BUILDER,),
            "document.chunk_building",
        ),
        (HarnessWorkflow.OCR, HarnessStage.OCR_PAGE): HarnessOperationStageRegistration(
            HarnessWorkflow.OCR,
            HarnessStage.OCR_PAGE,
            "app.services.ocr_engine",
            (HarnessComponentName.OCR_ENGINE,),
            "document.ocr_page",
        ),
        (HarnessWorkflow.STUDY_UNIT_CLEANUP, HarnessStage.STUDY_UNIT_CLEANUP): HarnessOperationStageRegistration(
            HarnessWorkflow.STUDY_UNIT_CLEANUP,
            HarnessStage.STUDY_UNIT_CLEANUP,
            "app.services.study_arrangement",
            (HarnessComponentName.STUDY_UNIT_CLEANER,),
            "document.study_unit_cleanup",
        ),
        (HarnessWorkflow.PLANNING, HarnessStage.PLAN_REVISION): HarnessOperationStageRegistration(
            HarnessWorkflow.PLANNING, HarnessStage.PLAN_REVISION,
            "app.services.plan_revision", (HarnessComponentName.PLAN_REVISION_PATCH,),
            "planning.plan_revision",
        ),
        (HarnessWorkflow.PLANNING, HarnessStage.PLAN_GENERATION): HarnessOperationStageRegistration(
            HarnessWorkflow.PLANNING,
            HarnessStage.PLAN_GENERATION,
            "app.services.model_provider",
            (
                HarnessComponentName.PLANNING_PROMPT,
                HarnessComponentName.PLANNING_TOOLSET,
            ),
            "planning.plan_generation",
        ),
        (HarnessWorkflow.PLANNING, HarnessStage.PLANNING_TOOL_EXECUTION): HarnessOperationStageRegistration(
            HarnessWorkflow.PLANNING,
            HarnessStage.PLANNING_TOOL_EXECUTION,
            "app.services.plan_tool_runtime",
            (
                HarnessComponentName.PLANNING_TOOL_RUNTIME,
                HarnessComponentName.PLANNING_TOOLSET,
            ),
            "planning.tool_execution",
        ),
        (HarnessWorkflow.PERSONA, HarnessStage.PERSONA_GENERATION): HarnessOperationStageRegistration(
            HarnessWorkflow.PERSONA,
            HarnessStage.PERSONA_GENERATION,
            "app.services.persona_cards",
            (HarnessComponentName.PERSONA_COMPILER,),
            "persona.generation",
        ),
        (HarnessWorkflow.SCENE, HarnessStage.SCENE_GENERATION): HarnessOperationStageRegistration(
            HarnessWorkflow.SCENE,
            HarnessStage.SCENE_GENERATION,
            "app.services.scene_setup",
            (HarnessComponentName.SCENE_COMPILER,),
            "scene.generation",
        ),
        (HarnessWorkflow.STUDY_CHAT, HarnessStage.STUDY_CHAT_REPLY): HarnessOperationStageRegistration(
            HarnessWorkflow.STUDY_CHAT,
            HarnessStage.STUDY_CHAT_REPLY,
            "app.services.study_sessions",
            (
                HarnessComponentName.STUDY_CHAT_PROMPT,
                HarnessComponentName.STUDY_CHAT_TOOLSET,
            ),
            "study_chat.reply",
        ),
        (HarnessWorkflow.TAVERN, HarnessStage.TAVERN_ACTOR_REPLY): HarnessOperationStageRegistration(
            HarnessWorkflow.TAVERN,
            HarnessStage.TAVERN_ACTOR_REPLY,
            "app.services.tavern",
            (
                HarnessComponentName.TAVERN_ACTOR_PROMPT,
                HarnessComponentName.TAVERN_PERSONA_COMPILER,
                HarnessComponentName.TAVERN_SCHEDULER,
            ),
            "tavern.actor_reply",
        ),
        (HarnessWorkflow.FRONTEND_DECODE, HarnessStage.FRONTEND_RESPONSE_DECODE): HarnessOperationStageRegistration(
            HarnessWorkflow.FRONTEND_DECODE,
            HarnessStage.FRONTEND_RESPONSE_DECODE,
            "apps.web.lib.api",
            (HarnessComponentName.FRONTEND_DECODER,),
            "frontend.response_decode",
        ),
    }
)

HARNESS_OPERATION_STAGE_OWNERS = MappingProxyType(
    {
        (HarnessWorkflow.DOCUMENT_PARSE, HarnessStage.DOCUMENT_PARSE): "app.services.document_parser",
        (HarnessWorkflow.DOCUMENT_PARSE, HarnessStage.PAGE_EXTRACTION): "app.services.document_parser",
        (HarnessWorkflow.DOCUMENT_PARSE, HarnessStage.SECTION_DETECTION): "app.services.document_parser",
        (HarnessWorkflow.DOCUMENT_PARSE, HarnessStage.CHUNK_BUILDING): "app.services.document_parser",
        (HarnessWorkflow.OCR, HarnessStage.OCR_PAGE): "app.services.ocr_engine",
        (HarnessWorkflow.STUDY_UNIT_CLEANUP, HarnessStage.STUDY_UNIT_CLEANUP): "app.services.study_arrangement",
        (HarnessWorkflow.PLANNING, HarnessStage.PLAN_REVISION): "app.services.plan_revision",
        (HarnessWorkflow.PLANNING, HarnessStage.PLAN_GENERATION): "app.services.model_provider",
        (HarnessWorkflow.PLANNING, HarnessStage.PLANNING_TOOL_EXECUTION): "app.services.plan_tool_runtime",
        (HarnessWorkflow.PERSONA, HarnessStage.PERSONA_GENERATION): "app.services.persona_cards",
        (HarnessWorkflow.SCENE, HarnessStage.SCENE_GENERATION): "app.services.scene_setup",
        (HarnessWorkflow.STUDY_CHAT, HarnessStage.STUDY_CHAT_REPLY): "app.services.study_sessions",
        (HarnessWorkflow.TAVERN, HarnessStage.TAVERN_ACTOR_REPLY): "app.services.tavern",
        (HarnessWorkflow.FRONTEND_DECODE, HarnessStage.FRONTEND_RESPONSE_DECODE): "apps.web.lib.api",
    }
)

HARNESS_STAGE_WORKFLOWS = MappingProxyType(
    {
        HarnessStage.DOCUMENT_PARSE: HarnessWorkflow.DOCUMENT_PARSE,
        HarnessStage.PAGE_EXTRACTION: HarnessWorkflow.DOCUMENT_PARSE,
        HarnessStage.SECTION_DETECTION: HarnessWorkflow.DOCUMENT_PARSE,
        HarnessStage.CHUNK_BUILDING: HarnessWorkflow.DOCUMENT_PARSE,
        HarnessStage.OCR_PAGE: HarnessWorkflow.OCR,
        HarnessStage.STUDY_UNIT_CLEANUP: HarnessWorkflow.STUDY_UNIT_CLEANUP,
        HarnessStage.PLAN_REVISION: HarnessWorkflow.PLANNING,
        HarnessStage.PLAN_GENERATION: HarnessWorkflow.PLANNING,
        HarnessStage.PLANNING_TOOL_EXECUTION: HarnessWorkflow.PLANNING,
        HarnessStage.PERSONA_GENERATION: HarnessWorkflow.PERSONA,
        HarnessStage.SCENE_GENERATION: HarnessWorkflow.SCENE,
        HarnessStage.STUDY_CHAT_REPLY: HarnessWorkflow.STUDY_CHAT,
        HarnessStage.TAVERN_ACTOR_REPLY: HarnessWorkflow.TAVERN,
        HarnessStage.FRONTEND_RESPONSE_DECODE: HarnessWorkflow.FRONTEND_DECODE,
    }
)

HARNESS_OPERATION_STAGE_KEYS = frozenset(
    (workflow, stage) for stage, workflow in HARNESS_STAGE_WORKFLOWS.items()
)


HARNESS_STAGE_COMPONENT_NAMES = MappingProxyType(
    {
        key: registration.component_names
        for key, registration in HARNESS_OPERATION_STAGE_REGISTRATIONS.items()
    }
)


def registered_harness_stage_component_contracts(
    workflow: HarnessWorkflow,
    stage: HarnessStage,
) -> tuple[HarnessContractRef, ...]:
    registration = HARNESS_OPERATION_STAGE_REGISTRATIONS.get((workflow, stage))
    if registration is None:
        raise ValueError("harness_stage_not_registered")
    contracts: list[HarnessContractRef] = []
    for component_name in registration.component_names:
        component = HARNESS_COMPONENT_REGISTRATIONS.get(component_name)
        if component is None:
            raise ValueError("harness_stage_component_not_registered")
        if component.contract is None:
            raise ValueError("harness_stage_component_version_unregistered")
        contracts.append(component.contract.to_ref())
    return tuple(sorted(contracts, key=lambda item: item.name))


def validate_harness_operation_stage_registry(
    component_registry: Mapping[object, object],
    stage_registry: Mapping[object, object],
) -> None:
    if set(HARNESS_STAGE_WORKFLOWS) != set(HarnessStage):
        raise ValueError("harness_stage_workflow_registry_incomplete")
    if set(HARNESS_COMPONENT_OWNERS) != set(HarnessComponentName):
        raise ValueError("harness_component_owner_registry_incomplete")
    if set(HARNESS_OPERATION_STAGE_OWNERS) != HARNESS_OPERATION_STAGE_KEYS:
        raise ValueError("harness_stage_owner_registry_incomplete")
    if set(component_registry) != set(HarnessComponentName):
        raise ValueError("harness_component_registry_incomplete")
    for key, registration in component_registry.items():
        if not isinstance(key, HarnessComponentName) or not isinstance(
            registration, HarnessComponentRegistration
        ):
            raise ValueError("harness_component_registry_invalid")
        if registration.component_name != key:
            raise ValueError("harness_component_registry_key_mismatch")
        if registration.owner_module != HARNESS_COMPONENT_OWNERS[key]:
            raise ValueError("harness_component_owner_module_mismatch")
        if not re.fullmatch(r"[A-Za-z0-9_.]+", registration.owner_module):
            raise ValueError("harness_component_owner_module_invalid")
        if registration.contract is not None:
            require_versioned_harness_contract(registration.contract.to_ref())
            if registration.contract.name != key.value:
                raise ValueError("harness_component_contract_name_mismatch")

    if set(stage_registry) != HARNESS_OPERATION_STAGE_KEYS:
        raise ValueError("harness_stage_registry_incomplete")
    stages: set[HarnessStage] = set()
    workflows: set[HarnessWorkflow] = set()
    eval_routes: set[str] = set()
    for key, registration in stage_registry.items():
        if (
            not isinstance(key, tuple)
            or len(key) != 2
            or not isinstance(registration, HarnessOperationStageRegistration)
            or key != (registration.workflow, registration.stage)
        ):
            raise ValueError("harness_stage_registry_invalid")
        if registration.stage in stages:
            raise ValueError("harness_stage_registry_stage_duplicate")
        if registration.owner_module != HARNESS_OPERATION_STAGE_OWNERS[key]:
            raise ValueError("harness_stage_owner_module_mismatch")
        stages.add(registration.stage)
        workflows.add(registration.workflow)
        component_names = tuple(item.value for item in registration.component_names)
        if not component_names:
            raise ValueError("harness_stage_component_set_empty")
        if len(component_names) != len(set(component_names)):
            raise ValueError("harness_stage_component_duplicate")
        if component_names != tuple(sorted(component_names)):
            raise ValueError("harness_stage_components_not_sorted")
        if any(item not in component_registry for item in registration.component_names):
            raise ValueError("harness_stage_component_not_registered")
        if not re.fullmatch(r"[A-Za-z0-9_.]+", registration.owner_module):
            raise ValueError("harness_stage_owner_module_invalid")
        if not re.fullmatch(
            r"[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+",
            registration.eval_route,
        ):
            raise ValueError("harness_stage_eval_route_invalid")
        if registration.eval_route in eval_routes:
            raise ValueError("harness_stage_eval_route_duplicate")
        eval_routes.add(registration.eval_route)

    if stages != set(HarnessStage):
        raise ValueError("harness_stage_registry_incomplete")
    if workflows != set(HarnessWorkflow):
        raise ValueError("harness_stage_workflow_unrepresented")
    if {item.value for item in HarnessStage} & {
        item.value for item in HarnessAttemptPhase
    }:
        raise ValueError("harness_stage_attempt_phase_overlap")


def harness_operation_stage_registry_snapshot() -> dict[str, object]:
    return {
        "schema_name": "HarnessOperationStageRegistry",
        "schema_version": "harness-operation-stage-registry-v1",
        "components": [
            {
                "component_name": name.value,
                "owner_module": registration.owner_module,
                "contract": (
                    {
                        "name": registration.contract.name,
                        "version": registration.contract.version,
                    }
                    if registration.contract is not None
                    else None
                ),
            }
            for name, registration in sorted(
                HARNESS_COMPONENT_REGISTRATIONS.items(),
                key=lambda item: item[0].value,
            )
        ],
        "stages": [
            {
                "workflow": registration.workflow.value,
                "stage": registration.stage.value,
                "owner_module": registration.owner_module,
                "component_names": [item.value for item in registration.component_names],
                "eval_route": registration.eval_route,
            }
            for _, registration in sorted(
                HARNESS_OPERATION_STAGE_REGISTRATIONS.items(),
                key=lambda item: (item[0][0].value, item[0][1].value),
            )
        ],
    }


class HarnessResourceRef(HarnessV2Model):
    """The registered v2 wire shape; keep open strings for persisted compatibility."""

    resource_type: str = Field(min_length=1, max_length=96)
    resource_id: str = Field(min_length=1, max_length=160)
    revision: int | None = Field(default=None, ge=0)


class HarnessSnapshotRef(HarnessV2Model):
    """The registered v2 wire shape; v3 adds typed artifacts and contracts."""

    artifact_type: str = Field(min_length=1, max_length=96)
    artifact_id: str = Field(min_length=1, max_length=160)
    schema_version: str = Field(min_length=1, max_length=160)
    digest_algorithm: Literal[HarnessDigestAlgorithm.SHA256] = HarnessDigestAlgorithm.SHA256
    payload_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class HarnessContextEnvelope(HarnessV2Model):
    """The immutable v2 context wire contract."""

    schema_name: str = Field(min_length=1, max_length=160)
    schema_version: str = Field(min_length=1, max_length=160)
    workflow: HarnessWorkflow
    operation_id: str = Field(min_length=1, max_length=160)
    subject_refs: list[HarnessResourceRef] = Field(default_factory=list, max_length=64)
    component_versions: list[HarnessContractRef] = Field(
        default_factory=list,
        max_length=64,
    )
    snapshot_refs: list[HarnessSnapshotRef] = Field(default_factory=list, max_length=64)
    digest_algorithm: Literal[HarnessDigestAlgorithm.SHA256] = HarnessDigestAlgorithm.SHA256
    input_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    context_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    policy_version: str | None = Field(default=None, min_length=1, max_length=160)
    prompt_version: str | None = Field(default=None, min_length=1, max_length=160)

    @model_validator(mode="after")
    def validate_canonical_references(self) -> "HarnessContextEnvelope":
        subject_identities = [
            (item.resource_type, item.resource_id) for item in self.subject_refs
        ]
        if len(subject_identities) != len(set(subject_identities)):
            raise ValueError("harness_context_subject_ref_duplicate")
        if subject_identities != sorted(subject_identities):
            raise ValueError("harness_context_subject_refs_not_sorted")

        component_names = [item.name for item in self.component_versions]
        if len(component_names) != len(set(component_names)):
            raise ValueError("harness_context_component_version_duplicate")
        if component_names != sorted(component_names):
            raise ValueError("harness_context_component_versions_not_sorted")
        snapshot_identities = [
            (item.artifact_type, item.artifact_id) for item in self.snapshot_refs
        ]
        if len(snapshot_identities) != len(set(snapshot_identities)):
            raise ValueError("harness_context_snapshot_ref_duplicate")
        if snapshot_identities != sorted(snapshot_identities):
            raise ValueError("harness_context_snapshot_refs_not_sorted")
        return self


HARNESS_CONTEXT_CONTRACT_V3 = HarnessContractRef(
    name="HarnessContextEnvelopeV3",
    version="harness-context-v3",
)
HARNESS_CONTEXT_DIGEST_CONTRACT_V1 = HarnessContractRef(
    name="HarnessContextManifestDigest",
    version="harness-context-manifest-digest-v1",
)


HARNESS_RESOURCE_EVIDENCE_POLICIES = MappingProxyType(
    {
        HarnessResourceType.DOCUMENT: HarnessResourceEvidencePolicy(
            semantics=HarnessResourceSemantics.UNVERSIONED_MUTABLE,
            context_evidence=HarnessContextEvidencePolicy.UNSUPPORTED,
            commit_evidence=HarnessCommitEvidencePolicy.DIGEST,
            rollback_evidence=HarnessRollbackEvidencePolicy.UNSUPPORTED,
        ),
        HarnessResourceType.DOCUMENT_PAGE: HarnessResourceEvidencePolicy(
            semantics=HarnessResourceSemantics.PARENT_BOUND,
            context_evidence=HarnessContextEvidencePolicy.UNSUPPORTED,
            commit_evidence=HarnessCommitEvidencePolicy.UNSUPPORTED,
            rollback_evidence=HarnessRollbackEvidencePolicy.UNSUPPORTED,
        ),
        HarnessResourceType.DOCUMENT_DEBUG: HarnessResourceEvidencePolicy(
            semantics=HarnessResourceSemantics.UNVERSIONED_MUTABLE,
            context_evidence=HarnessContextEvidencePolicy.UNSUPPORTED,
            commit_evidence=HarnessCommitEvidencePolicy.UNSUPPORTED,
            rollback_evidence=HarnessRollbackEvidencePolicy.UNSUPPORTED,
        ),
        HarnessResourceType.STUDY_UNIT: HarnessResourceEvidencePolicy(
            semantics=HarnessResourceSemantics.PARENT_BOUND,
            context_evidence=HarnessContextEvidencePolicy.UNSUPPORTED,
            commit_evidence=HarnessCommitEvidencePolicy.UNSUPPORTED,
            rollback_evidence=HarnessRollbackEvidencePolicy.UNSUPPORTED,
        ),
        HarnessResourceType.PLAN_REVISION: HarnessResourceEvidencePolicy(
            semantics=HarnessResourceSemantics.IMMUTABLE,
            context_evidence=HarnessContextEvidencePolicy.PROTECTED_SNAPSHOT,
            commit_evidence=HarnessCommitEvidencePolicy.DIGEST,
            rollback_evidence=HarnessRollbackEvidencePolicy.UNSUPPORTED,
        ),
        HarnessResourceType.LEARNING_PLAN: HarnessResourceEvidencePolicy(
            semantics=HarnessResourceSemantics.UNVERSIONED_MUTABLE,
            context_evidence=HarnessContextEvidencePolicy.UNSUPPORTED,
            commit_evidence=HarnessCommitEvidencePolicy.DIGEST,
            rollback_evidence=HarnessRollbackEvidencePolicy.UNSUPPORTED,
        ),
        HarnessResourceType.PLANNING_TRACE: HarnessResourceEvidencePolicy(
            semantics=HarnessResourceSemantics.UNVERSIONED_MUTABLE,
            context_evidence=HarnessContextEvidencePolicy.UNSUPPORTED,
            commit_evidence=HarnessCommitEvidencePolicy.UNSUPPORTED,
            rollback_evidence=HarnessRollbackEvidencePolicy.UNSUPPORTED,
        ),
        HarnessResourceType.PERSONA: HarnessResourceEvidencePolicy(
            semantics=HarnessResourceSemantics.UNVERSIONED_MUTABLE,
            context_evidence=HarnessContextEvidencePolicy.UNSUPPORTED,
            commit_evidence=HarnessCommitEvidencePolicy.UNSUPPORTED,
            rollback_evidence=HarnessRollbackEvidencePolicy.UNSUPPORTED,
        ),
        HarnessResourceType.SCENE: HarnessResourceEvidencePolicy(
            semantics=HarnessResourceSemantics.UNVERSIONED_MUTABLE,
            context_evidence=HarnessContextEvidencePolicy.UNSUPPORTED,
            commit_evidence=HarnessCommitEvidencePolicy.UNSUPPORTED,
            rollback_evidence=HarnessRollbackEvidencePolicy.UNSUPPORTED,
        ),
        HarnessResourceType.STUDY_SESSION: HarnessResourceEvidencePolicy(
            semantics=HarnessResourceSemantics.REVISIONED_CONTROL_AGGREGATE,
            context_evidence=HarnessContextEvidencePolicy.AUTHORITATIVE_REVISION,
            commit_evidence=HarnessCommitEvidencePolicy.REVISION,
            rollback_evidence=HarnessRollbackEvidencePolicy.UNSUPPORTED,
        ),
        HarnessResourceType.TAVERN_ROOM: HarnessResourceEvidencePolicy(
            semantics=HarnessResourceSemantics.REVISIONED_CONTROL_AGGREGATE,
            context_evidence=HarnessContextEvidencePolicy.AUTHORITATIVE_REVISION,
            commit_evidence=HarnessCommitEvidencePolicy.REVISION,
            rollback_evidence=HarnessRollbackEvidencePolicy.UNSUPPORTED,
        ),
        HarnessResourceType.TAVERN_RUN: HarnessResourceEvidencePolicy(
            semantics=HarnessResourceSemantics.UNVERSIONED_MUTABLE,
            context_evidence=HarnessContextEvidencePolicy.UNSUPPORTED,
            commit_evidence=HarnessCommitEvidencePolicy.UNSUPPORTED,
            rollback_evidence=HarnessRollbackEvidencePolicy.UNSUPPORTED,
        ),
        HarnessResourceType.TAVERN_MESSAGE: HarnessResourceEvidencePolicy(
            semantics=HarnessResourceSemantics.APPEND_ONLY,
            context_evidence=HarnessContextEvidencePolicy.UNSUPPORTED,
            commit_evidence=HarnessCommitEvidencePolicy.SEQUENCE,
            rollback_evidence=HarnessRollbackEvidencePolicy.UNSUPPORTED,
        ),
        HarnessResourceType.FRONTEND_REQUEST: HarnessResourceEvidencePolicy(
            semantics=HarnessResourceSemantics.OPERATION_IDENTITY,
            context_evidence=HarnessContextEvidencePolicy.OPERATION_IDENTITY,
            commit_evidence=HarnessCommitEvidencePolicy.UNSUPPORTED,
            rollback_evidence=HarnessRollbackEvidencePolicy.UNSUPPORTED,
        ),
    }
)


def validate_harness_resource_evidence_policy_registry(
    registry: Mapping[object, object],
) -> None:
    if set(registry) != set(HarnessResourceType):
        raise ValueError("harness_resource_evidence_policy_registry_incomplete")
    for resource_type in HarnessResourceType:
        policy = registry[resource_type]
        if (
            not isinstance(policy, HarnessResourceEvidencePolicy)
            or not isinstance(policy.semantics, HarnessResourceSemantics)
            or not isinstance(policy.context_evidence, HarnessContextEvidencePolicy)
            or not isinstance(policy.commit_evidence, HarnessCommitEvidencePolicy)
            or not isinstance(policy.rollback_evidence, HarnessRollbackEvidencePolicy)
        ):
            raise ValueError("harness_resource_evidence_policy_registry_invalid")
        shape = (
            policy.semantics,
            policy.context_evidence,
            policy.commit_evidence,
            policy.rollback_evidence,
        )
        allowed_shapes = {
            (HarnessResourceSemantics.IMMUTABLE, HarnessContextEvidencePolicy.PROTECTED_SNAPSHOT,
             HarnessCommitEvidencePolicy.DIGEST, HarnessRollbackEvidencePolicy.UNSUPPORTED),
            (
                HarnessResourceSemantics.REVISIONED_CONTROL_AGGREGATE,
                HarnessContextEvidencePolicy.AUTHORITATIVE_REVISION,
                HarnessCommitEvidencePolicy.REVISION,
                HarnessRollbackEvidencePolicy.UNSUPPORTED,
            ),
            (
                HarnessResourceSemantics.APPEND_ONLY,
                HarnessContextEvidencePolicy.UNSUPPORTED,
                HarnessCommitEvidencePolicy.SEQUENCE,
                HarnessRollbackEvidencePolicy.UNSUPPORTED,
            ),
            (
                HarnessResourceSemantics.IMMUTABLE,
                HarnessContextEvidencePolicy.PROTECTED_SNAPSHOT,
                HarnessCommitEvidencePolicy.UNSUPPORTED,
                HarnessRollbackEvidencePolicy.UNSUPPORTED,
            ),
            (
                HarnessResourceSemantics.PARENT_BOUND,
                HarnessContextEvidencePolicy.UNSUPPORTED,
                HarnessCommitEvidencePolicy.UNSUPPORTED,
                HarnessRollbackEvidencePolicy.UNSUPPORTED,
            ),
            (
                HarnessResourceSemantics.UNVERSIONED_MUTABLE,
                HarnessContextEvidencePolicy.UNSUPPORTED,
                HarnessCommitEvidencePolicy.UNSUPPORTED,
                HarnessRollbackEvidencePolicy.UNSUPPORTED,
            ),
            (
                HarnessResourceSemantics.UNVERSIONED_MUTABLE,
                HarnessContextEvidencePolicy.UNSUPPORTED,
                HarnessCommitEvidencePolicy.DIGEST,
                HarnessRollbackEvidencePolicy.UNSUPPORTED,
            ),
            (
                HarnessResourceSemantics.OPERATION_IDENTITY,
                HarnessContextEvidencePolicy.UNSUPPORTED,
                HarnessCommitEvidencePolicy.UNSUPPORTED,
                HarnessRollbackEvidencePolicy.UNSUPPORTED,
            ),
            (
                HarnessResourceSemantics.OPERATION_IDENTITY,
                HarnessContextEvidencePolicy.OPERATION_IDENTITY,
                HarnessCommitEvidencePolicy.UNSUPPORTED,
                HarnessRollbackEvidencePolicy.UNSUPPORTED,
            ),
        }
        if shape not in allowed_shapes:
            raise ValueError("harness_resource_evidence_policy_registry_inconsistent")


validate_harness_resource_evidence_policy_registry(
    HARNESS_RESOURCE_EVIDENCE_POLICIES
)


_TAVERN_ACTOR_MESSAGE_COMMIT_POLICY_KEY = HarnessOperationCommitPolicyKey(
    workflow=HarnessWorkflow.TAVERN,
    stage=HarnessStage.TAVERN_ACTOR_REPLY,
    trace_contract_name=TAVERN_ACTOR_REPLY_CONTRACT_NAME,
    trace_contract_version=TAVERN_ACTOR_REPLY_COMMIT_CONTRACT_VERSION,
    payload_contract_name=TAVERN_MESSAGE_COMMITTED_PROJECTION_CONTRACT_NAME,
    payload_contract_version=TAVERN_MESSAGE_COMMITTED_PROJECTION_CONTRACT_VERSION,
)
_TAVERN_ACTOR_MESSAGE_COMMIT_POLICY = HarnessOperationCommitPolicy(
    key=_TAVERN_ACTOR_MESSAGE_COMMIT_POLICY_KEY,
    projection_contract=HarnessRegisteredContract(
        TAVERN_MESSAGE_COMMITTED_PROJECTION_CONTRACT_NAME,
        TAVERN_MESSAGE_COMMITTED_PROJECTION_CONTRACT_VERSION,
    ),
    binding_contract=HarnessRegisteredContract(
        TAVERN_MESSAGE_COMMIT_BINDING_CONTRACT_NAME,
        TAVERN_MESSAGE_COMMIT_BINDING_CONTRACT_VERSION,
    ),
    digest_scope=HarnessDigestScope.COMMITTED_PROJECTION,
    evidence_scope=HarnessOperationEvidenceScope.PRIMARY_OUTPUT_ONLY,
    subject_resource_type=HarnessResourceType.TAVERN_ROOM,
    subject_resource_count=1,
    status_rules=(
        HarnessOperationCommitStatusRule(
            HarnessStatus.FAILED,
            HarnessCommitStatus.NOT_COMMITTED,
        ),
        HarnessOperationCommitStatusRule(
            HarnessStatus.PASSED,
            HarnessCommitStatus.COMMITTED,
        ),
        HarnessOperationCommitStatusRule(
            HarnessStatus.REPAIRED,
            HarnessCommitStatus.COMMITTED,
        ),
    ),
    resource_rules=(
        HarnessOperationCommitResourceRule(
            HarnessResourceType.TAVERN_MESSAGE,
            1,
            1,
            1,
            1,
        ),
    ),
)

_STUDY_CHAT_TURN_COMMIT_POLICY_KEY = HarnessOperationCommitPolicyKey(
    workflow=HarnessWorkflow.STUDY_CHAT,
    stage=HarnessStage.STUDY_CHAT_REPLY,
    trace_contract_name="StudyChatReply",
    trace_contract_version=STUDY_CHAT_TRACE_CONTRACT_VERSION,
    payload_contract_name="StudySessionTurnCommittedProjection",
    payload_contract_version=STUDY_CHAT_COMMITTED_PROJECTION_CONTRACT_VERSION,
)
_STUDY_CHAT_TURN_COMMIT_POLICY = HarnessOperationCommitPolicy(
    key=_STUDY_CHAT_TURN_COMMIT_POLICY_KEY,
    projection_contract=HarnessRegisteredContract(
        "StudySessionTurnCommittedProjection",
        STUDY_CHAT_COMMITTED_PROJECTION_CONTRACT_VERSION,
    ),
    binding_contract=HarnessRegisteredContract(
        "StudyChatOperationBinding", "study-chat-operation-binding-v1"
    ),
    digest_scope=HarnessDigestScope.COMMITTED_PROJECTION,
    evidence_scope=HarnessOperationEvidenceScope.PRIMARY_OUTPUT_ONLY,
    subject_resource_type=HarnessResourceType.STUDY_SESSION,
    subject_resource_count=1,
    status_rules=(
        HarnessOperationCommitStatusRule(HarnessStatus.FAILED, HarnessCommitStatus.NOT_COMMITTED),
        HarnessOperationCommitStatusRule(HarnessStatus.PASSED, HarnessCommitStatus.COMMITTED),
        HarnessOperationCommitStatusRule(HarnessStatus.REPAIRED, HarnessCommitStatus.COMMITTED),
    ),
    resource_rules=(HarnessOperationCommitResourceRule(HarnessResourceType.STUDY_SESSION, 1, 1, 1, 1),),
)

_DOCUMENT_PROCESS_COMMIT_POLICY_KEY = HarnessOperationCommitPolicyKey(
    workflow=HarnessWorkflow.DOCUMENT_PARSE,
    stage=HarnessStage.DOCUMENT_PARSE,
    trace_contract_name="DocumentProcessRuntimeOutput",
    trace_contract_version="document-process-runtime-output-v1",
    payload_contract_name="DocumentProcessCommittedProjection",
    payload_contract_version="document-process-committed-projection-v1",
)
_DOCUMENT_PROCESS_COMMIT_POLICY = HarnessOperationCommitPolicy(
    key=_DOCUMENT_PROCESS_COMMIT_POLICY_KEY,
    projection_contract=HarnessRegisteredContract(
        "DocumentProcessCommittedProjection",
        "document-process-committed-projection-v1",
    ),
    binding_contract=HarnessRegisteredContract(
        "DocumentProcessOperationBinding", "document-process-operation-binding-v1"
    ),
    digest_scope=HarnessDigestScope.COMMITTED_PROJECTION,
    evidence_scope=HarnessOperationEvidenceScope.COMPLETE_TRANSACTION,
    subject_resource_type=HarnessResourceType.FRONTEND_REQUEST,
    subject_resource_count=1,
    status_rules=(
        HarnessOperationCommitStatusRule(HarnessStatus.FAILED, HarnessCommitStatus.NOT_COMMITTED),
        HarnessOperationCommitStatusRule(HarnessStatus.PASSED, HarnessCommitStatus.COMMITTED),
        HarnessOperationCommitStatusRule(HarnessStatus.REPAIRED, HarnessCommitStatus.COMMITTED),
    ),
    resource_rules=(
        HarnessOperationCommitResourceRule(HarnessResourceType.DOCUMENT, 1, 1, 1, 1),
    ),
)

_LEARNING_PLAN_COMMIT_POLICY_KEY = HarnessOperationCommitPolicyKey(
    workflow=HarnessWorkflow.PLANNING,
    stage=HarnessStage.PLAN_GENERATION,
    trace_contract_name="LearningPlanRuntimeOutput",
    trace_contract_version="learning-plan-runtime-output-v1",
    payload_contract_name="LearningPlanCommittedProjection",
    payload_contract_version="learning-plan-committed-projection-v1",
)
_LEARNING_PLAN_COMMIT_POLICY = HarnessOperationCommitPolicy(
    key=_LEARNING_PLAN_COMMIT_POLICY_KEY,
    projection_contract=HarnessRegisteredContract(
        "LearningPlanCommittedProjection", "learning-plan-committed-projection-v1"
    ),
    binding_contract=HarnessRegisteredContract(
        "LearningPlanOperationBinding", "learning-plan-operation-binding-v1"
    ),
    digest_scope=HarnessDigestScope.COMMITTED_PROJECTION,
    evidence_scope=HarnessOperationEvidenceScope.COMPLETE_TRANSACTION,
    subject_resource_type=HarnessResourceType.FRONTEND_REQUEST,
    subject_resource_count=1,
    status_rules=(
        HarnessOperationCommitStatusRule(HarnessStatus.FAILED, HarnessCommitStatus.NOT_COMMITTED),
        HarnessOperationCommitStatusRule(HarnessStatus.PASSED, HarnessCommitStatus.COMMITTED),
        HarnessOperationCommitStatusRule(HarnessStatus.REPAIRED, HarnessCommitStatus.COMMITTED),
    ),
    resource_rules=(
        HarnessOperationCommitResourceRule(HarnessResourceType.LEARNING_PLAN, 1, 1, 1, 1),
    ),
)


_PLAN_REVISION_COMMIT_POLICY_KEY = HarnessOperationCommitPolicyKey(
    workflow=HarnessWorkflow.PLANNING, stage=HarnessStage.PLAN_REVISION,
    trace_contract_name="PlanRevisionProposal", trace_contract_version="plan-revision-proposal-v1",
    payload_contract_name="PlanRevisionCommittedProjection", payload_contract_version="plan-revision-committed-projection-v1",
)
_PLAN_REVISION_COMMIT_POLICY = HarnessOperationCommitPolicy(
    key=_PLAN_REVISION_COMMIT_POLICY_KEY,
    projection_contract=HarnessRegisteredContract("PlanRevisionCommittedProjection", "plan-revision-committed-projection-v1"),
    binding_contract=HarnessRegisteredContract("PlanRevisionOperationBinding", "plan-revision-operation-binding-v1"),
    digest_scope=HarnessDigestScope.COMMITTED_PROJECTION,
    evidence_scope=HarnessOperationEvidenceScope.COMPLETE_TRANSACTION,
    subject_resource_type=HarnessResourceType.FRONTEND_REQUEST, subject_resource_count=1,
    status_rules=(
        HarnessOperationCommitStatusRule(HarnessStatus.FAILED, HarnessCommitStatus.NOT_COMMITTED),
        HarnessOperationCommitStatusRule(HarnessStatus.PASSED, HarnessCommitStatus.COMMITTED),
    ),
    resource_rules=(
        HarnessOperationCommitResourceRule(HarnessResourceType.PLAN_REVISION, 1, 1, 1, 1),
    ),
)

HARNESS_OPERATION_COMMIT_POLICIES = MappingProxyType(
    {
        _PLAN_REVISION_COMMIT_POLICY_KEY: _PLAN_REVISION_COMMIT_POLICY,
        _DOCUMENT_PROCESS_COMMIT_POLICY_KEY: _DOCUMENT_PROCESS_COMMIT_POLICY,
        _LEARNING_PLAN_COMMIT_POLICY_KEY: _LEARNING_PLAN_COMMIT_POLICY,
        _TAVERN_ACTOR_MESSAGE_COMMIT_POLICY_KEY: (
            _TAVERN_ACTOR_MESSAGE_COMMIT_POLICY
        ),
        _STUDY_CHAT_TURN_COMMIT_POLICY_KEY: _STUDY_CHAT_TURN_COMMIT_POLICY,
    }
)


def validate_harness_operation_commit_policy_registry(
    registry: Mapping[object, object],
) -> None:
    """Fail closed when a commit policy drifts from its audited operation."""

    if set(registry) != set(HARNESS_OPERATION_COMMIT_POLICIES):
        raise ValueError("harness_operation_commit_policy_registry_incomplete")
    for key, policy in registry.items():
        if (
            not isinstance(key, HarnessOperationCommitPolicyKey)
            or not isinstance(policy, HarnessOperationCommitPolicy)
            or policy.key != key
        ):
            raise ValueError("harness_operation_commit_policy_registry_invalid")
        if (key.workflow, key.stage) not in HARNESS_OPERATION_STAGE_KEYS:
            raise ValueError("harness_operation_commit_stage_unregistered")
        for contract in (
            HarnessContractRef(
                name=key.trace_contract_name,
                version=key.trace_contract_version,
            ),
            HarnessContractRef(
                name=key.payload_contract_name,
                version=key.payload_contract_version,
            ),
            policy.projection_contract.to_ref(),
            policy.binding_contract.to_ref(),
        ):
            require_versioned_harness_contract(contract)
        if (
            policy.projection_contract.name != key.payload_contract_name
            or policy.projection_contract.version != key.payload_contract_version
        ):
            raise ValueError("harness_operation_commit_projection_contract_mismatch")
        if policy.digest_scope != HarnessDigestScope.COMMITTED_PROJECTION:
            raise ValueError("harness_operation_commit_digest_scope_invalid")
        if policy.evidence_scope not in {
            HarnessOperationEvidenceScope.PRIMARY_OUTPUT_ONLY,
            HarnessOperationEvidenceScope.COMPLETE_TRANSACTION,
        }:
            raise ValueError("harness_operation_commit_evidence_scope_invalid")
        if policy.subject_resource_count < 1:
            raise ValueError("harness_operation_commit_subject_count_invalid")
        status_keys = [item.trace_status for item in policy.status_rules]
        if len(status_keys) != len(set(status_keys)):
            raise ValueError("harness_operation_commit_status_rule_duplicate")
        if status_keys != sorted(status_keys, key=lambda item: item.value):
            raise ValueError("harness_operation_commit_status_rules_not_sorted")
        resource_types = [item.resource_type for item in policy.resource_rules]
        if not resource_types:
            raise ValueError("harness_operation_commit_resource_rules_empty")
        if len(resource_types) != len(set(resource_types)):
            raise ValueError("harness_operation_commit_resource_rule_duplicate")
        if resource_types != sorted(resource_types, key=lambda item: item.value):
            raise ValueError("harness_operation_commit_resource_rules_not_sorted")
        for rule in policy.resource_rules:
            if (
                rule.committed_attempted_count < 1
                or rule.committed_resource_count < 1
                or rule.not_committed_attempted_min < 0
                or rule.not_committed_attempted_max
                < rule.not_committed_attempted_min
            ):
                raise ValueError("harness_operation_commit_resource_count_invalid")
            if (
                HARNESS_RESOURCE_EVIDENCE_POLICIES[
                    rule.resource_type
                ].commit_evidence
                == HarnessCommitEvidencePolicy.UNSUPPORTED
            ):
                raise ValueError("harness_operation_commit_resource_unsupported")
        if policy != HARNESS_OPERATION_COMMIT_POLICIES[key]:
            raise ValueError("harness_operation_commit_policy_definition_mismatch")


def harness_operation_commit_policy_registry_snapshot() -> dict[str, object]:
    """Return the canonical Python/TypeScript operation-policy projection."""

    return {
        "schema_name": "HarnessOperationCommitPolicyRegistry",
        "schema_version": "harness-operation-commit-policies-v1",
        "policies": [
            {
                "workflow": key.workflow.value,
                "stage": key.stage.value,
                "trace_contract": {
                    "name": key.trace_contract_name,
                    "version": key.trace_contract_version,
                },
                "payload_contract": {
                    "name": key.payload_contract_name,
                    "version": key.payload_contract_version,
                },
                "projection_contract": {
                    "name": policy.projection_contract.name,
                    "version": policy.projection_contract.version,
                },
                "binding_contract": {
                    "name": policy.binding_contract.name,
                    "version": policy.binding_contract.version,
                },
                "digest_scope": policy.digest_scope.value,
                "evidence_scope": policy.evidence_scope.value,
                "subject_resource_type": policy.subject_resource_type.value,
                "subject_resource_count": policy.subject_resource_count,
                "status_rules": [
                    {
                        "trace_status": item.trace_status.value,
                        "commit_status": item.commit_status.value,
                    }
                    for item in policy.status_rules
                ],
                "resource_rules": [
                    {
                        "resource_type": item.resource_type.value,
                        "committed_attempted_count": item.committed_attempted_count,
                        "committed_resource_count": item.committed_resource_count,
                        "not_committed_attempted_min": (
                            item.not_committed_attempted_min
                        ),
                        "not_committed_attempted_max": (
                            item.not_committed_attempted_max
                        ),
                    }
                    for item in policy.resource_rules
                ],
            }
            for key, policy in sorted(
                HARNESS_OPERATION_COMMIT_POLICIES.items(),
                key=lambda item: tuple(
                    value.value if isinstance(value, StrEnum) else value
                    for value in item[0]
                ),
            )
        ],
    }


def validate_harness_context_resource_evidence(
    resource: "HarnessResourceRefV3",
) -> None:
    policy = HARNESS_RESOURCE_EVIDENCE_POLICIES[resource.resource_type]
    if (
        policy.context_evidence
        == HarnessContextEvidencePolicy.AUTHORITATIVE_REVISION
        and resource.revision is None
    ):
        raise ValueError("harness_context_resource_revision_required")
    if policy.context_evidence == HarnessContextEvidencePolicy.PROTECTED_SNAPSHOT:
        raise ValueError("harness_context_resource_snapshot_binding_required")
    if (
        policy.context_evidence == HarnessContextEvidencePolicy.OPERATION_IDENTITY
        and resource.revision is not None
    ):
        raise ValueError("harness_context_operation_identity_revision_forbidden")
    if policy.context_evidence == HarnessContextEvidencePolicy.UNSUPPORTED:
        raise ValueError("harness_context_resource_policy_unsupported")


def validate_harness_attempted_resource_shape(
    resource: "HarnessResourceRefV3",
    *,
    require_commit_proof: bool = False,
) -> None:
    policy = HARNESS_RESOURCE_EVIDENCE_POLICIES[resource.resource_type]
    if (
        require_commit_proof
        and policy.commit_evidence == HarnessCommitEvidencePolicy.REVISION
        and resource.revision is None
    ):
        raise ValueError("harness_revision_commit_attempt_revision_required")
    if (
        policy.commit_evidence == HarnessCommitEvidencePolicy.SEQUENCE
        and resource.revision is not None
    ):
        raise ValueError("harness_sequence_commit_attempt_revision_forbidden")
    if (
        policy.commit_evidence == HarnessCommitEvidencePolicy.UNSUPPORTED
        and resource.revision is not None
    ):
        raise ValueError("harness_unsupported_commit_attempt_revision_forbidden")
    if (
        policy.commit_evidence == HarnessCommitEvidencePolicy.DIGEST
        and resource.revision is not None
    ):
        raise ValueError("harness_digest_commit_attempt_revision_forbidden")


def validate_harness_committed_resource_commit_evidence(
    resource: "HarnessCommittedResourceRefV3",
) -> None:
    policy = HARNESS_RESOURCE_EVIDENCE_POLICIES[resource.resource_type]
    if policy.commit_evidence == HarnessCommitEvidencePolicy.UNSUPPORTED:
        raise ValueError("harness_commit_resource_policy_unsupported")
    if policy.commit_evidence == HarnessCommitEvidencePolicy.REVISION:
        if resource.expected_revision is None or resource.committed_revision is None:
            raise ValueError("harness_revision_commit_evidence_required")
        if resource.first_sequence is not None or resource.last_sequence is not None:
            raise ValueError("harness_revision_commit_sequence_forbidden")
        if resource.committed_revision != resource.expected_revision + 1:
            raise ValueError("harness_revision_commit_increment_invalid")
    elif policy.commit_evidence == HarnessCommitEvidencePolicy.SEQUENCE:
        if resource.expected_revision is not None or resource.committed_revision is not None:
            raise ValueError("harness_sequence_commit_revision_forbidden")
        if resource.first_sequence is None or resource.last_sequence is None:
            raise ValueError("harness_sequence_commit_evidence_required")
        if resource.first_sequence != resource.last_sequence:
            raise ValueError("harness_message_commit_sequence_must_be_single")
    elif policy.commit_evidence == HarnessCommitEvidencePolicy.DIGEST:
        if (
            resource.expected_revision is not None
            or resource.committed_revision is not None
            or resource.first_sequence is not None
            or resource.last_sequence is not None
        ):
            raise ValueError("harness_digest_commit_position_forbidden")


def validate_harness_rollback_resource_evidence(
    resource: "HarnessResourceRefV3",
) -> None:
    policy = HARNESS_RESOURCE_EVIDENCE_POLICIES[resource.resource_type]
    if policy.rollback_evidence == HarnessRollbackEvidencePolicy.UNSUPPORTED:
        raise ValueError("harness_rollback_resource_policy_unsupported")


def harness_resource_evidence_policy_registry_snapshot() -> dict[str, object]:
    """Return the canonical cross-language registry fixture projection."""

    return {
        "schema_name": "HarnessResourceEvidencePolicyRegistry",
        "schema_version": "harness-resource-evidence-policies-v1",
        "resources": [
            {
                "resource_type": resource_type.value,
                "semantics": policy.semantics.value,
                "context_evidence": policy.context_evidence.value,
                "commit_evidence": policy.commit_evidence.value,
                "rollback_evidence": policy.rollback_evidence.value,
            }
            for resource_type, policy in sorted(
                HARNESS_RESOURCE_EVIDENCE_POLICIES.items(),
                key=lambda item: item[0].value,
            )
        ],
    }


class HarnessResourceRefV3(HarnessV2Model):
    resource_type: HarnessResourceType
    resource_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9:._-]{0,159}$")
    revision: int | None = Field(default=None, ge=0)


class HarnessSnapshotRefV3(HarnessV2Model):
    artifact_type: HarnessArtifactType
    artifact_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,159}$")
    contract: HarnessContractRef
    digest_algorithm: Literal[HarnessDigestAlgorithm.SHA256] = HarnessDigestAlgorithm.SHA256
    payload_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_contract(self) -> "HarnessSnapshotRefV3":
        require_versioned_harness_contract(self.contract)
        return self


class HarnessContextEnvelopeV3(HarnessV2Model):
    """Trace-safe, self-validating context identity for adopted workflows."""

    context_contract: HarnessContractRef
    workflow: HarnessWorkflow
    stage: HarnessStage
    operation_id: str = Field(pattern=r"^harness-operation-[0-9a-f]{32}$")
    input_contract: HarnessContractRef
    subject_refs: list[HarnessResourceRefV3] = Field(default_factory=list, max_length=64)
    component_versions: list[HarnessContractRef] = Field(
        default_factory=list,
        max_length=64,
    )
    snapshot_refs: list[HarnessSnapshotRefV3] = Field(default_factory=list, max_length=64)
    digest_algorithm: Literal[HarnessDigestAlgorithm.SHA256] = HarnessDigestAlgorithm.SHA256
    digest_contract: HarnessContractRef
    input_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    context_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    policy_contract: HarnessContractRef | None = None
    prompt_contract: HarnessContractRef | None = None

    @model_validator(mode="before")
    @classmethod
    def revalidate_nested_context_instances(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value
        subjects = value.get("subject_refs")
        if isinstance(subjects, list):
            for raw in subjects:
                revalidate_harness_resource_ref_v3(raw)
        snapshots = value.get("snapshot_refs")
        if isinstance(snapshots, list):
            for raw in snapshots:
                revalidate_harness_snapshot_ref_v3(raw)
        return value

    @model_validator(mode="after")
    def validate_canonical_context(self) -> "HarnessContextEnvelopeV3":
        if self.context_contract != HARNESS_CONTEXT_CONTRACT_V3:
            raise ValueError("harness_context_contract_mismatch")
        if self.digest_contract != HARNESS_CONTEXT_DIGEST_CONTRACT_V1:
            raise ValueError("harness_context_digest_contract_mismatch")
        for contract in (
            self.input_contract,
            self.policy_contract,
            self.prompt_contract,
            *self.component_versions,
        ):
            if contract is not None:
                require_versioned_harness_contract(contract)

        subject_identities = [
            (item.resource_type, item.resource_id) for item in self.subject_refs
        ]
        for item in self.subject_refs:
            revalidate_harness_resource_ref_v3(item)
            validate_harness_context_resource_evidence(item)
        if len(subject_identities) != len(set(subject_identities)):
            raise ValueError("harness_context_subject_ref_duplicate")
        if subject_identities != sorted(subject_identities):
            raise ValueError("harness_context_subject_refs_not_sorted")

        component_names = [item.name for item in self.component_versions]
        if len(component_names) != len(set(component_names)):
            raise ValueError("harness_context_component_version_duplicate")
        if component_names != sorted(component_names):
            raise ValueError("harness_context_component_versions_not_sorted")
        required_components = HARNESS_STAGE_COMPONENT_NAMES.get((self.workflow, self.stage))
        if required_components is None:
            raise ValueError("harness_context_stage_not_registered")
        if component_names != sorted(item.value for item in required_components):
            raise ValueError("harness_context_component_set_mismatch")
        try:
            expected_component_versions = list(
                registered_harness_stage_component_contracts(
                    self.workflow,
                    self.stage,
                )
            )
        except ValueError as error:
            raise ValueError(str(error)) from error
        if self.component_versions != expected_component_versions:
            raise ValueError("harness_context_component_version_mismatch")

        snapshot_identities = [
            (item.artifact_type, item.artifact_id) for item in self.snapshot_refs
        ]
        for item in self.snapshot_refs:
            revalidate_harness_snapshot_ref_v3(item)
        if len(snapshot_identities) != len(set(snapshot_identities)):
            raise ValueError("harness_context_snapshot_ref_duplicate")
        if snapshot_identities != sorted(snapshot_identities):
            raise ValueError("harness_context_snapshot_refs_not_sorted")
        if self.context_digest != canonical_harness_context_digest(self):
            raise ValueError("harness_context_digest_mismatch")
        return self


class HarnessCheckV2(HarnessV2Model):
    name: str = Field(min_length=1, max_length=160)
    status: HarnessCheckStatus
    code: str = Field(max_length=160)
    message: str = Field(max_length=2000)


class HarnessAttemptRecord(HarnessV2Model):
    attempt_id: str = Field(min_length=1, max_length=160)
    attempt_index: int = Field(ge=1)
    phase: HarnessAttemptPhase
    status: HarnessAttemptStatus
    output_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    error_code: str = Field(max_length=160)
    duration_ms: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_error_code(self) -> "HarnessAttemptRecord":
        if self.status == HarnessAttemptStatus.FAILED and not self.error_code:
            raise ValueError("harness_failed_attempt_error_code_required")
        if self.status != HarnessAttemptStatus.FAILED and self.error_code:
            raise ValueError("harness_nonfailed_attempt_error_code_forbidden")
        return self


class HarnessCommittedResourceRef(HarnessV2Model):
    resource_type: str = Field(min_length=1, max_length=96)
    resource_id: str = Field(min_length=1, max_length=160)
    expected_revision: int | None = Field(default=None, ge=0)
    committed_revision: int | None = Field(default=None, ge=0)
    first_sequence: int | None = Field(default=None, ge=1)
    last_sequence: int | None = Field(default=None, ge=1)
    payload_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_committed_resource(self) -> "HarnessCommittedResourceRef":
        if (self.first_sequence is None) != (self.last_sequence is None):
            raise ValueError("harness_commit_sequence_range_incomplete")
        if (
            self.first_sequence is not None
            and self.last_sequence is not None
            and self.first_sequence > self.last_sequence
        ):
            raise ValueError("harness_commit_sequence_range_invalid")
        if (
            self.expected_revision is not None
            and self.committed_revision is not None
            and self.committed_revision < self.expected_revision
        ):
            raise ValueError("harness_commit_revision_regressed")
        return self


class HarnessCommittedResourceRefV3(HarnessCommittedResourceRef):
    resource_type: HarnessResourceType
    resource_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9:._-]{0,159}$")


def revalidate_harness_snapshot_ref_v3(
    snapshot: object,
) -> HarnessSnapshotRefV3:
    payload = (
        snapshot.model_dump(mode="json", exclude_none=False)
        if isinstance(snapshot, HarnessSnapshotRefV3)
        else snapshot
    )
    return HarnessSnapshotRefV3.model_validate(payload)


def revalidate_harness_resource_ref_v3(
    resource: object,
) -> HarnessResourceRefV3:
    payload = (
        resource.model_dump(mode="json", exclude_none=False)
        if isinstance(resource, HarnessResourceRefV3)
        else resource
    )
    return HarnessResourceRefV3.model_validate(payload)


def revalidate_harness_committed_resource_ref_v3(
    resource: object,
) -> HarnessCommittedResourceRefV3:
    payload = (
        resource.model_dump(mode="json", exclude_none=False)
        if isinstance(resource, HarnessCommittedResourceRefV3)
        else resource
    )
    return HarnessCommittedResourceRefV3.model_validate(payload)


class HarnessCommitEvidence(HarnessV2Model):
    status: HarnessCommitStatus
    effect_batch_id: str | None = Field(default=None, min_length=1, max_length=160)
    payload_contract: HarnessContractRef | None = None
    digest_algorithm: Literal[HarnessDigestAlgorithm.SHA256] | None = None
    digest_scope: HarnessDigestScope | None = None
    attempted_resource_refs: list[HarnessResourceRef] = Field(
        default_factory=list,
        max_length=64,
    )
    committed_resources: list[HarnessCommittedResourceRef] = Field(
        default_factory=list,
        max_length=64,
    )
    payload_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    committed_at: AwareDatetime | None = None
    rollback_reason_code: str = Field(max_length=160)
    rolled_back_at: AwareDatetime | None = None

    @field_validator("committed_at", "rolled_back_at")
    @classmethod
    def require_utc_timestamp(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.utcoffset() != timedelta(0):
            raise ValueError("harness_effect_timestamp_must_be_utc")
        return value

    @model_validator(mode="after")
    def validate_commit_shape(self) -> "HarnessCommitEvidence":
        attempted_identities = [
            (item.resource_type, item.resource_id)
            for item in self.attempted_resource_refs
        ]
        if len(attempted_identities) != len(set(attempted_identities)):
            raise ValueError("harness_attempted_resource_ref_duplicate")
        if attempted_identities != sorted(attempted_identities):
            raise ValueError("harness_attempted_resource_refs_not_sorted")

        committed_identities = [
            (item.resource_type, item.resource_id)
            for item in self.committed_resources
        ]
        if len(committed_identities) != len(set(committed_identities)):
            raise ValueError("harness_committed_resource_ref_duplicate")
        if committed_identities != sorted(committed_identities):
            raise ValueError("harness_committed_resource_refs_not_sorted")

        if (
            self.digest_scope == HarnessDigestScope.COMMITTED_PROJECTION
            and len(self.attempted_resource_refs) != 1
        ):
            raise ValueError("harness_projection_digest_requires_single_resource")

        if self.status == HarnessCommitStatus.NOT_APPLICABLE:
            if (
                self.effect_batch_id is not None
                or self.payload_contract is not None
                or self.digest_algorithm is not None
                or self.digest_scope is not None
                or self.attempted_resource_refs
                or self.committed_resources
                or self.payload_digest is not None
                or self.committed_at is not None
                or self.rollback_reason_code
                or self.rolled_back_at is not None
            ):
                raise ValueError("harness_not_applicable_evidence_not_empty")
        elif self.status == HarnessCommitStatus.NOT_COMMITTED:
            if self.committed_resources or self.payload_digest is not None or self.committed_at:
                raise ValueError("harness_not_committed_contains_committed_state")
            if self.rollback_reason_code or self.rolled_back_at is not None:
                raise ValueError("harness_not_committed_contains_rollback_state")
            attempted_metadata = (
                self.effect_batch_id,
                self.payload_contract,
                self.digest_algorithm,
                self.digest_scope,
            )
            if self.attempted_resource_refs:
                if any(value is None for value in attempted_metadata):
                    raise ValueError("harness_not_committed_attempt_metadata_incomplete")
            elif any(value is not None for value in attempted_metadata):
                raise ValueError("harness_not_committed_attempt_resources_missing")
        elif self.status == HarnessCommitStatus.COMMITTED:
            if (
                self.effect_batch_id is None
                or self.payload_contract is None
                or self.digest_algorithm is None
                or self.digest_scope is None
                or not self.attempted_resource_refs
                or not self.committed_resources
                or self.payload_digest is None
                or self.committed_at is None
            ):
                raise ValueError("harness_committed_evidence_incomplete")
            if attempted_identities != committed_identities:
                raise ValueError("harness_commit_resource_set_mismatch")
            for attempted, committed in zip(
                self.attempted_resource_refs,
                self.committed_resources,
                strict=True,
            ):
                if attempted.revision != committed.expected_revision:
                    raise ValueError("harness_commit_expected_revision_mismatch")
            if (
                self.digest_scope == HarnessDigestScope.COMMITTED_PROJECTION
                and self.payload_digest != self.committed_resources[0].payload_digest
            ):
                raise ValueError("harness_projection_digest_mismatch")
            if (
                self.digest_scope == HarnessDigestScope.COMMITTED_BATCH
                and self.payload_digest
                != canonical_harness_commit_digest(
                    payload_contract=self.payload_contract,
                    committed_resources=self.committed_resources,
                    digest_scope=self.digest_scope,
                )
            ):
                raise ValueError("harness_batch_manifest_digest_mismatch")
            if self.rollback_reason_code or self.rolled_back_at is not None:
                raise ValueError("harness_committed_contains_rollback_state")
        elif self.status == HarnessCommitStatus.ROLLED_BACK:
            if (
                self.effect_batch_id is None
                or self.payload_contract is None
                or self.digest_algorithm is None
                or self.digest_scope is None
                or not self.attempted_resource_refs
                or not self.rollback_reason_code
                or self.rolled_back_at is None
            ):
                raise ValueError("harness_rollback_evidence_incomplete")
            if self.committed_resources or self.payload_digest is not None or self.committed_at:
                raise ValueError("harness_rolled_back_contains_committed_state")
        return self


class HarnessCommitEvidenceV3(HarnessCommitEvidence):
    attempted_resource_refs: list[HarnessResourceRefV3] = Field(
        default_factory=list,
        max_length=64,
    )
    committed_resources: list[HarnessCommittedResourceRefV3] = Field(
        default_factory=list,
        max_length=64,
    )

    @model_validator(mode="before")
    @classmethod
    def validate_v3_resource_policy_shape(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value
        attempted = value.get("attempted_resource_refs")
        require_commit_proof = value.get("status") == HarnessCommitStatus.COMMITTED.value
        if isinstance(attempted, list):
            for raw in attempted:
                resource = revalidate_harness_resource_ref_v3(raw)
                validate_harness_attempted_resource_shape(
                    resource,
                    require_commit_proof=require_commit_proof,
                )
        committed = value.get("committed_resources")
        if isinstance(committed, list):
            for raw in committed:
                resource = revalidate_harness_committed_resource_ref_v3(raw)
                validate_harness_committed_resource_commit_evidence(resource)
        return value

    @model_validator(mode="after")
    def validate_v3_contract(self) -> "HarnessCommitEvidenceV3":
        if self.payload_contract is not None:
            require_versioned_harness_contract(self.payload_contract)
        for resource in self.attempted_resource_refs:
            revalidate_harness_resource_ref_v3(resource)
            validate_harness_attempted_resource_shape(
                resource,
                require_commit_proof=self.status == HarnessCommitStatus.COMMITTED,
            )
            if self.status == HarnessCommitStatus.ROLLED_BACK:
                validate_harness_rollback_resource_evidence(resource)
        for resource in self.committed_resources:
            revalidate_harness_committed_resource_ref_v3(resource)
            validate_harness_committed_resource_commit_evidence(resource)
        return self


class HarnessTraceV2(HarnessV2Model):
    trace_schema_version: Literal["harness-trace-v2"]
    trace_id: str = Field(min_length=1, max_length=160)
    operation_id: str = Field(min_length=1, max_length=160)
    parent_trace_id: str | None = Field(default=None, min_length=1, max_length=160)
    workflow: HarnessWorkflow
    stage: str = Field(min_length=1, max_length=160)
    status: HarnessStatus
    contract: HarnessContractRef
    context: HarnessContextEnvelope
    output_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    checks: list[HarnessCheckV2] = Field(default_factory=list, max_length=256)
    attempt_records: list[HarnessAttemptRecord] = Field(min_length=1, max_length=128)
    recovery_strategy: str = Field(min_length=1, max_length=320)
    error_code: str = Field(max_length=160)
    duration_ms: int = Field(ge=0)
    commit_evidence: HarnessCommitEvidence
    started_at: AwareDatetime
    completed_at: AwareDatetime

    @field_validator("started_at", "completed_at")
    @classmethod
    def require_utc_timestamp(cls, value: datetime) -> datetime:
        if value.utcoffset() != timedelta(0):
            raise ValueError("harness_trace_timestamp_must_be_utc")
        return value

    @model_validator(mode="after")
    def validate_trace_shape(self) -> "HarnessTraceV2":
        if self.parent_trace_id == self.trace_id:
            raise ValueError("harness_parent_trace_self_reference")
        if self.context.operation_id != self.operation_id:
            raise ValueError("harness_context_operation_mismatch")
        if self.context.workflow != self.workflow:
            raise ValueError("harness_context_workflow_mismatch")
        attempt_ids = [item.attempt_id for item in self.attempt_records]
        if len(attempt_ids) != len(set(attempt_ids)):
            raise ValueError("harness_attempt_id_duplicate")
        attempt_indexes = [item.attempt_index for item in self.attempt_records]
        if attempt_indexes != list(range(1, len(attempt_indexes) + 1)):
            raise ValueError("harness_attempt_indexes_not_contiguous")

        if self.completed_at < self.started_at:
            raise ValueError("harness_trace_time_range_invalid")
        if any(item.duration_ms > self.duration_ms for item in self.attempt_records):
            raise ValueError("harness_attempt_duration_exceeds_trace")

        failed_attempts = [
            item for item in self.attempt_records if item.status == HarnessAttemptStatus.FAILED
        ]
        failed_checks = [
            item for item in self.checks if item.status == HarnessCheckStatus.FAILED
        ]
        warning_checks = [
            item for item in self.checks if item.status == HarnessCheckStatus.WARNING
        ]
        repair_attempts = [
            item
            for item in self.attempt_records
            if item.phase == HarnessAttemptPhase.REPAIR
            and item.status == HarnessAttemptStatus.PASSED
        ]
        commit_attempts = [
            item for item in self.attempt_records if item.phase == HarnessAttemptPhase.COMMIT
        ]
        rollback_attempts = [
            item for item in self.attempt_records if item.phase == HarnessAttemptPhase.ROLLBACK
        ]

        if self.status == HarnessStatus.PASSED:
            if self.output_digest is None:
                raise ValueError("harness_success_output_digest_required")
            if failed_attempts or failed_checks or warning_checks:
                raise ValueError("harness_passed_trace_contains_failure_or_warning")
            if self.recovery_strategy != "none" or repair_attempts:
                raise ValueError("harness_passed_trace_contains_recovery")
        elif self.status == HarnessStatus.REPAIRED:
            if self.output_digest is None:
                raise ValueError("harness_success_output_digest_required")
            if self.recovery_strategy == "none" or not repair_attempts:
                raise ValueError("harness_repaired_trace_strategy_required")
            if not failed_attempts and not warning_checks:
                raise ValueError("harness_repaired_trace_recovery_trigger_missing")
            if failed_checks:
                raise ValueError("harness_repaired_trace_contains_failed_check")
        elif self.status == HarnessStatus.FAILED:
            if not self.error_code:
                raise ValueError("harness_failed_trace_error_code_required")
            if not failed_attempts and not failed_checks:
                raise ValueError("harness_failed_trace_failure_evidence_missing")
            if self.commit_evidence.status == HarnessCommitStatus.COMMITTED:
                raise ValueError("harness_failed_trace_cannot_be_committed")
        elif self.status == HarnessStatus.SKIPPED:
            if self.output_digest is not None or self.error_code:
                raise ValueError("harness_skipped_trace_contains_output_or_error")
            if self.recovery_strategy != "none" or failed_attempts or failed_checks:
                raise ValueError("harness_skipped_trace_contains_execution")
            if any(
                item.status != HarnessAttemptStatus.SKIPPED
                for item in self.attempt_records
            ):
                raise ValueError("harness_skipped_trace_attempt_not_skipped")
            if self.commit_evidence.status != HarnessCommitStatus.NOT_APPLICABLE:
                raise ValueError("harness_skipped_trace_commit_not_applicable_required")

        if self.status != HarnessStatus.FAILED and self.error_code:
            raise ValueError("harness_nonfailed_trace_error_code_forbidden")

        output_attempts = [
            item
            for item in self.attempt_records
            if item.phase
            in {
                HarnessAttemptPhase.GENERATE,
                HarnessAttemptPhase.DECODE,
                HarnessAttemptPhase.VALIDATE,
                HarnessAttemptPhase.REPAIR,
            }
        ]
        if self.status in {HarnessStatus.PASSED, HarnessStatus.REPAIRED}:
            if not output_attempts:
                raise ValueError("harness_success_output_attempt_missing")
            terminal_output_attempt = output_attempts[-1]
            if (
                terminal_output_attempt.phase != HarnessAttemptPhase.VALIDATE
                or terminal_output_attempt.status != HarnessAttemptStatus.PASSED
            ):
                raise ValueError("harness_terminal_output_attempt_not_passed")
            if terminal_output_attempt.output_digest != self.output_digest:
                raise ValueError("harness_output_attempt_digest_mismatch")
            if self.status == HarnessStatus.REPAIRED:
                last_repair_index = repair_attempts[-1].attempt_index
                if last_repair_index >= terminal_output_attempt.attempt_index:
                    raise ValueError("harness_repaired_trace_validation_after_repair_required")

        if self.commit_evidence.status == HarnessCommitStatus.COMMITTED:
            if self.status not in {HarnessStatus.PASSED, HarnessStatus.REPAIRED}:
                raise ValueError("harness_committed_trace_status_invalid")
            if not commit_attempts or commit_attempts[-1] != self.attempt_records[-1]:
                raise ValueError("harness_commit_attempt_not_terminal")
            successful_commit = commit_attempts[-1]
            if successful_commit.status != HarnessAttemptStatus.PASSED:
                raise ValueError("harness_committed_trace_attempt_missing")
            if successful_commit.output_digest != self.commit_evidence.payload_digest:
                raise ValueError("harness_commit_attempt_digest_mismatch")
        elif self.commit_evidence.status in {
            HarnessCommitStatus.NOT_APPLICABLE,
            HarnessCommitStatus.NOT_COMMITTED,
        }:
            if any(item.status == HarnessAttemptStatus.PASSED for item in commit_attempts):
                raise ValueError("harness_uncommitted_trace_has_passed_commit")
            if rollback_attempts:
                raise ValueError("harness_uncommitted_trace_has_rollback")
            if self.commit_evidence.status == HarnessCommitStatus.NOT_APPLICABLE:
                if commit_attempts:
                    raise ValueError("harness_not_applicable_trace_has_commit_attempt")
            elif self.commit_evidence.attempted_resource_refs:
                if not commit_attempts or commit_attempts[-1].status != HarnessAttemptStatus.FAILED:
                    raise ValueError("harness_not_committed_failed_attempt_missing")
            elif commit_attempts:
                raise ValueError("harness_not_committed_attempt_evidence_missing")
        elif self.commit_evidence.status == HarnessCommitStatus.ROLLED_BACK:
            if self.status != HarnessStatus.FAILED:
                raise ValueError("harness_rolled_back_trace_status_invalid")
            if (
                not commit_attempts
                or commit_attempts[-1].status != HarnessAttemptStatus.FAILED
                or any(
                    item.status == HarnessAttemptStatus.PASSED
                    for item in commit_attempts
                )
            ):
                raise ValueError("harness_rollback_failed_commit_missing")
            if not rollback_attempts or rollback_attempts[-1] != self.attempt_records[-1]:
                raise ValueError("harness_rollback_attempt_not_terminal")
            if rollback_attempts[-1].status != HarnessAttemptStatus.PASSED:
                raise ValueError("harness_rollback_success_missing")
            if commit_attempts[-1] != self.attempt_records[-2]:
                raise ValueError("harness_rollback_failed_commit_not_adjacent")

        for timestamp in (
            self.commit_evidence.committed_at,
            self.commit_evidence.rolled_back_at,
        ):
            if timestamp is not None and not (self.started_at <= timestamp <= self.completed_at):
                raise ValueError("harness_effect_timestamp_outside_trace")
        return self


class HarnessTraceV3(HarnessTraceV2):
    """V2 lifecycle evidence paired with the stricter v3 context contract."""

    trace_schema_version: Literal["harness-trace-v3"]
    operation_id: str = Field(pattern=r"^harness-operation-[0-9a-f]{32}$")
    stage: HarnessStage
    context: HarnessContextEnvelopeV3
    commit_evidence: HarnessCommitEvidenceV3

    @model_validator(mode="before")
    @classmethod
    def revalidate_nested_v3_trace_evidence(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value
        context = value.get("context")
        if isinstance(context, HarnessContextEnvelopeV3):
            HarnessContextEnvelopeV3.model_validate(
                context.model_dump(mode="json", exclude_none=False)
            )
        evidence = value.get("commit_evidence")
        if isinstance(evidence, HarnessCommitEvidenceV3):
            HarnessCommitEvidenceV3.model_validate(
                evidence.model_dump(mode="json", exclude_none=False)
            )
        contract = value.get("contract")
        if isinstance(contract, HarnessContractRef):
            HarnessContractRef.model_validate(
                contract.model_dump(mode="json", exclude_none=False)
            )
        return value

    @model_validator(mode="after")
    def bind_v3_context(self) -> "HarnessTraceV3":
        if self.context.stage != self.stage:
            raise ValueError("harness_context_stage_mismatch")
        require_versioned_harness_contract(self.contract)
        self._validate_operation_commit_policy()
        return self

    def _validate_operation_commit_policy(self) -> None:
        evidence = HarnessCommitEvidenceV3.model_validate(
            self.commit_evidence.model_dump(mode="json", exclude_none=False)
        )
        has_operation_claim = (
            evidence.status
            in {
                HarnessCommitStatus.COMMITTED,
                HarnessCommitStatus.ROLLED_BACK,
            }
            or evidence.payload_contract is not None
            or bool(evidence.attempted_resource_refs)
            or bool(evidence.committed_resources)
        )
        base_key = (
            self.workflow,
            self.stage,
            self.contract.name,
            self.contract.version,
        )
        candidates = [
            policy
            for key, policy in HARNESS_OPERATION_COMMIT_POLICIES.items()
            if key[:4] == base_key
        ]
        if not candidates:
            if has_operation_claim:
                raise ValueError("harness_operation_commit_policy_unregistered")
            return
        if evidence.payload_contract is None:
            if (
                self.status == HarnessStatus.FAILED
                and evidence.status == HarnessCommitStatus.NOT_COMMITTED
                and not has_operation_claim
            ):
                # Decode/generate/validate can fail before a concrete resource
                # or effect batch exists. The empty not-committed envelope is
                # the truthful claim for that pre-commit boundary.
                return
            raise ValueError("harness_operation_commit_payload_contract_required")
        key = HarnessOperationCommitPolicyKey(
            self.workflow,
            self.stage,
            self.contract.name,
            self.contract.version,
            evidence.payload_contract.name,
            evidence.payload_contract.version,
        )
        policy = HARNESS_OPERATION_COMMIT_POLICIES.get(key)
        if policy is None:
            raise ValueError("harness_operation_commit_policy_unregistered")
        expected_status = {
            item.trace_status: item.commit_status for item in policy.status_rules
        }.get(self.status)
        if expected_status is None or evidence.status != expected_status:
            raise ValueError("harness_operation_commit_status_mismatch")
        if evidence.digest_scope != policy.digest_scope:
            raise ValueError("harness_operation_commit_digest_scope_mismatch")
        if evidence.status == HarnessCommitStatus.ROLLED_BACK:
            raise ValueError("harness_operation_commit_rollback_forbidden")
        subject_refs = [
            item
            for item in self.context.subject_refs
            if item.resource_type == policy.subject_resource_type
        ]
        if len(subject_refs) != policy.subject_resource_count:
            raise ValueError("harness_operation_commit_subject_set_mismatch")
        allowed_resource_types = {item.resource_type for item in policy.resource_rules}
        actual_resource_types = {
            item.resource_type for item in evidence.attempted_resource_refs
        } | {item.resource_type for item in evidence.committed_resources}
        if not actual_resource_types <= allowed_resource_types:
            raise ValueError("harness_operation_commit_resource_set_mismatch")
        for rule in policy.resource_rules:
            attempted_count = sum(
                item.resource_type == rule.resource_type
                for item in evidence.attempted_resource_refs
            )
            committed_count = sum(
                item.resource_type == rule.resource_type
                for item in evidence.committed_resources
            )
            if evidence.status == HarnessCommitStatus.COMMITTED:
                if (
                    attempted_count != rule.committed_attempted_count
                    or committed_count != rule.committed_resource_count
                ):
                    raise ValueError("harness_operation_commit_resource_count_mismatch")
            elif (
                attempted_count < rule.not_committed_attempted_min
                or attempted_count > rule.not_committed_attempted_max
                or committed_count != 0
            ):
                raise ValueError("harness_operation_commit_resource_count_mismatch")
        if evidence.status == HarnessCommitStatus.COMMITTED:
            committed = evidence.committed_resources[0]
            if evidence.payload_digest != committed.payload_digest:
                raise ValueError("harness_operation_commit_payload_digest_mismatch")


ProposalT = TypeVar("ProposalT", bound=HarnessV2Model)


class HarnessProposalEnvelope(HarnessV2Model, Generic[ProposalT]):
    """Metadata wrapper; each workflow must supply a strict domain proposal DTO."""

    operation_id: str = Field(min_length=1, max_length=160)
    contract: HarnessContractRef
    context_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    payload_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    proposal: ProposalT

    @model_validator(mode="after")
    def validate_payload_digest(self) -> "HarnessProposalEnvelope[ProposalT]":
        generic_metadata = getattr(
            self.__class__,
            "__pydantic_generic_metadata__",
            {},
        )
        if not generic_metadata.get("args"):
            raise ValueError("harness_proposal_type_parameter_required")
        if not isinstance(self.proposal, BaseModel):
            raise ValueError("harness_proposal_pydantic_model_required")
        if self.proposal.model_config.get("extra") != "forbid":
            raise ValueError("harness_proposal_extra_forbid_required")
        if canonical_harness_digest(self.proposal) != self.payload_digest:
            raise ValueError("harness_proposal_payload_digest_mismatch")
        return self


HarnessTraceWire = HarnessTraceRecord | HarnessTraceV2 | HarnessTraceV3
_HARNESS_V1_ADAPTER = TypeAdapter(HarnessTraceRecord)
_HARNESS_V2_ADAPTER = TypeAdapter(HarnessTraceV2)
_HARNESS_V3_ADAPTER = TypeAdapter(HarnessTraceV3)


def validate_harness_trace(payload: object) -> HarnessTraceWire:
    """Strictly decode legacy v1 or registered v2/v3 wire evidence."""

    discriminator = payload.get("trace_schema_version") if isinstance(payload, dict) else None
    if discriminator == HARNESS_TRACE_SCHEMA_V2:
        return _HARNESS_V2_ADAPTER.validate_python(payload)
    if discriminator == HARNESS_TRACE_SCHEMA_V3:
        return _HARNESS_V3_ADAPTER.validate_python(payload)
    if discriminator is not None:
        # Use the strictest registered adapter so callers consistently receive a
        # Pydantic ValidationError without permitting an unknown-version fallback.
        return _HARNESS_V3_ADAPTER.validate_python(payload)
    return _HARNESS_V1_ADAPTER.validate_python(payload)


def canonical_harness_digest(payload: object) -> str:
    """SHA-256 over UTF-8 canonical JSON, preserving explicit null values."""

    if isinstance(payload, BaseModel):
        payload = payload.model_dump(mode="json", exclude_none=False)
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def canonical_harness_context_digest(
    context: HarnessContextEnvelopeV3 | dict[str, object],
) -> str:
    """Recompute a v3 context-manifest digest from trace-visible evidence."""

    if isinstance(context, HarnessContextEnvelopeV3):
        manifest = context.model_dump(
            mode="json",
            exclude={"operation_id", "context_digest"},
            exclude_none=False,
        )
    else:
        manifest = dict(context)
        manifest.pop("operation_id", None)
        manifest.pop("context_digest", None)
    digest_contract = HarnessContractRef.model_validate(manifest["digest_contract"])
    return canonical_harness_digest(
        {
            "contract": digest_contract.model_dump(
                mode="json",
                exclude_none=False,
            ),
            "payload": manifest,
        }
    )


def _is_placeholder_version(value: str) -> bool:
    normalized = value.strip().lower()
    return normalized.startswith("pending-") or normalized in {
        "latest",
        "unknown",
        "none",
    }


def require_versioned_harness_contract(contract: HarnessContractRef) -> None:
    """Reject ambiguous or placeholder contract identities used by V3 evidence."""

    token_pattern = r"^[A-Za-z0-9][A-Za-z0-9:._-]{0,159}$"
    if not re.fullmatch(token_pattern, contract.name) or not re.fullmatch(
        token_pattern,
        contract.version,
    ):
        raise ValueError("harness_contract_token_invalid")
    if _is_placeholder_version(contract.version):
        raise ValueError("harness_contract_version_not_adopted")


validate_harness_operation_stage_registry(
    HARNESS_COMPONENT_REGISTRATIONS,
    HARNESS_OPERATION_STAGE_REGISTRATIONS,
)
validate_harness_operation_commit_policy_registry(
    HARNESS_OPERATION_COMMIT_POLICIES,
)


def canonical_harness_commit_digest(
    *,
    payload_contract: HarnessContractRef,
    committed_resources: list[HarnessCommittedResourceRef],
    digest_scope: HarnessDigestScope,
) -> str:
    """Digest one projection directly or a canonical ordered resource manifest."""

    if digest_scope == HarnessDigestScope.COMMITTED_PROJECTION:
        if len(committed_resources) != 1:
            raise ValueError("harness_projection_digest_requires_single_resource")
        return committed_resources[0].payload_digest
    return canonical_harness_digest(
        {
            "payload_contract": payload_contract.model_dump(
                mode="json",
                exclude_none=False,
            ),
            "resources": [
                item.model_dump(mode="json", exclude_none=False)
                for item in committed_resources
            ],
        }
    )


def build_tavern_persona_message_commit_binding(
    projection: TavernPersonaMessageCommittedProjectionV1,
) -> TavernPersonaMessageCommitBindingV1:
    """Build trace-safe identity from a strictly revalidated protected projection."""

    canonical = revalidate_tavern_message_committed_projection(projection)
    return TavernPersonaMessageCommitBindingV1(
        operation_id=canonical.operation_id,
        effect_batch_id=canonical.effect_batch_id,
        room_id=canonical.room_id,
        message_id=canonical.message_id,
        sequence=canonical.sequence,
        run_id=canonical.run_id,
        step_index=canonical.step_index,
        reply_to_message_id=canonical.reply_to_message_id,
        author_kind=canonical.author_kind,
        persona_id=canonical.persona_id,
        persona_name=canonical.persona_name,
        client_request_id=canonical.client_request_id,
        created_at=canonical.created_at,
        projection_digest=canonical_harness_digest(canonical),
    )


def validate_harness_operation_commit(
    trace: HarnessTraceV3,
    binding: TavernPersonaMessageCommitBindingV1,
    *,
    message: "TavernMessageRecord",
    run: "TavernRunRecord",
    step: "TavernSpeakerStepRecord",
    participants: list["TavernParticipantRecord"],
    reply_anchor: "TavernMessageRecord",
) -> TavernPersonaMessageCommittedProjectionV1:
    """Validate one registered operation against protected committed read-back.

    This sidecar validator deliberately leaves the registered v3 wire unchanged.
    A trace alone proves lifecycle evidence; only this trace + repository
    read-back records + trace-safe binding proves the registered primary output.
    """

    strict_trace = HarnessTraceV3.model_validate(
        trace.model_dump(mode="json", exclude_none=False)
    )
    from app.models.tavern import (
        build_tavern_persona_message_committed_projection,
    )

    strict_projection = build_tavern_persona_message_committed_projection(
        message=message,
        run=run,
        step=step,
        participants=participants,
        reply_anchor=reply_anchor,
    )
    strict_binding = revalidate_tavern_message_commit_binding(binding)
    evidence = strict_trace.commit_evidence
    if (
        evidence.status != HarnessCommitStatus.COMMITTED
        or evidence.payload_contract is None
    ):
        raise ValueError("harness_operation_commit_success_required")
    key = HarnessOperationCommitPolicyKey(
        strict_trace.workflow,
        strict_trace.stage,
        strict_trace.contract.name,
        strict_trace.contract.version,
        evidence.payload_contract.name,
        evidence.payload_contract.version,
    )
    policy = HARNESS_OPERATION_COMMIT_POLICIES.get(key)
    if policy is None:
        raise ValueError("harness_operation_commit_policy_unregistered")
    if policy.evidence_scope != HarnessOperationEvidenceScope.PRIMARY_OUTPUT_ONLY:
        raise ValueError("harness_operation_commit_evidence_scope_invalid")
    expected_binding = build_tavern_persona_message_commit_binding(strict_projection)
    if strict_binding != expected_binding:
        raise ValueError("harness_operation_commit_binding_projection_mismatch")
    room_refs = [
        item
        for item in strict_trace.context.subject_refs
        if item.resource_type == policy.subject_resource_type
    ]
    if len(room_refs) != policy.subject_resource_count:
        raise ValueError("harness_operation_commit_subject_set_mismatch")
    attempted = evidence.attempted_resource_refs
    committed = evidence.committed_resources
    if len(attempted) != 1 or len(committed) != 1:
        raise ValueError("harness_operation_commit_resource_count_mismatch")
    attempted_message = attempted[0]
    committed_message = committed[0]
    if (
        attempted_message.resource_type != HarnessResourceType.TAVERN_MESSAGE
        or committed_message.resource_type != HarnessResourceType.TAVERN_MESSAGE
    ):
        raise ValueError("harness_operation_commit_resource_set_mismatch")
    if strict_projection.operation_id != strict_trace.operation_id:
        raise ValueError("harness_operation_commit_binding_operation_mismatch")
    if strict_projection.effect_batch_id != evidence.effect_batch_id:
        raise ValueError("harness_operation_commit_binding_effect_batch_mismatch")
    if strict_projection.room_id != room_refs[0].resource_id:
        raise ValueError("harness_operation_commit_binding_room_mismatch")
    if (
        strict_projection.message_id != attempted_message.resource_id
        or strict_projection.message_id != committed_message.resource_id
    ):
        raise ValueError("harness_operation_commit_binding_message_mismatch")
    if (
        strict_projection.sequence != committed_message.first_sequence
        or strict_projection.sequence != committed_message.last_sequence
    ):
        raise ValueError("harness_operation_commit_binding_sequence_mismatch")
    projection_digest = canonical_harness_digest(strict_projection)
    if (
        projection_digest != strict_binding.projection_digest
        or projection_digest != committed_message.payload_digest
        or projection_digest != evidence.payload_digest
    ):
        raise ValueError("harness_operation_commit_binding_digest_mismatch")
    return strict_projection
