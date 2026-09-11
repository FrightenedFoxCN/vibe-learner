"""Paired synthetic setting prompt experiments via the production SDK/decoder.

No domain admission/trace is fabricated for experimental prompts. Persisted
domain validation follows only after a candidate has been reviewed and adopted.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import time

from app.services.model_provider import OpenAIModelProvider
from app.services.provider_settings import RemoteSettingsProvider


RELATIONSHIP_RULE = """
人际关系约束适用于 summary、relationship、learner_address 和每一张卡片的全部文字。
导学是能力，不是身份关系：必须沿用输入指定的伙伴、同事、亲属或师生关系与称呼；不能因本产品支持学习就自动把用户叫作学生、学员或晚辈。
未指定关系时使用中性的“用户”；不能从职业相同或一起旅行擅自推导用户的职业、共同经历或年龄。
如需描述解释与反馈，用用户的实际称呼或“对方”，并在所有卡片中保持一致。不要一张卡片说平等合作者，另一张卡片又说给学生讲课。
"""

SCENE_CONCISION_RULE = """
先满足输入明确给出的全部区域、物体和否定约束，再用简洁字段完整表达空间树。
不要为凑深度添加用户未要求的地点。每个空间只描述其区别于父空间的特征，避免在 summary、atmosphere、rules 和 reuse_hint 重复同一件事。
短输入的每个描述字段通常用一句话、约 20–50 个汉字；source 中有更多明确细节时优先保留细节，不机械截断。tags 通常 1–3 项。
用户只要求少量空间时，物体仅保留明确指定或理解空间必需的设施，避免大量装饰品与冗长来历。输出完整闭合的 JSON，不能省略 schema 的必填字段。
"""

CASES = {
    "persona": [
        ("research", "long_text", "角色林澈是植物学研究员。用户是合作研究者，称小顾，不是学生、学员或亲属。讲事实时区分观察和猜测。"),
        ("travel", "keywords", "沈舟，温厚的修伞匠；用户是旅途中结识的朋友，称阿岚，用户职业未知。不编造共同往事。"),
        ("peer", "long_text", "角色方宁是软件工程师。用户是平级设计师同事，称小周；双方平等，不是老师与学生。讨论问题先交换假设再查证。"),
        ("sibling", "keywords", "角色许夏是医生，用户是成年姐姐，称姐，不是患者或学生；温和但说话利落。不因职业改变既定亲属关系。"),
    ],
    "scene": [
        ("tea", "keywords", "山间茶馆，包含茶室与檐下两个区域。无电器，无魔法，不含人物已发生的行为。用简洁中文。"),
        ("observatory", "long_text", "深夜天文台只有观测室与资料室。观测室有光学望远镜和红色弱光灯，资料室有星图。窗外阴天，不能直接看见星星。不要添加地下层或第三个空间。"),
        ("workshop", "long_text", "修伞作坊只有前屋与后院。前屋有工作台、伞骨和棉线，后院有晾晒绳。停电，禁止添加正在工作的电器。只包含上述两个区域，保留全部物品。"),
    ],
}


def run(domain, repetitions, output):
    provider = OpenAIModelProvider(api_key=os.environ["K3_API_KEY"],
        base_url="https://api.minimax.cn/v1", plan_model="MiniMax-M3",
        setting_model="MiniMax-M3", setting_web_search_enabled=False,
        setting_max_tokens=4096, timeout_seconds=90)
    adapter = provider._sdk_adapter()
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    rule = RELATIONSHIP_RULE if domain == "persona" else SCENE_CONCISION_RULE
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        for repetition in range(repetitions):
            for index, (case_id, mode, source) in enumerate(CASES[domain]):
                for candidate in ([False, True] if (index+repetition) % 2 else [True, False]):
                    calls = []

                    def request(payload, *, request_kind, model):
                        outgoing = dict(payload)
                        if candidate:
                            outgoing["messages"] = [dict(m) for m in outgoing["messages"]]
                            outgoing["messages"][0]["content"] += "\n" + rule
                        started = time.perf_counter()
                        call = {"max_tokens": outgoing.get("max_tokens")}
                        calls.append(call)
                        try:
                            raw, elapsed = adapter.request_chat_completion(outgoing, request_kind=request_kind, model=model)
                            choices = raw.get("choices", [])
                            call.update(usage=raw.get("usage"), finish_reason=choices[0].get("finish_reason") if choices else None)
                            content = choices[0].get("message", {}).get("content", "") if choices else ""
                            try:
                                value = json.loads(content)
                                if isinstance(value, dict):
                                    call["candidate_json"] = value
                            except (TypeError, ValueError):
                                call["candidate_json_valid"] = False
                            return raw, elapsed
                        except Exception as exc:
                            call["error_class"] = type(exc).__name__
                            raise
                        finally:
                            call["elapsed_ms"] = round((time.perf_counter()-started)*1000)

                    def unavailable(*args, **kwargs):
                        raise RuntimeError("web_search_not_enabled_for_probe")

                    remote = RemoteSettingsProvider("MiniMax-M3", 0.4, 4096, False, request, unavailable)
                    row = {"scope": "sdk_prompt_decoder_experiment_no_admission", "git_revision": revision,
                        "fixture_version": "setting-comparison-v1", "domain": domain, "case_id": case_id,
                        "mode": mode, "source": source, "repetition": repetition,
                        "candidate": domain + "-constraint-v1" if candidate else None,
                        "model": "MiniMax-M3", "temperature": 0.4, "calls": calls}
                    try:
                        if domain == "persona":
                            result = remote.generate_persona_cards_from_keywords(keywords=source, count=3) if mode == "keywords" else remote.generate_persona_cards_from_text(text=source, count=3)
                        else:
                            result = remote.generate_scene_tree_from_keywords(keywords=source, layer_count=2) if mode == "keywords" else remote.generate_scene_tree_from_text(text=source, layer_count=2)
                        row.update(success=True, result=result)
                    except Exception as exc:
                        row.update(success=False, error_class=type(exc).__name__)
                        if isinstance(exc, RuntimeError) and str(exc).startswith("setting_"):
                            row["error_code"] = str(exc)
                    stream.write(json.dumps(row, ensure_ascii=False) + "\n")
                    stream.flush()
                    print(json.dumps({k: row[k] for k in ("case_id", "candidate", "success", "repetition")}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--domain", choices=CASES, required=True)
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not 1 <= args.repetitions <= 30:
        parser.error("repetitions must be between 1 and 30")
    run(args.domain, args.repetitions, args.output)
