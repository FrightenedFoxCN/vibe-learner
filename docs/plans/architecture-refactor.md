# 代码解耦重构计划

状态：实施中；在 0.3.0 之后的小版本逐步推进，不属于 0.3.0 已实现功能。本文件维护七项重构的明细，根 [TODO](../../TODO.md) 作为统一索引。与 [统一 Logging / Debug](unified-debug.md) 共享基础边界，不要求先做完全仓重构。

- [x] `ARCH-TRANSACTION-001` `[P1]` 明确领域事务校验边界。
  - 当前 `Database.session()` 在存在未 flush ORM 变更时执行 Tavern 全图扫描。审计实测普通 Settings 写入扫描三张 Tavern 表；提前 flush 则不触发该检查。
  - 采用明确的事务写集/领域校验接口，对受影响房间及引用进行验证；完整扫描保留为显式审计工具。
  - 验收：不相关写入不扫描 Tavern；相关写入在显式 flush、SQL 更新和提交等路径都不能绕过校验；SQLite/PostgreSQL 语义一致。不能直接删除现有 guard 而无等价替代。

- [x] `ARCH-LIFECYCLE-001` `[P2]` 将全局容器迁入应用生命周期。
  - 消除 `bootstrap.py` 模块导入时的 `Container()`；FastAPI lifespan 创建/关闭服务，路由通过依赖注入获得应用实例的容器。
  - logging 先于数据库初始化、恢复与 provider 创建；启动恢复只在显式启动边界运行。
  - 验收：导入模块不访问运行数据库或启动恢复；两个应用实例使用不同临时数据库互不影响；退出释放资源。与 `PERF-002` 的懒加载协同，不重复立项。

- [x] `ARCH-STUDY-001` `[P2]` 提取 Study Chat 应用服务。
  - 将 `routes.py::_admit_and_run_study_chat` / `_run_study_chat` 的上下文、工具、effects、运行与提交编排迁至独立应用服务。
  - 路由只解析输入、投影 API DTO 和映射错误；应用服务接收明确依赖和不可变执行上下文。
  - 验收：现有 API、幂等/uncertain 语义、私有评分材料隔离、Session/Turn/effect/receipt/trace 原子提交及故障恢复全部保持。

- [x] `ARCH-HARNESS-CONTRACTS-001` `[P2]` 让 Harness 领域契约归位。
  - 将 `harness_broad_adoption.py` 中 Persona/Scene/Document/Planning 的输入、输出与证据 DTO 移至对应 models 模块，领域适配器分开维护。
  - Repository 不再为了类型与输出检查依赖整个应用编排模块；通过窄事务内 finalize 接口协作。
  - 验收：持久化层到高层服务的依赖减少；迁移前后 golden fixtures、公开序列化和历史 trace 解码保持一致。只移动契约不擅自升级其语义版本。

- [x] `ARCH-PROVIDER-001` `[P2]` 分离模型能力、传输与 fallback。
  - 拆分 Planning、Study、Tavern、Persona/Scene、Embedding/Image 等能力接口；共享传输、usage、错误分类和有界重试设施。
  - 移除真实 provider 对 mock provider 的隐式继承；独立练习生成/提交评价等沿用 mock 的能力必须显式标记或实现，不能悄悄改变行为。
  - 验收：逐能力 contract tests；配置快照在一次操作内稳定；调用/重试上限、取消能力和 truthful provider 状态保持。

- [ ] `ARCH-WEB-001` `[P2]` 收窄前端状态范围并拆分领域控制器。
  - DebugProvider 独立于 LearningWorkspaceProvider；Settings/Model Usage 等路由不初始化学习数据。此部分与 `OBS-DEBUG-001` / `PERF-WEB-PROVIDER-001` 共用同一实现。
  - 将大型学习 controller、Persona Spectrum 和 Scene Setup 页面拆成数据访问、编辑草稿、动作/恢复控制器与展示组件。
  - 验收：路由请求清单、focus 刷新、取消/过期响应、草稿保存和页面切换保持正确；不以单纯文件拆分作为完成标准。
  - 按用户 2026-09-10 补充授权，同步处理直接相关 UX：Scene 删除 Dialog、Persona/Scene 默认折叠与主次动作、异步状态/错误反馈；进度归入 TODO 的原任务，不复制 checkbox。跨页面 UX 条目只有所有指定页面及独立/设备级验收通过后才关闭。

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
- [x] 完成事务入口、领域回归、release/recovery 阶段门禁与本机 PostgreSQL 17 实例验收。

测试分层：引用规则/作用域测试不启动 API 或 provider；事务入口测试只构建临时数据库；Tavern 业务及恢复测试单独运行。阶段交付仍执行 release 与 recovery-limits 门禁。

事务入口测试独立为 `tests.test_transaction_validation`，使用临时 SQLite，覆盖 SQL/ORM 写入、过期 identity map、回滚、savepoint 和 Settings 查询隔离；`npm run test:ai:transactions` 只运行事务基础模块。公共 fixture `tests.support.database.isolated_database` 支持 `VIBE_TEST_POSTGRES_URL`，逐测试创建/删除独立 schema；默认仍使用临时 SQLite。

2026-09-10 事务接入阶段验证：`test:ai:transactions` 23 项通过；`check:release` 通过（后端 587 项、共享/Web 检查、13 个 eval suite 与生产构建）；`test:acceptance:recovery-limits` 通过（后端 188 项、Web 169 通过/2 条环境相关跳过）。SQLite savepoint 故障修复后已重新执行两个阶段门禁。

2026-09-10 PostgreSQL 验收：启动本机 OrbStack 临时 `postgres:17-alpine` 容器，在 PostgreSQL 上运行 `tests.test_transaction_validation` 与 `tests.test_tavern_reference_scope` 共 22 项，全部通过；SQLite 模块入口 23 项通过。测试 schema 与临时容器在验收后清理。复跑方式：将 `VIBE_TEST_POSTGRES_URL` 指向可创建 schema 的测试数据库，执行 `cd services/ai && uv run python -m unittest tests.test_transaction_validation tests.test_tavern_reference_scope`。

### ARCH-LIFECYCLE-001

- FastAPI lifespan 创建实例容器并调用幂等 `start()`，退出或恢复失败时 `close()`；构造失败也释放已初始化的数据库。logging 在数据库/恢复/provider 之前配置。
- 删除导入期 `container = Container()`。路由使用 `get_container(Request)` 依赖，内部编排通过显式参数传递实例；没有全局代理或隐式运行数据库 fallback。
- 公共 `tests.support.api` 提供实例级 fixture 与全新测试 app 的依赖覆盖；原 8 个测试模块的全局 container patch 已迁移。路由故障注入与真实 lifespan 验收分开运行。
- `npm run test:ai:lifecycle` 独立覆盖导入无数据库访问、双应用 Settings 隔离、恢复启动边界、退出/失败清理和 logging 初始化顺序。2026-09-10 阶段门禁通过：`check:release`（后端 592 项、共享/Web、13 个 eval suite、生产构建）与 `test:acceptance:recovery-limits`（后端 188 项、Web 169 通过/2 条环境相关跳过）。

### ARCH-STUDY-001

- `StudyChatApplication` 接收冻结依赖集合；`StudyChatExecutionContext` 固定一次已 admission 执行的身份、输入与附件集合。上下文拼装 helpers 与错误分类分模块维护，应用服务不依赖 bootstrap 或 API DTO。
- admission、preclaim、附件 staging/compensation、protected snapshot、工具/effects、Harness prepare/finalize 与 receipt read-back 已移出路由；`commit_chat_operation_turn` 仍是一次 Session/Turn/effects/receipt/terminal trace 原子提交的事务 owner。
- 路由只解析输入、映射应用错误并投影公开 receipt；服务端历史 payload 的私有评分材料仍在 API 投影时隔离。操作捕获 provider/settings 与 Settings 替换通过同一个短锁协调，provider 调用在锁外运行。
- 测试拆为 `test:ai:study:decode`（18 项）、`test:ai:study:application`（37 项）和 `test:ai:study:api`（4 项），均通过；公共样例和数据库 fixture 移到 `tests/support/`，没有跨 TestCase 的私有 helper 依赖。2026-09-10 完整阶段门禁通过：`check:release`（后端 593 项、共享/Web、13 个 eval suite、生产构建）与 `test:acceptance:recovery-limits`（后端 195 项、Web 169 通过/2 条环境相关跳过）。

### ARCH-HARNESS-CONTRACTS-001

- 15 个 Persona/Scene/Document/Planning DTO 和 33 个契约常量归入四个领域 models 模块；迁移前基线取自 `6f2e449`，schema 摘要与常量全部一致，未升级语义版本。
- 领域适配器拆为四个 `*_harness_adapter.py`，经 `HarnessDomainExecutionPort` 使用共享执行设施；旧 manifest decoder-route anchors 保持为 façade，不修改注册/golden fixtures。
- Document/Planning Repository 通过 `HarnessTransactionFinalizer` 在调用方 Session 内读取执行状态、finalize 或记录失败；prepared/finalize DTO 归入 models，不再导入 `app.services.harness_runtime` 或 broad orchestration。
- `test:ai:harness:contracts` 的 5 项模块测试（含 48 个 schema/constant 子项）与 `test:ai:harness:commit` 的 44 项绑定/提交/故障回归通过。benchmark 源码身份清单纳入拆出的文件。2026-09-10 阶段门禁通过：`check:release`（后端 598 项、共享/Web、13 个 eval suite、生产构建）与 `test:acceptance:recovery-limits`（后端 195 项、Web 169 通过/2 条环境相关跳过）。

### ARCH-PROVIDER-001

- [x] 拆出 Planning、Study、Tavern、Persona、Scene、Embedding、Image、Exercise 能力接口与 reply DTO；Planning/Tavern/Pedagogy 消费方收窄依赖。聚合 `ModelProvider` 保留兼容入口。
- [x] 真实 provider 不再继承 Mock。独立练习生成与提交评价显式委托 `LocalExerciseProvider`，标记 `exercise_implementation=local_heuristic`，保留原文本和长度启发式，不调用传输。
- [x] 将共享执行器、payload 归一化、错误分类、usage 记录与有界重试移至 `provider_transport.py`；注入 SDK 错误类型、时钟、sleep 与 recovery sink，不依赖 provider 类或导入 LiteLLM。新增 `test:ai:provider:transport` 7 项独立测试，原兼容性/provider审计/Persona 回归 124 项通过。
- [x] Embedding/Image 真实能力实现迁入独立模块，使用冻结的 model/readiness 配置与显式请求接口；聚合 provider 在入口创建能力实例。新增独立测试入口 `test:ai:provider:embedding`（3 项）与 `test:ai:provider:image`（4 项），不启动 SDK/数据库；原兼容性/provider 审计/Persona 回归 124 项通过。
- [x] Tavern actor 能力独立为 `RemoteTavernProvider`，共享响应包络解码移入 `provider_payload.py`；保留严格 schema、transport fallback、一次语义修复与调用前取消检查。两项纯 provider 测试移出 API/数据库 fixture，新增 `test:ai:provider:tavern` 5 项独立契约，Tavern API/调度/安全和共享解码相关 97 项回归通过。
- [x] Planning 能力、proposal decode/reference checks 和 fallback/repair 编排迁入 `provider_planning.py`；入口捕获模型参数与工具禁用集合，能力通过显式 request/runner factory 协作。计划修复测试移出数据库 fixture，公共样例归入 `tests/support/planning_samples.py`。`test:ai:provider:planning` 4 项通过，Planning/Persona/阶段 eval/持久操作等相关回归 145 项通过；保留 manifest/eval 使用的原 decoder aliases。
- [x] Study 生成、工具预算/执行和严格回复解码归入 `provider_study.py`，工具禁用集合在操作入口捕获。原解码模块中的三项生成/修复测试迁入无 SDK 的能力测试；`test:ai:provider:study` 19 项通过，配置变更跨轮次测试 1 项通过，Study 应用/effects/v3/Persona/阶段 eval 等相关回归 150 项通过。保留调用上限、单次无工具修复和私有答案 redaction。
- [x] Persona/Scene 生成、web-search fallback 和有界结构化重试迁入冻结配置的 `RemoteSettingsProvider`；共享 envelope diagnostics 归入 `provider_payload.py`，Settings 不依赖 Study 能力。两项纯卡片测试迁出大型 Persona 流程模块，旧测试不再 patch `_request_setting_json_*` 内部 helper，公共场景样例归入 `tests/support/`。Persona/Scene 独立模块各 3 项通过，相关流程/schema/Study decode/阶段 eval 回归 151 项通过。
- [x] SDK 请求适配移入 `provider_sdk.py`，SDK callable/error types 由实例 `ProviderSDK` 注入，旧测试不再 patch SDK 模块全局变量。操作入口捕获实例参数和冻结的请求适配器（端点、凭据、超时、callable、provider-prefix 集合、usage sink）；下一次操作读取新配置。SDK/配置模块 7 项通过，原兼容性/Persona/Planning/本地练习相关回归 133 项通过。`test:ai:provider` 聚合各独立模块，亦可通过各能力脚本单独运行。
- [x] 2026-09-10 provider 阶段门禁通过：`check:release`（后端 635 项、共享/Web 检查、13 个 eval suite、生产构建）与 `test:acceptance:recovery-limits`（后端 193 项、Web 169 通过/2 条环境相关跳过）。恢复集中的两项纯 Tavern provider 测试已移入独立能力模块，45 项 provider 聚合测试通过。阶段 eval 的请求计数器改为 SDK 注入依赖，避免将可变 fixture 计数误放进 provider 配置快照。

首个子任务验证：原 provider 审计、Study 解码、Tavern 安全模块 38 项通过；新增能力/练习契约连同 provider 审计与 Persona 流程共 122 项通过。测试能力导入无需 LiteLLM、真实 provider 无 Mock 继承、本地练习输出兼容及无传输调用。

### ARCH-WEB-001

- [x] 新建独立 `DebugProvider`，只接收学习模块发布的窄只读投影，不初始化 controller 或请求数据；全局 Overlay 移到学习 Provider 外侧。发布与读取 context 分离，学习 owner 卸载清空投影，避免旧页面调试状态残留。
- [x] 引入 React Testing Library/jsdom/TSX 的完整组件执行入口（不切片源码），以及后续路由浏览器验收所需 Playwright。`test:web:debug` 2 项真实生命周期测试、Web 类型检查和可靠性回归（169 通过/2 条环境相关跳过）通过；组件测试已加入常规 reliability 门禁。
- [x] 学习 Provider 迁到 `(learning)` 路由组，Plan/Study 共享实例；根布局仅保留不发请求的草稿缓存。文件草稿、目标与所选 Plan/Persona/Scene 跨路由保留，重新进入后仍从服务端恢复学习资源。离开时废弃旧 Study response ticket、停止本地流读取并请求取消已知 stream。
- [x] 生产 Chromium 的 12 项路由/导航测试通过：十个顶级页面初始请求清单、focus 请求上限、Plan/Study 切换不重复初始化、离开后不刷新学习数据、目标/PDF 草稿跨 Settings 导航。`test:web:workspace` 2 项组件/选择初始化测试通过；Web 类型检查、可靠性门禁和生产构建通过。请求 JSON 附件输出到 `/tmp/vibe-learner-route-report.json`；范围详见 `docs/frontend-test-boundaries.md`。
- [ ] 补充有历史 Plan/Session 和在途操作的浏览器恢复验收；路由网络基线通过不替代这些恢复场景。
- [x] 学习快照查询归入 `WorkspaceSnapshotLoader`，首次/focus/手动刷新共享响应归属判断；卸载后禁止新查询和旧结果投影，初始化被刷新取代时仍加载 Persona。独立 `test:workspace:data` 4 项并发/失败/卸载测试通过，Web 类型、可靠性回归、生产构建及 12 项 Chromium 路由验收通过。
- [ ] 继续拆分学习动作/恢复、Persona、Scene controller 并完成相关 UX 和前端阶段门禁。

- [x] 计划生成归入 `usePlanGeneration`，以显式 API port 注入上传/解析/计划/Session 请求，主 controller 只保留选择与视图投影。每轮生成持有独立响应归属，旧进度和 finally 不清空新任务；Scene 在生成入口捕获并用于初始 Session。独立 `test:workspace:generation` 6 项真实 Hook 行为测试通过，Web 类型、可靠性门禁、生产构建与 12 项 Chromium 路由验收通过。

- [x] Scene 草稿结构、树操作、导入与 Profile 投影归入 `scene-editor-model`；候选生成归入 `useSceneGeneration`，以独立 port 调用生成 API。请求身份覆盖长文本文件读取，卸载/新请求/草稿变更/导入均阻止旧候选回写，成功结果仍需用户显式应用。独立 `test:scene:generation` 5 项真实 Hook 测试通过，Web 类型、可靠性门禁、生产构建与 12 项 Chromium 路由验收通过。

- [x] Scene 删除确认展示提取为独立原生模态组件，取消/Escape 返回触发控件，确认删除移除触发控件时落到 Scene 标题；提供 44px 按钮、背景 inert 与 Tab 循环。2 项生产 Chromium 键盘/删除测试、12 项路由回归及 Web 类型/可靠性/构建通过；原 TODO UX 项保留独立复核要求。浏览器 API fixture 移为公共模块。

- [x] Scene 编辑状态、选中层级/物体、Profile 投影、草稿 revision/subject 与本地恢复归入 `useSceneDraft`；存储和时钟显式注入。保留 700ms 防抖，离页/pagehide 写入最新待保存草稿，修复快速离页丢编辑。5 项草稿 Hook 测试、Web 类型/可靠性/生产构建及 15 项 Chromium 验收通过，包含 Scene 快速离页再返回和完整刷新。新增 `test:browser` 聚合独立浏览器模块。

- [x] Scene 字段重写、请求归属、恢复记录与撤销归入 `useSceneRewrite`；卸载、切换选中对象和导入场景均废弃旧回复。撤销核对场景 subject 与已应用字段值，拒绝覆盖后续手工编辑，导入清空旧撤销记录。5 项完整草稿/重写 Hook 协作测试通过，Web 类型/可靠性/生产构建及 15 项 Chromium 回归通过。

- [x] Scene 场景库与可复用节点读写归入 `useSceneLibrary`，晚到初始列表与本地已确认写入/删除对账，单个列表失败不清空另一列表；同场景并发写入受本地守卫约束，API expectedRevision 保持不变。保存不覆盖后续用户选择，可复用节点状态由请求序号归属。6 项独立 Hook 测试、Web 类型/可靠性/生产构建及 15 项 Chromium 回归通过；读取失败提供页面 alert，常规进度提供 status。

- [x] Scene 路由缩为工作区装配；`useSceneWorkspaceController` 组合独立库/草稿/生成/重写 owners，`SceneWorkspaceView` 与树卡片负责展示，样式独立。文件导入 owner 在卸载时废弃 ticket。2 项真实卡片交互测试验证按钮事件隔离与禁用态，Web 类型/可靠性/生产构建和 15 项 Chromium 回归通过；前述模块测试未依赖原页面路径或内部函数位置。

### ARCH-TEST-SEAMS-001

- [x] Settings 保存队列归入显式 `SettingsSaveCoordinator`，计时与持久化依赖可注入；`useSettingsSave` 负责 React 生命周期和 pagehide，密钥持久化仍由 Settings 领域适配器执行。移除源码切片/VM 模拟 effect 的测试，保留原 5 类故障/离页/恢复原值场景，新增归一化读回及普通保存队列覆盖。`test:settings:save` 包含 6 项协调器与 2 项真实 Hook 测试；Web 类型、可靠性门禁、生产构建和 12 项 Chromium 路由验收通过。该结果不替代桌面 Vault 与完整进程故障阶段门禁。
- [ ] 完成剩余跨 TestCase 公共 fixture/helper 迁移，并运行最终 release/recovery 阶段门禁。
