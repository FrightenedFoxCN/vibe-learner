from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.models.domain import ModelToolConfigRecord
from app.models.harness import HarnessStage, HarnessWorkflow
from app.models.tool_manifest import resolve_tool_manifest_entry
from app.services.local_store import LocalJsonStore

PLAN_STAGE = "plan_generation"
CHAT_STAGE = "study_chat"

_TOOL_UI_CATALOG: dict[str, dict[str, dict[str, str]]] = {
    PLAN_STAGE: {
        "get_study_unit_detail": {
            "label": "学习单元详情",
            "category": "planning",
            "category_label": "规划分析",
        },
        "ask_planning_question": {
            "label": "计划澄清提问",
            "category": "planning",
            "category_label": "规划分析",
        },
        "estimate_plan_completion": {
            "label": "学习单元结构估分",
            "category": "planning",
            "category_label": "规划分析",
        },
        "revise_study_units": {
            "label": "学习单元重编排",
            "category": "planning",
            "category_label": "规划分析",
        },
        "read_page_range_content": {
            "label": "页范围文本读取",
            "category": "sensory",
            "category_label": "感官工具",
        },
        "read_page_range_images": {
            "label": "页范围图像读取",
            "category": "sensory",
            "category_label": "感官工具",
        },
    },
    CHAT_STAGE: {
        "ask_multiple_choice_question": {
            "label": "选择题生成",
            "category": "assessment",
            "category_label": "练习评测",
        },
        "ask_fill_blank_question": {
            "label": "填空题生成",
            "category": "assessment",
            "category_label": "练习评测",
        },
        "retrieve_memory_context": {
            "label": "跨会话记忆检索",
            "category": "memory",
            "category_label": "记忆工具",
        },
        "read_session_memory": {
            "label": "临时记忆读取",
            "category": "memory",
            "category_label": "记忆工具",
        },
        "write_session_memory": {
            "label": "临时记忆写入",
            "category": "memory",
            "category_label": "记忆工具",
        },
        "read_system_time": {
            "label": "系统时间读取",
            "category": "session",
            "category_label": "会话工具",
        },
        "schedule_session_follow_up": {
            "label": "自动续接调度",
            "category": "session",
            "category_label": "会话工具",
        },
        "read_affinity_state": {
            "label": "好感度读取",
            "category": "relationship",
            "category_label": "关系工具",
        },
        "update_affinity_state": {
            "label": "好感度更新",
            "category": "relationship",
            "category_label": "关系工具",
        },
        "read_learning_plan_progress": {
            "label": "计划进度读取",
            "category": "planning",
            "category_label": "计划工具",
        },
        "update_learning_plan": {
            "label": "计划修改提案",
            "category": "planning",
            "category_label": "计划工具",
        },
        "update_learning_plan_progress": {
            "label": "计划进度更新",
            "category": "planning",
            "category_label": "计划工具",
        },
        "read_page_range_content": {
            "label": "页范围文本读取",
            "category": "sensory",
            "category_label": "感官工具",
        },
        "read_page_range_images": {
            "label": "页范围图像读取",
            "category": "sensory",
            "category_label": "感官工具",
        },
        "project_uploaded_pdf": {
            "label": "投射上传 PDF",
            "category": "sensory",
            "category_label": "感官工具",
        },
        "project_uploaded_image": {
            "label": "投射上传图片",
            "category": "sensory",
            "category_label": "感官工具",
        },
        "generate_projected_image": {
            "label": "生成并投射图片",
            "category": "sensory",
            "category_label": "感官工具",
        },
        "read_projected_pdf_content": {
            "label": "投射 PDF 文本读取",
            "category": "sensory",
            "category_label": "感官工具",
        },
        "read_projected_pdf_images": {
            "label": "投射 PDF 图像读取",
            "category": "sensory",
            "category_label": "感官工具",
        },
        "read_projected_pdf_layout_candidates": {
            "label": "投射 PDF 图形候选",
            "category": "sensory",
            "category_label": "感官工具",
        },
        "focus_projected_pdf_page": {
            "label": "投射 PDF 切页",
            "category": "sensory",
            "category_label": "感官工具",
        },
        "highlight_projected_pdf_text": {
            "label": "投射 PDF 文字高亮",
            "category": "sensory",
            "category_label": "感官工具",
        },
        "annotate_projected_pdf_region": {
            "label": "投射 PDF 区域框选",
            "category": "sensory",
            "category_label": "感官工具",
        },
        "clear_projected_pdf_overlays": {
            "label": "清空投射 PDF 标注",
            "category": "sensory",
            "category_label": "感官工具",
        },
        "annotate_projected_image_region": {
            "label": "投射图片区域框选",
            "category": "sensory",
            "category_label": "感官工具",
        },
        "clear_projected_image_overlays": {
            "label": "清空投射图片标注",
            "category": "sensory",
            "category_label": "感官工具",
        },
        "read_scene_overview": {
            "label": "会话场景读取",
            "category": "scene",
            "category_label": "场景工具",
        },
        "add_scene": {
            "label": "新增场景",
            "category": "scene",
            "category_label": "场景工具",
        },
        "move_to_scene": {
            "label": "转移至场景",
            "category": "scene",
            "category_label": "场景工具",
        },
        "add_object": {
            "label": "新增物体",
            "category": "scene",
            "category_label": "场景工具",
        },
        "update_object_description": {
            "label": "修改物体描述",
            "category": "scene",
            "category_label": "场景工具",
        },
        "delete_object": {
            "label": "删除物体",
            "category": "scene",
            "category_label": "场景工具",
        },
    },
}

# Provider descriptions have one authority; UI metadata must not fork them.
TOOL_CATALOG = {
    stage: {
        name: {
            **metadata,
            "description": resolve_tool_manifest_entry(
                workflow=(HarnessWorkflow.PLANNING if stage == PLAN_STAGE else HarnessWorkflow.STUDY_CHAT),
                offered_in_stage=(HarnessStage.PLAN_GENERATION if stage == PLAN_STAGE else HarnessStage.STUDY_CHAT_REPLY),
                transport_name=name,
            ).display.provider_description,
        }
        for name, metadata in entries.items()
    }
    for stage, entries in _TOOL_UI_CATALOG.items()
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
