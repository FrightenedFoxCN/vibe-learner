from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.models.domain import ModelToolConfigRecord
from app.services.local_store import LocalJsonStore

PLAN_STAGE = "plan_generation"
CHAT_STAGE = "study_chat"

TOOL_CATALOG: dict[str, dict[str, dict[str, str]]] = {
    PLAN_STAGE: {
        "get_study_unit_detail": {
            "label": "学习单元详情",
            "description": "读取单个学习单元的细节结构与切块摘录，用于精细规划。",
            "category": "planning",
            "category_label": "规划分析",
        },
        "ask_planning_question": {
            "label": "计划澄清提问",
            "description": "在目标或边界不清时，向学习者提出一个具体确认问题，并保留保守假设。",
            "category": "planning",
            "category_label": "规划分析",
        },
        "estimate_plan_completion": {
            "label": "计划完成度评估",
            "description": "根据当前学习单元与目录细度估计计划完成度，判断是否还需要继续打磨。",
            "category": "planning",
            "category_label": "规划分析",
        },
        "revise_study_units": {
            "label": "学习单元重编排",
            "description": "在章节切分明显错误时，允许模型重写完整学习单元列表。",
            "category": "planning",
            "category_label": "规划分析",
        },
        "read_page_range_content": {
            "label": "页范围文本读取",
            "description": "读取教材页范围文本，补充计划生成需要的上下文细节。",
            "category": "sensory",
            "category_label": "感官工具",
        },
        "read_page_range_images": {
            "label": "页范围图像读取",
            "description": "渲染教材页图像，用于公式、图表、版式等视觉线索判断。",
            "category": "sensory",
            "category_label": "感官工具",
        },
    },
    CHAT_STAGE: {
        "ask_multiple_choice_question": {
            "label": "选择题生成",
            "description": "生成章节上下文驱动的选择题。",
            "category": "assessment",
            "category_label": "练习评测",
        },
        "ask_fill_blank_question": {
            "label": "填空题生成",
            "description": "生成章节上下文驱动的填空题。",
            "category": "assessment",
            "category_label": "练习评测",
        },
        "retrieve_memory_context": {
            "label": "跨会话记忆检索",
            "description": "读取历史学习片段，为当前回答补充长期记忆。",
            "category": "memory",
            "category_label": "记忆工具",
        },
        "read_learning_plan_progress": {
            "label": "计划进度读取",
            "description": "读取当前学习计划的整体完成度、章节完成度、排期状态和待补充规划问题。",
            "category": "planning",
            "category_label": "计划工具",
        },
        "update_learning_plan_progress": {
            "label": "计划进度更新",
            "description": "更新当前学习计划的排期项状态；既可按 schedule_id，也可按章节对应的 unit_id 批量更新。",
            "category": "planning",
            "category_label": "计划工具",
        },
        "read_page_range_content": {
            "label": "页范围文本读取",
            "description": "读取教材页范围文本，增强章节讲解的教材依据。",
            "category": "sensory",
            "category_label": "感官工具",
        },
        "read_page_range_images": {
            "label": "页范围图像读取",
            "description": "渲染教材页图像，辅助解释公式、图表与布局细节。",
            "category": "sensory",
            "category_label": "感官工具",
        },
        "read_scene_overview": {
            "label": "会话场景读取",
            "description": "读取当前会话绑定场景的整体状态、路径与物体信息。",
            "category": "scene",
            "category_label": "场景工具",
        },
        "add_scene": {
            "label": "新增场景",
            "description": "在当前会话绑定场景中新增一个子场景并切换过去。",
            "category": "scene",
            "category_label": "场景工具",
        },
        "move_to_scene": {
            "label": "转移至场景",
            "description": "将当前会话焦点转移到绑定场景树中的另一处。",
            "category": "scene",
            "category_label": "场景工具",
        },
        "add_object": {
            "label": "新增物体",
            "description": "向当前场景或指定场景加入新的物体。",
            "category": "scene",
            "category_label": "场景工具",
        },
        "update_object_description": {
            "label": "修改物体描述",
            "description": "更新当前会话场景内某个物体的描述。",
            "category": "scene",
            "category_label": "场景工具",
        },
        "delete_object": {
            "label": "删除物体",
            "description": "从当前会话绑定场景中删除一个物体。",
            "category": "scene",
            "category_label": "场景工具",
        },
    },
}

STAGE_META: dict[str, dict[str, str]] = {
    PLAN_STAGE: {
        "label": "学习计划阶段",
        "description": "学习计划生成过程中的模型工具调用能力。",
    },
    CHAT_STAGE: {
        "label": "章节对话阶段",
        "description": "章节对话过程中，模型可调用的检索与练习工具。",
    },
}


class ModelToolConfigService:
    def __init__(self, store: LocalJsonStore) -> None:
        self._store = store
        self._record = self._load_or_default()

    def list_stage_names(self) -> list[str]:
        return list(TOOL_CATALOG.keys())

    def list_stage_tools(self, stage_name: str) -> list[str]:
        return list(TOOL_CATALOG.get(stage_name, {}).keys())

    def is_enabled(self, *, stage_name: str, tool_name: str) -> bool:
        if tool_name not in TOOL_CATALOG.get(stage_name, {}):
            return False
        stage_settings = self._record.stage_tool_enabled.get(stage_name, {})
        return bool(stage_settings.get(tool_name, True))

    def disabled_tools_for_stage(self, stage_name: str) -> set[str]:
        return {
            tool_name
            for tool_name in self.list_stage_tools(stage_name)
            if not self.is_enabled(stage_name=stage_name, tool_name=tool_name)
        }

    def describe(self) -> dict[str, Any]:
        stages: list[dict[str, Any]] = []
        for stage_name in self.list_stage_names():
            stage_tools = TOOL_CATALOG.get(stage_name, {})
            tools_payload: list[dict[str, Any]] = []
            for tool_name, meta in stage_tools.items():
                tools_payload.append(
                    {
                        "name": tool_name,
                        "label": meta["label"],
                        "description": meta["description"],
                        "category": meta["category"],
                        "category_label": meta["category_label"],
                        "enabled": self.is_enabled(stage_name=stage_name, tool_name=tool_name),
                    }
                )
            stage_meta = STAGE_META.get(stage_name, {})
            stages.append(
                {
                    "name": stage_name,
                    "label": stage_meta.get("label", stage_name),
                    "description": stage_meta.get("description", ""),
                    "tools": tools_payload,
                }
            )
        return {
            "updated_at": self._record.updated_at,
            "stages": stages,
        }

    def update(self, updates: list[dict[str, Any]]) -> ModelToolConfigRecord:
        next_stage_map = {
            key: dict(value) for key, value in self._record.stage_tool_enabled.items()
        }

        for item in updates:
            stage_name = str(item.get("stage_name") or "").strip()
            tool_name = str(item.get("tool_name") or "").strip()
            enabled = item.get("enabled")
            if not stage_name or not tool_name or not isinstance(enabled, bool):
                raise ValueError("invalid_tool_toggle")
            if stage_name not in TOOL_CATALOG:
                raise ValueError(f"unknown_stage:{stage_name}")
            if tool_name not in TOOL_CATALOG[stage_name]:
                raise ValueError(f"unknown_tool:{stage_name}:{tool_name}")
            stage_settings = next_stage_map.get(stage_name, {})
            stage_settings[tool_name] = enabled
            next_stage_map[stage_name] = stage_settings

        self._record = ModelToolConfigRecord(
            config_id="default",
            updated_at=_now_iso(),
            stage_tool_enabled=next_stage_map,
        )
        self._store.save_item("model_tool_config", "default", self._record)
        return self._record

    def _load_or_default(self) -> ModelToolConfigRecord:
        existing = self._store.load_item("model_tool_config", "default", ModelToolConfigRecord)
        if existing is not None:
            return existing
        record = ModelToolConfigRecord(
            config_id="default",
            updated_at=_now_iso(),
            stage_tool_enabled={},
        )
        self._store.save_item("model_tool_config", "default", record)
        return record


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
