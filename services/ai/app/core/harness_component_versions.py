"""Audited application-component contract versions used by Harness registries.

These constants describe repository-owned behavior, not dependency, model, or
package versions. Owning modules re-export their matching constant so registry
drift can be checked without making the Harness model import domain services.
"""

DOCUMENT_PAGE_EXTRACTOR_CONTRACT_VERSION = "document-page-extractor-v1"
DOCUMENT_SECTION_DETECTOR_CONTRACT_VERSION = "document-section-detector-v1"
DOCUMENT_CHUNK_BUILDER_CONTRACT_VERSION = "document-chunk-builder-v1"
PLANNING_TOOLSET_CONTRACT_VERSION = "planning-toolset-v1"
PLANNING_TOOL_RUNTIME_CONTRACT_VERSION = "planning-tool-runtime-v1"
TAVERN_PERSONA_COMPILER_CONTRACT_VERSION = "tavern-persona-compiler-v1"
TAVERN_ACTOR_PROMPT_CONTRACT_VERSION = "tavern-actor-v1"
TAVERN_SCHEDULER_CONTRACT_VERSION = "tavern-schedule-v1"
