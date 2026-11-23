# AGENTS

本文件只放**每次对话都必须遵守的约束**。机制细节在下方索引里按需阅读，不在这里重复。

## 仓库布局

`apps/web`（Next.js 16 前端）· `services/ai`（FastAPI 后端）· `packages/shared`（TS 契约）· `apps/desktop`（Tauri 壳）· `docs`（文档）

未完成工作只由 [TODO](TODO.md) 维护。

## 铁律

1. **数据分层与兜底**：外部形状（外部 JSON / 旧行 / 模型输出）只在 `app/core/coerce.py` 归一化；域模型保持 strict，必填字段缺失必须报错；前端 decode 只校验形状，不发明语义默认值。见 [data-flow-layers](docs/data-flow-layers.md)。
2. **Harness 生命周期**：新增或迁移工作流必须走 typed input → versioned context → strict decode → invariant validation → bounded recovery → atomic commit → trace。见 [harness/README](docs/harness/README.md)。
3. **Operation identity**：与领域操作准入在**同一数据库事务**内分配；不得从 provider `tool_call_id` 推导，不得为 legacy 行捏造。
4. **提交证据**：必须匹配已注册的 operation key 与版本化 committed projection；通用资源证据不足以声称提交成功。
5. **提案 ≠ 已提交**：模型/heuristic 提案与已提交记录、API 响应严格分离；生成的 ID、身份、顺序、修订、时间戳不得进入模型自有 schema。
6. **交互题评分材料**只存在于服务端；浏览器只渲染持久化后的 Session 读回。
7. **验证入口**：`npm run test:baseline`（不变量基线）+ `npm run check`（style + contracts + web types + baseline）。完整测试套件与 `eval:harness:*` 已移除，不要引用旧命令。
8. **新增 `test:*` 脚本前**先确认对应测试入口存在；没有入口就不要加脚本。

## 运行形态（要点）

- 前端与后端分离运行；后端默认 SQLite，可用 `DATABASE_URL` 指向 PostgreSQL。
- `LocalJsonStore` 是兼容层；Documents / Study Sessions 必须走单行插入 + revision CAS，不得回退到 `save_list`。
- Tavern 是独立域（rooms / participants / messages / runs / steps），不要把 Tavern 字段塞进 `StudySessionRecord`。

## 常用命令

```bash
npm install
npm run dev:web
npm run build:web
npm run test:baseline
npm run check

cd services/ai && uv sync
cd services/ai && uv run uvicorn app.main:app --reload
```

## 配置

- Python 一律 `uv`，不要假定全局激活的虚拟环境。
- 规划 provider 默认来自 `services/ai/.env`；数据库权威运行时设置可无需重启覆盖。
- `VIBE_LEARNER_PLAN_PROVIDER=mock` 保持本地确定性；`litellm` 走真实模型。

## 按需阅读

| 想知道 | 读 |
|---|---|
| 代码入口与所有权 | [docs/entry-points.md](docs/entry-points.md) |
| 机制与工程约定（31 条） | [docs/conventions.md](docs/conventions.md) |
| 页面、区块与术语命名 | [docs/page-vocabulary.md](docs/page-vocabulary.md) |
| 系统结构与主流程 | [docs/architecture.md](docs/architecture.md) |
| Harness 生命周期、数据库与恢复 | [docs/harness/README.md](docs/harness/README.md) |
| 数据分层与兜底责任 | [docs/data-flow-layers.md](docs/data-flow-layers.md) |
| 全部文档索引 | [docs/README.md](docs/README.md) |
