# AI Service

`services/ai` 是 Vibe Learner 的 FastAPI 后端服务，负责文档入库与 OCR、Study Unit 清洗、学习计划生成与修订、Study Chat 教学对话、Persona/Scene 管理、Tavern 多角色互动以及 Harness 与诊断持久化。

## 本地开发

在 `services/ai` 目录执行：

```bash
uv sync --frozen
uv run uvicorn app.main:app --reload
```

数据库迁移与本地 JSON 兼容数据导入：

```bash
uv run alembic upgrade head
uv run python -m app.persistence.migrate_local_data
```

## 配置说明

- 复制 `.env.example` 为 `.env` 作为启动默认配置。
- `VIBE_LEARNER_PLAN_PROVIDER=mock` 启用本地确定性模拟；`litellm` 启用真实模型 provider。
- 数据库中的运行时设置优先于环境变量，可在线覆盖并立即生效。
- 默认使用本地 SQLite；通过 `DATABASE_URL` 可切换至 PostgreSQL。

## 相关文档

- 系统架构与存储布局：[docs/architecture.md](../../docs/architecture.md)
- 配置优先级与运行预算：[docs/harness/configuration.md](../../docs/harness/configuration.md)
- 自动生成 API 端点清单：[docs/api-reference.md](../../docs/api-reference.md)
- API 契约语义说明：[docs/api-contracts.md](../../docs/api-contracts.md)

## 常见排障

**对话返回 `chat_model_invalid_payload`**：长推理模型可能因耗尽输出预算触发 `finish_reason=length`，导致可见正文或结构化 JSON 不完整。请检查当前生效的输出 token 上限、超时预算、模型对严格 JSON Schema 的支持以及 LiteLLM 响应兼容配置。若向量嵌入服务不可用，记忆检索会自动降级为本地确定性词法散列检索。
