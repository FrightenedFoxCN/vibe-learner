from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from fastapi import HTTPException

from app.models.domain import (
    SceneLayerStateRecord,
    SceneObjectStateRecord,
    SceneProfileRecord,
    SessionSceneRecord,
)
from app.services.local_store import LocalJsonStore
from app.services.model_tool_config import CHAT_STAGE, TOOL_CATALOG


SCENE_TOOL_NAMES = (
    "read_scene_overview",
    "add_scene",
    "move_to_scene",
    "add_object",
    "update_object_description",
    "delete_object",
)


class SessionSceneToolRuntime:
    def __init__(self, service: "SessionSceneService", scene_instance_id: str) -> None:
        self._service = service
        self.scene_instance_id = scene_instance_id

    def scene_context(self) -> str:
        record = self._service.require_scene(self.scene_instance_id)
        selected = _find_layer(record.scene_layers, record.selected_layer_id)
        selected_layer = selected[0] if selected else None
        selected_path = selected[1] if selected else []
        object_names = ", ".join(obj.name for obj in (selected_layer.objects[:4] if selected_layer else []))
        return (
            f"场景名：{record.scene_name or '未命名场景'}\n"
            f"场景摘要：{record.scene_summary or '无'}\n"
            f"当前场景路径：{' / '.join(selected_path) or '无'}\n"
            f"当前场景标题：{selected_layer.title if selected_layer else '无'}\n"
            f"可见物体：{object_names or '无'}\n"
            f"根场景数量：{len(record.scene_layers)}"
        )

    def tool_specs(self) -> list[dict[str, object]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "read_scene_overview",
                    "description": TOOL_CATALOG[CHAT_STAGE]["read_scene_overview"]["description"],
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "additionalProperties": False,
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "add_scene",
                    "description": TOOL_CATALOG[CHAT_STAGE]["add_scene"]["description"],
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "parent_scene_id": {
                                "type": "string",
                                "description": "可选。父场景 ID，默认使用当前选中的场景。",
                            },
                            "title": {"type": "string", "description": "新场景标题。"},
                            "scope_label": {"type": "string", "description": "场景层级或范围标签，例如 room、zone。"},
                            "summary": {"type": "string", "description": "新场景的简短摘要。"},
                            "atmosphere": {"type": "string", "description": "场景氛围。"},
                            "rules": {"type": "string", "description": "该场景下的重要规则或限制。"},
                            "entrance": {"type": "string", "description": "进入该场景的入口描述。"},
                        },
                        "required": ["title", "scope_label"],
                        "additionalProperties": False,
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "move_to_scene",
                    "description": TOOL_CATALOG[CHAT_STAGE]["move_to_scene"]["description"],
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "scene_id": {"type": "string", "description": "目标场景 ID。"},
                        },
                        "required": ["scene_id"],
                        "additionalProperties": False,
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "add_object",
                    "description": TOOL_CATALOG[CHAT_STAGE]["add_object"]["description"],
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "scene_id": {
                                "type": "string",
                                "description": "可选。目标场景 ID，默认使用当前选中的场景。",
                            },
                            "name": {"type": "string", "description": "新物体名称。"},
                            "description": {"type": "string", "description": "物体描述。"},
                            "interaction": {"type": "string", "description": "该物体可触发的互动方式。"},
                            "tags": {"type": "string", "description": "逗号分隔的标签字符串。"},
                        },
                        "required": ["name"],
                        "additionalProperties": False,
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "update_object_description",
                    "description": TOOL_CATALOG[CHAT_STAGE]["update_object_description"]["description"],
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "object_id": {"type": "string", "description": "需要更新的物体 ID。"},
                            "description": {"type": "string", "description": "新的物体描述。"},
                        },
                        "required": ["object_id", "description"],
                        "additionalProperties": False,
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "delete_object",
                    "description": TOOL_CATALOG[CHAT_STAGE]["delete_object"]["description"],
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "object_id": {"type": "string", "description": "需要删除的物体 ID。"},
                        },
                        "required": ["object_id"],
                        "additionalProperties": False,
                    },
                },
            },
        ]

    def execute_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if tool_name == "read_scene_overview":
            return self._service.read_scene_overview(self.scene_instance_id)
        if tool_name == "add_scene":
            return self._service.add_scene(
                self.scene_instance_id,
                parent_scene_id=str(arguments.get("parent_scene_id") or "").strip(),
                title=str(arguments.get("title") or "").strip(),
                scope_label=str(arguments.get("scope_label") or "").strip(),
                summary=str(arguments.get("summary") or "").strip(),
                atmosphere=str(arguments.get("atmosphere") or "").strip(),
                rules=str(arguments.get("rules") or "").strip(),
                entrance=str(arguments.get("entrance") or "").strip(),
            )
        if tool_name == "move_to_scene":
            return self._service.move_to_scene(
                self.scene_instance_id,
                scene_id=str(arguments.get("scene_id") or "").strip(),
            )
        if tool_name == "add_object":
            return self._service.add_object(
                self.scene_instance_id,
                scene_id=str(arguments.get("scene_id") or "").strip(),
                name=str(arguments.get("name") or "").strip(),
                description=str(arguments.get("description") or "").strip(),
                interaction=str(arguments.get("interaction") or "").strip(),
                tags=str(arguments.get("tags") or "").strip(),
            )
        if tool_name == "update_object_description":
            return self._service.update_object_description(
                self.scene_instance_id,
                object_id=str(arguments.get("object_id") or "").strip(),
                description=str(arguments.get("description") or "").strip(),
            )
        if tool_name == "delete_object":
            return self._service.delete_object(
                self.scene_instance_id,
                object_id=str(arguments.get("object_id") or "").strip(),
            )
        raise HTTPException(status_code=400, detail="scene_tool_unknown")


class SessionSceneService:
    def __init__(self, store: LocalJsonStore) -> None:
        self._store = store

    def build_tool_runtime(self, scene_instance_id: str) -> SessionSceneToolRuntime:
        self.require_scene(scene_instance_id)
        return SessionSceneToolRuntime(self, scene_instance_id)

    def clone_scene_for_session(
        self,
        *,
        session_id: str,
        document_id: str,
        persona_id: str,
        scene_profile: SceneProfileRecord | None,
    ) -> SessionSceneRecord | None:
        if scene_profile is None:
            return None
        scene_layers = [node.model_copy(deep=True) for node in scene_profile.scene_tree]
        selected_layer_id = scene_profile.scene_id.strip() or (scene_layers[0].id if scene_layers else "")
        scene_name = scene_profile.scene_name.strip() or scene_profile.title.strip() or "未命名场景"
        scene_summary = scene_profile.summary.strip()
        record = SessionSceneRecord(
            scene_instance_id=f"session-scene-{uuid4().hex[:10]}",
            session_id=session_id,
            document_id=document_id,
            persona_id=persona_id,
            source_scene_id=scene_profile.scene_id,
            source_scene_name=scene_profile.scene_name,
            config_id=session_id,
            created_at=_now_iso(),
            updated_at=_now_iso(),
            scene_name=scene_name,
            scene_summary=scene_summary,
            scene_layers=scene_layers,
            selected_layer_id=selected_layer_id,
            collapsed_layer_ids=[],
            scene_profile=_build_scene_profile(
                scene_name=scene_name,
                scene_summary=scene_summary,
                scene_layers=scene_layers,
                selected_layer_id=selected_layer_id,
            ),
        )
        self._save(record)
        return record

    def require_scene(self, scene_instance_id: str) -> SessionSceneRecord:
        record = self._store.load_item("session_scenes", scene_instance_id, SessionSceneRecord)
        if record is None:
            raise HTTPException(status_code=404, detail="session_scene_not_found")
        if record.scene_profile is None:
            record = self._sync_scene_profile(record)
        return record

    def read_scene_overview(self, scene_instance_id: str) -> dict[str, Any]:
        record = self.require_scene(scene_instance_id)
        selected = _find_layer(record.scene_layers, record.selected_layer_id)
        selected_layer = selected[0] if selected else None
        selected_path = selected[1] if selected else []
        total_object_count = _count_objects(record.scene_layers)
        return {
            "ok": True,
            "tool_name": "read_scene_overview",
            "scene_instance_id": record.scene_instance_id,
            "scene_name": record.scene_name,
            "scene_summary": record.scene_summary,
            "selected_scene_id": record.selected_layer_id,
            "selected_scene_path": selected_path,
            "selected_scene_title": selected_layer.title if selected_layer else "",
            "object_count": total_object_count,
            "scene_tree": [node.model_dump(mode="json") for node in record.scene_layers],
            "scene_profile": record.scene_profile.model_dump(mode="json") if record.scene_profile else None,
            "summary": f"已读取场景“{record.scene_profile.title if record.scene_profile else record.scene_name}”，当前路径为 {' / '.join(selected_path) or '未选定'}。",
        }

    def add_scene(
        self,
        scene_instance_id: str,
        *,
        parent_scene_id: str,
        title: str,
        scope_label: str,
        summary: str,
        atmosphere: str,
        rules: str,
        entrance: str,
    ) -> dict[str, Any]:
        if not title:
            raise HTTPException(status_code=400, detail="scene_title_required")
        if not scope_label:
            raise HTTPException(status_code=400, detail="scene_scope_label_required")
        record = self.require_scene(scene_instance_id)
        target_parent_id = parent_scene_id or record.selected_layer_id
        new_layer = SceneLayerStateRecord(
            id=f"scene-layer-{uuid4().hex[:10]}",
            title=title,
            scope_label=scope_label,
            summary=summary,
            atmosphere=atmosphere,
            rules=rules,
            entrance=entrance,
            objects=[],
            children=[],
        )
        next_layers = [node.model_copy(deep=True) for node in record.scene_layers]
        if target_parent_id:
            if not _append_child_scene(next_layers, target_parent_id, new_layer):
                raise HTTPException(status_code=404, detail="scene_parent_not_found")
        else:
            next_layers.append(new_layer)
        updated = self._replace_record(
            record,
            scene_layers=next_layers,
            selected_layer_id=new_layer.id,
        )
        path = updated.scene_profile.selected_path if updated.scene_profile else [new_layer.title]
        return {
            "ok": True,
            "tool_name": "add_scene",
            "scene_instance_id": updated.scene_instance_id,
            "added_scene_id": new_layer.id,
            "selected_scene_id": updated.selected_layer_id,
            "selected_scene_path": path,
            "scene_profile": updated.scene_profile.model_dump(mode="json") if updated.scene_profile else None,
            "summary": f"已新增场景“{new_layer.title}”，并切换到 {' / '.join(path) or new_layer.title}。",
        }

    def move_to_scene(self, scene_instance_id: str, *, scene_id: str) -> dict[str, Any]:
        if not scene_id:
            raise HTTPException(status_code=400, detail="scene_id_required")
        record = self.require_scene(scene_instance_id)
        selected = _find_layer(record.scene_layers, scene_id)
        if selected is None:
            raise HTTPException(status_code=404, detail="scene_not_found_in_session")
        updated = self._replace_record(record, selected_layer_id=scene_id)
        path = updated.scene_profile.selected_path if updated.scene_profile else selected[1]
        return {
            "ok": True,
            "tool_name": "move_to_scene",
            "scene_instance_id": updated.scene_instance_id,
            "selected_scene_id": scene_id,
            "selected_scene_path": path,
            "scene_profile": updated.scene_profile.model_dump(mode="json") if updated.scene_profile else None,
            "summary": f"已切换到场景 {' / '.join(path) or scene_id}。",
        }

    def add_object(
        self,
        scene_instance_id: str,
        *,
        scene_id: str,
        name: str,
        description: str,
        interaction: str,
        tags: str,
    ) -> dict[str, Any]:
        if not name:
            raise HTTPException(status_code=400, detail="scene_object_name_required")
        record = self.require_scene(scene_instance_id)
        target_scene_id = scene_id or record.selected_layer_id
        if not target_scene_id:
            raise HTTPException(status_code=400, detail="scene_target_required")
        next_layers = [node.model_copy(deep=True) for node in record.scene_layers]
        added_object = SceneObjectStateRecord(
            id=f"scene-object-{uuid4().hex[:10]}",
            name=name,
            description=description,
            interaction=interaction,
            tags=tags,
        )
        if not _append_object(next_layers, target_scene_id, added_object):
            raise HTTPException(status_code=404, detail="scene_not_found_in_session")
        updated = self._replace_record(record, scene_layers=next_layers, selected_layer_id=target_scene_id)
        path = updated.scene_profile.selected_path if updated.scene_profile else []
        return {
            "ok": True,
            "tool_name": "add_object",
            "scene_instance_id": updated.scene_instance_id,
            "object_id": added_object.id,
            "selected_scene_id": updated.selected_layer_id,
            "selected_scene_path": path,
            "scene_profile": updated.scene_profile.model_dump(mode="json") if updated.scene_profile else None,
            "summary": f"已在 {' / '.join(path) or '当前场景'} 中加入物体“{added_object.name}”。",
        }

    def update_object_description(
        self,
        scene_instance_id: str,
        *,
        object_id: str,
        description: str,
    ) -> dict[str, Any]:
        if not object_id:
            raise HTTPException(status_code=400, detail="scene_object_id_required")
        record = self.require_scene(scene_instance_id)
        next_layers = [node.model_copy(deep=True) for node in record.scene_layers]
        updated_object = _update_object_description(next_layers, object_id, description)
        if updated_object is None:
            raise HTTPException(status_code=404, detail="scene_object_not_found")
        updated = self._replace_record(record, scene_layers=next_layers)
        return {
            "ok": True,
            "tool_name": "update_object_description",
            "scene_instance_id": updated.scene_instance_id,
            "object_id": updated_object.id,
            "object_name": updated_object.name,
            "scene_profile": updated.scene_profile.model_dump(mode="json") if updated.scene_profile else None,
            "summary": f"已更新物体“{updated_object.name}”的描述。",
        }

    def delete_object(self, scene_instance_id: str, *, object_id: str) -> dict[str, Any]:
        if not object_id:
            raise HTTPException(status_code=400, detail="scene_object_id_required")
        record = self.require_scene(scene_instance_id)
        next_layers = [node.model_copy(deep=True) for node in record.scene_layers]
        deleted_name = _delete_object(next_layers, object_id)
        if not deleted_name:
            raise HTTPException(status_code=404, detail="scene_object_not_found")
        updated = self._replace_record(record, scene_layers=next_layers)
        return {
            "ok": True,
            "tool_name": "delete_object",
            "scene_instance_id": updated.scene_instance_id,
            "object_id": object_id,
            "scene_profile": updated.scene_profile.model_dump(mode="json") if updated.scene_profile else None,
            "summary": f"已删除物体“{deleted_name}”。",
        }

    def _replace_record(
        self,
        record: SessionSceneRecord,
        *,
        scene_layers: list[SceneLayerStateRecord] | None = None,
        selected_layer_id: str | None = None,
    ) -> SessionSceneRecord:
        next_layers = scene_layers if scene_layers is not None else [node.model_copy(deep=True) for node in record.scene_layers]
        next_selected_layer_id = selected_layer_id if selected_layer_id is not None else record.selected_layer_id
        next_record = record.model_copy(
            update={
                "updated_at": _now_iso(),
                "scene_layers": next_layers,
                "selected_layer_id": next_selected_layer_id,
                "scene_profile": _build_scene_profile(
                    scene_name=record.scene_name,
                    scene_summary=record.scene_summary,
                    scene_layers=next_layers,
                    selected_layer_id=next_selected_layer_id,
                ),
            }
        )
        self._save(next_record)
        return next_record

    def _save(self, record: SessionSceneRecord) -> None:
        self._store.save_item("session_scenes", record.scene_instance_id, record)

    def _sync_scene_profile(self, record: SessionSceneRecord) -> SessionSceneRecord:
        next_record = record.model_copy(
            update={
                "scene_profile": _build_scene_profile(
                    scene_name=record.scene_name,
                    scene_summary=record.scene_summary,
                    scene_layers=record.scene_layers,
                    selected_layer_id=record.selected_layer_id,
                ),
            }
        )
        self._save(next_record)
        return next_record


def summarize_chat_tool_result(result: dict[str, Any]) -> str:
    summary = str(result.get("summary") or "").strip()
    if summary:
        return summary
    if str(result.get("tool_name") or "") == "read_scene_overview":
        return f"场景读取完成，当前共有 {result.get('object_count') or 0} 个物体。"
    if result.get("ok") is False:
        return str(result.get("error") or "工具调用失败")
    return str(result.get("tool_name") or "工具")


def extract_scene_profile_from_tool_results(tool_results: list[dict[str, Any]]) -> SceneProfileRecord | None:
    for result in reversed(tool_results):
        raw_profile = result.get("scene_profile")
        if isinstance(raw_profile, dict):
            return SceneProfileRecord.model_validate(raw_profile)
    return None


def serialize_chat_tool_trace_item(
    *,
    tool_call_id: str,
    tool_name: str,
    arguments_json: str,
    result: dict[str, Any],
) -> dict[str, str]:
    return {
        "tool_call_id": tool_call_id,
        "tool_name": tool_name,
        "arguments_json": arguments_json,
        "result_summary": summarize_chat_tool_result(result),
        "result_json": json.dumps(result, ensure_ascii=False),
    }


def _build_scene_profile(
    *,
    scene_name: str,
    scene_summary: str,
    scene_layers: list[SceneLayerStateRecord],
    selected_layer_id: str,
) -> SceneProfileRecord:
    selected = _find_layer(scene_layers, selected_layer_id)
    if selected is not None:
        selected_layer, selected_path = selected
    elif scene_layers:
        selected_layer, selected_path = _find_layer(scene_layers, scene_layers[0].id) or (scene_layers[0], [scene_layers[0].title])
    else:
        selected_layer, selected_path = (
            SceneLayerStateRecord(
                id="scene-empty",
                title=scene_name or "未命名场景",
                scope_label="未定义范围",
                summary=scene_summary,
                atmosphere="",
                rules="",
                entrance="",
                objects=[],
                children=[],
            ),
            [scene_name or "未命名场景"],
        )
    focus_objects = [obj.name for obj in selected_layer.objects[:4] if obj.name.strip()]
    tags = _collect_tags(selected_layer.objects)
    return SceneProfileRecord(
        scene_name=scene_name,
        scene_id=selected_layer.id,
        title=selected_layer.title,
        summary=scene_summary or selected_layer.summary or f"场景路径：{' > '.join(selected_path)}",
        tags=tags,
        selected_path=selected_path,
        focus_object_names=focus_objects,
        scene_tree=[node.model_copy(deep=True) for node in scene_layers],
    )


def _find_layer(
    scene_layers: list[SceneLayerStateRecord],
    target_id: str,
    path: list[str] | None = None,
) -> tuple[SceneLayerStateRecord, list[str]] | None:
    current_path = path or []
    for layer in scene_layers:
        next_path = [*current_path, layer.title]
        if target_id and layer.id == target_id:
            return layer, next_path
        found = _find_layer(layer.children, target_id, next_path)
        if found is not None:
            return found
    return None


def _append_child_scene(
    scene_layers: list[SceneLayerStateRecord],
    parent_scene_id: str,
    child: SceneLayerStateRecord,
) -> bool:
    for layer in scene_layers:
        if layer.id == parent_scene_id:
            layer.children.append(child)
            return True
        if _append_child_scene(layer.children, parent_scene_id, child):
            return True
    return False


def _append_object(
    scene_layers: list[SceneLayerStateRecord],
    scene_id: str,
    obj: SceneObjectStateRecord,
) -> bool:
    for layer in scene_layers:
        if layer.id == scene_id:
            layer.objects.append(obj)
            return True
        if _append_object(layer.children, scene_id, obj):
            return True
    return False


def _update_object_description(
    scene_layers: list[SceneLayerStateRecord],
    object_id: str,
    description: str,
) -> SceneObjectStateRecord | None:
    for layer in scene_layers:
        for obj in layer.objects:
            if obj.id == object_id:
                obj.description = description
                return obj
        updated = _update_object_description(layer.children, object_id, description)
        if updated is not None:
            return updated
    return None


def _delete_object(scene_layers: list[SceneLayerStateRecord], object_id: str) -> str:
    for layer in scene_layers:
        for index, obj in enumerate(layer.objects):
            if obj.id == object_id:
                layer.objects.pop(index)
                return obj.name
        deleted = _delete_object(layer.children, object_id)
        if deleted:
            return deleted
    return ""


def _collect_tags(objects: list[SceneObjectStateRecord]) -> list[str]:
    tags: list[str] = []
    seen: set[str] = set()
    for obj in objects:
        for item in obj.tags.split(","):
            normalized = item.strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            tags.append(normalized)
            if len(tags) >= 8:
                return tags
    return tags


def _count_objects(scene_layers: list[SceneLayerStateRecord]) -> int:
    total = 0
    for layer in scene_layers:
        total += len(layer.objects)
        total += _count_objects(layer.children)
    return total


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
