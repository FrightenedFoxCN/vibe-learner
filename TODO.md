# TODO

本文件是产品、Harness、模型质量和桌面工作的唯一待办入口；仅保留未完成任务。运行约束见 `AGENTS.md`，架构见 `docs/`，完成事项和实验过程通过发布记录、Git 历史及对应本地实验分支查询。

优先级表示下一阶段排程，不追溯为 v0.2.1 发布缺陷：

- `P1`：用户可用性、数据一致性或跨工作流基础边界，应优先处理。
- `P2`：明确且有收益的产品、性能或可靠性工作。
- `P3`：文档、账务和候选验证。

## UX 与文档

- [x] `UX-MODEL-USAGE-001` `[P2]` 让 Model Usage 支持明确时区、按 operation/workflow 分类、筛选和导出。
  - 2026-09-13：用量记录带出 Harness operation/workflow/stage（无 Harness 的 Settings/Embedding 使用明确 fallback workflow），Model Usage 支持时区、workflow/operation/日期筛选、50 条分页和当前筛选 CSV 导出；页面明确 Token 统计与实际供应商费用的边界。
  - Planning repair、失败/中断重试和自动下游调用必须可区分；页面统计与 `PLAN-OBSERVABILITY-001` 的 operation 聚合口径一致，不再只展示当前一次成功调用。
  - Settings 的真实代表请求必须纳入账务或明确标成排除范围；刷新、分页/时间范围与成本估算的统计口径对用户可见，长明细不再无限单页堆叠。

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

- [x] `PLAN-NAVIGATION-LIFECYCLE-001` `[P1]` 让 Planning 长任务跨页持续，或在离页前明确提示将取消并展示已发生费用。
  - 2026-09-13：Planning 生成期间通过统一 AppLink 拦截离页，明确说明任务会中断、已发生 Token/费用不会撤销且费用以供应商账单为准；浏览器关闭/刷新提供 beforeunload 保护，任务身份保留在本地活动标记直到结束。
  - 当前普通导航会调用 Document/Planning stream cancel；真实请求仍可能完成并计费，但 Learning Plan 不提交。全局 Debug 与返回后的 Plan Workspace 应显示活动、已中断、费用和可恢复状态。

- [ ] `PLAN-PAGE-BOUNDS-001` `[P1]` 将用户显式 PDF 物理页范围变成服务端工具、proposal 与 commit invariant。
  - 2026-09-13 审计：服务端已有 `PlanningIntentV1.pdf_page_ranges`、工具范围拒绝、proposal/schedule anchor/content slice invariant 和 resolved intent；但前端没有用户输入/持久化显式 PDF 页范围，数据模型只有物理页整数，未独立建模印刷页，且尚无端到端验收证明“100–103”贯穿请求、取证、proposal 与 commit。因此保持未完成。
  - 用户指定 PDF 100–103 时，取证工具参数、schedule anchor 和 content slices 必须落在该范围；物理页与印刷页分别建模，不能让模型把印刷 70–73 当成物理 70–73 后成功提交。
  - 本票只负责应用约束；教材语义、公式、旧记号和范围完整性质量由本文件的 `MQ-04` 负责。

- [x] `PLAN-OBSERVABILITY-001` `[P1]` 统一一次 Planning operation 的 provider round、工具、repair、token、时延、终态与产物口径。
  - 2026-09-13：Plan Workspace 独立展示解析与计划阶段，并将计划 round、工具调用、repair 次数、Token（有供应商 usage 时）、耗时、finish reason、错误和终态纳入同一进度摘要；Model Usage 支持 workflow/operation/date 过滤、时区显示与 CSV 导出，记录可关联 operation/stage。
  - UI/Model Usage/Harness trace 必须包含 schema repair 和失败前的安全字段级证据，并聚合首次失败、中断、重试及自动下游调用；不能再出现 UI 2 calls、审计 3 completions 的分裂。
  - 重新界定 Planning trace 的留存、脱敏与访问政策；在 `provider_reasoning_committed=false`、`raw_book_text_committed=false` 时，不得从 API/Debug 暴露完整 thinking 或原始教材输出。
  - Document 已 committed 而 Planning schema/repair 失败时，Plan Workspace 必须显示 Planning 失败及已发生费用，不能泛化为“教材处理失败”；长最终轮展示已等待/总耗时、超时边界和当前阶段。

- [ ] `PLAN-STUDY-UNIT-REVISION-001` `[P1]` 将 Planning 的 `revise_study_units` 从隐式共享 Document 改写变成可审查的提案与独立确认。
  - 模型取证阶段不得在没有预览的情况下替换后续所有 Plan/Study 共用的 Study Units；展示旧/新页范围、标题、分类与保留/删除 diff，并使用 Document revision CAS 提交。
  - 拒绝或跳过修订仍可继续生成保守计划；确认后的 Document、Plan context、Harness effect/trace 与重启 read-back 必须指向同一 revision。

- [ ] `OCR-CHECKPOINT-RECOVERY-001` `[P1]` 让长 OCR 在阶段完成后可读、可续跑。
  - 总 wall-time 在全部页面处理完成后耗尽时，不得抹掉已完成页和 Study Unit；保存有界 checkpoint，并验证重启、超时和重复请求的 read-back/续跑语义。

- [x] `OCR-PROGRESS-UX-001` `[P1]` 向 Plan Workspace 投影长 OCR 的真实进度与可恢复错误。
  - 2026-09-13：Plan Workspace 独立投影 parser/page/OCR fallback/清理阶段、完成页数/总页数、速率与有证据 ETA；失败显示已完成范围、失败阶段、进度保留提示和拆分/调整配置/重试建议，不覆盖 Document 终态。
  - 显示总页数、已完成页、当前 text/OCR fallback 阶段、速率与有证据的预计时间/警告；跨领域 notice 不得覆盖当前 Document 终态。
  - 失败时说明已完成范围、失败阶段、是否保存 checkpoint、同配置重试风险，以及拆分 PDF、调整上限或联系管理员等可行动建议；不直接暴露内部异常码。

### 性能与 Tavern transport

- [ ] `TAV-FACILITATED-ORDER-001` `[P2]` 统一 Tavern facilitated 的目标选择顺序、服务端 schedule 与 Participant Roster 反馈。
  - 服务端仍以 participant `display_order` 为权威时，UI 必须在发送前显示实际执行顺序；若产品承诺用户选择顺序，则需在契约、持久化、恢复和 retry 中共同保留该顺序。

- [ ] `PERF-WEB-DEDUPE-001` `[P2]` 去除页面内重复资源请求。
  - Tavern 对 Persona/Scene 各请求一次；窗口 focus 与恢复流程不得造成无界重复刷新。

- [ ] `PERF-WEB-BUNDLE-001` `[P2]` 建立 `/`、Settings、Model Usage、Tavern 的 production gzip 基线和 5% 回退门。

- [ ] `PERF-WEB-PROVIDER-SCOPE-001` `[P3]` 将根布局中的 `LearningWorkspaceProvider` 下沉到实际消费者，避免 Settings、Model Usage、Tavern 等无关路由初始化学习工作区状态和请求。

- [ ] `TAV-CANCEL-TRANSPORT-001` `[P2]` 建立 capability-aware provider cancellation。
  - 可取消 adapter 必须中断本地传输并释放连接/worker；不支持时继续使用 commit fencing 和 truthful UI。
  - 关闭本项前至少一个实际生产 adapter 必须证明已发请求可中断且资源已释放；全部 adapter 均标记 unsupported 不是关闭路径。
  - 仅在 provider 提供权威证据时声明停止上游计算或计费，不把本地连接关闭冒充 token 停止。

### Study operation hardening

- [ ] `STUDY-OP-RECOVERY-UX-001` `[P2]` 覆盖超长轮询、终态刷新、断网和页面恢复文案，不放宽 same-key mismatch 或 `uncertain` 禁止重放。

## 可靠性、部署与输入边界

- [x] `SETTING-GENERATION-OUTPUT-001` `[P1]` 收口 Persona/Scene 生成的输出预算、截断恢复与错误可观测性。
  - 2026-09-13：统一结构化生成上限与修复增量；Chat finish_reason length/max_tokens 和 Responses incomplete_details 触发独立截断码，重试预算只增不减；Persona/Scene 前端按 timeout、truncation、schema、provider 等稳定码给出可行动文案，并保留 usage/operation 关联。
  - 2026-09-13 桌面应用证据：关键词 Scene 连续三次以 `setting_model_invalid_json` 失败，Persona 一次同类失败，provider 输出均贴近当时 1200/1400 token 上限；另一次 Scene 修复请求连续超时。临时缓解已将 Persona/Scene 生成有效上限提到 8192，不将此作为长期预算设计。
  - 识别 Responses/Chat 的权威 finish reason、`incomplete_details` 和 token 上限命中，将截断映射为独立、可行动的错误；结构化重试必须增加或至少保持预算，不得在重试时降低上限。
  - 对不支持 web search、输出截断、结构修复失败和超时分别定义有界降级政策；仅在安全且预算允许时切到无联网生成，并保留真实 `used_web_search`/recovery 证据。
  - 统一 `max_tokens` / `max_output_tokens` 与 `per_call_timeout_ms` 的配置真源、命名、各 workflow 有效值与重试规则；Settings、运行时与诊断导出应能便捷查询“用户配置或非 Harness fallback / workflow manifest 声明 / 本次实际值”，避免分散硬编码或让全局 timeout 文案误导 Harness 工作流。
  - FastAPI `detail` 字符串必须被前端保留为稳定 error code；Persona/Scene 显示超时、截断、schema 与 provider 错误的可行动文案，Diagnostic/Harness/Model Usage 可按同一 request/operation 关联原因、各次输出预算和终态。
  - 增加输出恰好命中上限、Responses 不完整终态、重试不降预算、web-search 降级、HTTP 错误文案及真实 MiniMax/Gemini 代表请求的回归门。

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

- 本文件是唯一待办索引；其他文档只描述当前契约、限制和复现方式，不维护平行待办。已实现的 Harness 基础设施、13 个阶段评测套件、SQLite 恢复和已定义输入上限测试不再列为待办。
- 架构和逐工作流工程说明见 `docs/harness/README.md`，工程约束见 `AGENTS.md`。`QG-002` / `web-strict-decode-adversarial-v1` 保持不可变，扩展使用新版本。
- Debug 是全局 Overlay，不恢复已删除的 `/debug` 页面。
- 性能任务必须记录 fixture、环境、raw samples 和 before/after；不得通过放宽既有预算关闭回归。
