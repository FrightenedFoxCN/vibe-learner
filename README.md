# 氛围学习（vibe learning）

一个以本地优先（local-first）为核心、支持人格化教学体验的学习系统。项目面向「教材上传 -> 解析 -> 学习计划生成 -> 章节对话学习 -> 追踪」的完整闭环，采用前后端分离的 Monorepo 结构，便于持续迭代与调试。

Warning: still under heavy development. See [TODO.md](./TODO.md) for more information.

## 项目目标

- 把原始教材（PDF）转成可学习、可追踪的结构化内容。
- 用可配置的人格角色（Persona）和环境场景（Scene）提供更具氛围感的学习陪伴。
- 支持稳定的本地 mock 流程，也支持通过 LiteLLM Python SDK 接入更多模型进行真实计划生成与对话。
- 为研发与提示词迭代提供可视化调试控制台与过程留痕。

## 核心能力

- 文档处理与抽取
	- 上传教材文档并建立文档记录。
	- 支持文本抽取与 OCR 回退。
	- 清洗章节噪声并生成可用于规划的 Study Unit。
- 学习计划生成
	- 基于清洗后的学习单元生成 Learning Plan。
	- 支持流式计划输出与 planning trace 持久化。
	- 可在 mock/litellm 两种 provider 间切换。
- 学习会话与角色交互
	- 发起 Study Session 并进行章节学习对话。
	- 返回结构化 Character Event，驱动前端角色表现层。
	- 支持引用信息与过程化反馈。
- 人格色谱（Persona Spectrum）
	- 通过人格插槽（世界观、经历、思维方式、教学法、鼓励与纠错策略等）构建教学人格。
	- 支持关键词生成与长文本提取人格卡片，并可筛选后回填到当前人格草稿。
	- 支持 AI 辅助润色设定字段、卡片拖拽插入、权重排序与配置导入导出。
	- 内置人格只读，鼓励在其基础上另存为新人格，形成可复用人格库。
- 场景搭建（Scene Setup）
	- 以“世界 -> 区域 -> 校园 -> 建筑 -> 教室”的分层场景树组织学习空间。
	- 每层可配置 summary、atmosphere、rules、entrance，并挂载可互动物体。
	- 支持关键词生成场景树、长文本提取场景树，以及生成候选一键应用。
	- 支持场景库保存/更新、JSON 导入导出、可复用节点库沉淀与快速插入。
- 运行时能力治理
	- 感官工具页可按阶段和分类启停工具，统一控制模型工具链可用性。
	- 统一设置页支持 provider 切换、分场景模型分配、能力探测与自动保存。
- 用量审计与调试可观测性
	- 用量审计页按日期与功能追踪 Token 消耗，支持模型维度拆分查看。
	- 提供文档解析、计划生成、会话链路的调试面板与过程留痕，便于复盘和排障。

## 仓库结构

```text
.
├─ apps/web          # Next.js 16 前端：学习工作台、调试控制台、角色交互页面
├─ services/ai       # FastAPI 后端：解析、规划、会话、角色事件与调试 API
├─ packages/shared   # 前后端共享 TypeScript 协议与类型
└─ docs              # 架构、API、数据流、页面设计等文档
```

## 主要页面

- 导航首页（`/`）
	- 统一导航入口，快速进入计划、对话、人格、场景、工具与设置页面。
- 计划生成（`/plan`）
	- 人格与场景选择、教材上传解析、计划生成轮次、学习单元编辑、计划历史管理。
- 章节对话（`/study`）
	- 按章节/子章节进行学习对话，联动教材页码与角色表现。
- 人格色谱（`/persona-spectrum`）
	- 人格插槽编辑、人格卡片生成与回填、配置导入导出。
- 场景搭建（`/scene-setup`）
	- 分层场景树编辑、复用节点库、场景库管理、JSON 导入导出。
- 感官工具（`/sensory-tools`）
	- 按阶段与分类治理模型工具开关。
- 统一设置（`/settings`）
	- provider/模型/能力探测/高级参数与自动保存控制。
- 用量审计（`/model-usage`）
	- 模型调用与 Token 消耗统计复盘。

## 技术栈

- 前端：Next.js App Router + TypeScript
- 后端：FastAPI（Python）
- Python 依赖管理：uv
- 工作区：npm workspaces

## 软件依赖（新增与建议版本）

- Git（新增）: >= 2.40
- Node.js: >= 20
- npm: >= 10
- Python: >= 3.9
- uv: 建议最新稳定版

## 项目现有依赖项（按清单文件整理）

### JavaScript / TypeScript

根工作区（`package.json`）依赖：

- rehype-katex: ^7.0.1

前端应用（`apps/web/package.json`）运行时依赖：

- @vibe-learner/shared: 0.1.0
- mermaid: ^11.14.0
- next: 16.2.3
- react: 19.2.0
- react-dom: 19.2.0
- react-markdown: ^10.1.0
- rehype-mathjax: ^7.1.0
- remark-gfm: ^4.0.1
- remark-math: ^6.0.0

前端应用（`apps/web/package.json`）开发依赖：

- @types/node: 24.8.1
- @types/react: 19.2.2
- @types/react-dom: 19.2.2
- tailwindcss: 4.1.13
- typescript: ^6.0.2

共享包（`packages/shared/package.json`）说明：

- 当前无额外 third-party 依赖，仅导出本地 TypeScript 合同类型。

### Python

后端（`services/ai/pyproject.toml`）依赖：

- fastapi>=0.116.0
- PyMuPDF>=1.26.0
- pydantic>=2.11.0
- python-multipart>=0.0.20
- uvicorn>=0.35.0

## 快速开始

### 1) 安装依赖

在仓库根目录执行：

```bash
npm install
```

安装后端依赖：

```bash
cd services/ai
uv sync
```

### 2) 启动开发环境

启动前端（仓库根目录）：

```bash
npm run dev:web
```

启动后端（`services/ai` 目录）：

```bash
uv run uvicorn app.main:app --reload
```

默认情况下，前端将请求 `http://127.0.0.1:8000` 的 AI 服务；可通过 `NEXT_PUBLIC_AI_BASE_URL` 覆盖。

## 环境变量与模型配置

复制环境变量模板：

```bash
cd services/ai
cp .env.example .env
```

### 方案 A：本地稳定开发

```bash
VIBE_LEARNER_PLAN_PROVIDER=mock
```

使用内置 deterministic planner，便于联调与回归测试。

### 方案 B：接入 LiteLLM SDK

```bash
VIBE_LEARNER_PLAN_PROVIDER=litellm
OPENAI_API_KEY=sk-...
OPENAI_BASE_URL=http://127.0.0.1:4000
OPENAI_PLAN_MODEL=gpt-4.1-mini
OPENAI_SETTING_MODEL=gpt-4.1-mini
OPENAI_CHAT_MODEL=gpt-4.1-mini
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
OPENAI_TIMEOUT_SECONDS=30
```

当前真实模型调用已经切到 LiteLLM Python SDK。最简单的做法仍然是把 LiteLLM Proxy 当统一网关；如果你要直连其他 provider / proxy server，也可以直接在模型名里使用 LiteLLM 的 provider 前缀，并按需覆盖对应 `OPENAI_*_BASE_URL`。需要注意：设置页的模型探测目前仍基于 `/models` 兼容接口，直连某些上游时可能需要手填模型名。

常见可选项（按需开启）：

```bash
OPENAI_CHAT_TEMPERATURE=0.35
OPENAI_SETTING_TEMPERATURE=0.4
OPENAI_SETTING_MAX_TOKENS=900
OPENAI_CHAT_MAX_TOKENS=800
OPENAI_CHAT_HISTORY_MESSAGES=8
OPENAI_CHAT_TOOL_MAX_ROUNDS=4
OPENAI_CHAT_MODEL_MULTIMODAL=false
```

### 环境变量与设置页配置的关系（重要）

当前项目存在两条配置输入路径：

1. 后端环境变量（`services/ai/.env` + 进程环境变量）
2. 前端统一设置页（`/settings`）通过 Runtime Settings API 写入的运行时配置

它们的关系与优先级如下：

1. 启动时，后端先读取环境变量作为基线配置。
2. 若 `services/ai/data/runtime_settings/default.json` 已存在，则优先加载这个运行时配置记录。
3. 前端设置页的修改会通过 `PATCH /runtime-settings` 自动保存到该 JSON 文件，并立即触发后端重建模型提供器。
4. 因此在日常开发中，“设置页保存后的值”通常会覆盖 `.env` 的同名值。
5. `.env` 更适合作为首次启动基线或兜底值，不是设置页的实时镜像。

补充规则：

- 设置页中的分场景密钥（plan/setting/chat）如果留空，会回退到全局 `openai_api_key`。
- 分场景 Base URL 如果留空，会在模型提供器层回退到全局 `openai_base_url`。
- 设置页的“拉取模型与能力”仅用于探测；真正持久化要依赖设置字段写回（例如选择模型、回填能力开关）。

如果希望重新以 `.env` 为准：

- 停掉后端后删除 `services/ai/data/runtime_settings/default.json`，再重启后端。
- 重启后会用当前环境变量重新生成 runtime settings 基线。

## 常用脚本

在仓库根目录执行：

```bash
npm run dev:web      # 启动前端
npm run build:web    # 构建前端
npm run lint:web     # 前端 lint
npm run test:ai      # 运行后端测试（unittest）
```

## 典型使用流程

### 流程 1：教材解析与调试

1. 在 Learning Workspace 上传 PDF。
2. 触发文档处理与解析。
3. 在计划生成页查看计划轮次和状态反馈，必要时结合后端数据目录中的调试产物排查。

### 流程 2：生成学习计划

1. 获取文档 planning context。
2. 触发学习计划生成（支持流式）。
3. 在计划面板查看 overview、主题与任务，并可回看历史计划。

### 流程 3：进入学习对话

1. 创建/恢复 Study Session。
2. 在章节上下文中发起提问。
3. 使用返回的结构化信息与 Character Event 进行学习交互。

## 数据与调试产物

后端本地数据主要位于 `services/ai/data/`：

- `documents.json`：文档元信息
- `plans.json`：学习计划记录
- `sessions.json`：学习会话记录
- `document_debug/`：解析调试产物
- `document_process_stream/`：文档处理流式日志
- `learning_plan_stream/`：计划生成流式日志
- `planning_trace/`：计划模型 trace

## 文档导航

- `docs/README.md`：文档索引
- `docs/user_manual.md`：完整功能使用手册（逐页逐部件）
- `docs/architecture.md`：架构说明
- `docs/api-reference.md`：API 参考
- `docs/parsing-and-planning-data-flow.md`：解析与规划数据链路
- `docs/frontend-learning-workspace.md`：前端学习工作台职责拆分
- `AGENTS.md`：仓库扫描快照、入口与开发约定
- `TODO.md`：当前迭代任务

## 常见问题

### 1) 前端无法请求后端

- 检查后端是否运行在 `http://127.0.0.1:8000`。
- 若后端地址不同，设置 `NEXT_PUBLIC_AI_BASE_URL` 后重启前端。

### 2) LiteLLM 上游返回内容异常或 `chat_model_invalid_payload`

- 先提高 `OPENAI_CHAT_MAX_TOKENS`（例如 1600 或 2400）。
- 再检查当前上游或代理的输出是否能被 LiteLLM 稳定映射到 OpenAI Chat Completions 结构。
- 同时确认 `OPENAI_TIMEOUT_SECONDS` 是否足够。

### 3) 计划结果看起来不稳定

- 先用 `VIBE_LEARNER_PLAN_PROVIDER=mock` 做链路验证。
- 再切换到 `litellm` 比较差异，结合 trace 定位提示词、模型参数或上游兼容性问题。

## 贡献建议

- 修改前后端接口时，同步更新共享协议与 API 文档。
- 新增后端路由时，保持前端客户端与模型定义一致。
- 涉及解析、规划、调试数据结构变更时，建议同时更新对应 docs。

## 许可证

本项目采用仓库内 LICENSE 指定的许可证。
