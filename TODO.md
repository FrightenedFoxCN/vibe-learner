# TODO

本文件只保留未完成工作。完成事实、运行约束和长期设计应进入 `AGENTS.md` 或 `docs/`；tracking epic 与研究候选不作为可领取 checkbox。

优先级表示下一阶段排程，不追溯为 v0.2.1 发布缺陷：

- `P1`：用户可用性、数据一致性或跨工作流基础边界，应优先处理。
- `P2`：明确且有收益的产品、性能或可靠性工作。
- `P3`：文档、账务和候选验证。

## Now（下一批可领取）

- [ ] `UX-A11Y-STUDY-QUESTION-001` `[P1]` 完成 Interactive Question 无障碍语义。
  - 补齐题组 busy 状态、单选/多选选择语义、填空显式 label、错误播报、焦点恢复和至少 44px 触控目标。
  - 验收：键盘、屏幕阅读语义和持久化 read-back 流程均通过独立验收。

- [ ] `UX-A11Y-SCENE-DIALOG-001` `[P1]` 完成 Scene 删除层级 Dialog 的模态行为。
  - 补齐初始焦点、focus trap、Escape、背景 inert，以及取消/确认后的焦点恢复。
  - 验收：键盘无法逃逸到背景，关闭后焦点回到发起控件。

- [ ] `SCH-TAV-001` `[P1]` 收口 Tavern Run/Message/Step 软引用策略。
  - 覆盖 Message `run_id`、Run 输入/锚点 Message、Step 输出/回复 Message 等引用。
  - 验收：要么使用可迁移 FK 与明确插入顺序，要么由统一 invariant scanner 检测并阻断破损图；SQLite/PostgreSQL 均有故障 fixture。

- [ ] `TAV-UX-COPY-001` `[P2]` 完成 Tavern 状态文案的关闭验收。
  - 增加表驱动 copy contract，覆盖 run/step、partial、failed、blocked、retry、stale、archived、cancel 与 raw-code 隔离。
  - `blocked` 不得显示为角色失败，raw code 只进入 Reliability Details / Debug Overlay。
  - 由非实现者在浏览器中各验收一个 partial、failed、blocked 场景；通过后关闭本项。

- [ ] `PERF-002` `[P2]` 完成 LiteLLM lazy import，并守住现有 OCR lazy import。
  - 验收：10 个全新 mock 进程 `/health` 均低于 2 秒；`litellm` / `onnxtr` 不在启动后的 `sys.modules`；启动期间没有 cost-map 网络请求。
  - 使用固定临时数据库、明确计时边界和 machine-readable raw samples。

- [ ] `PERF-TAV-ROOMS-001` `[P2]` 完成 Tavern Room 分页时间门。
  - 保留已完成的稳定 cursor、复合索引、每页最多 4 SQL、payload 和 100 个按钮结构门。
  - 按 `docs/performance-budgets-v1.md` 记录首/中/末页 server samples、React Profiler commits 和原始样本；纯函数时间不得冒充 React 门。

- [ ] `PERF-WEB-PROVIDER-001` `[P2]` 建立路由级 Provider ownership。
  - Settings、Model Usage、404 等无关页面不得加载 Learning Workspace 数据；Debug Overlay 与 Workspace Context 解耦。
  - 验收：为每个顶级路由冻结允许请求清单，并以浏览器网络记录和自动化测试验证。

## Next（已定义、待排期）

### UX 与文档

- [ ] `UX-NAV-001` `[P2]` 重构顶级导航信息架构。
  - 对学习、角色与世界、系统入口分组；390/760/桌面宽度不依赖隐藏的横向滚动。
  - 验收：当前组/当前页语义、完整键盘遍历、可发现性与焦点顺序通过独立验收。

- [ ] `UX-A11Y-ASYNC-TOUCH-001` `[P2]` 收口跨页面异步播报和触控门。
  - 覆盖 Persona Spectrum、Scene Setup、Sensory Tools 及 Tavern 的 `status` / `alert`、错误定位和 44px 控件；修复 Persona 无可访问名称的图标按钮。
  - 验收必须包含 390×844 设备级视口，不以静态 CSS contract 代替真实量测。

- [ ] `UX-DENSITY-SENSORY-001` `[P2]` 为 Sensory Tools 增加搜索、筛选和渐进披露；保存/错误定位不得丢失滚动或焦点，批量/删除动作与普通编辑分层。
- [ ] `UX-DENSITY-PERSONA-001` `[P2]` 收口 Persona 的默认折叠、搜索/筛选和主次动作；保存/错误定位不得丢失滚动或焦点，批量/删除动作与普通编辑分层。
- [ ] `UX-DENSITY-SCENE-001` `[P2]` 收口 Scene 的默认折叠、搜索/筛选和危险操作分层；保存/错误定位不得丢失滚动或焦点，批量/删除动作与普通编辑分层。

- [ ] `DOC-USER-001` `[P2]` 补齐并独立走查用户手册。
  - 覆盖 goal-only、mock/real 首次使用路线，Document/Plan/Study/Persona/Scene/Tavern 主任务、恢复语义、数据位置与留存，以及产品限制。
  - 覆盖 DMG/NSIS/AppImage 安装、unsigned 限制和 SHA-256 校验。
  - 使用全新临时数据目录走通一次 mock 主流程和一次桌面安装流程。

### 性能与 Tavern transport

- [ ] `PERF-WEB-DEDUPE-001` `[P2]` 去除页面内重复资源请求。
  - Tavern 对 Persona/Scene 各请求一次；窗口 focus 与恢复流程不得造成无界重复刷新。

- [ ] `PERF-WEB-BUNDLE-001` `[P2]` 建立 `/`、Settings、Model Usage、Tavern 的 production gzip 基线和 5% 回退门。

- [ ] `TAV-CANCEL-TRANSPORT-001` `[P2]` 建立 capability-aware provider cancellation。
  - 可取消 adapter 必须中断本地传输并释放连接/worker；不支持时继续使用 commit fencing 和 truthful UI。
  - 关闭本项前至少一个实际生产 adapter 必须证明已发请求可中断且资源已释放；全部 adapter 均标记 unsupported 不是关闭路径。
  - 仅在 provider 提供权威证据时声明停止上游计算或计费，不把本地连接关闭冒充 token 停止。

### Study operation hardening

- [ ] `STUDY-OP-CLOCK-001` `[P2]` 使用 canonical database clock 判定 admission abandonment、claim/heartbeat 和 execution deadline，并保持 SQLite/PostgreSQL DDL/JSON/状态约束一致。
- [ ] `STUDY-OP-SCANNER-001` `[P2]` 增加 journal corruption、未知版本和 digest drift scanner，输出 typed read-back 结论。
- [ ] `STUDY-OP-RECOVERY-UX-001` `[P2]` 覆盖超长轮询、终态刷新、断网和页面恢复文案，不放宽 same-key mismatch 或 `uncertain` 禁止重放。

## Harness roadmap（按依赖顺序）

跨工作流 Harness 是长期主线。局部 decoder、effect 或 evidence 完成不代表任一业务域已整体采用 v3。

### Foundation

- [ ] `HRN-SUBJECT-001` `[P1]` 定义 artifact principal / authorization 模型。
  - 当前 API 无认证；必须先决定单用户本地主体、capability scope 或正式认证边界，并形成版本化 principal/capability contract。
  - fixture 必须证明同主体允许、跨主体 `forbidden`、无主体 fail closed，才能赋予授权结论权威语义。

- [ ] `SCH-HRN-EFFECT-001` `[P1]` 抽取跨工作流 durable effect batch primitive。
  - 数据库、文件/staging/outbox 与外部 adapter 共享版本化 prepare/commit/compensate/read-back 接口和 durable per-effect journal。
  - 应用必须按 `operation + slot` 分配 effect identity；重试不得重新发号或改变 effect 顺序。
  - DB 事务不得冒充 provider exactly-once；无 idempotency/read-back 时保持 `uncertain`。

- [ ] `HRN-CTX-ARTIFACT-001` `[P1]` 建立受保护 artifact resolver；依赖 `HRN-SUBJECT-001`。
  - 支持 opaque ID、类型/contract 注册、授权后读取、留存/过期、digest read-back 和批量解析预算。
  - 返回 typed `resolved/not_found/expired/forbidden/digest_mismatch/schema_unsupported`。
  - fixture 覆盖删除、篡改和跨主体访问；可清理的 `document_debug` / `planning_trace` 不得冒充永久 replay artifact。

- [ ] `HRN-CTX-RUNTIME-001` `[P1]` 建立跨业务 operation runtime；依赖 effect 与 artifact boundary。
  - 统一 operation/attempt/check/commit/rollback/terminal-failure 组装，并提供幂等、失败持久化和 adapter 故障 fixture；生产调用方只能经过注册的 context/artifact/effect boundary。

- [ ] `HRN-EVAL-001` `[P1]` 建立 fixture/eval core 与版本化基线。
  - 提供 runner、指标 schema、raw samples、CI threshold 和域 adapter 注册；覆盖 malformed、boundary、retry、duplicate、concurrency 与 commit failure。
  - 通用报告至少包含 schema-valid、repair、failure、commit-consistency 与 p95 指标。
  - 每个域登记版本化最低阈值和回退门：OCR 文本/页覆盖、Section/Study Unit 边界、Plan grounding/tool correctness、Persona/Tavern identity、Scene 结构、Study citation/effect correctness 与 Frontend decode。

- [ ] `HRN-CTX-PERF-001` `[P2]` 为 context canonical bytes、snapshot bytes、引用数、resolver I/O 和 p50/p95 建立预算；依赖可运行的 resolver/runtime，任何超限必须在模型/provider/worker 执行前 fail closed。

- [ ] `HRN-RECOVERY-MIG-001` `[P2]` 统一 legacy recovery 与 v3 attempt/check 映射；依赖 runtime，确保同一 operation 可关联、兼容 API、指标不重复计数，并给出明确弃用路径。

### Production adoption

所有 v3 生产采用项共享关闭契约：依赖可运行的 artifact resolver、operation runtime 与 eval core；敏感原文不得进入 trace，受保护 artifact 必须可授权 replay；每个 stage 均有 attempt/check 与 terminal trace；失败路径和成功 commit evidence 必须完整。下列条目只补充各域特有的 proposal、invariant、effect 与指标，不能以局部 strict decoder 或 schema fixture 代替共享契约；独立 eval/perf 条目只服从其显式依赖。

- [ ] `HRN-TAV-V3-001` `[P1]` 将 Tavern 生产证据从 legacy v1 切换到 v3。
  - 依赖 `SCH-TAV-001`、artifact、runtime、eval 与 recovery migration。
  - 覆盖 parent lineage、partial/failed/not-committed、per-step commit、child retry，以及 Message/Run/Step/Room 的真实证据范围。
  - legacy v1/v2 保持可读，前端 v1/v2/v3 fixture 全部通过；迁移不得伪造历史证据。

- [ ] `HRN-TAV-002` `[P1]` 建立 Tavern 身份与 prompt-injection eval 矩阵；只依赖 eval core，v3 trace 集成由 `HRN-TAV-V3-001` 后续承接。
  - 覆盖身份、称呼、目标、跨角色冒充和 prompt injection，报告 schema-valid、repair、false-positive 和 identity-consistency rate，不以实现者单测代替基线。

- [ ] `HRN-TAV-PERF-001` `[P2]` 完成 Tavern prompt 性能/eval 门；依赖 artifact、eval 与 Tavern v3。
  - 使用最坏 6 人长对话、真实 tokenizer/provider p50/p95、版本化回退阈值和 content-free trace。

- [ ] `HRN-STUDY-001` `[P1]` 将 Study Chat 接入 v3；依赖 durable effect、artifact、runtime 与 eval。
  - 覆盖 prompt/context、strict reply、attempt/check、protected artifact replay、commit/rollback/uncertain、citation/effect correctness。

- [ ] `HRN-PLAN-001` `[P2]` 将 Planning 接入 v3；覆盖版本化 toolset/prompt/context、attempt/check、protected artifact replay、terminal evidence、grounding 与 tool correctness。
- [ ] `HRN-DOC-001` `[P2]` 将 extraction/OCR/Section/Chunk/Study Unit cleanup 接入 v3；记录真实 parser/heuristic 版本，并验证页覆盖、边界、排序、source-ID 与密度预算。
- [ ] `HRN-SCENE-001` `[P2]` 建立 Scene v3 lifecycle、allow-list reuse、递归 invariant、失败零持久化和 replay/eval。
- [ ] `HRN-PERSONA-001` `[P2]` 建立 Persona v3 lifecycle、proposal ownership、slot/身份/称呼 invariant、失败零持久化和 replay/eval。

- [ ] `HRN-WEB-001` `[P2]` 完成 Frontend Decode v3 adoption。
  - 列清仍未经过 `unknown -> strict decoder` 的端点，注册真实 Frontend Decoder component version。
  - 增加独立 live-wire、v2/v3 trace forwarding、resource evidence 和未知版本 fail-closed fixture。

## Planning 与工具演进

- [ ] `TOOL-CATALOG-001` `[P1]` 建立单一版本化 Tool Manifest。
  - 每个 Planning/Study tool 登记 ownership、input schema、effect class、sensitivity、budget、parallel safety、依赖和 provider capability。
  - 重复、废弃和更名工具必须有兼容迁移与退役路径。

- [ ] `PLAN-TOOLS-EVAL-001` `[P2]` 建立 Planning tool 基线。
  - 报告 batch size、实际调用率、无效调用率、每工具 p50/p95、总 wall-clock、grounding 和 tool correctness；不得以 prompt 鼓励冒充调用证据。

- [ ] `PLAN-TOOLS-PERF-001` `[P2]` 根据 eval 决定是否并行。
  - 只有整批均为 `parallel_safe` 且读取同一不可变快照时才能并行；同批结果必须稳定排序。目标是降低同轮 wall-clock，不宣称减少模型轮次。

- [ ] `SCH-PLAN-CAS-001` `[P1]` 建立数据库权威 Plan revision/CAS。
  - 覆盖全部计划写入口、旧数据迁移，以及既有 Study Session、进度和 schedule identity 的并发语义。

- [ ] `PLAN-PATCH-001` `[P2]` 建立 strict patch proposal 与 durable operation；依赖 Plan CAS 和 Planning Harness lifecycle。
  - 覆盖 base revision、冲突、回滚、恢复，以及 ID/progress 映射。

- [ ] `PLAN-REV-UX-001` `[P2]` 增加修订 diff、接受/拒绝、冲突刷新、回滚和恢复 UX；依赖 `PLAN-PATCH-001`。

## Tracking epics（不可直接领取）

- `UX-001`：Tavern 发布体验；关闭条件包括 Copy、无 Persona/无 Room、设备级 IME、完整焦点顺序和 390×844 设备量测。
- `UX-A11Y-001`：由 Study Question、Scene Dialog、Async/Touch 三个子项关闭。
- `UX-EDITOR-DENSITY-001`：由 Sensory、Persona、Scene 三个子项关闭。
- `PERF-001`：由 Provider ownership、Request dedupe、Bundle budget 三个子项关闭。
- `STUDY-OP-HARDEN-001`：由 Clock、Scanner、Recovery UX 三个子项关闭。
- `HRN-CTX-001`：仅在 foundation、全部生产域 adoption、eval 和性能门完成后关闭。
- `PLAN-ITER-001`：由 Plan CAS、Patch Operation、Revision UX 三个子项关闭。

## Research parking lot（未排期）

以下候选只有在触发证据出现后才建立可领取任务；研究票必须写明假设、time-box、产出物和采用/放弃标准。

- `RND-RUST-001`：仅在 profiling 证明 Python/TypeScript 热点后评估 Rust 重写。
- `RND-THEME-001`：需要用户需求、稳定 design tokens、对比度基线和可关闭开关。
- `RND-LIVE2D-001`：需要授权、资源预算、动画降级和设备性能证据。
- `RND-TTS-001`：需要隐私、延迟、成本、可取消传输、字幕和静音降级证据。
- `SKILL-DISTILL-001`：只抽取稳定、可验证、无密钥/用户数据的仓库流程；`AGENTS.md` 仍是事实真源。

## 持续规则

- `QG-002` 的 `web-strict-decode-adversarial-v1` 已是 release gate。新增域、decoder 或攻击类别必须原子更新 fixture、golden 和 runner；扩展基线使用新版本任务，不保留永久开放 checkbox。
- Harness stage、attempt phase 与 stream event 是不同词汇；新增值必须同步 Python、TypeScript、registry、fixture、decoder routing 和 eval routing。
- 无 provider idempotency 或权威 read-back 时保持 `uncertain`，不得以数据库提交冒充外部 exactly-once。
- Debug 是全局 Overlay，不恢复已删除的 `/debug` 页面。
- 性能任务必须记录 fixture、环境、raw samples 和 before/after；不得通过放宽既有预算关闭回归。
