"""Isolated local acceptance service; never loads project runtime credentials."""
import argparse
import os
from pathlib import Path
from unittest.mock import patch

from app.core.settings import Settings

parser = argparse.ArgumentParser()
parser.add_argument("--root", type=Path, required=True)
parser.add_argument("--port", type=int, default=18045)
parser.add_argument("--live", action="store_true")
args = parser.parse_args()
args.root.mkdir(parents=True, exist_ok=True)
settings = Settings(database_url=f"sqlite:///{args.root}/acceptance.db",
                    storage_root=str(args.root), plan_provider="mock",
                    allowed_origins=("http://localhost:13045", "http://127.0.0.1:13045"))
if args.live:
    from dataclasses import replace
    settings = replace(settings, plan_provider="litellm",
        openai_api_key=os.environ["K3_API_KEY"],
        openai_base_url="https://api.minimax.cn/v1",
        openai_plan_model="MiniMax-M3", openai_setting_model="MiniMax-M3",
        openai_chat_model="MiniMax-M3", openai_setting_max_tokens=4096,
        openai_chat_max_tokens=4096, openai_timeout_seconds=90,
        openai_setting_web_search_enabled=False)
with patch.object(Settings, "from_env", return_value=settings):
    from app.app_factory import create_app
    import uvicorn
    uvicorn.run(create_app(), host="127.0.0.1", port=args.port)
