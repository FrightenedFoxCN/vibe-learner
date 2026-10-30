# Vibe Learner

Vibe Learner 是一个本地优先的学习工作区，覆盖教材解析、学习计划、Study Dialog、Persona、Scene 和 Tavern。

仓库是一个 monorepo：

- `apps/web`：Next.js Web 前端
- `services/ai`：FastAPI 后端
- `packages/shared`：共享 TypeScript 契约
- `apps/desktop`：Tauri 桌面壳

## 开发

需要 Node.js 26、Python 3.12+ 和 uv。从仓库根目录执行：

```bash
npm install
uv sync --directory services/ai --frozen
npm run dev:web
```

后端可从 `services/ai` 启动：

```bash
uv run uvicorn app.main:app --reload
```

架构、API、运行边界和测试入口见 [`docs/README.md`](docs/README.md)。当前待办见 [`TODO.md`](TODO.md)，仓库约定见 [`AGENTS.md`](AGENTS.md)。

本项目采用仓库内 LICENSE 指定的许可证。
