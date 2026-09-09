# 代码解耦重构计划

状态：实施中；在 0.3.0 之后的小版本逐步推进，不属于 0.3.0 已实现功能。本文件维护七项重构的明细，根 [TODO](../../TODO.md) 作为统一索引。与 [统一 Logging / Debug](unified-debug.md) 共享基础边界，不要求先做完全仓重构。

- [ ] `ARCH-TRANSACTION-001` `[P1]` 明确领域事务校验边界。
  - 当前 `Database.session()` 在存在未 flush ORM 变更时执行 Tavern 全图扫描。审计实测普通 Settings 写入扫描三张 Tavern 表；提前 flush 则不触发该检查。
  - 采用明确的事务写集/领域校验接口，对受影响房间及引用进行验证；完整扫描保留为显式审计工具。
  - 验收：不相关写入不扫描 Tavern；相关写入在显式 flush、SQL 更新和提交等路径都不能绕过校验；SQLite/PostgreSQL 语义一致。不能直接删除现有 guard 而无等价替代。

- [ ] `ARCH-LIFECYCLE-001` `[P2]` 将全局容器迁入应用生命周期。
  - 消除 `bootstrap.py` 模块导入时的 `Container()`；FastAPI lifespan 创建/关闭服务，路由通过依赖注入获得应用实例的容器。
  - logging 先于数据库初始化、恢复与 provider 创建；启动恢复只在显式启动边界运行。
  - 验收：导入模块不访问运行数据库或启动恢复；两个应用实例使用不同临时数据库互不影响；退出释放资源。与 `PERF-002` 的懒加载协同，不重复立项。

- [ ] `ARCH-STUDY-001` `[P2]` 提取 Study Chat 应用服务。
  - 将 `routes.py::_admit_and_run_study_chat` / `_run_study_chat` 的上下文、工具、effects、运行与提交编排迁至独立应用服务。
  - 路由只解析输入、投影 API DTO 和映射错误；应用服务接收明确依赖和不可变执行上下文。
  - 验收：现有 API、幂等/uncertain 语义、私有评分材料隔离、Session/Turn/effect/receipt/trace 原子提交及故障恢复全部保持。

- [ ] `ARCH-HARNESS-CONTRACTS-001` `[P2]` 让 Harness 领域契约归位。
  - 将 `harness_broad_adoption.py` 中 Persona/Scene/Document/Planning 的输入、输出与证据 DTO 移至对应 models 模块，领域适配器分开维护。
  - Repository 不再为了类型与输出检查依赖整个应用编排模块；通过窄事务内 finalize 接口协作。
  - 验收：持久化层到高层服务的依赖减少；迁移前后 golden fixtures、公开序列化和历史 trace 解码保持一致。只移动契约不擅自升级其语义版本。

- [ ] `ARCH-PROVIDER-001` `[P2]` 分离模型能力、传输与 fallback。
  - 拆分 Planning、Study、Tavern、Persona/Scene、Embedding/Image 等能力接口；共享传输、usage、错误分类和有界重试设施。
  - 移除真实 provider 对 mock provider 的隐式继承；独立练习生成/提交评价等沿用 mock 的能力必须显式标记或实现，不能悄悄改变行为。
  - 验收：逐能力 contract tests；配置快照在一次操作内稳定；调用/重试上限、取消能力和 truthful provider 状态保持。

- [ ] `ARCH-WEB-001` `[P2]` 收窄前端状态范围并拆分领域控制器。
  - DebugProvider 独立于 LearningWorkspaceProvider；Settings/Model Usage 等路由不初始化学习数据。此部分与 `OBS-DEBUG-001` / `PERF-WEB-PROVIDER-001` 共用同一实现。
  - 将大型学习 controller、Persona Spectrum 和 Scene Setup 页面拆成数据访问、编辑草稿、动作/恢复控制器与展示组件。
  - 验收：路由请求清单、focus 刷新、取消/过期响应、草稿保存和页面切换保持正确；不以单纯文件拆分作为完成标准。

- [ ] `ARCH-TEST-SEAMS-001` `[P2]` 建立可重构的测试边界。
  - 公共 fixture/helper 不再藏在其他 TestCase 模块的私有函数中；使用应用实例级依赖覆盖，逐步减少全局 container patch。
  - 将按源码字符串切片的 Settings 测试替换为显式保存协调器测试及真实 Hook/组件行为测试。
  - 验收：重命名/移动内部函数不破坏行为测试；保留当前故障注入、24 个进程中断场景及真实 HTTP read-back 覆盖。

## 执行顺序和护栏

1. 先收口事务校验与应用生命周期；测试 seam 随每次变更一起改善。
2. 提取 Study 应用服务，再让 Harness DTO/适配器归位，保持事务由一个明确 owner 管理。
3. 按能力拆 provider；按领域拆前端 controller，Debug 关联基础可同步推进。
4. 每个小提交跑受影响的契约/故障测试；阶段交付跑 `npm run check:release`，涉及恢复时加 `npm run test:acceptance:recovery-limits`。

操作身份、授权、CAS、私有 DTO 隔离、primary-output commit proof 及外部 provider 的 uncertain 边界不可在重构中放宽。禁止把原本一次原子提交拆成多个独立事务，也不引入一轮重构同时修改业务语义的大变更。

## 实施记录

### ARCH-TRANSACTION-001

- [x] 提取不可变 `TavernReferenceWriteSet` 和作用域扫描接口；完整扫描保留为显式审计入口。独立模块 `tests.test_tavern_reference_scope` 覆盖空写集、无关房间、跨房间双向引用和删除身份，连同原审计测试共 7 项通过。
- [x] 接入连接级事务写集，覆盖 ORM flush、SQLAlchemy DML、Session/Connection 显式提交；替换旧全图 guard。托管事务内不透明写 SQL、无法确定身份的表达式写入和嵌套 DML 明确拒绝；维护 SQL 仍走 engine 与显式审计。修复 SQLite 首个 savepoint 在外层 BEGIN 前释放会提前提交的问题。
- [ ] 完成事务入口、领域回归及阶段验收后关闭主任务。

测试分层：引用规则/作用域测试不启动 API 或 provider；事务入口测试只构建临时数据库；Tavern 业务及恢复测试单独运行。阶段交付仍执行 release 与 recovery-limits 门禁。

事务入口测试独立为 `tests.test_transaction_validation`，使用临时 SQLite，覆盖 SQL/ORM 写入、过期 identity map、回滚、savepoint 和 Settings 查询隔离；`npm run test:ai:transactions` 只运行事务基础模块。PostgreSQL 实例级验收尚缺运行环境，不以 SQLite 结果替代。

2026-09-10 事务接入阶段验证：`test:ai:transactions` 23 项通过；`check:release` 通过（后端 587 项、共享/Web 检查、13 个 eval suite 与生产构建）；`test:acceptance:recovery-limits` 通过（后端 188 项、Web 169 通过/2 条环境相关跳过）。SQLite savepoint 故障修复后已重新执行两个阶段门禁。
