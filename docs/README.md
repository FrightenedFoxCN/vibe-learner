# 项目文档

未完成工作统一由 [TODO](../TODO.md) 索引；模型质量的详细任务与证据维护在[独立质量 TODO](quality/TODO.md)。本目录保留当前架构、接口、操作手册和可执行预算；历史审计、验收日志及阶段推进记录通过 Git 历史查询。

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
| [计划修订](plan-revision.md) | Plan CAS、修订预览、接受/拒绝、历史回滚与恢复 |
| [计划文本契约](plan-text-contract.md) | 面向学习者的文本字段语义 |
| [模型运行时质量](model-runtime-quality.md) | 已采用的规划、记忆、多模态和 Provider 边界 |
| [规划 Prompt 契约](learning-plan-prompt-contract.md) | Prompt 结构和模型输入 |
| [学习工作区](frontend-learning-workspace.md) | Plan/Study 前端职责 |
| [前端测试边界](frontend-test-boundaries.md) | 独立数据/Hook/组件模块与生产浏览器验收 |
| [后端测试边界](backend-test-boundaries.md) | 领域契约、生命周期、事务与进程中断门 |
| [场景编辑器](scene-setup.md) | 层级场景和保存结构 |

修改前先阅读对应领域文档及 [AGENTS](../AGENTS.md)。未完成任务由根 TODO 索引，模型质量细项只维护在独立质量 TODO；已完成的阶段计划、逐日进展和重复审查记录通过 Git 历史查询，不在当前目录重复维护。

## 发布与验收

- [0.3.4 发布记录](releases/0.3.4.md)：模型运行时质量修复、采用范围与研究接手入口。

- [0.3.3 发布记录](releases/0.3.3.md)：完成事项、证据入口与保留限制。
- [启动性能协议](performance/backend-startup-v1.md)、[房间分页 HTTP](performance/tavern-room-http-v1.md)、[React 渲染](performance/tavern-room-react-v1.md)：可重放测量与原始样本。
- [尚未完成的 PostgreSQL / 制品重放验收](plans/postgres-replay-independent-acceptance-2026-09-11.md)。
- [用户手册验收进度](plans/acceptance-audit-2026-09-11.md)。
- [诊断测量基线](performance/diagnostic-local-baseline-v1.md)：诊断存储与导出协议。

原始结果保留在 `acceptance/`、`performance/` 和 `plans/acceptance/`；保留证据不等于扩大其模型、平台或独立性范围。

## 模型质量研究

[Agentic design 与 ACL 2025/2026 研究](quality/agentic-design-research-2026-09-12.md)将外部结果对应到现有质量子任务；[M3 高并行探索计划](quality/m3-parallel-exploration-2026-09-12.md)按首日 2000M tokens 上限、最短决策时间安排并发与证据产出。首批[本地诊断](quality/evidence/agentic-preflight-local-2026-09-12.json)已执行，随后已完成[独立实验运行器](../tools/model-quality/README.md)、领域接入预检与[真实容量测量](quality/evidence/m3-live-concurrency-capacity-2026-09-12.json)：4 并发通过，8 并发触发 429；独立质量确认仍待完成。

[研究接手摘要](quality/research-summary.md)说明已采用结论、未采用策略和复现入口；[质量研究索引](quality/minimax-m3-v1.md)保留旧链接。未关闭问题的混合实验与原始失败继续保留，纯已完成过程通过 Git 查询。
