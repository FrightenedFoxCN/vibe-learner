# 项目文档

未完成工作统一维护在 [TODO](../TODO.md)。本目录保留当前架构、接口、操作手册和可执行预算；历史审计、验收日志及阶段推进记录通过 Git 历史查询。

| 文档 | 用途 |
| --- | --- |
| [用户手册](user_manual.md) | 页面功能与使用流程 |
| [系统架构](architecture.md) | Web、AI、共享契约、桌面与存储边界 |
| [Harness 架构图](harness-architecture.md) | 可靠性生命周期、制品/效果边界与代码入口 |
| [Tavern 架构](tavern-architecture.md) | 房间、消息、调度、事务和恢复 |
| [API 参考](api-reference.md) | HTTP 和流式协议 |
| [桌面打包](desktop-packaging.md) | 本地构建、sidecar、Vault 与发布配置 |
| [性能预算](performance-budgets-v1.md) | Room 分页、Harness 字节/调用/时延门 |
| [解析与规划数据流](parsing-and-planning-data-flow.md) | Document → Study Unit → Learning Plan |
| [章节与日程](study-chapter-and-schedule.md) | 领域术语和 Session 范围 |
| [计划文本契约](plan-text-contract.md) | 面向学习者的文本字段语义 |
| [规划 Prompt 契约](learning-plan-prompt-contract.md) | Prompt 结构和模型输入 |
| [学习工作区](frontend-learning-workspace.md) | Plan/Study 前端职责 |
| [场景编辑器](scene-setup.md) | 层级场景和保存结构 |

修改前先阅读对应领域文档及 [AGENTS](../AGENTS.md)。除用户指定的下列专项计划外，不另建 roadmap 或复制待办列表；新评测数据放在版本化 fixture 或运行产物中，避免重新积累日期命名的过程文档。

## 下一版本专项计划

- [代码解耦重构](plans/architecture-refactor.md)：分步重构顺序及验收边界。
- [统一 Logging 与 Debug](plans/unified-debug.md)：独立任务、诊断链路和数据留存设计。

两份计划均为待实施设计；产品及其他验收任务继续维护在根 TODO。
