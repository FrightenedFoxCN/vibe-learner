# SCH-PLAN-CAS-001 完成记录

Plan 现为数据库权威聚合。全部现有写入口使用 revision CAS；Study confirmation 的 Plan 效果和 Session 决策同事务提交，重复批准不重复执行。普通读取只投影派生进度，不改写历史记录。旧 plans.json 仅供 insert-only 导入；删除 tombstone 防止旧文件恢复已删除计划。0020 为旧记录添加 revision=0，保留原始 payload 和创建回执摘要。

现代客户端传 expected_revision，旧客户端省略时保留有界 CAS 重试。Planning question 答案保存不再隐式调用模型覆盖整份计划；后续修订通过单独预览/接受流程执行。

验证：独立子智能体在 SQLite 和 PostgreSQL 17 验证同 revision 并发写入一胜一冲突、并发重复批准仅一次、Session 写入失败时 Plan/history 回滚。独立迁移测试确认既有创建回执仍可读回。仓库另保留独立于修订预览的 tests.test_learning_plan_cas 三项回归。

本项不声称完成整个 PostgreSQL 操作中断矩阵或原生平台验收；这些仍在统一 TODO 跟踪。
