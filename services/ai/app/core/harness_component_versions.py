"""Audited application-component contract versions used by Harness registries.

These constants describe repository-owned behavior, not dependency, model, or
package versions. Owning modules re-export their matching constant so registry
drift can be checked without making the Harness model import domain services.
"""

DOCUMENT_PAGE_EXTRACTOR_CONTRACT_VERSION = "document-page-extractor-v1"
DOCUMENT_SECTION_DETECTOR_CONTRACT_VERSION = "document-section-detector-v1"
DOCUMENT_CHUNK_BUILDER_CONTRACT_VERSION = "document-chunk-builder-v1"
DOCUMENT_PARSER_CONTRACT_VERSION = "document-parser-v1"
OCR_ENGINE_CONTRACT_VERSION = "ocr-engine-v1"
STUDY_UNIT_CLEANER_CONTRACT_VERSION = "study-unit-cleaner-v1"
PLANNING_PROMPT_CONTRACT_VERSION = "planning-prompt-v1"
PLANNING_TOOLSET_CONTRACT_VERSION = "planning-toolset-v1"
PLANNING_TOOL_RUNTIME_CONTRACT_VERSION = "planning-tool-runtime-v1"
PERSONA_COMPILER_CONTRACT_VERSION = "persona-compiler-v1"
SCENE_COMPILER_CONTRACT_VERSION = "scene-compiler-v1"
FRONTEND_DECODER_CONTRACT_VERSION = "frontend-decoder-v1"
TAVERN_PERSONA_COMPILER_CONTRACT_VERSION = "tavern-persona-compiler-v1"
TAVERN_ACTOR_PROMPT_CONTRACT_VERSION = "tavern-actor-v1"
TAVERN_SCHEDULER_CONTRACT_VERSION = "tavern-schedule-v1"
STUDY_CHAT_PROMPT_CONTRACT_VERSION = "study-chat-prompt-v1"
STUDY_CHAT_TOOLSET_CONTRACT_VERSION = "study-chat-toolset-v2"
STUDY_VISUAL_GROUNDING_CONTRACT_VERSION = "study-visual-grounding-v1"
STUDY_CHAT_WORKFLOW_ADAPTER_CONTRACT_VERSION = "study-chat-workflow-adapter-v1"
STUDY_CHAT_TRACE_CONTRACT_VERSION = "study-chat-reply-trace-v1"
STUDY_CHAT_COMMIT_CONTRACT_VERSION = "study-chat-turn-commit-v1"
STUDY_CHAT_COMMITTED_PROJECTION_CONTRACT_VERSION = "study-chat-turn-committed-projection-v1"

TAVERN_ACTOR_REPLY_CONTRACT_NAME = "TavernActorReply"
TAVERN_ACTOR_REPLY_CONTRACT_VERSION = "tavern-actor-reply-v1"
TAVERN_ACTOR_REPLY_COMMIT_CONTRACT_VERSION = "tavern-actor-reply-v2"
TAVERN_MESSAGE_COMMITTED_PROJECTION_CONTRACT_NAME = (
    "TavernPersonaMessageCommittedProjection"
)
TAVERN_MESSAGE_COMMITTED_PROJECTION_CONTRACT_VERSION = (
    "tavern-persona-message-committed-projection-v1"
)
TAVERN_MESSAGE_COMMIT_BINDING_CONTRACT_NAME = (
    "TavernPersonaMessageCommitBinding"
)
TAVERN_MESSAGE_COMMIT_BINDING_CONTRACT_VERSION = (
    "tavern-persona-message-commit-binding-v1"
)
TAVERN_MESSAGE_COMMIT_METADATA_CONTRACT_NAME = (
    "TavernPersonaMessageCommitMetadata"
)
TAVERN_MESSAGE_COMMIT_METADATA_CONTRACT_VERSION = (
    "tavern-persona-message-commit-metadata-v1"
)
