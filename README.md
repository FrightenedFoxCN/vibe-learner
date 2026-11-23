# Vibe Learner

Vibe Learner 是一个本地优先的学习工作区，涵盖教材解析、学习计划、Study Dialog、Persona、Scene 与 Tavern 互动。

## 仓库结构

| 目录 | 说明 |
| --- | --- |
| `apps/web` | Next.js 16（App Router）Web 前端 |
| `services/ai` | FastAPI 后端（解析、OCR、规划、教学对话、Tavern 与持久化） |
| `packages/shared` | 前后端共享 TypeScript 契约与标准夹具 |
| `apps/desktop` | Tauri 2 桌面壳、Sidecar 打包与 Stronghold Vault |
| `docs` | 架构、领域契约、前端规范、Harness 手册与运维文档 |

## 本地开发

环境要求：Node.js 26、Python 3.12+、`uv`。

在仓库根目录安装依赖并启动前端：

```bash
npm install
uv sync --directory services/ai --frozen
npm run dev:web
```

在 `services/ai` 目录启动后端（首次运行可先复制 `.env.example` 为 `.env`）：

```bash
cd services/ai
uv run uvicorn app.main:app --reload
```

默认以 `VIBE_LEARNER_PLAN_PROVIDER=mock` 提供本地确定性运行；将模型配置切换为 `litellm`（或在应用内 **设置** 页面保存运行时配置）即可接入真实模型服务。

## 常用检查

```bash
npm run check           # 代码风格 + 共享契约类型 + Web 类型 + API 参考同步 + 不变量基线
npm run check:release   # 完整检查并构建生产 Web
npm run test:baseline   # 后端与前端不变量基线测试
```

## 文档导航

- 完整文档目录：[docs/README.md](docs/README.md)
- 应用内用户手册：启动后访问 `/manual`，说明见 [docs/user_manual.md](docs/user_manual.md)
- 协作约束与铁律：[AGENTS.md](AGENTS.md)
- 未完成事项与研究项：[TODO.md](TODO.md)

## 许可证

本项目采用仓库内 [LICENSE](LICENSE) 指定的许可证（GPL-3.0）。
