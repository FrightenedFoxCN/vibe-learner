"""Developer regression suites for the ten previously unregistered stages.

Registration does not attest held-out quality or complete workflow adoption.
"""

from types import MappingProxyType

from app.models.harness import HarnessContractRef

STAGE_EVAL_SUITES = MappingProxyType(
    {
        key: HarnessContractRef(name=name, version=name.replace("_", "-") + "-v1")
        for key, name in (
            ("document_parse:document_parse", "document_process_regression"),
            ("document_parse:page_extraction", "page_extraction_regression"),
            ("document_parse:section_detection", "section_detection_regression"),
            ("document_parse:chunk_building", "chunk_building_regression"),
            ("ocr:ocr_page", "ocr_page_regression"),
            ("study_unit_cleanup:study_unit_cleanup", "study_unit_cleanup_regression"),
            ("planning:plan_generation", "plan_generation_regression"),
            ("persona:persona_generation", "persona_generation_regression"),
            ("scene:scene_generation", "scene_generation_regression"),
            ("frontend_decode:response_decode", "frontend_decode_regression"),
        )
    }
)
