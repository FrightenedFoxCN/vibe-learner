"""Temporary desktop model configuration; secrets stay in session memory."""
import argparse
import json
import os
from pathlib import Path
import httpx

parser = argparse.ArgumentParser()
parser.add_argument("--url", required=True)
parser.add_argument("--restore", action="store_true")
parser.add_argument("--secrets-only", action="store_true")
parser.add_argument("--evidence-dir", type=Path)
args = parser.parse_args()
root = args.evidence_dir or Path(__file__).parent / "desktop"
root.mkdir(parents=True, exist_ok=True)
saved = root / "original-settings.json"
c = httpx.Client(base_url=args.url, timeout=30)
if args.secrets_only:
    c.put("/runtime-settings/session-secrets", json={
        k: os.environ["K3_API_KEY"] for k in (
            "openai_api_key", "openai_plan_api_key", "openai_chat_api_key", "openai_setting_api_key")
    }).raise_for_status()
elif args.restore:
    response = c.patch("/runtime-settings", json=json.loads(saved.read_text()))
    response.raise_for_status()
    c.delete("/runtime-settings/session-secrets").raise_for_status()
else:
    from app.models.api import UpdateRuntimeSettingsRequest
    original = c.get("/runtime-settings").json()
    safe = {k: v for k, v in original.items()
            if k in UpdateRuntimeSettingsRequest.model_fields and "api_key" not in k}
    if saved.exists():
        raise RuntimeError("original_desktop_settings_already_saved")
    saved.write_text(json.dumps(safe, indent=2))
    c.put("/runtime-settings/session-secrets", json={
        k: os.environ["K3_API_KEY"] for k in (
            "openai_api_key", "openai_plan_api_key", "openai_chat_api_key", "openai_setting_api_key")
    }).raise_for_status()
    c.patch("/runtime-settings", json={
        "plan_provider": "litellm", "openai_base_url": "https://api.minimax.cn/v1",
        **{f"openai_{s}_base_url": "https://api.minimax.cn/v1" for s in ("plan", "chat", "setting")},
        **{f"openai_{s}_model": "MiniMax-M3" for s in ("plan", "chat", "setting")},
        "openai_timeout_seconds": 90, "openai_chat_max_tokens": 4096,
        "openai_setting_max_tokens": 4096, "openai_setting_web_search_enabled": False,
        "openai_plan_model_multimodal": False, "openai_chat_model_multimodal": False,
    }).raise_for_status()
print(json.dumps({"restored": args.restore, "status": "ok"}))
