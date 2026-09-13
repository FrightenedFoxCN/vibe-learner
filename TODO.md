# TODO

本文件是产品、Harness 和桌面工作的统一待办入口；仅保留未完成任务；完成事项见[0.3.5 发布记录](docs/releases/0.3.5.md)。运行约束见 `AGENTS.md`，架构见 `docs/`，已完成过程记录通过 Git 历史查询。

已完成的 2026-09-12 实验与修复见[阶段归档](docs/quality/completed-work-2026-09-12.md)；质量未完成项仅由[独立质量 TODO](docs/quality/TODO.md)维护。

优先级表示下一阶段排程，不追溯为 v0.2.1 发布缺陷：

- `P1`：用户可用性、数据一致性或跨工作流基础边界，应优先处理。
- `P2`：明确且有收益的产品、性能或可靠性工作。
- `P3`：文档、账务和候选验证。

## UX 与文档

- [ ] `UX-MODEL-USAGE-001` `[P2]` 让 Model Usage 支持明确时区、按 operation/workflow 分类、筛选和导出。
  - Planning repair、失败/中断重试和自动下游调用必须可区分；页面统计与 `PLAN-OBSERVABILITY-001` 的 operation 聚合口径一致，不再只展示当前一次成功调用。
  - Settings 的真实代表请求必须纳入账务或明确标成排除范围；刷新、分页/时间范围与成本估算的统计口径对用户可见，长明细不再无限单页堆叠。

- [ ] `UX-OUTPUT-LANGUAGE-001` `[P2]` 为 Planning 与 Study 提供显式、可持久化的输出语言偏好。
  - `自动` 模式说明如何根据用户目标、教材与 Persona 决定语言；用户指定法文等语言后，计划指导语、任务与后续 Study 默认保持一致，不因中文产品壳混成中法英三语。
  - 语言偏好属于应用输入并进入 operation fingerprint/read-back，不靠模型从自由文本猜测，也不改写教材原文、引文或专有名词。

- [ ] `UX-DENSITY-SENSORY-001` `[P2]` 为 Sensory Tools 增加搜索、筛选和渐进披露；保存/错误定位不得丢失滚动或焦点，批量/删除动作与普通编辑分层。
- [ ] `UX-DENSITY-PERSONA-001` `[P2]` 收口 Persona 的默认折叠、搜索/筛选和主次动作；保存/错误定位不得丢失滚动或焦点，批量/删除动作与普通编辑分层。
  - 重构同步进展：人格库默认折叠，展开状态具有 ARIA 语义；草稿/保存/模型辅助与展示已分离。完整筛选、危险动作分层与独立 UX 复核仍待完成。
  - 生成提案应用前展示名称缺失、字段 diff 和将被清空的内容；允许逐卡接受/拒绝或合并，不能让“清空后全量应用”与普通编辑处在同一风险层级。若名称仍为空，应用后聚焦并明确提示必填字段。
- [ ] `UX-DENSITY-SCENE-001` `[P2]` 收口 Scene 的默认折叠、搜索/筛选和危险操作分层；保存/错误定位不得丢失滚动或焦点，批量/删除动作与普通编辑分层。
  - 重构同步进展：复用/存档区与示例深层树默认折叠，树折叠接入原草稿存储，树操作控件扩大到 44px；删除采用独立模态。完整搜索筛选、错误焦点定位与独立设备复核仍待完成。
  - 生成预览须展示层/物体数量、规则与相对当前树的结构 diff；覆盖当前编辑树前暴露新增物体和约束冲突，不能只显示名称、摘要和节点数。

- [x] `UX-STUDY-PRESENTATION-001` `[P2]` 收口 Study Dialog 的宽屏布局、状态来源和教师正文/表演提示/系统回执层级。
  - 宽桌面不保留无意义的右侧与 Conversation—Composer 大片空白；首轮回复、待确认效果和输入区保持可连续阅读。
  - 顶部 action notice、网络同步、Session 状态和模型生成状态各有稳定职责；角色动作、delivery cue、工具回执默认渐进披露，不与教师正文争夺主层级。
  - 2026-09-13：移除 Conversation 的强制视口高度与内部滚动，把 Composer 紧随 transcript；1440×1000 production Chromium 验证主对话宽度、连续间距和教师正文可见。顶部只承载“操作反馈”，Conversation 内分别投影 Session、记录同步和模型状态，Character Shell 只表达角色状态；动作、表达提示和工具回执默认折叠且可展开。

- [ ] `DOC-USER-001` `[P2]` 补齐并独立走查用户手册。
  - 2026-09-11：新增主页独立入口与 `/manual` 网页手册，简述首次使用、主要操作、恢复、数据及安装；正文统一在网页维护。独立新数据主流程与桌面安装走查仍待验收。
  - 本轮主智能体使用全新临时数据库/真实 mock 后端，走通纯目标生成、自动创建会话、提问与刷新读回；不替代独立完整手册验收。仍需 Settings 首次配置、教材路线、其他领域及桌面安装走查，见[核对报告](docs/plans/acceptance-audit-2026-09-11.md)。
  - 覆盖 goal-only、mock/real 首次使用路线，Document/Plan/Study/Persona/Scene/Tavern 主任务、恢复语义、数据位置与留存，以及产品限制。
  - 覆盖 DMG/NSIS/AppImage 安装、unsigned 限制和 SHA-256 校验。
  - 使用全新临时数据目录走通一次 mock 主流程和一次桌面安装流程。

### Planning → Study 工作流

本节复现证据见 [2026-09-13 M3 Planning production 配对复测](docs/acceptance/m3-planning-retest-2026-09-13.md)；验收报告保留事实，本节维护工程状态。

- [ ] `PLAN-NAVIGATION-LIFECYCLE-001` `[P1]` 让 Planning 长任务跨页持续，或在离页前明确提示将取消并展示已发生费用。
  - 当前普通导航会调用 Document/Planning stream cancel；真实请求仍可能完成并计费，但 Learning Plan 不提交。全局 Debug 与返回后的 Plan Workspace 应显示活动、已中断、费用和可恢复状态。

- [ ] `PLAN-PAGE-BOUNDS-001` `[P1]` 将用户显式 PDF 物理页范围变成服务端工具、proposal 与 commit invariant。
  - 用户指定 PDF 100–103 时，取证工具参数、schedule anchor 和 content slices 必须落在该范围；物理页与印刷页分别建模，不能让模型把印刷 70–73 当成物理 70–73 后成功提交。
  - 本票只负责应用约束；教材语义、公式、旧记号和范围完整性质量由 `docs/quality/TODO.md` 的 `MQ-04` 负责。

- [ ] `PLAN-OBSERVABILITY-001` `[P1]` 统一一次 Planning operation 的 provider round、工具、repair、token、时延、终态与产物口径。
  - UI/Model Usage/Harness trace 必须包含 schema repair 和失败前的安全字段级证据，并聚合首次失败、中断、重试及自动下游调用；不能再出现 UI 2 calls、审计 3 completions 的分裂。
  - 重新界定 Planning trace 的留存、脱敏与访问政策；在 `provider_reasoning_committed=false`、`raw_book_text_committed=false` 时，不得从 API/Debug 暴露完整 thinking 或原始教材输出。
  - Document 已 committed 而 Planning schema/repair 失败时，Plan Workspace 必须显示 Planning 失败及已发生费用，不能泛化为“教材处理失败”；长最终轮展示已等待/总耗时、超时边界和当前阶段。

- [ ] `PLAN-STUDY-UNIT-REVISION-001` `[P1]` 将 Planning 的 `revise_study_units` 从隐式共享 Document 改写变成可审查的提案与独立确认。
  - 模型取证阶段不得在没有预览的情况下替换后续所有 Plan/Study 共用的 Study Units；展示旧/新页范围、标题、分类与保留/删除 diff，并使用 Document revision CAS 提交。
  - 拒绝或跳过修订仍可继续生成保守计划；确认后的 Document、Plan context、Harness effect/trace 与重启 read-back 必须指向同一 revision。

- [ ] `OCR-CHECKPOINT-RECOVERY-001` `[P1]` 让长 OCR 在阶段完成后可读、可续跑。
  - 总 wall-time 在全部页面处理完成后耗尽时，不得抹掉已完成页和 Study Unit；保存有界 checkpoint，并验证重启、超时和重复请求的 read-back/续跑语义。

- [ ] `OCR-PROGRESS-UX-001` `[P1]` 向 Plan Workspace 投影长 OCR 的真实进度与可恢复错误。
  - 显示总页数、已完成页、当前 text/OCR fallback 阶段、速率与有证据的预计时间/警告；跨领域 notice 不得覆盖当前 Document 终态。
  - 失败时说明已完成范围、失败阶段、是否保存 checkpoint、同配置重试风险，以及拆分 PDF、调整上限或联系管理员等可行动建议；不直接暴露内部异常码。

### 性能与 Tavern transport

- [ ] `TAV-FACILITATED-ORDER-001` `[P2]` 统一 Tavern facilitated 的目标选择顺序、服务端 schedule 与 Participant Roster 反馈。
  - 服务端仍以 participant `display_order` 为权威时，UI 必须在发送前显示实际执行顺序；若产品承诺用户选择顺序，则需在契约、持久化、恢复和 retry 中共同保留该顺序。

- [ ] `PERF-WEB-DEDUPE-001` `[P2]` 去除页面内重复资源请求。
  - Tavern 对 Persona/Scene 各请求一次；窗口 focus 与恢复流程不得造成无界重复刷新。

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

## 模型质量复核

- [ ] `QG-MODEL-QUALITY-001` `[P2 · 已暂停，待独立复核]` 建立真实模型质量与 held-out 评测基线。
  - 历史 MiniMax-M3 第 121 轮已按要求停止；本次明确重新授权的并行实验已另行交付。详细未完成事项、证据和关闭标准只维护在[独立质量 TODO](docs/quality/TODO.md)，不自动继续实测。
  - [已采用运行时行为](docs/model-runtime-quality.md)与[研究接手摘要](docs/quality/research-summary.md)已整理；旧 `QG-002` / `web-strict-decode-adversarial-v1` 不变。
  - 新增[Agentic design / ACL 研究](docs/quality/agentic-design-research-2026-09-12.md)与[首日 2000M tokens 探索计划](docs/quality/m3-parallel-exploration-2026-09-12.md)：优先引用、写入忠实度、记忆时间关系及独立评审，按需扩容并保留失败证据。
  - 已完成的确定性注册不重做；模型 grader 需独立人工校准，技术恢复和维护者评审不代替内容质量验收。

## Research parking lot（未排期）

以下候选只有在触发证据出现后才建立可领取任务；研究票必须写明假设、time-box、产出物和采用/放弃标准。

- `RND-RUST-001`：仅在 profiling 证明 Python/TypeScript 热点后评估 Rust 重写。
- `RND-THEME-001`：需要用户需求、稳定 design tokens、对比度基线和可关闭开关。
- `RND-LIVE2D-001`：需要授权、资源预算、动画降级和设备性能证据。
- `RND-TTS-001`：需要隐私、延迟、成本、可取消传输、字幕和静音降级证据。
- 桌面自动更新、崩溃上报及 sidecar 打包形态调整：先确定发布策略并通过性能测量再立项。
- `SKILL-DISTILL-001`：只抽取稳定、可验证、无密钥/用户数据的仓库流程；`AGENTS.md` 仍是事实真源。

## 持续规则

- 本文件是统一待办索引；已实现的 Harness 基础设施、13 个阶段评测套件、SQLite 恢复和已定义输入上限测试不再列为待办。
- 架构见 `docs/harness-architecture.md`，工程约束见 `AGENTS.md`。`QG-002` / `web-strict-decode-adversarial-v1` 保持不可变，扩展使用新版本。
- Debug 是全局 Overlay，不恢复已删除的 `/debug` 页面。
- 性能任务必须记录 fixture、环境、raw samples 和 before/after；不得通过放宽既有预算关闭回归。
