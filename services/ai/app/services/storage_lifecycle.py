from __future__ import annotations

from pathlib import Path

from app.models.domain import DocumentRecord
from app.services.local_store import LocalJsonStore
from app.services.token_usage import TokenUsageService


PERSISTENT_DATABASE_BUCKETS = [
    "documents",
    "plans",
    "sessions",
    "personas",
    "persona_cards",
    "scene_setup",
    "scene_library",
    "reusable_scene_nodes",
    "session_scenes",
    "runtime_settings",
    "model_tool_config",
]

MANAGED_CLEANUP_BUCKETS = [
    "document_debug",
    "planning_trace",
    "document_process_stream",
    "learning_plan_stream",
    "token_usage",
    "chat_attachments",
    "runtime_temp",
    "cache_files",
]


class StorageLifecycleService:
    def __init__(self, store: LocalJsonStore, token_usage_service: TokenUsageService) -> None:
        self._store = store
        self._token_usage_service = token_usage_service

    def summarize(self) -> list[dict[str, object]]:
        buckets: list[dict[str, object]] = []
        for bucket in PERSISTENT_DATABASE_BUCKETS:
            buckets.append(
                {
                    "bucket": bucket,
                    "layer": "database",
                    "lifecycle": "persistent",
                    "item_count": self._store.count_bucket(bucket),
                    "size_bytes": 0,
                    "mutable": False,
                    "description": _bucket_description(bucket),
                }
            )
        for bucket in ("document_debug", "planning_trace", "document_process_stream", "learning_plan_stream"):
            buckets.append(
                {
                    "bucket": bucket,
                    "layer": "database",
                    "lifecycle": "cache",
                    "item_count": self._store.count_bucket(bucket),
                    "size_bytes": 0,
                    "mutable": True,
                    "description": _bucket_description(bucket),
                }
            )
        token_usage_count = len(self._token_usage_service.load_all())
        buckets.append(
            {
                "bucket": "token_usage",
                "layer": "database",
                "lifecycle": "cache",
                "item_count": token_usage_count,
                "size_bytes": 0,
                "mutable": True,
                "description": _bucket_description("token_usage"),
            }
        )
        for bucket, path, lifecycle in (
            ("chat_attachments", self._store.chat_attachment_root, "temp"),
            ("runtime_temp", self._store.runtime_temp_root, "temp"),
            ("cache_files", self._store.root / "cache", "cache"),
            ("uploads", self._store.upload_root, "persistent"),
        ):
            stats = self._store.storage.describe_dir(path)
            buckets.append(
                {
                    "bucket": bucket,
                    "layer": "filesystem",
                    "lifecycle": lifecycle,
                    "item_count": stats.file_count,
                    "size_bytes": stats.total_bytes,
                    "mutable": bucket != "uploads",
                    "path": stats.path,
                    "description": _bucket_description(bucket),
                }
            )
        return buckets

    def cleanup(
        self,
        *,
        buckets: list[str],
        document_id: str = "",
        session_id: str = "",
    ) -> list[dict[str, object]]:
        normalized_buckets = [bucket.strip() for bucket in buckets if bucket.strip()]
        if not normalized_buckets:
            return []
        cleaned: list[dict[str, object]] = []
        for bucket in normalized_buckets:
            if bucket not in MANAGED_CLEANUP_BUCKETS:
                raise ValueError(f"cleanup_bucket_not_supported:{bucket}")
            removed = 0
            if bucket == "token_usage":
                removed = self._token_usage_service.clear()
            elif bucket == "chat_attachments":
                removed = self._cleanup_chat_attachments(session_id=session_id)
            elif bucket == "runtime_temp":
                removed = self._store.storage.clear_dir(self._store.runtime_temp_root)
            elif bucket == "cache_files":
                removed = self._store.storage.clear_dir(self._store.root / "cache")
            else:
                removed = self._store.clear_bucket(bucket, item_id=document_id or None)
            cleaned.append({"bucket": bucket, "removed_count": removed})
        return cleaned

    def _cleanup_chat_attachments(self, *, session_id: str) -> int:
        if session_id:
            return self._store.storage.delete_tree(self._store.chat_attachment_root / session_id)
        return self._store.storage.clear_dir(self._store.chat_attachment_root)

    def list_orphaned_uploads(self) -> list[str]:
        active_paths = {
            Path(document.stored_path).resolve()
            for document in self._store.load_list("documents", DocumentRecord)
            if document.stored_path
        }
        orphaned: list[str] = []
        for path in self._store.upload_root.glob("*"):
            if not path.is_file():
                continue
            if path.resolve() not in active_paths:
                orphaned.append(str(path))
        return sorted(orphaned)


def _bucket_description(bucket: str) -> str:
    descriptions = {
        "documents": "教材文档主记录",
        "plans": "学习计划主记录",
        "sessions": "学习会话主记录",
        "personas": "用户人格记录",
        "persona_cards": "人格卡片库",
        "scene_setup": "场景编辑器当前状态",
        "scene_library": "场景模板库",
        "reusable_scene_nodes": "可复用场景节点",
        "session_scenes": "会话绑定场景实例",
        "runtime_settings": "运行时模型配置",
        "model_tool_config": "模型工具开关配置",
        "document_debug": "文档解析调试产物",
        "planning_trace": "计划生成 trace",
        "document_process_stream": "文档处理流事件",
        "learning_plan_stream": "计划生成流事件",
        "token_usage": "模型 token 用量记录",
        "chat_attachments": "会话附件临时文件",
        "runtime_temp": "OCR 与运行期临时目录",
        "cache_files": "本地缓存文件目录",
        "uploads": "上传教材原始文件",
    }
    return descriptions.get(bucket, bucket)
