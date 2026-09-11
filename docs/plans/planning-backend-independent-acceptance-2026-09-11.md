# Planning 后端独立验收（2026-09-11）

范围：Plan revision/CAS、持久修订操作、Study confirmation 原子事务、迁移 0020/0021、Harness 提交与恢复绑定。执行者为独立子智能体，独立测试与实现测试分开。未访问用户数据库，未调用真实模型 provider。

## 结果

**SQLite 11 项、实际 PostgreSQL 17 共 11 项全部通过。** 每个平台包括 10 项独立并发/对抗/事务测试与 1 项带数据历史迁移测试。

| 独立场景 | 验证结果 |
| --- | --- |
| Barrier 强制两个客户端从同一 revision 写入 | 一个 revision=1 成功，一个 HTTP 409；无覆盖 |
| 并发重复批准 Study confirmation | Plan revision 与 Session revision 均只增加一次 |
| Plan 写完后、Session confirmation 更新时注入异常 | Plan 内容、revision、历史记录全部回滚；确认仍 pending |
| 修订生成后并发更新 Plan，再接受旧修订 | conflict；最新 Plan 内容保留 |
| 响应结果重新连接查询、同 key 重发 | 与持久结果一致；provider 只调用一次 |
| 接受提交期间 terminal trace 写入异常 | Plan 保持旧 revision，无 decision receipt；失败终态证据存在 |
| 将另一 operation 的 prepared output 用于本 operation 提交 | 绑定校验拒绝，两个 operation 及 Plan 均零写入 |
| 将另一 operation 的 preview receipt 写入本 operation | 查询 fail closed |
| 超时恢复已有 runtime trace，随后迟到提交 | domain 与 trace 同事务终态；迟到提交被 fence |
| 超时恢复生成 terminal trace 时注入异常 | domain status 与 runtime state 均回滚 |
| 成功接受、重复接受、修改进度后历史回滚 | 重复接受不重复提交；回滚生成新 revision，保留当前进度和 schedule ID；两个成功 trace 均 committed |
| 带历史创建回执的 0019 数据升级至 0021，再修改 Plan | 原 committed projection digest 不变，原 receipt 严格 read-back 仍通过，Plan revision 从 0 增至 1 |

表格拆开了个别 unittest 内的多个断言，因此行数不等于测试数。

## 本轮发现并修复的问题

1. `PlanRevisionRepository.get()` 原先只将超时 operation 改成 uncertain/failed，已存在的 v3 runtime trace 仍停在 claimed。独立测试稳定复现后，主智能体授权本子智能体修复 get/恢复辅助方法。现在以数据库时间判断超时，在同一事务中 fence domain，再按现有 trace 的 state/token/count/updated_at 写入失败终态及 digest。恢复不重新发起 provider 调用。独立注入验证恢复写 trace 失败时 domain fence 也回滚。
2. `response(row)` 原先未校验 receipt 与 operation 行的 scope，将另一个 operation 的合法 preview receipt 写入后仍可查询成功。主智能体补齐绑定校验后，独立测试在 SQLite/PostgreSQL 均通过。

第一项修复由发现该问题的子智能体实施；测试用例在修复前编写并失败，修复后通过，但这一项不应被描述为另一个独立作者对修复代码完成了二次复核。

## 可复现命令

在仓库的 `services/ai` 目录执行。

SQLite：

```bash
UV_CACHE_DIR=/tmp/vibe-independent-uv uv run --offline python -m unittest \
  tests.test_plan_revision_independent \
  tests.test_plan_revision_migration_independent -v
```

PostgreSQL 并发/事务测试，每个测试创建并清理独立 schema：

```bash
VIBE_TEST_POSTGRES_URL='<专用一次性 PostgreSQL URL>' \
UV_CACHE_DIR=/tmp/vibe-independent-uv uv run --offline python -m unittest \
  tests.test_plan_revision_independent -v
```

PostgreSQL 带数据迁移测试需要**独立空数据库**，会在其中先迁移到 0019、插入合成历史数据，再升级 head；不得指向用户数据库：

```bash
VIBE_INDEPENDENT_MIGRATION_URL='<专用空 PostgreSQL URL>' \
UV_CACHE_DIR=/tmp/vibe-independent-uv uv run --offline python -m unittest \
  tests.test_plan_revision_migration_independent.IndependentMigrationTests -v
```

本轮使用本机已有 `postgres:17-alpine` 镜像，容器名 `vibe-plan-audit-pg-20260911`，仅绑定 `127.0.0.1:55439`，数据库 `acceptance`。完成后容器已删除。迁移测试分别在 SQLite、PostgreSQL 独立执行；PostgreSQL 并发测试按前 8 项、补充 2 项分批执行。

## 限制

- provider 使用 Mock；不证明真实模型修订质量、费用或延迟。
- 历史迁移数据来自生产创建路径生成的合成 fixture，按 0019 表结构插入；不是用户真实历史数据库备份。
- 验证的是持久查询、新 Database/连接、事务失败注入和实际数据库并发；未新增 OS kill、HTTP 服务进程重启或桌面断网验收。
- 修订内容限制为已有 schedule 目标的标题、focus、顺序及计划文案；本轮验证了这种范围下的 ID/进度保留，不证明任务增删或 Study Unit 替换。
- 不代替仓库整体 release、所有领域 PostgreSQL 恢复矩阵或前端交互验收。

## 收尾边界复核

在后续两处修改后，重新执行上述 SQLite 独立测试：11 项通过（0.960 秒）。只读确认 `admit()` 与 `begin_accept()` 均使用 `_database_utc_now(session)`，与超时恢复同源；接受路径在 finalizer 前刷新数据库 Plan 行，并验证未删除且与 candidate 精确相等。未发现新增问题。

另外新增 SQLite 专项对抗测试：通过临时 AFTER UPDATE 触发器在 Plan CAS 写入后将其标为 deleted。接受流程严格 read-back 拒绝，整个事务回滚，Plan revision 仍为 0，decision receipt 为空；1 项通过（0.101 秒）。本次累计 SQLite 12 项，PostgreSQL 仍为前述 11 项；按要求没有为这两处收尾改动再次启动 PostgreSQL。

## 浏览器发现的进度投影问题复验

针对提取到 `models/plan_progress.py` 的共享纯投影，独立复核并新增两项测试：

- 旧 Plan 的默认 summary 为 0 时，修订 preview 的 base 会得到真实 schedule 总数与 Study Unit 进度；数据库 Plan payload、revision 与 revision 0 历史 payload 均保持原样，不触发隐式写入。
- 模型 proposal 将任务重排并改变 focus 后，实际接受结果与正常 `LearningPlanService.require_plan()` 查询投影完全相等；`study_unit_progress.schedule_ids` 顺序和 `objective_fragment` 随之更新。随后增加真实进度、回滚到 revision 0，接受结果仍与正常查询完全相等，且保留已完成状态和 50% 进度。

SQLite 独立合集 **14 项通过（1.383 秒）**。另增强原迁移测试，确认旧创建回执在 revision admission 的投影规范化之后仍精确相等、当前 Plan 未被写入；该增强测试 **1 项通过（0.259 秒）**。最新改动未重复 PostgreSQL；原 PostgreSQL 11 项证据仅对应此前版本。
