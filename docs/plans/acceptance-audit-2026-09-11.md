# 用户手册验收进度

`DOC-USER-001` 尚未完成。2026-09-11 主智能体使用全新临时数据库和真实 mock 后端，走通纯目标生成、自动创建 Session、提问与刷新读回。这是限定的开发者验证，不代替独立完整手册验收。

仍需独立覆盖 Settings 首次配置、教材路线、Persona/Scene/Tavern、真实 provider 首次使用、DMG/NSIS/AppImage 安装及数据/留存说明。PostgreSQL 与制品重放的部分通过范围见[独立报告](postgres-replay-independent-acceptance-2026-09-11.md)。

复现脚本保留：[隔离 mock 后端](acceptance/manual_mock_server_20260911.py)、[浏览器路线](acceptance/manual_mock_20260911.mjs)。后端在 `services/ai` 使用 `PYTHONPATH=. UV_CACHE_DIR=/tmp/vibe-learner-uv-cache LITELLM_LOCAL_MODEL_COST_MAP=True uv run python ../../docs/plans/acceptance/manual_mock_server_20260911.py`；前端从 `apps/web` 使用 `npm run start -- --hostname 127.0.0.1 --port 3430`；根目录执行 `node docs/plans/acceptance/manual_mock_20260911.mjs`。仅针对一次性数据运行。

已完成任务的逐项开发记录清理于 0.3.3；历史审计可由 Git 的 `e13fd02` 及更早提交查询。
