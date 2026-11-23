# 项目文档

本目录维护 Vibe Learner 当前的架构设计、领域契约、前端规范、Harness 工程手册与运维说明。未完成事项统一由根目录 [TODO.md](../TODO.md) 维护，开发铁律见 [AGENTS.md](../AGENTS.md)。

## 系统总览与工程规范

| 文档 | 内容 |
| --- | --- |
| [用户手册](user_manual.md) | 应用内 `/manual` 功能手册入口与维护位置 |
| [系统架构](architecture.md) | Monorepo 结构、运行时形态、核心边界、主流程与存储布局 |
| [关键入口清单](entry-points.md) | 按子域整理的代码入口、模块与所有权 |
| [工程机制与约定](conventions.md) | 契约分层、Harness、提交所有权与持久化约定 |
| [数据流分层与兜底责任](data-flow-layers.md) | 外部输入 → 归一化 → 域模型 → 持久化 → API DTO → 前端 decode → UI 职责边界 |
| [代码风格门禁](code-style.md) | ESLint、Ruff、Prettier、基线管理与 CI 检查 |

## 核心业务域

| 文档 | 内容 |
| --- | --- |
| [教材解析与入库链路](document-pipeline.md) | 上传输入上限、PDF/OCR 解析、Study Unit 清洗、断点续跑、印刷页对照与单元修订 |
| [学习计划链路与契约](learning-plan.md) | Planning Context、6 个规划工具、Prompt 与文本契约、物理页范围、计划修订与可观测性 |
| [学习会话与对话恢复](study-session.md) | 章节与排期术语、Session 作用域、交互题判分、原文记忆指令、输出语言与浏览器恢复协议 |
| [Tavern 多角色互动](tavern.md) | 房间/参与者/消息/Run/Step 存储模型、调度顺序、子重试、租约恢复与传输取消 |
| [场景编辑器（Scene Setup）](scene-setup.md) | 层级场景结构、提案与保存契约、可复用节点库与前端数据流 |
| [模型运行时行为与边界](model-runtime.md) | Provider 路由与重试、记忆与引用、可选 PDF 版面候选、Persona/OCR/Tavern 运行约束 |

## Harness 工程手册

| 文档 | 内容 |
| --- | --- |
| [Harness 总览](harness/README.md) | 统一生命周期、工作流索引、上限辨析、模型输出所有权与权威入口 |
| [配置与预算](harness/configuration.md) | 配置优先级、可编辑参数范围、输出 token 上限、调用次数与 Manifest 预算 |
| [数据库映射](harness/database.md) | 共享 Harness 表、领域表映射与恢复状态语义 |
| [各工作流手册](harness/README.md#用户工作流索引) | [Document](harness/document-processing.md) · [Planning](harness/planning.md) · [Persona](harness/persona-generation.md) · [Scene](harness/scene-generation.md) · [Study Chat](harness/study-chat.md) · [Tavern](harness/tavern.md) |

## 前端规范

| 文档 | 内容 |
| --- | --- |
| [前端页面边界与分层](frontend-learning-workspace.md) | 路由分组、Provider 作用域、页面/Controller/Reducer/Data Lib 职责划分 |
| [前端设计基线](frontend-design-baseline.md) | 视觉方向、尺寸间距、颜色 Token、组件规范、响应式与可访问性 |
| [前端人工验收](frontend-manual-acceptance.md) | 本地浏览器冒烟与按域回归清单 |
| [页面命名与术语](page-vocabulary.md) | 标准页面名、区块命名、命名规则与核心数据术语 |

## 接口、诊断、性能与打包

| 文档 | 内容 |
| --- | --- |
| [API 参考（自动生成）](api-reference.md) | 从 FastAPI OpenAPI 自动生成的全部 HTTP 端点清单（勿手改） |
| [API 契约说明](api-contracts.md) | 响应版本与兼容规则、NDJSON 流信封、各域写语义、CAS/幂等与错误码 |
| [诊断与审计体系](diagnostics.md) | 事件采集、分类关联、存储配额与回收、桌面原生 Spool、审计统计与导出边界 |
| [性能预算与基准](performance-budgets.md) | Web 生产包门禁、Harness 运行时预算、分页/启动/读取约束与本地基准命令 |
| [桌面打包与发布](desktop-packaging.md) | Tauri 桌面端本地构建、离线 OCR 打包、Sidecar、预览签名与 Release 流程 |

## 验证边界

`npm run check` 与 `npm run test:baseline` 验证的是**实现不变量**：代码风格、共享契约类型、Web 类型、API 参考同步、Harness 生命周期、提交证据、领域规则与前端解码契约。

自动化基线不替代真实模型输出质量、教学效果、跨平台桌面环境或线上 Provider 延迟评估；这些维度需通过各自的人工验收或线上观测确认。
