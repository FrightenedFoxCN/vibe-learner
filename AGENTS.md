# AGENTS

本文件只保留每次任务都必须遵守的核心约束；各领域详细设计见下方索引。

## 仓库布局

`apps/web`（Next.js 16 前端）· `services/ai`（FastAPI 后端）· `packages/shared`（TS 契约）· `apps/desktop`（Tauri 壳）· `docs`（文档）

待办与未排期研究由 [TODO.md](TODO.md) 统一维护。

## 核心铁律

1. **数据分层与兜底**：外部未知形状只在 `services/ai/app/core/coerce.py` 归一化；域模型保持 strict，必填字段缺失必须报错；前端 decode 只校验形状，不发明语义默认值。见 [数据流分层](docs/data-flow-layers.md)。
2. **Harness 生命周期**：所有模型或启发式工作流遵循 `typed input → versioned context → strict decode → invariant validation → bounded recovery → atomic commit → trace`。见 [Harness 工程手册](docs/harness/README.md)。
3. **Operation Identity**：Harness 身份与领域操作准入在同一数据库事务内分配；不得从 provider `tool_call_id` 推导，也不得为历史行捏造。
4. **提交证据**：提交声明必须匹配已注册的 operation key 与版本化 committed projection；通用资源证据不足以证明提交成功。
5. **提案与提交分离**：模型/启发式提案、已提交记录与 API 响应严格分离；系统生成的 ID、身份、顺序、修订号与时间戳不得进入模型自有 schema。
6. **交互题评分隔离**：评分材料仅存在于服务端；浏览器只渲染持久化读回的 Session 状态。
7. **验证门禁**：改动后运行 `npm run test:baseline`（不变量基线）与 `npm run check`（风格、契约类型、Web 类型、API 参考同步与基线）。
8. **脚本诚实性**：新增 `test:*` 脚本前先确认对应测试入口存在。

## 运行形态

- 前端与后端分离运行；后端默认使用 SQLite，可通过 `DATABASE_URL` 切换至 PostgreSQL。
- `LocalJsonStore` 仅为兼容层；Documents 与 Study Sessions 走单行写入与 revision CAS，不使用集合级 `save_list`。
- Tavern 是独立领域（rooms / participants / messages / runs / steps），不与 `StudySessionRecord` 混用。
- 页面与区块命名统一遵循 [页面命名与术语](docs/page-vocabulary.md)。

## 常用命令

```bash
npm install
npm run dev:web
npm run build:web
npm run test:baseline
npm run check

cd services/ai && uv sync --frozen
cd services/ai && uv run uvicorn app.main:app --reload
```

## 环境与配置

- Python 命令统一通过 `uv` 执行，不假定全局虚拟环境。
- 模型默认配置来自 `services/ai/.env`；数据库内的运行时设置可在不重启服务的情况下覆盖默认值。
- `VIBE_LEARNER_PLAN_PROVIDER=mock` 保持本地确定性；`litellm` 走真实模型。

## 按需阅读

| 需求 | 文档 |
| --- | --- |
| 全部文档总目录 | [docs/README.md](docs/README.md) |
| 代码入口与所有权 | [docs/entry-points.md](docs/entry-points.md) |
| 工程机制与约定 | [docs/conventions.md](docs/conventions.md) |
| 系统架构与主流程 | [docs/architecture.md](docs/architecture.md) |
| 数据流分层与兜底 | [docs/data-flow-layers.md](docs/data-flow-layers.md) |
| Harness 工程手册 | [docs/harness/README.md](docs/harness/README.md) |
| 页面、区块与术语 | [docs/page-vocabulary.md](docs/page-vocabulary.md) |
| 前端边界与设计基线 | [docs/frontend-learning-workspace.md](docs/frontend-learning-workspace.md) · [docs/frontend-design-baseline.md](docs/frontend-design-baseline.md) |
