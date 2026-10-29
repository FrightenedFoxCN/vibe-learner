# TODO

本文件是产品、Harness、模型质量和桌面工作的唯一待办入口；仅保留未完成任务。运行约束见 `AGENTS.md`，架构见 `docs/`，完成事项和实验过程通过发布记录、Git 历史及对应本地实验分支查询。

优先级表示下一阶段排程，不追溯为 v0.2.1 发布缺陷：

- `P1`：用户可用性、数据一致性或跨工作流基础边界，应优先处理。
- `P2`：明确且有收益的产品、性能或可靠性工作。
- `P3`：文档、账务和候选验证。

## 数据一致性与工程重构

- [ ] `ENG-WEB-DECODE-001` `[P2]` 为 Settings、工具配置、模型探测和 Model Usage 补齐领域严格响应解码。
  - 2026-10-29 审计：`apps/web/lib/api.ts` 仍使用 `any` 与 `String`/`Boolean`/`Number` 强制转换；工具配置中的字符串 `"false"` 会被当作 `true`，缺失字段和未知枚举也可能被默认值掩盖。
  - 从 `unknown` 严格验证字段、枚举、布尔值和有限数值，明确兼容默认值适用的历史契约；沿用 `strict-response-decode` 和已有诊断边界，并由 `lib/data/*` 暴露领域入口。
  - 增加畸形响应、字符串布尔值、非法计数和未知状态的行为回归；保持 Python/共享 TypeScript 契约一致，不将类型断言作为运行时验证。

- [ ] `ENG-TAV-WORKSPACE-001` `[P2]` 拆分 Tavern Workspace 的查询、Run 恢复和交互提交职责。
  - 2026-10-29 审计：`apps/web/components/tavern-workspace.tsx` 的主组件同时拥有房间分页、轮询、恢复、mutation fencing、草稿与界面状态；已有纯状态工具不覆盖完整异步编排。
  - 参照现有学习工作区的领域 Hook/展示组件边界，注入窄 API、时钟和存储 port；保留原有幂等身份、房间/请求版本 fencing、终态单调性、取消与 retry 语义。
  - 以行为测试覆盖切房、迟到结果、分页竞争、轮询清理及恢复/提交交错；源码字符串断言不能替代运行时测试。完整设备 UX 仍由 `REL-DESKTOP-001` 独立验收。

- [ ] `ENG-STUDY-TOOLS-001` `[P2]` 按领域职责拆分 Study Session 工具执行器。
  - 2026-10-29 审计：`services/ai/app/services/study_session_chat_runtime.py` 的 `execute_tool` 集中处理记忆、好感、续接、PDF/图片投影、生成与计划确认等分支。
  - 拆出领域处理器并复用既有 Tool Manifest 作为唯一目录，保留统一 effect collector、prepared/committed 区分、operation/slot 绑定和原子提交边界；不新增平行工具注册表。
  - 复用工具契约与 Study effect 回归，覆盖拒绝参数、重复调用、失败回滚、工具预算及 read-back；拆分不得改变模型可见契约或放宽 server-only 字段边界。

- [ ] `ENG-STYLE-GATES-001` `[P3]` 渐进建立前后端代码风格与静态检查门。
  - 2026-10-29 审计：Web 的 `lint` 仅为 TypeScript 检查别名，Python 未配置 Ruff 等风格检查；类型检查不能覆盖 React Hooks 规则、未使用导入和格式一致性。
  - 明确格式化与 lint 的职责，优先启用未使用导入、React Hooks 和新增/修改文件的格式检查，接入本地命令及 CI；对既有问题建立显式基线，避免一次性全仓格式化混入功能变更。

## UX 与文档

- [ ] `UX-OUTPUT-LANGUAGE-001` `[P2]` 为 Planning 与 Study 提供显式、可持久化的输出语言偏好。
  - `自动` 模式说明如何根据用户目标、教材与 Persona 决定语言；用户指定法文等语言后，计划指导语、任务与后续 Study 默认保持一致，不因中文产品壳混成中法英三语。
  - 语言偏好属于应用输入并进入 operation fingerprint/read-back，不靠模型从自由文本猜测，也不改写教材原文、引文或专有名词。

- [ ] `UX-DENSITY-SENSORY-001` `[P2]` 独立验收 Sensory Tools 的密度与保存反馈。
  - 2026-09-13：已实现名称/用途/分类搜索、阶段/可用性筛选、结果计数、用途按需展开和独立批量管理；批量动作仅作用于筛选结果中的可用工具。修复首次保存提示出现造成的滚动跳动，保留 44px 点击区域。
  - 剩余：真实设备、长错误与慢网连续保存的独立 UX 复核；本轮浏览器合成数据回归不替代独立验收。
- [ ] `UX-DENSITY-PERSONA-001` `[P2]` 收口 Persona 的默认折叠、搜索/筛选和主次动作；保存/错误定位不得丢失滚动或焦点，批量/删除动作与普通编辑分层。
  - 2026-09-13：人格库默认折叠；补齐卡片类型/人格来源筛选、结果计数和空态，删除及批量清空从普通编辑中分层。生成预览列出摘要/关系/称呼前后值、清空范围及名称缺失，支持单卡合并；整批应用成功后定位缺失名称。
  - 剩余：逐卡拒绝/选择后批量应用、完整参考提示 diff，以及保存/错误焦点和真实设备的独立 UX 复核。
  - 生成提案应用前展示名称缺失、字段 diff 和将被清空的内容；允许逐卡接受/拒绝或合并，不能让“清空后全量应用”与普通编辑处在同一风险层级。若名称仍为空，应用后聚焦并明确提示必填字段。
- [ ] `UX-DENSITY-SCENE-001` `[P2]` 收口 Scene 的默认折叠、搜索/筛选和危险操作分层；保存/错误定位不得丢失滚动或焦点，批量/删除动作与普通编辑分层。
  - 2026-09-13：保留复用/存档与深层树的默认折叠、44px 树控件和删除模态；增加已保存场景搜索、复用节点类型筛选、结果计数/空态和库删除动作分层。生成预览列出层/物体数量、按路径计算的增删及逐层规则/物体变化。
  - 剩余：语义约束冲突识别、完整树字段 diff、保存/错误定位与独立设备复核。当前预览明确要求人工检查规则冲突，不声称自动验证。
  - 生成预览须展示层/物体数量、规则与相对当前树的结构 diff；覆盖当前编辑树前暴露新增物体和约束冲突，不能只显示名称、摘要和节点数。

- [ ] `DOC-USER-001` `[P2]` 补齐并独立走查用户手册。
  - 2026-09-11：新增主页独立入口与 `/manual` 网页手册，简述首次使用、主要操作、恢复、数据及安装；正文统一在网页维护。独立新数据主流程与桌面安装走查仍待验收。
  - 本轮主智能体使用全新临时数据库/真实 mock 后端，走通纯目标生成、自动创建会话、提问与刷新读回；不替代独立完整手册验收。仍需 Settings 首次配置、教材路线、其他领域及桌面安装走查，见[核对报告](docs/plans/acceptance-audit-2026-09-11.md)。
  - 覆盖 goal-only、mock/real 首次使用路线，Document/Plan/Study/Persona/Scene/Tavern 主任务、恢复语义、数据位置与留存，以及产品限制。
  - 覆盖 DMG/NSIS/AppImage 安装、unsigned 限制和 SHA-256 校验。
  - 使用全新临时数据目录走通一次 mock 主流程和一次桌面安装流程。

### Planning → Study 工作流

本节已吸收 2026-09-13 M3 Planning production 配对复测中仍未关闭的工程结论；实验明细由本地归档分支保存。

- [ ] `PLAN-PAGE-BOUNDS-001` `[P1]` 将用户显式 PDF 物理页范围变成服务端工具、proposal 与 commit invariant。
  - 2026-09-13 审计：服务端已有 `PlanningIntentV1.pdf_page_ranges`、工具范围拒绝、proposal/schedule anchor/content slice invariant 和 resolved intent；但前端没有用户输入/持久化显式 PDF 页范围，数据模型只有物理页整数，未独立建模印刷页，且尚无端到端验收证明“100–103”贯穿请求、取证、proposal 与 commit。因此保持未完成。
  - 用户指定 PDF 100–103 时，取证工具参数、schedule anchor 和 content slices 必须落在该范围；物理页与印刷页分别建模，不能让模型把印刷 70–73 当成物理 70–73 后成功提交。
  - 本票只负责应用约束；教材语义、公式、旧记号和范围完整性质量由本文件的 `MQ-04` 负责。

- [ ] `OCR-CHECKPOINT-RECOVERY-001` `[P1]` 让长 OCR 在阶段完成后可读、可续跑。
  - 总 wall-time 在全部页面处理完成后耗尽时，不得抹掉已完成页和 Study Unit；保存有界 checkpoint，并验证重启、超时和重复请求的 read-back/续跑语义。

### 性能与 Tavern transport

- [ ] `TAV-FACILITATED-ORDER-001` `[P2]` 独立复核 Tavern facilitated 的顺序预览、服务端 schedule 与 Participant Roster 一致性。
  - 2026-10-29 核对：Interaction Composer 已按 participant `displayOrder` 排序，并在发送前展示“本轮回应：A → B”；Participant Roster 与服务端调度也采用名册顺序，目标选择仍为集合。无需重新实现顺序预览。
  - 剩余：逆序多选、恢复房间、partial 后 child retry 的独立端到端复核，确认发送前预览、服务端 Speaker Steps 和名册状态始终一致；不把用户点击顺序当作执行顺序。

- [ ] `PERF-WEB-DEDUPE-001` `[P2]` 复核窗口 focus、跨页返回与恢复交错时的资源请求边界。
  - 2026-10-29 核对：Tavern bootstrap 对 Persona/Scene 已各请求一次；LearningWorkspaceProvider 已限定在 `(learning)` 路由组，根布局只保留不发起学习请求的页面草稿缓存。路由清单与既有验收范围见 `docs/frontend-test-boundaries.md`。
  - 剩余：以有历史 Room/Run 的请求记录独立复核连续 focus、跨页返回、轮询与恢复并发；区分必要 read-back 与重复请求，保留原始请求计数、时序和 before/after，避免无界刷新。空库首次加载基线不能替代这些场景。

- [ ] `PERF-WEB-BUNDLE-001` `[P2]` 建立 `/`、Settings、Model Usage、Tavern 的 production gzip 基线和 5% 回退门。

- [ ] `TAV-CANCEL-TRANSPORT-001` `[P2]` 建立 capability-aware provider cancellation。
  - 可取消 adapter 必须中断本地传输并释放连接/worker；不支持时继续使用 commit fencing 和 truthful UI。
  - 关闭本项前至少一个实际生产 adapter 必须证明已发请求可中断且资源已释放；全部 adapter 均标记 unsupported 不是关闭路径。
  - 仅在 provider 提供权威证据时声明停止上游计算或计费，不把本地连接关闭冒充 token 停止。

### Study operation hardening

- [ ] `STUDY-OP-RECOVERY-UX-001` `[P2]` 覆盖超长轮询、终态刷新、断网和页面恢复文案，不放宽 same-key mismatch 或 `uncertain` 禁止重放。

## 可靠性、部署与输入边界

- [ ] `REL-DESKTOP-001` `[P2]` 完成真实桌面/浏览器恢复验收。
  - 覆盖慢网、断网、刷新/离页、Settings 未保存变更、编辑器异步返回、删除/归档组合、桌面安装/退出；覆盖 Tavern 无 Persona/无 Room、设备级 IME 和完整焦点顺序。
  - 已有进程退出、事务回滚、HTTP 重启读回测试作为回归门；不得重复列为待实现。Study 文案由 `STUDY-OP-RECOVERY-UX-001` 负责。

- [ ] `REL-POSTGRES-001` `[P2]` 在实际 PostgreSQL 上完成迁移、并发 CAS、事务回滚和重启恢复验收。
  - 2026-09-11 独立 PostgreSQL 17 实测：原事务/引用 22 项、空库 Alembic 升级、Study Session 并发 CAS、异常回滚、数据库重启后新进程读回通过，见[独立报告](docs/plans/postgres-replay-independent-acceptance-2026-09-11.md)。
  - 剩余：带数据旧版本迁移、Document/Planning/Study/Tavern 操作 admission/lease/commit 中断窗口及应用 HTTP 重启恢复。SQLite 完整恢复矩阵不能替代这些 PostgreSQL 实测。

- [ ] `REL-REPLAY-001` `[P2]` 独立复核 Document、Planning、Persona/Scene 的受保护制品重放。
  - 覆盖授权、保留/删除、摘要损坏和版本兼容；复用现有运行时、解析器和测试，不新增一套 Harness 基础设施。
  - 2026-09-11 四领域合成快照独立授权/版本拒绝/过期/损坏/删除/新连接解析矩阵通过，另 29 项相关回归通过。剩余真实历史制品的完整领域 adapter 重放、历史契约兼容及旧 grant 过期后重新授权；共享解析边界通过不等于完整重放认证，见[独立报告](docs/plans/postgres-replay-independent-acceptance-2026-09-11.md)。

- [ ] `DOC-INPUT-BOUNDS-001` `[P2]` 定义文档上传字节/页数上限与可恢复的拒绝行为。
  - 当前上传没有硬性上限；256 页压力测试已通过。明确单个不可分割文本块的策略，不能把 chunk packing target 当作硬上限。

- [ ] `OCR-STRESS-001` `[P2]` 完成真实 OCR 多语言、大型扫描件和失败恢复测试。
  - 复用已实现的 CPU fallback；测量内存、时延及错误状态，区分压力样本与正式支持上限。

- [ ] `PERF-TAV-LIVE-001` `[P2]` 完成代表性真实 provider 的 Tavern 性能验收。
  - 使用六人名册、每次最多四个调度目标及长对话，记录 token、真实计费证据、P50/P95、修复/失败率和 retry/cancel 行为。
  - 既有 MiniMax 样本出现过上游 529；本地确定性门和 mock 恢复成功不代表真实 provider 全通过。

- [ ] `DESKTOP-RELEASE-001` `[P2]` 完成生产签名、公证和跨平台安装验收。
  - macOS sidecar/native dependencies 使用同一 Developer ID Team，验证后开启 hardened runtime；验证 Windows/Linux 安装、退出与校验和。
  - 明确预览版缺少打包 OCR 模型时允许 fallback 还是阻止发布的策略。

- [ ] `DOC-LAYOUT-LICENSE-001` `[P1]` 在分发或托管启用 DocLayout-YOLO 前完成代码、权重和训练数据许可复核。
  - 明确 GPL-3.0/AGPL-3.0 组合的源码提供义务，并取得 DocSynth300K 等训练数据的可分发/托管授权证据；项目许可证不能替代数据集许可。
  - 未关闭前保持外部子进程默认关闭，不把模型权重或相关依赖并入默认安装包。

- [ ] `DIAG-INSTALLATION-BUDGET-001` `[P2]` 完成诊断数据的安装级磁盘预算与恢复验收。
  - 把 event、Harness index、桌面 spool、WAL/SHM/journal、锁文件和文件系统分配开销纳入同一 200 MiB 口径；验证并发桌面写入、外部写入、超限旧库、长读者占用 WAL 及 Windows/macOS/Linux 文件语义。
  - 给出超限后的可恢复清理/迁移路径和真实工作流开销；只有跨进程、跨平台证据齐全后，导出中的 `disk_size_limit_certified` 才可为 true。

- [ ] `DIAG-NATIVE-EXPORT-001` `[P2]` 独立验收诊断快照的原生保存交接。
  - 覆盖桌面保存对话框、取消、覆盖、权限/磁盘失败和最终文件校验；浏览器触发下载或前端已生成 Blob 不等于文件已持久化。
  - 与 `REL-DESKTOP-001` 共用 macOS/Windows/Linux 设备矩阵，但分别记录导出 DTO 正确性和原生文件落盘结果。

## 模型质量复核（已暂停，须重新授权真实模型调用）

以下项目吸收原质量 TODO 和 2026-09-13 Planning 审计的未完成结论。实验原始数据由本地 `codex/m3-quality-evidence-archive` 及各专项实验分支保存；生产已采用边界见[模型运行时质量](docs/model-runtime-quality.md)。旧 `QG-002` / `web-strict-decode-adversarial-v1` 保持不可变。

- [ ] `MQ-01` `[P2]` 独立复核 Study 引用精度与召回：覆盖中英法、多页、否定、无来源和中文整段 token；未提交结果不得计为成功弃引。
- [ ] `MQ-02` `[P2]` 独立核对原文与写入状态：逐字模式按字符比较，摘要按固定字段语义比较，并用 effect receipt 区分 Turn 持久化、专门记忆写入和模型口头声明。
- [ ] `MQ-03` `[P2]` 复核长历史记忆检索与时间关系：覆盖中段更新、重新启用、未知时间、多对象、取消/归档及记录时间/事件时间，分开归因检索、读取、写入和载荷失败。
- [ ] `MQ-04` `[P1]` 建立 Planning 来源、页码、范围、内容、时长与 Persona 活动关系的 held-out 专家门；物理/印刷页、公式、旧记号和完整目标范围必须分别核验。
- [ ] `MQ-05` `[P1]` 复核 Planning 工具调度、Unit ID/schema repair 与成本：固定输入、摘录和限额，记录首次失败、修复、重试、request tokens、端到端 P50/P95，并核对实际 wire 行为。
- [ ] `MQ-06` `[P2]` 建立 Persona 权限/事实边界和 Tavern 关系防编造的独立盲测；Persona claim ledger 与 Tavern counterfactual fixture 先校准，再决定是否另行预注册 live shadow。
- [ ] `MQ-07` `[P2]` 复核 Study 题目、工具效果与视觉定位：题目提交前不得泄漏答案，逐工具核对领域效果；OCR 文本/字符与 Picture/Formula 候选分流，并在页面隔离留出集验收。
- [ ] `MQ-08` `[P2]` 量化缓存与压缩收益和损失：控制冷暖、前缀、配置与调用顺序，记录真实 `cached_tokens`、摘要/回查总成本和事实保留率，不以 token 减少推导费用或时延改善。
- [ ] `MQ-09` `[P2]` 完成 OCR 与图片生成的生产接入质量门：从 admission 到 read-back 覆盖语言/版面/平台打包；噪声 OCR 用原页或专家 ground truth 分开评分“不确定性识别”和正文正确性。
- [ ] `MQ-10` `[P2]` 建立独立、盲测、held-out 的总体质量基线：grader 需独立人工校准，数据/基础设施/评分器/候选失败分母分离，并补真实前端与适用平台验收。

## Research parking lot（未排期）

以下候选只有在触发证据出现后才建立可领取任务；研究票必须写明假设、time-box、产出物和采用/放弃标准。

- `RND-RUST-001`：仅在 profiling 证明 Python/TypeScript 热点后评估 Rust 重写。
- `RND-THEME-001`：需要用户需求、稳定 design tokens、对比度基线和可关闭开关。
- `RND-LIVE2D-001`：需要授权、资源预算、动画降级和设备性能证据。
- `RND-TTS-001`：需要隐私、延迟、成本、可取消传输、字幕和静音降级证据。
- 桌面自动更新、崩溃上报及 sidecar 打包形态调整：先确定发布策略并通过性能测量再立项。
- `SKILL-DISTILL-001`：只抽取稳定、可验证、无密钥/用户数据的仓库流程；`AGENTS.md` 仍是事实真源。

## 持续规则

- 本文件是唯一待办索引；其他文档只描述当前契约、限制和复现方式，不维护平行待办。已实现的 Harness 基础设施、15 个 Harness 评测套件、SQLite 恢复和已定义输入上限测试不再列为待办。
- 架构和逐工作流工程说明见 `docs/harness/README.md`，工程约束见 `AGENTS.md`。`QG-002` / `web-strict-decode-adversarial-v1` 保持不可变，扩展使用新版本。
- Debug 是全局 Overlay，不恢复已删除的 `/debug` 页面。
- 性能任务必须记录 fixture、环境、raw samples 和 before/after；不得通过放宽既有预算关闭回归。
