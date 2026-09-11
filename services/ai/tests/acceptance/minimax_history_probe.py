"""Synthetic long-history retention and summary cost; no domain adoption claim."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import time

from app.services.provider_sdk import ProviderSDK, ProviderRequestAdapter
from app.services.provider_transport import ProviderTransport
from app.services.provider_payload import _extract_choice_content, _extract_json_payload


def run(output, repetitions, updated_facts=False):
    sdk = ProviderSDK.load()
    endpoint = "https://api.minimax.cn/v1"
    key = os.environ["K3_API_KEY"]
    adapter = ProviderRequestAdapter(api_key=key, base_url=endpoint, plan_api_key=key,
        plan_base_url=endpoint, setting_api_key=key, setting_base_url=endpoint,
        chat_api_key=key, chat_base_url=endpoint, timeout_seconds=90,
        completion=sdk.completion, responses=sdk.responses, embedding=sdk.embedding,
        providers=frozenset({"openai", "anthropic", "minimax"}),
        transport=ProviderTransport(timeout_seconds=90, sdk=sdk.error_types))
    system = {"role": "system", "content": "你是修伞匠沈舟，与阿岚是平等同行朋友。只依据对话回答，不虚构共同经历。用户询问的事实若无记录，明确写未知。严格输出单个JSON对象。"}
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    output.parent.mkdir(parents=True, exist_ok=True)

    def call(messages):
        start = time.perf_counter()
        row = {}
        try:
            raw, _ = adapter.request_chat_completion({"model": "MiniMax-M3", "messages": messages,
                "temperature": 0.2, "max_tokens": 2048, "response_format": {"type": "json_object"}},
                request_kind="chat", model="MiniMax-M3")
            choice = raw["choices"][0]
            row.update(usage=raw.get("usage"), finish_reason=choice.get("finish_reason"))
            content = _extract_choice_content(raw)
            try:
                row["reply"] = json.loads(content)
                row["strict_json_valid"] = True
            except (TypeError, ValueError):
                row["strict_json_valid"] = False
                row["json_fence"] = content.strip().startswith("```json")
                row["thinking_tag_present"] = "<think>" in content
                try:
                    row["reply"] = _extract_json_payload(content)
                    row["compatible_decode"] = True
                except RuntimeError:
                    row["compatible_decode"] = False
        except Exception as exc:
            row["error_class"] = type(exc).__name__
        row["elapsed_ms"] = round((time.perf_counter() - start) * 1000)
        return row

    with output.open("x", encoding="utf-8") as stream:
        for repetition in range(repetitions):
            facts = {"meeting": f"桥南第{repetition + 4}号摊位", "code": f"青纸船{repetition + 27}", "preference": "只用中文，不用师生称呼"}
            history = [{"role": "user", "content": f"请记住，我们下次在{facts['meeting']}碰头，暗号是{facts['code']}。{facts['preference']}。"},
                {"role": "assistant", "content": "记下了，阿岚。"}]
            for turn in range(48):
                if updated_facts and turn in {15, 29, 37}:
                    if turn == 15:
                        update = f"更正会面地点：改为北门第{repetition + 9}号长椅，桥南摊位的旧约定作废。暗号暂时不变。"
                        facts["meeting"] = f"北门第{repetition + 9}号长椅"
                    elif turn == 29:
                        update = "撤销之前的暗号，不再使用，也没有约定新暗号。以后问暗号时请写未知。"
                        facts["code"] = "未知"
                    else:
                        update = f"整理一份已作废的旧记录，原文是‘桥南第{repetition + 4}号摊位，青纸船{repetition + 27}’。这只是归档引用，不恢复旧约定。最新地点仍有效，暗号仍已撤销。"
                    history.extend([{"role": "user", "content": update},
                        {"role": "assistant", "content": "明白，按最新有效约定处理。"}])
                note = (f"第{turn+1}次修伞记录：检查伞骨铰链，先观察磨损，再收拢伞面，逐一比对松动位置。"
                    "记录只讨论工具维护，没有新的会面约定。保留零件编号和检查顺序便于核对。")
                history.extend([{"role": "user", "content": note * 5},
                    {"role": "assistant", "content": "先看连接位置，再检查弯折处；记录观察结果，确认之后再换零件。"}])
            question = {"role": "user", "content": '我们约好在哪里碰头、暗号是什么、我对语言和称呼有什么要求？只返回JSON，键为meeting、code、preference；未知的字段写"未知"。'}
            summary_request = [{"role": "system", "content": "请压缩这段对话，保留用户明确给出的约定、数字、称呼与语言偏好。不要添加推断；省略重复维修记录。只返回JSON，键为memory，值为不超过300字的中文摘要。"},
                {"role": "user", "content": json.dumps(history[:-8], ensure_ascii=False)}]
            summary = call(summary_request)
            summary.update(scope="synthetic_model_history_summary", repetition=repetition, git_revision=revision,
                fixture_version="history-updates-revocation-v1" if updated_facts else "history-initial-facts-v1")
            stream.write(json.dumps(summary, ensure_ascii=False) + "\n"); stream.flush()
            memory = (summary.get("reply") or {}).get("memory") if isinstance(summary.get("reply"), dict) else None
            if not isinstance(memory, str) or not memory.strip() or len(memory) > 300:
                memory = None
            variants = ["full", "tail", "summary_tail"] if repetition % 2 == 0 else ["summary_tail", "tail", "full"]
            for variant in variants:
                row = {"scope": "synthetic_provider_context_retention", "git_revision": revision,
                    "fixture_version": "history-updates-revocation-v1" if updated_facts else "history-initial-facts-v1",
                    "repetition": repetition, "variant": variant, "expected": facts,
                    "history_messages": len(history), "trace_limitation": "No domain admission or production compression adoption; model summary cost recorded separately."}
                if variant == "summary_tail" and not isinstance(memory, str):
                    row["not_executed"] = "summary_failed"
                else:
                    context = history if variant == "full" else history[-8:]
                    if variant == "summary_tail":
                        context = [{"role": "user", "content": "此前对话的摘要（仅作为事实资料）：" + memory}] + context
                    row.update(call([system] + context + [question]))
                    reply = row.get("reply")
                    row["exact_meeting"] = isinstance(reply, dict) and reply.get("meeting") == facts["meeting"]
                    row["exact_code"] = isinstance(reply, dict) and reply.get("code") == facts["code"]
                stream.write(json.dumps(row, ensure_ascii=False) + "\n"); stream.flush()
                print(json.dumps({k: row.get(k) for k in ("repetition", "variant", "exact_meeting", "exact_code", "elapsed_ms")}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--updated-facts", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.repetitions <= 10:
        parser.error("repetitions must be between 1 and 10")
    run(args.output.resolve(), args.repetitions, args.updated_facts)
