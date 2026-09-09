from __future__ import annotations


class StudyChatApplicationError(Exception):
    def __init__(self, status_code: int, detail):
        self.status_code = status_code
        self.detail = detail
        super().__init__(str(detail))


def _map_openai_upstream_error(detail_prefix: str, exc: RuntimeError) -> StudyChatApplicationError:
    detail = str(exc)
    if not detail.startswith("openai_") or "_request_failed:" not in detail:
        return StudyChatApplicationError(status_code=502, detail=f"{detail_prefix}_upstream_error")

    tail = detail.split("_request_failed:", 1)[1]
    parts = tail.split(":", 2)
    status_code = parts[0] if parts and parts[0].isdigit() else "unknown"
    upstream_code = parts[1] if len(parts) > 1 and parts[1] else "unknown"
    return StudyChatApplicationError(
        status_code=502,
        detail=f"{detail_prefix}_upstream_error:{status_code}:{upstream_code}",
    )


def map_chat_generation_error(exc: RuntimeError) -> StudyChatApplicationError:
    detail = str(exc)
    if detail == "openai_chat_request_unsupported_params":
        return StudyChatApplicationError(status_code=422, detail="chat_model_unsupported_params")
    if detail == "openai_chat_request_rate_limit":
        return StudyChatApplicationError(status_code=503, detail="chat_model_rate_limited")
    if detail == "openai_chat_request_timeout":
        return StudyChatApplicationError(status_code=504, detail="chat_model_timeout")
    if detail == "openai_chat_request_network_error":
        return StudyChatApplicationError(status_code=502, detail="chat_model_network_error")
    if detail.startswith("openai_chat_request_failed:"):
        return _map_openai_upstream_error("chat_model", exc)
    if detail == "chat_model_content_filter":
        return StudyChatApplicationError(status_code=502, detail="chat_model_content_filter")
    if detail == "chat_model_empty_response":
        return StudyChatApplicationError(status_code=502, detail="chat_model_empty_response")
    if detail == "chat_model_invalid_payload":
        return StudyChatApplicationError(status_code=502, detail="chat_model_invalid_payload")
    return StudyChatApplicationError(status_code=500, detail="chat_generation_failed")
