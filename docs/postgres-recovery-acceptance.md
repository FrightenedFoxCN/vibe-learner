# PostgreSQL 迁移与恢复验收

2026-10-30 在隔离 PostgreSQL 17.11（Alpine / aarch64）上补齐 `REL-POSTGRES-001` 的剩余范围。原始结果见 [postgres-recovery-2026-10-30.json](acceptance/postgres-recovery-2026-10-30.json)，执行入口为 `services/ai/tests/acceptance/postgres_recovery_probe.py`。本次由主智能体执行，使用合成数据和 mock provider；进程外 HTTP 读回及数据库约束检查与故障 worker 分离。不是独立人工审查、真实模型质量或跨平台认证。

## 覆盖与结果

| 范围 | 实测证据 |
| --- | --- |
| 带数据旧版迁移 | 历史 `e3a03a9` 的 Alembic `20260914_0022` 升级到 `20261029_0026`；Document、Planning、Study、Tavern 可读；三类原 receipt digest 保持不变 |
| Document 中断 | admission 后、成功 commit 后，以及 Document/debug/terminal 提交中的 4 个语句窗口；真实进程以 73 突然退出，未提交状态回滚，已提交结果保留 |
| Planning 中断 | provider 前、provider 已发出、commit 后，以及 Document/debug/trace/Plan/terminal 事务中的 6 个窗口；不确定态不重发 provider |
| Study 中断 | admitted / claimed / issued 三个阶段，以及 Session、trace、receipt 更新后和实际 commit 后 4 个窗口；前三个事务内窗口回滚为 revision 0 / 零 Turn / `uncertain`，commit 后为 revision 1 / 一个 Turn / `committed` |
| Tavern 中断 | 六人名册、四个调度目标；admission 后和首个 actor 已提交、下一个 lease 已取得时退出；过期 lease 接管仅执行剩余步骤，保留原 Message/identity，重复 resume 零新增调用 |
| 并发与回滚 | Document / Plan 同 revision 并发各一个成功、一个冲突；Document/debug 标题一致；Study 两个并发写入均保留，revision 2；注入异常后完整 Session 等于回滚前 |
| 不可变边界 | runtime 的 `context_payload` 与 effect 的 `target_refs` 在 terminal 及非 terminal 状态均拒绝篡改；非 terminal 状态允许等值 JSON 更新 |
| 应用进程重启 | 两个全新 uvicorn 进程通过公开 GET 读回历史 Document status/debug、Planning/Study receipt 和 Tavern Run；另外四个进程读回 Study commit 中断结果；模型方法被禁止，实际调用数为零 |
| 数据库重启 | `pg_postmaster_start_time()` 从 `2026-10-29T18:09:04.217539+00:00` 变为 `2026-10-29T18:29:13.130755+00:00`；全新 HTTP 进程重新读回上述领域/中断结果及 revision 2 的 CAS Session |

共 24 个真实进程退出窗口：Document 6、Planning 9、Study 7、Tavern 2。测试复用 Wave45 的领域恢复断言，PostgreSQL scope 通过真实 Alembic 建库，不用 `create_all` 或 SQLite 替代。测试只推进持久化过期时间来触发恢复，不等待完整 lease 时长。

历史数据来自**未修改的旧应用代码在 SQLite 上生成的合成记录**，再按外键顺序精确恢复进旧 Alembic PostgreSQL schema，保留 SQL NULL / JSON null 区别后升级。原因是旧 PostgreSQL 触发器本身存在 JSON 比较缺陷，无法直接生成这些记录。因此本项证明旧应用实际记录形状在 PostgreSQL 上的带数据升级，不声称采集过真实用户旧 PostgreSQL 库。

## 验收修复

`20261029_0026_postgres_json_guards.py` 修复两个 PostgreSQL trigger function：旧 Alembic 列为 `JSON`，直接 `IS DISTINCT FROM` 会报 `operator does not exist: json = json`。比较时显式转换成 `jsonb`，保持原不可变字段集合、错误码、payload 和 digest。SQLite 无操作；降级保留等价比较修复，不恢复不可用的运算符。

历史 v3 context 以前只能匹配当前组件版本，升级后读取旧 Study receipt 会报 `harness_context_component_version_mismatch`。现在 Python 与浏览器共同接受精确登记的七组历史 profile，来源为 `e3a03a9`、`d7edbf9`、`7bb6bf0` 的已审阅 manifest。四份旧应用生成的真实 trace 作为 golden fixture，仍验证原始 digest 和字段。未知版本、混搭版本仍拒绝；新 context 构造、新 runtime prepare 和非终态 claim 只允许当前 manifest，历史兼容不授权继续执行。

## 复现

先安装锁定依赖：根目录 `npm ci`，`services/ai` 内 `uv sync --frozen`。需要本机 Docker 和 PostgreSQL 17 镜像；只对一次性测试库运行：

```bash
docker run --name vibe-pg-recovery -e POSTGRES_PASSWORD=fixture -e POSTGRES_DB=acceptance -p 127.0.0.1:55439:5432 -d postgres:17-alpine
docker exec vibe-pg-recovery pg_isready -U postgres -d acceptance
```

等待 `pg_isready` 成功，再从根目录执行。保留相同 root 与 URL，按顺序运行：

```bash
PG_ACCEPTANCE_URL='postgresql+psycopg://postgres:fixture@127.0.0.1:55439/acceptance'
PG_ACCEPTANCE_ROOT="$(mktemp -d /tmp/vibe-postgres-recovery.XXXXXX)"
for phase in migration crashes study cas http guards; do
  npm run test:acceptance:postgres -- --database-url "$PG_ACCEPTANCE_URL" --root "$PG_ACCEPTANCE_ROOT" --phase "$phase" || break
done
docker restart --timeout 10 vibe-pg-recovery
docker exec vibe-pg-recovery pg_isready -U postgres -d acceptance
npm run test:acceptance:postgres -- --database-url "$PG_ACCEPTANCE_URL" --root "$PG_ACCEPTANCE_ROOT" --phase after_restart
```

再次等待 readiness 成功才运行 `after_restart`。最终 phase 要求旧版本迁移、完整 crash matrix、CAS、rollback、四组不可变检查和重启前 HTTP 证据齐全，才写入 `status: passed`。使用随机映射端口时，重启后先 `docker inspect` 确认实际端口，再更新 `PG_ACCEPTANCE_URL`；数据库重启会改变映射端口，不能复用旧端口。

保存 `$PG_ACCEPTANCE_ROOT/probe.json` 后清理，仅删除脚本创建且记录的 `vibe_pg_accept_<32 hex>` schema：

```bash
npm run test:acceptance:postgres -- --database-url "$PG_ACCEPTANCE_URL" --root "$PG_ACCEPTANCE_ROOT" --phase cleanup
docker rm -f vibe-pg-recovery
```

脚本限制 loopback PostgreSQL URL，并校验 schema 名称。schema marker 丢失时不会回退到 SQLite。实际验收的 26 个 schema（含调试失败时留下的隔离 scope）和专用容器已清理；没有用户数据库挂载或真实 provider 调用。

SQLite 迁移/runtime/context 专项原有 41 项回归、历史 context 的 3 项 Python / 1 项浏览器测试、8 项既有对抗解码检查、一个 SQLite 进程恢复测试、Web 类型和 changed-file style 门已通过。未运行完整后端测试或生产构建。[2026-09-11 独立报告](plans/postgres-replay-independent-acceptance-2026-09-11.md) 保留当时结果；受保护制品的完整历史 adapter 重放仍由 `TODO.md` 的 `REL-REPLAY-001` 跟踪。
