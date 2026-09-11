# PostgreSQL 与受保护制品独立验收（2026-09-11）

执行者：独立子智能体；未修改产品代码，未接触用户数据库或真实模型 provider。阅读了根 AGENTS.md、Harness 架构、统一 TODO 及架构重构归档。

## 账目核对

原代码解耦归档（Git `e13fd02:docs/plans/architecture-refactor.md`）的 PostgreSQL 22 项准确对应 `test_transaction_validation`（16）和 `test_tavern_reference_scope`（6）。范围是写集合追踪、引用约束和事务提交/回滚路径，使用 `create_schema()` 建库；既不运行完整 Alembic 升级，也不覆盖领域 CAS 或服务/数据库重启。因此它与仍开放的 `REL-POSTGRES-001` 不冲突，不能以归档 22 项直接关闭该待办。

## 本轮 PostgreSQL 实测

使用本机已有 `postgres:17-alpine` 镜像，启动独立容器 `vibe-independent-pg-20260911`，仅绑定 `127.0.0.1:55439`。测试库为新建 `acceptance`。本轮创建的容器在完成后清理。

| 验收 | 结果 |
| --- | --- |
| 复跑原事务/引用测试 | 22 项通过，3.576 秒；各用独立 schema |
| 空库完整 Alembic upgrade head | 通过；实际读回版本 `20260909_0019` |
| 独立 Study Session 并发 CAS | 两个线程由 Barrier 强制同时读取 revision=0，再分别追加不同 prepared Study Unit；最终 revision=2，两个值均保留 |
| 独立事务异常回滚 | 结构化 UPDATE 后注入 RuntimeError；权威 Session 完整记录与注入前一致 |
| PostgreSQL 容器重启后新进程读回 | revision=2、两个 CAS 写入均保留 |

复现脚本：[independent_postgres_20260911.py](acceptance/independent_postgres_20260911.py)。从 `services/ai` 执行，显式设置 `VIBE_INDEPENDENT_POSTGRES_URL` 和 `PYTHONPATH=.`；首次执行写入/CAS/回滚，重启隔离 PostgreSQL 后加参数 `read` 只读检查。脚本会删除并重建 `independent-cas` 测试 Session，只允许在专用一次性数据库执行。

`REL-POSTGRES-001` **仍不建议整体关闭**：本轮补足了空库迁移、一个真实并发 CAS、事务回滚和数据库重启持久性，但尚未移植 SQLite 完整领域恢复矩阵。剩余包括带数据旧版本迁移、Document/Planning/Study/Tavern admission/lease/commit 中断窗口、应用 HTTP 重启 read-back，以及需要支持时的迁移降级/再升级。数据库重启后的普通记录持久性不能代替操作不确定态恢复。

## 本轮受保护制品复核

新增独立矩阵复用生产 `HarnessProposalRuntimeService._register_snapshot`、`AuthorizedJsonArtifactResolver`、`HarnessArtifactRepository` 和 `_decode_protected_json`。Document 与 Planning 从既有隔离领域 fixture 经真实 operation admission 获取 binding，Persona/Scene 从各自 generic workflow admission 获取 binding；所有内容为合成测试数据。没有新增 Harness 基础设施。

四个领域（Document、Planning、Persona、Scene）均验证：

- 新建 Database/连接及 repository 后，从持久化 artifact 精确恢复嵌套 Unicode 内容。
- 跨 operation 读请求拒绝；缺 grant 在 resolver 拒绝；不匹配 contract version 拒绝。
- 当前版本 envelope 可解码，旧/未来未知版本 envelope 均 fail closed。
- grant 过期返回 typed `expired`。
- 仅在测试库移除不可变触发器并篡改 payload 后返回 `digest_mismatch`。
- 通过正式删除入口删除后返回 `not_found`。

独立测试矩阵：1 个 unittest，4 个领域 subtest，全通过。复现：在 `services/ai` 下运行 `PYTHONPATH=. UV_CACHE_DIR=/tmp/vibe-independent-uv uv run --offline python ../../docs/plans/acceptance/independent_replay_20260911.py`。

另外复跑 `test_harness_artifact_resolver`、`test_harness_runtime`、`test_harness_broad_commit_binding`：**29 项通过，1.685 秒**。既有 resolver 测试补充 artifact 本身 retention expiry、跨 principal、revocation、digest-only、不泄漏内容的审计与 eval bridge 校验。

`REL-REPLAY-001` **建议保持开放并缩小剩余范围**：本轮独立证明四领域共享解析/授权边界对当前契约和常见破坏情形有效。尚未使用真实历史产物完成跨版本迁移/重放，也未验证原进程结束且旧 15 分钟 grant 过期后，如何重新授权并经完整领域 adapter 重放历史任务。当前结果是持久化快照解析与拒绝矩阵，不是完整历史工作流重放认证。未发现本轮覆盖范围内的产品失败。

## 验收脚本修正记录

首轮脚本用错 Document artifact enum，修正为生产 `DOCUMENT_UPLOAD` 后通过。首轮 PG 回滚脚本使用 raw SQL，被现有 `transaction_opaque_sql_requires_structured_dml` 正确拒绝；改为结构化 SQLAlchemy UPDATE 后完成异常回滚验收。这两项是验收脚本问题，不是产品缺陷。
