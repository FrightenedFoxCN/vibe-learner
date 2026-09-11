"""Opt-in M3 transcription diagnostic; source text stays outside repository evidence."""
import argparse
import base64
import json
import os
from pathlib import Path
import re
import subprocess
from unittest.mock import patch

import fitz
import httpx
from pydantic import BaseModel, ConfigDict, Field, StrictStr, ValidationError

from app.services.provider_sdk import ProviderRequestAdapter, ProviderSDK
from app.services.provider_transport import ProviderTransport


class Transcription(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    blocks: list[StrictStr] = Field(min_length=1, max_length=80)


def run(pdf_path, output, repetitions, reasoning_split=False, max_tokens=6400, thinking=None):
    output.mkdir(parents=True, exist_ok=False)
    key = os.environ["K3_API_KEY"]
    endpoint = "https://api.minimax.cn/v1"
    sdk = ProviderSDK.load()
    adapter = ProviderRequestAdapter(
        api_key=key, base_url=endpoint, plan_api_key=key, plan_base_url=endpoint,
        setting_api_key=key, setting_base_url=endpoint, chat_api_key=key, chat_base_url=endpoint,
        timeout_seconds=90, completion=sdk.completion, responses=sdk.responses,
        embedding=sdk.embedding, providers=frozenset({"openai", "anthropic", "minimax"}),
        transport=ProviderTransport(timeout_seconds=90, sdk=sdk.error_types),
    )
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    with fitz.open(pdf_path) as pdf:
        page = pdf[0]
        midpoint = (page.rect.x0 + page.rect.x1) / 2
        clips = [None, fitz.Rect(page.rect.x0, page.rect.y0, midpoint, page.rect.y1),
                 fitz.Rect(midpoint, page.rect.y0, page.rect.x1, page.rect.y1)]
        images = [base64.b64encode(page.get_pixmap(dpi=100, clip=clip).tobytes("png")).decode("ascii") for clip in clips]
    instruction = (
        "逐字转写图片中的可见正文和脚注，保持原文语言，不翻译、不总结、不解释、不补写背景知识。"
        "按从左到右、页内从上到下的阅读顺序保留段落；不确定的字用[无法辨认]标记。"
        "若收到同一页的局部裁剪，只用于核对，最终内容不要重复转写。"
        "严格返回一个JSON对象，只有blocks字段，值为按顺序排列的段落字符串数组。"
    )
    with (output / "report.jsonl").open("x") as report:
        for repetition in range(repetitions):
            modes = ("original", "original_crops") if repetition % 2 == 0 else ("original_crops", "original")
            for mode in modes:
                selected = images if mode == "original_crops" else images[:1]
                parts = [{"type": "text", "text": "以下是同一PDF物理页的原图，后续图片（若有）依次为其左半与右半："}]
                parts += [{"type": "image_url", "image_url": {"url": "data:image/png;base64," + data}} for data in selected]
                row = {"scope": "Direct provider transcription diagnostic, not admitted Document/OCR Harness execution",
                       "model": "MiniMax-M3", "git_revision": revision, "mode": mode, "repetition": repetition,
                       "image_count": len(selected), "image_dpi": 100, "strict_decode_success": False,
                       "reasoning_split": reasoning_split, "max_tokens": max_tokens,
                       "thinking": thinking or "default_adaptive", "wire_requests": []}
                try:
                    payload = {"model": "MiniMax-M3",
                        "messages": [{"role": "system", "content": instruction}, {"role": "user", "content": parts}],
                        "max_tokens": max_tokens, "reasoning_split": reasoning_split,
                        "response_format": {"type": "json_object"}}
                    if thinking:
                        payload["extra_body"] = {"thinking": {"type": thinking}}
                    original_send = httpx.Client.send

                    def observe_wire(client, request, *args, **kwargs):
                        if request.url.host == "api.minimax.cn":
                            body = json.loads(request.content)
                            row["wire_requests"].append({"thinking_type": (body.get("thinking") or {}).get("type"),
                                "reasoning_split": body.get("reasoning_split"), "max_tokens": body.get("max_tokens"),
                                "max_completion_tokens": body.get("max_completion_tokens")})
                        return original_send(client, request, *args, **kwargs)

                    with patch.object(httpx.Client, "send", observe_wire):
                        raw, elapsed = adapter.request_chat_completion(payload, request_kind="chat", model="MiniMax-M3")
                    choice = raw["choices"][0]
                    row.update(usage=raw.get("usage"), elapsed_ms=elapsed, finish_reason=choice.get("finish_reason"))
                    content = choice["message"].get("content") or ""
                    row["content_characters"] = len(content)
                    row["content_has_think_tag"] = "<think>" in content
                    row["content_has_json_fence"] = content.strip().startswith("```json")
                    # Local-only final output for diagnosis, only when the
                    # explicit non-thinking request and response agree.
                    reasoning_tokens = ((raw.get("usage") or {}).get("completion_tokens_details") or {}).get("reasoning_tokens")
                    if thinking == "disabled" and reasoning_split and reasoning_tokens == 0 and not row["content_has_think_tag"]:
                        (output / f"{repetition}-{mode}-private-final.txt").write_text(content)
                    parsed = Transcription.model_validate_json(choice["message"]["content"], strict=True)
                    text = "\n\n".join(parsed.blocks)
                    (output / f"{repetition}-{mode}-private-transcription.txt").write_text(text)
                    compact = re.sub(r"\s+", "", text)
                    row.update(strict_decode_success=True, block_count=len(parsed.blocks), characters=len(text),
                               han_characters=sum("\u4e00" <= c <= "\u9fff" for c in text),
                               uncertainty_markers=text.count("[无法辨认]"),
                               diagnostic_source_affirmation_present="不只是具有1930年的感觉" in compact,
                               diagnostic_unsupported_negation_present="不可能具有1930" in compact)
                except Exception as exc:
                    row["error_class"] = type(exc).__name__
                    if isinstance(exc, ValidationError):
                        row["validation_errors"] = [{"type": e['type'], "path": [
                            p if isinstance(p, int) or p == 'blocks' else '<unexpected_field>' for p in e['loc']]}
                            for e in exc.errors(include_input=False)[:8]]
                row["limitations"] = "Book transcription stored only in local probe output, not evidence; phrase checks are diagnostics, not full OCR correctness. Reasoning is not retained."
                report.write(json.dumps(row, ensure_ascii=False) + "\n")
                report.flush()
                print(json.dumps(row, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repetitions", type=int, default=2)
    parser.add_argument("--reasoning-split", action="store_true")
    parser.add_argument("--max-tokens", type=int, default=6400)
    parser.add_argument("--thinking", choices=("adaptive", "disabled"))
    args = parser.parse_args()
    if not 1 <= args.repetitions <= 20:
        parser.error("repetitions must be between 1 and 20")
    if not 1024 <= args.max_tokens <= 32768:
        parser.error("max-tokens must be between 1024 and 32768")
    run(args.pdf.resolve(), args.output.resolve(), args.repetitions, args.reasoning_split, args.max_tokens, args.thinking)
