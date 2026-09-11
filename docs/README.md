# 项目文档

未完成工作统一维护在 [TODO](../TODO.md)。本目录保留当前架构、接口、操作手册和可执行预算；历史审计、验收日志及阶段推进记录通过 Git 历史查询。

| 文档 | 用途 |
| --- | --- |
| [用户手册](user_manual.md) | 页面功能与使用流程 |
| [系统架构](architecture.md) | Web、AI、共享契约、桌面与存储边界 |
| [Harness 架构图](harness-architecture.md) | 可靠性生命周期、制品/效果边界与代码入口 |
| [Tavern 架构](tavern-architecture.md) | 房间、消息、调度、事务和恢复 |
| [API 参考](api-reference.md) | HTTP 和流式协议 |
| [诊断审计统计](diagnostic-audit.md) | 统计分组、分位数、去重与未知数据语义 |
| [诊断存储策略](diagnostic-storage-policy.md) | 已验证的分库配额、留存与恢复例外；200 MiB 非安装硬上限 |
| [原生计数检查点](diagnostic-native-counter.md) | 双槽格式、旧格式迁移、损坏恢复及降级行为 |
| [桌面打包](desktop-packaging.md) | 本地构建、sidecar、Vault 与发布配置 |
| [性能预算](performance-budgets-v1.md) | Room 分页、Harness 字节/调用/时延门 |
| [解析与规划数据流](parsing-and-planning-data-flow.md) | Document → Study Unit → Learning Plan |
| [章节与日程](study-chapter-and-schedule.md) | 领域术语和 Session 范围 |
| [计划文本契约](plan-text-contract.md) | 面向学习者的文本字段语义 |
| [规划 Prompt 契约](learning-plan-prompt-contract.md) | Prompt 结构和模型输入 |
| [学习工作区](frontend-learning-workspace.md) | Plan/Study 前端职责 |
| [前端测试边界](frontend-test-boundaries.md) | 独立数据/Hook/组件模块与生产浏览器验收 |
| [后端测试边界](backend-test-boundaries.md) | 领域契约、生命周期、事务与进程中断门 |
| [场景编辑器](scene-setup.md) | 层级场景和保存结构 |

修改前先阅读对应领域文档及 [AGENTS](../AGENTS.md)。除用户指定的下列专项计划外，不另建 roadmap 或复制待办列表；新评测数据放在版本化 fixture 或运行产物中，避免重新积累日期命名的过程文档。

## 版本与专项计划

- [代码解耦重构](plans/architecture-refactor.md)：分步重构顺序及验收边界。
- [统一 Logging 与 Debug 归档](plans/unified-debug-completion.md)：四阶段完成、最终验收、提交与限制；[实施计划](plans/unified-debug.md)保留过程记录。

0.3.1（2026-09-10）登记七项代码解耦重构：事务作用域、应用生命周期、Study 应用服务、Harness 契约、Provider 能力、前端职责和模块化测试边界。包含 Persona/Scene 编辑反馈与 Study 恢复相关改进。最终验收通过 635 项后端测试、13 个 eval suite、共享/Web 检查与生产构建、193 项恢复测试、23 项生产浏览器测试，以及事务阶段 22 项本机 PostgreSQL 17 测试。桌面安装包以远端发布流水线结果为准；独立 UX 复核仍在 TODO 跟踪。

0.3.2（2026-09-11）登记统一 Logging 与 Debug：跨流程诊断关联、全局 Debug 时间线、Harness 索引、审计统计、诊断导出与桌面原生计数检查点。实施已完成并归档，验收范围和限制见[最终归档](plans/unified-debug-completion.md)。产品及其他验收任务继续维护在根 TODO。

- [Diagnostic local measurement baseline](performance/diagnostic-local-baseline-v1.md): reproducible middleware/storage/export timings and pinned-reader WAL observations.
