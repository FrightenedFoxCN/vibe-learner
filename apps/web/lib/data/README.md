# 前端数据入口说明

`apps/web/lib/data/` 按领域资源提供前端唯一的数据访问入口；底层传输与严格解码分别由 `apps/web/lib/api/*.ts` 与 `apps/web/lib/*-decode.ts` 承担。页面与组件层优先从 `lib/data/*` 导入，不按页面另建重复的 API 封装。

## 领域模块清单

| 模块 | 职责 | 主要消费者 |
| --- | --- | --- |
| `documents.ts` | 文档上传、处理、状态/调试/上下文/Trace 读取、Study Unit 改名与 Checkpoint 读回 | `use-learning-workspace-controller.ts`、`use-document-debug-data.ts` |
| `learning-plans.ts` | 学习计划 CRUD、流式生成、进度更新、规划问题作答与计划修订 | `use-learning-workspace-controller.ts`、`use-plan-generation.ts`、`use-plan-mutations.ts` |
| `study-sessions.ts` | Study Session CRUD、对话与附件发送、交互题提交与计划确认 | `use-learning-workspace-controller.ts`、`use-study-*.ts` |
| `personas.ts` | Persona CRUD、辅助编辑与资产清单读取 | `use-persona-*.ts`、`use-scene-rewrite.ts`、`use-workspace-libraries.ts` |
| `persona-cards.ts` | Persona Card CRUD 与生成 | `use-persona-card-generation.ts` |
| `scenes.ts` | 场景草稿、已保存场景库、可复用节点与场景生成 | `use-scene-*.ts`、`use-workspace-libraries.ts` |
| `tavern.ts` | Tavern 房间分页/详情、Run/恢复链查询、回合发送、重试、恢复、取消与归档 | `lib/tavern-workspace-ports.ts`、`use-tavern-*.ts` |
| `runtime-settings.ts` | 运行时设置读写、会话密钥管理与模型连通性探测 | `runtime-settings-provider.tsx`、`use-settings-controller.ts` |
| `model-tools.ts` | 模型工具开关配置读写 | `app/sensory-tools/page.tsx`、`use-document-debug-data.ts` |
| `model-usage.ts` | Token 与调用统计读取 | `app/model-usage/page.tsx` |

Settings、Model Tools、Model Probe 与 Model Usage 的响应均通过 `runtime-settings-decode.ts`、`model-tools-decode.ts`、`model-usage-decode.ts` 从 `unknown` 严格解码。

## 页面资源依赖

| 路由 | 消费的领域数据模块 |
| --- | --- |
| `/`、`/manual` | 无直接业务 CRUD 请求 |
| `/plan` | `documents.ts`、`learning-plans.ts`、`study-sessions.ts`、`personas.ts`、`scenes.ts`（经 `LearningWorkspaceProvider`） |
| `/study` | 同 `/plan`（共享 `(learning)` 路由组上下文），另按 ID 打开 PDF 与附件预览 |
| `/persona-spectrum` | `personas.ts`、`persona-cards.ts` |
| `/scene-setup` | `scenes.ts`、`personas.ts`（文本改写复用 Persona 辅助接口） |
| `/tavern` | `tavern.ts`、`personas.ts`、`scenes.ts` |
| `/settings` | `runtime-settings.ts` |
| `/sensory-tools` | `model-tools.ts` |
| `/model-usage` | `model-usage.ts` |

## 全局运行时消费者

- `hooks/use-learning-workspace-controller.ts`：`/plan` 与 `/study` 的跨页编排核心，汇总 `documents`、`learning-plans`、`study-sessions`、`personas`、`scenes`。
- `hooks/use-document-debug-data.ts`：全局 Debug Overlay 的文档解析与工具配置数据源。
- `components/runtime-settings-provider.tsx`：全局运行时配置上下文。

## 边界规则

- 按**数据结构归属**选择导入模块，而非按当前页面名称拆分副本（例如不在 `lib/data/` 中新建 `plan-api.ts` 或 `study-api.ts`）。
- 新增页面级数据请求统一接入对应领域模块，并经由领域严格解码器校验后进入状态层。
