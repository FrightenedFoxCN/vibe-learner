# 审计证据说明

对应 `../audit-2026-09-06.md`，基线 `8f5ff0f`。本目录只存合成测试数据的精简证据，不含原业务数据或运行密钥。

- `repro-goal-only.py`：真实 FastAPI TestClient、独立临时 Settings/数据库，打印同步和流式纯目标计划的500与异常。
- `repro-backend-boundaries.py`：独立临时库；失败OCR trace、OCR不可用、注入非法Chunk、模拟模型畸形类型四种边界。明确包含故障注入，不是上游模型质量样本。
- `study-switch-loop-*.json`：按结构化日志唯一request id计数，不重复计算uvicorn access log。
- `study-switch-loop-*.log`：原始日志的有限摘录，行号对应本轮临时backend.log。完整日志保留在 `/tmp/vibe-learner-audit-20260905/backend.log`，不将整份大日志提交仓库。
- `study-switch-loop-analysis.md`：浏览器观察、日志事实和代码归因；包含无请求体的证据限制。
- `tavern-roster-observations.md`：已执行API复现的步骤与结果转录；原始内联脚本未保存，非原始日志。
- `live-decode.log`：Study和Tavern两个真实本地响应decoder用例结果，2 pass、0 skip。

两个Python复现脚本需在 `services/ai` 目录使用仓库uv环境执行，例如：

```bash
PYTHONPATH=. UV_CACHE_DIR=/tmp/vibe-learner-uv-cache uv run python ../../docs/audit-2026-09-06-evidence/repro-goal-only.py
PYTHONPATH=. UV_CACHE_DIR=/tmp/vibe-learner-uv-cache uv run python ../../docs/audit-2026-09-06-evidence/repro-backend-boundaries.py
```

脚本打印审计观察，未伪装成已进入CI的回归测试。修复后应重新解释结果，并建立真正有断言的关闭验收。
