# 后端测试边界

按受影响的领域和层级选用独立入口；聚合门禁保留完整覆盖。Python 由各脚本通过 `uv` 启动，测试数据库使用临时目录；事务专项可用 `VIBE_TEST_POSTGRES_URL` 指向隔离的 PostgreSQL schema。

| 入口 | 边界 |
| --- | --- |
| `npm run test:ai:transactions` | 数据库写集、引用作用域与完整审计；不启动 API/provider |
| `npm run test:ai:lifecycle` | 导入、应用启动/退出、实例隔离与恢复边界 |
| `npm run test:ai:migrations` | Alembic SQLite schema、升级与 eval admission；不执行模型 |
| `npm run test:ai:study:decode` | 完整嵌套 Study reply 解码及私有评分材料 |
| `npm run test:ai:study:application` | Study admission、CAS、effects、receipt、v3 trace 与故障恢复 |
| `npm run test:ai:study:api` | 公开响应及失败投影、服务端私有字段隔离 |
| `npm run test:ai:harness:contracts` | 领域 schema/常量及 persistence 依赖边界 |
| `npm run test:ai:harness:commit` | 领域操作绑定、原子提交与故障注入 |
| `npm run test:ai:harness:runtime` | 生命周期、claim/lease/fencing、修复与 terminal trace |
| `npm run test:ai:harness:performance` | 字节预算、时限、读取和执行前资源上限 |
| `npm run test:ai:limits` | Persona/Scene/Planning/Study/Tavern 输入边界；无数据库 |
| `npm run test:ai:provider` | 独立能力、SDK 适配、配置快照、传输与本地 fallback；各能力亦有独立脚本 |
| `npm run test:acceptance:process-crash` | 24 个真实子进程退出场景；重启后的持久状态和恢复证据 |
| `npm run test:acceptance:recovery-limits` | 进程中断、容量、领域恢复、真实 HTTP 重启读回和 Web 严格解码聚合门 |
| `npm run check:release` | shared/Web、13 个 eval suite、全部后端测试和生产 Web 构建 |

公共测试依赖放在 `services/ai/tests/support/`。Document/Planning operation 样例、Scene proposal、可注入 Tavern provider、Alembic 配置和 Harness runtime fixture 不从其他 TestCase 模块导入。`HarnessRuntimeFixture` 是显式构建/关闭的普通对象，调用者以 `addCleanup` 注册清理；性能测试不再调用另一 TestCase 的 `setUp`。单个测试独有的故障注入和断言仍留在所属模块。

进程中断 worker 仍从自身测试模块启动独立 Python 进程，这是执行入口，并非共享 fixture 依赖。公开 helper 的迁移不改变故障发生位置、提交事务或重启 read-back 判定。
