# 项目文档

未完成工作只由根 [TODO](../TODO.md) 维护。本目录保留当前架构、接口、操作手册、可执行预算和仍待关闭的验收协议；历史审计、实验数据、验收日志及阶段推进记录通过 Git 历史和对应本地实验分支查询。

| 文档 | 用途 |
| --- | --- |
| [用户手册](user_manual.md) | 页面功能与使用流程 |
| [系统架构](architecture.md) | Web、AI、共享契约、桌面与存储边界 |
| [Harness 工程手册](harness/README.md) | 按用户工作流整理的生命周期、数据库、模型约束、恢复与预算 |
| [Tavern 架构](tavern-architecture.md) | 房间、消息、调度、事务和恢复 |
| [Tavern 回应顺序验收](tavern-order-acceptance.md) | 真实后端逆序选择、房间恢复和部分失败子重试的证据与复现 |
| [Tavern 请求取消](tavern-provider-cancellation.md) | 可取消传输能力、本地连接/线程释放、数据库取消与上游计费边界 |
| [API 参考](api-reference.md) | HTTP 和流式协议 |
| [诊断审计统计](diagnostic-audit.md) | 统计分组、分位数、去重与未知数据语义 |
| [诊断存储策略](diagnostic-storage-policy.md) | 已验证的分库配额、留存与恢复例外；200 MiB 非安装硬上限 |
| [原生计数检查点](diagnostic-native-counter.md) | 双槽格式、旧格式迁移、损坏恢复及降级行为 |
| [桌面打包](desktop-packaging.md) | 本地构建、sidecar、Vault 与发布配置 |
| [性能预算](performance-budgets-v1.md) | Room 分页、Harness 字节/调用/时延门 |
| [前端资源读取边界](performance/web-resource-reads-v1.md) | 历史数据下 focus、跨页与恢复的请求计数门和原始 before/after |
| [解析与规划数据流](parsing-and-planning-data-flow.md) | Document → Study Unit → Learning Plan |
| [章节与日程](study-chapter-and-schedule.md) | 领域术语和 Session 范围 |
| [计划修订](plan-revision.md) | Plan CAS、修订预览、接受/拒绝、历史回滚与恢复 |
| [OCR 保存进度](document-checkpoints.md) | 逐页/阶段 checkpoint、显式续跑、重启与查询读回 |
| [文档输入上限](document-input-limits.md) | 上传字节/物理页、不可分割文本块和可恢复拒绝 |
| [输出语言偏好](output-language.md) | Planning/Study 的显式语言、自动模式、操作绑定和持久化 |
| [Study 请求恢复](study-recovery.md) | 等待上限、有界查询、断网及终态刷新，不重放未知结果 |
| [物理页范围](planning-page-scope.md) | PDF 物理页输入、印刷标签对照、取证与提交范围 |
| [教材单元修订](study-unit-revision.md) | Planning 建议、独立确认、Document CAS 与查询恢复 |
| [计划文本契约](plan-text-contract.md) | 面向学习者的文本字段语义 |
| [模型运行时质量](model-runtime-quality.md) | 已采用的规划、记忆、多模态和 Provider 边界 |
| [规划 Prompt 契约](learning-plan-prompt-contract.md) | Prompt 结构和模型输入 |
| [学习工作区](frontend-learning-workspace.md) | Plan/Study 前端职责 |
| [代码风格门](code-style.md) | ESLint、Ruff、格式化、既有基线与 CI |
| [前端测试边界](frontend-test-boundaries.md) | 独立数据/Hook/组件模块与生产浏览器验收 |
| [后端测试边界](backend-test-boundaries.md) | 领域契约、生命周期、事务与进程中断门 |
| [PostgreSQL 迁移与恢复](postgres-recovery-acceptance.md) | 旧版本带数据迁移、24 个进程中断窗口、CAS、回滚与 HTTP / 数据库重启实测 |
| [历史受保护制品重放](historical-artifact-replay-2026-10-30.md) | 旧应用实际 artifact、历史合同、授权续期和 Document / Planning / Persona / Scene adapter 重放 |
| [场景编辑器](scene-setup.md) | 层级场景和保存结构 |

修改前先阅读对应领域文档及 [AGENTS](../AGENTS.md)。未完成任务只由根 TODO 维护；已完成的阶段计划、逐日进展、实验原始数据和重复审查记录不在当前目录重复维护。

## 发布与验收

- [0.3.5 发布记录](releases/0.3.5.md)：数学书页候选定位、真实书页证据、许可边界与发布门修复。

- [0.3.4 发布记录](releases/0.3.4.md)：模型运行时质量修复、采用范围与研究接手入口。

- [0.3.3 发布记录](releases/0.3.3.md)：完成事项、证据入口与保留限制。
- [启动性能协议](performance/backend-startup-v1.md)、[房间分页 HTTP](performance/tavern-room-http-v1.md)、[React 渲染](performance/tavern-room-react-v1.md)：可重放测量与原始样本。
- [PostgreSQL / 制品重放历史独立验收](plans/postgres-replay-independent-acceptance-2026-09-11.md)；PostgreSQL 后续范围见[迁移与恢复实测](postgres-recovery-acceptance.md)。
- [用户手册验收进度](plans/acceptance-audit-2026-09-11.md)。
- [诊断测量基线](performance/diagnostic-local-baseline-v1.md)：诊断存储与导出协议。

性能目录只保留当前可重放协议、预算及其必要基线；实验原始结果不作为主线文档长期维护。
