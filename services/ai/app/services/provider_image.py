from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

import re

from app.services.provider_capabilities import ImageModelCapability


class ImageRequest(Protocol):
    def __call__(self, payload: dict[str, Any], *, request_kind: str, model: str) -> tuple[dict[str, Any], int]: ...


CHAT_IMAGE_GENERATION_MODEL_HINTS = (
    re.compile(r"^gpt-4o(?:[-.:]|$)", re.IGNORECASE),
    re.compile(r"^gpt-4\.1(?:[-.:]|$)", re.IGNORECASE),
    re.compile(r"^gpt-5(?:[-.:]|$)", re.IGNORECASE),
    re.compile(r"^o3(?:[-.:]|$)", re.IGNORECASE),
    re.compile(r"^chatgpt-image-latest$", re.IGNORECASE),
    re.compile(r"^gpt-image-1(?:[-.:]|$)", re.IGNORECASE),
)



@dataclass(frozen=True)
class RemoteImageProvider(ImageModelCapability):
    """Image capability with captured model/readiness and no SDK dependency."""

    chat_model: str
    responses_available: bool
    request: ImageRequest

    def supports_chat_generated_image_tools(self) -> bool:
        return self.responses_available and _model_supports_chat_image_generation(self.chat_model)

    def generate_projected_image(
        self,
        *,
        prompt: str,
        size: str = "1024x1024",
    ) -> dict[str, str]:
        normalized_prompt = prompt.strip()
        if not normalized_prompt:
            raise RuntimeError("chat_image_generation_prompt_required")
        if not self.supports_chat_generated_image_tools():
            raise RuntimeError("chat_image_generation_unsupported")
        payload: dict[str, Any] = {
            "model": self.chat_model,
            "input": normalized_prompt,
            "tools": [
                {
                    "type": "image_generation",
                    "size": _normalize_generated_image_size(size),
                }
            ],
        }
        raw_payload, _ = self.request(
            payload,
            request_kind="chat",
            model=self.chat_model,
        )
        return _extract_response_output_image(raw_payload)



def _extract_response_output_image(payload: dict[str, Any]) -> dict[str, str]:
    output = payload.get("output")
    if not isinstance(output, list):
        raise RuntimeError("chat_image_generation_empty_response")
    for item in output:
        if not isinstance(item, dict):
            continue
        if item.get("type") == "image_generation_call":
            raw_result = item.get("result")
            if isinstance(raw_result, str) and raw_result.strip():
                image_base64 = raw_result.strip()
            elif isinstance(raw_result, list):
                image_base64 = next(
                    (
                        str(entry).strip()
                        for entry in raw_result
                        if isinstance(entry, str) and str(entry).strip()
                    ),
                    "",
                )
            else:
                image_base64 = ""
            if image_base64:
                return {
                    "image_url": f"data:image/png;base64,{image_base64}",
                    "revised_prompt": str(item.get("revised_prompt") or "").strip(),
                }
    raise RuntimeError("chat_image_generation_empty_response")



def _normalize_generated_image_size(value: str) -> str:
    normalized = value.strip().lower()
    if normalized in {"1024x1024", "1536x1024", "1024x1536", "auto"}:
        return normalized
    return "1024x1024"



def _model_supports_chat_image_generation(model: str) -> bool:
    normalized = model.strip()
    if not normalized:
        return False
    return any(pattern.search(normalized) for pattern in CHAT_IMAGE_GENERATION_MODEL_HINTS)

