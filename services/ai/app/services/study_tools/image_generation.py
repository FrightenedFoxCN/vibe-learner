from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.models.harness_effect import HARNESS_EFFECT_ADAPTER_POLICIES
from app.models.study_chat_effect import (
    StudyProjectionEffectAction,
    StudyProjectionEffectProposalV1,
)
from app.models.study_chat_operation import study_chat_provider_effect_id
from app.services.study_tools.context import StudyToolContext
from fastapi import HTTPException


@dataclass
class ImageGenerationTools:
    context: StudyToolContext

    def generate_projected_image(self, arguments: dict[str, Any]) -> dict[str, Any]:
        if self.context.model_provider is None:
            raise HTTPException(
                status_code=422, detail="chat_image_generation_unsupported"
            )
        if self.context.effects is None:
            raise HTTPException(
                status_code=409, detail="study_chat_effect_collector_required"
            )
        prompt = str(arguments.get("prompt") or "").strip()
        title = str(arguments.get("title") or "").strip() or "AI 生成图像"
        size = str(arguments.get("size") or "1024x1024").strip() or "1024x1024"
        if not prompt:
            raise HTTPException(
                status_code=422, detail="chat_image_generation_prompt_required"
            )
        expected_projection_effect_id = self.context.effects.next_effect_id()
        external_effect_id = study_chat_provider_effect_id(
            operation_id=self.context.effects.operation_id,
            source_effect_id=expected_projection_effect_id,
        )
        try:
            generated = self.context.model_provider.generate_projected_image(
                prompt=prompt,
                size=size,
            )
        except RuntimeError as exc:
            return {
                "ok": False,
                "tool_name": "generate_projected_image",
                "error": str(exc),
            }
        proposal = StudyProjectionEffectProposalV1(
            action=StudyProjectionEffectAction.SET,
            source_kind="generated_image",
            title=title,
            page_number=1,
            page_count=1,
            image_url=str(generated.get("image_url") or ""),
        )
        effect = self.context.effects.prepare_projection(proposal)
        if effect.effect_id != expected_projection_effect_id:
            raise RuntimeError("study_provider_effect_slot_drift")
        session = self.context.sessions.require_session(self.context.session_id)
        projected_pdf = self.context.effects.preview_projected_state(
            session.projected_pdf
        )
        assert projected_pdf is not None
        return {
            "ok": True,
            "tool_name": "generate_projected_image",
            "effect_state": "prepared",
            "committed": False,
            "prepared_effect_id": effect.effect_id,
            "prepared_proposal": proposal.model_dump(mode="json"),
            "predicted_state": projected_pdf.model_dump(mode="json"),
            "external_effect_state": "completed_uncommitted",
            "external_effect_id": external_effect_id,
            "external_effect_adapter": HARNESS_EFFECT_ADAPTER_POLICIES[
                "study_provider_execution"
            ].model_dump(mode="json"),
            "external_effect_read_back": "unsupported",
            "revised_prompt": str(generated.get("revised_prompt") or ""),
        }
