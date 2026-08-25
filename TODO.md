# TODO

## 当前接手顺序（2026-08-25）

本文件只保留未完成工作；完成项的运行约束和验证事实应迁入 `AGENTS.md`、架构或 API 文档，不保留勾选行，也不依赖历史 handoff 文档。

1. Study safe-retry 与当前数据库/Scene/file effect 提交边界已通过独立故障复核；跨工作流 durable effect primitive、provider exactly-once 与 Study v3 仍是不同的开放范围。无 provider idempotency 或权威 read-back 时必须保持 `uncertain`。
2. 下一阶段按已登记的性能、文档、P2/P3 与研究候选继续推进，不把长期 Harness 采用项扩回已关闭的发布门。

跨工作流 Harness 仍是长期主线；局部 strict decoder、effect 或 evidence 基础完成不代表 Document、Planning、Persona、Scene、Study、Tavern 或 Frontend Decode 已整体采用 v3。

## 酒馆与角色可靠性

完成 Tavern 的 Harness 项不代表其他工作流已接入 Harness；全链路状态以“审计与质量门”及 `docs/harness-schema-ownership.md` 为准。

- [ ] `HRN-TAV-002` 建立身份、称呼、目标、跨角色冒充和 prompt injection 回归矩阵；speaker identity v2 已集中编译角色名称、Persona ID 与安全别名，覆盖行内引号、Markdown、Unicode 冒号、他人引语/内心活动、名称包含关系及修复后全字段复扫，无法安全修复时 fail closed。剩余验收：由统一 eval 记录 schema-valid rate、repair rate、误报率与身份一致率，不能以实现者单测代替完整矩阵。
- [ ] `HRN-TAV-PERF-001` 完成 Tavern prompt 性能/eval 门；prompt-budget-v1 已在 provider 前限制 canonical prompt 256 KiB、保守 input token estimate 48k、Scene 64 KiB/8 层、transcript 128 KiB、Persona instruction/cast 分区，并从最旧消息确定性裁剪；成功 trace 只记录无内容的原/终 bytes 与删除数，拒绝 trace 记录 content-free partition/actual/limit。剩余验收：最坏 6 人长对话的真实 tokenizer/provider p50/p95、v3 protected artifact/trace 与版本化回退阈值，当前局部 preflight 不冒充完整 eval gate。
- [ ] `SCH-TAV-001` 决定并实现 run/message/step 软引用策略；验收：`run_id`、`message_id`、`reply_to_message_id` 要么具备可迁移外键与插入顺序，要么由统一 invariant scanner 检测并阻断破损图。
- [ ] `UX-001` Tavern Workspace 发布体验 tracking epic（剩余依赖 `TAV-UX-COPY-001`）；仅在剩余子项通过独立验收后关闭，本项不重复承载已关闭实现。
- [ ] `TAV-CANCEL-TRANSPORT-001` 将 Tavern provider 改为真正可取消的传输；验收：Cancel 能中断已发出的上游请求而不只 fencing 结果，释放连接/worker 并停止 token 消耗；在此之前 UI 文案必须称“取消接收结果”，不能承诺已停止模型计算。
- [ ] `TAV-UX-COPY-001` 固化 pending/generating/completed/partial/failed/blocked/retry/stale/archived 中文文案；验收：blocked 不显示为角色失败，raw code 只进入 Reliability Details/debug。

## 审计与质量门

- [ ] `SCH-HRN-EFFECT-001` 将已在 Study 验证的 typed effect 分类收敛为跨工作流 durable batch primitive；验收：数据库写、文件/staging/outbox 与外部/provider adapter 共享版本化 prepare/commit/compensate/read-back 接口和 durable per-effect journal，应用按 operation + slot 分配 identity，且 `not_committed/committed/uncertain` 语义不会把 DB 事务冒充外部 effect exactly-once。Study 当前数据库/Scene/file safe-retry 边界已独立通过；本项只跟踪尚未抽取的跨工作流 primitive 与 durable journal，不冒充 provider read-back 或 v3 stage。
- [ ] `HRN-CTX-ARTIFACT-001` 建立受保护 artifact resolver；验收：不可变 opaque ID、artifact/type/contract 注册、先鉴权后读取、留存与过期规则、read-back digest，返回 `resolved/not_found/expired/forbidden/digest_mismatch/schema_unsupported` 等 typed result，并覆盖删除、篡改、跨主体访问和批量解析预算。现有 `document_debug` / `planning_trace` 可清理缓存不得冒充永久 replay artifact。
- [ ] `HRN-CTX-RUNTIME-001` 建立跨业务可复用的 Harness operation runtime；验收：统一 operation/attempt/check/commit/rollback/terminal-failure 组装，调用方只能通过注册的 context/artifact/effect boundary 进入，幂等与失败持久化有 adapter 接口和故障 fixture。各分域采用项依赖该 primitive；`HRN-CTX-001` 是汇总 epic，不作为所有分域开始实施的循环前置。
- [ ] `HRN-CTX-PERF-001` 为 context build/digest/resolve 建立预算；验收：限制 manifest canonical bytes、单/总 snapshot bytes、引用数量和 resolver I/O，最坏 fixture 记录 p50/p95，超限在模型/worker 执行前失败。
- [ ] `HRN-CTX-001` 将 v3 context/trace lifecycle 接入全部工作流（tracking epic；context foundation 已具备，仍依赖 `HRN-CTX-ARTIFACT-001`、`HRN-CTX-RUNTIME-001`，仅在全部分域采用项完成后关闭）；验收：真实版本化 parser/heuristic/toolset/compiler/decoder，受保护 snapshot refs 可解析并校验，敏感原文不入 trace，失败与 commit evidence 完整。
- [ ] `HRN-RECOVERY-MIG-001` 统一旧 `ModelRecoveryRecord`、Planning round recovery 与 v3 attempt/check 的映射（依赖 `HRN-CTX-RUNTIME-001`；各分域在触及旧 recovery 时按需采用）；验收：同一 operation 可关联，旧 API 保持兼容，新指标不重复计数，并有明确弃用路径。
- [ ] `STUDY-OP-HARDEN-001` 集中收口 admission 上线后的非阻断 hardening，避免将极端项反复扩回当前 release gate；验收：SQLite/PostgreSQL journal DDL/JSON 类型和状态约束持续对齐，统一 canonical database clock，把 scheduled-follow-up/scene-binding 等确定性校验前移到 claim 前并产生可信 `not_committed`，增加 journal corruption/version/digest read-back scanner，覆盖超长等待、active-slot 高竞争、终态轮询与刷新/断网页面文案；这些防御不得放宽 same-key mismatch、`uncertain` 禁止重放或 committed 同快照回读不变量。已完成 claim 前 Session revision / scheduled follow-up / Scene binding / attachment 校验，以及并发 active-slot 与 execution deadline fixture；database clock、跨方言 DDL scanner、超长轮询/断网文案仍开放。
- [ ] `HRN-DOC-001` 将 extraction/OCR/Section/Chunk/Study Unit cleanup 接入 v3（resource/stage registries 已具备，仍依赖 `HRN-CTX-ARTIFACT-001`、`HRN-CTX-RUNTIME-001`）；验收：在已修复提交边界上为各 stage 记录 parser/heuristic/context 版本、页覆盖/边界/排序/source-ID/密度预算 invariant，并补齐 v3 terminal trace、protected artifact replay/eval；本项不重复定义 Document 原子提交修复。
- [ ] `HRN-PLAN-001` 将 Planning 接入 validate/repair/commit 生命周期（strict proposal/tool ownership、原子提交边界与 resource/stage registries 已具备，仍依赖 `HRN-CTX-ARTIFACT-001`、`HRN-CTX-RUNTIME-001`）；验收：集成版本化 toolset/prompt/context、attempt/check、terminal trace、protected artifact replay 和 grounding/tool-correctness eval。
- [ ] `HRN-PERSONA-001` 建立 Persona 生成 Harness（resource evidence registry 已具备，仍依赖 `HRN-CTX-ARTIFACT-001`、`HRN-CTX-RUNTIME-001`）；当前 `count` 已定义为 1..24 的精确卡片数，prompt 与 Mock 已对齐，provider 输出在 normalizer 后对过多/过少均稳定 fail closed；缺省 `count` 仍由模型按素材决定。剩余验收：严格 proposal 不含应用 ID/source/time，slot/身份/称呼 invariant、版本化 prompt/context、失败零持久化和 fixture replay 通过。
- [ ] `HRN-SCENE-001` 建立 Scene 生成 Harness（strict proposal/committed-save ownership、Scene row CAS 与 resource evidence registry 已具备，仍依赖 `HRN-CTX-ARTIFACT-001`、`HRN-CTX-RUNTIME-001`）；验收：版本化 proposal/context、allow-list reuse 引用、递归结构 invariant、失败零持久化和 fixture replay/eval 通过。
- [ ] `HRN-STUDY-001` 将 Study Chat 接入 v3 Harness（safe-retry、typed effect commit/staging 与 resource evidence registry 已具备，仍依赖 `HRN-CTX-ARTIFACT-001`、`HRN-CTX-RUNTIME-001`）；验收：记录版本化 prompt/context、strict reply、attempt/check、commit/rollback/uncertain evidence、protected artifact replay 与 citation/effect correctness eval。当前 safe-retry PASS 不等于本项完成。
- [ ] `HRN-TAV-V3-001` 将 Tavern 生产证据从 legacy v1 切换到 v3（resource evidence registry 已具备，仍依赖 `HRN-CTX-ARTIFACT-001`、`HRN-CTX-RUNTIME-001`、`HRN-RECOVERY-MIG-001`）；验收：旧 v1/v2 可读，run/step/message 产生 v3，actor parent lineage、partial/failed/not-committed、per-step commit 与 child retry trace 可聚合，前端 v1/v2/v3 fixtures 通过。
- [ ] `HRN-WEB-001` 前端 decode/recovery Harness tracking epic；域 decoder、versioned stream state machine 与 stale-result fence 已完成，仍依赖开放的 `QG-002` 共享攻击语料维护门。本项不重复实现 decoder、stream 或 stale fence；Python 后端仍是 canonical digest authority，浏览器不得用 `JSON.stringify` 伪装同构 digest。
- [ ] `HRN-EVAL-001` 建立跨工作流 fixture/eval 运行器与版本基线；验收：覆盖 malformed、boundary、retry exhaustion、duplicate、concurrency、commit failure，报告 schema-valid/repair/failure/commit-consistency/p95，并由各 workflow 注册最低 accuracy 指标（OCR 文本/覆盖、Section/Study Unit 边界、plan grounding/tool correctness、Persona/Tavern identity、Scene 结构、Study citation/effect correctness、frontend decode），用版本化基线和回退阈值使 CI 失败。
- [ ] `QG-002` 维护跨 Document/Plan/Persona/Scene/Study/Tavern 的共享 adversarial payload/stream fixtures 与运行入口；本项只提供攻击语料和 golden，不替代各域 decoder、stale fence 或 stream 状态机的实现/关闭。
- [ ] `UX-NAV-001` 重构顶级导航信息架构与 390px 行为；移动链接现已具备 44×44 触控目标与可访问名称，但 9 个平级入口仍隐藏标签并依赖单行横向滚动。验收：学习、角色与世界、系统分组清晰，加入 Tavern 后标签不依赖隐蔽横向滚动，当前页与入口层级语义明确，焦点顺序可预测。
- [ ] `UX-A11Y-001` 为跨页面异步状态补齐 `aria-live` / `role=alert`、焦点恢复和最小 44px 交互目标；Tavern 的导航、动作按钮、Setup input/select、历史消息与 Provider details 已具备 44px 静态契约，但本轮环境未能重新建立 390×844 专用浏览器视口，不冒充设备级量测。本次抽样中 Persona Spectrum、Scene Setup、Sensory Tools 分别约有 57/71/64 个交互目标低于 44px，Persona 还有多个无可访问名称的 24px 图标按钮。Interactive Question 还需 `aria-busy`、选择状态语义、填空 label，并将当前约 30–36px 的答题控件提升到触控门槛。Scene 删除层级 dialog 虽已有 `role="dialog"` / `aria-modal`，但打开后焦点仍在背景、背景未 inert、Escape 不关闭，Cancel 后焦点落到 `body`；需补初始聚焦、focus trap、Escape、背景 inert 与关闭后焦点恢复。
- [ ] `UX-EDITOR-DENSITY-001` 为 Persona Spectrum、Scene Setup 与 Sensory Tools 建立渐进披露和长表单导航；本次页面抽样约有 60、78、66 个交互控件，Sensory Tools 页面高度约 2712px，主任务、批量开关、危险操作与高级字段处于同一视觉层级。验收：首屏只突出创建/选择/保存等主任务，高级字段可分组折叠，长列表支持搜索/筛选和稳定上下文，保存/错误定位不丢滚动与焦点，批量及删除动作与普通编辑明显区分。

## 性能与文档

- [ ] `PERF-001` 将完整 Learning Workspace Provider 从无关页面下沉；本次后端访问日志确认 Settings 与 Model Usage 等无关路由仍各自请求 `/personas`、`/documents`、`/learning-plans`、`/scene-library`、`/runtime-settings`，Tavern 还重复读取 Persona/Scene。验收：404/设置页不再加载学习工作台数据，同一页面相同资源请求去重，首屏 gzip 不回退超过 5%。
- [ ] `PERF-002` 延迟导入 LiteLLM/OCR 重依赖；mock `/health` 冷启动当前已低于 2 秒且 ONNXTR 为首次 OCR 才加载，但 LiteLLM 仍在 mock 启动时顶层导入并可能尝试远端 cost map。验收：10 个全新进程均低于 2 秒，mock import 后 `litellm` / `onnxtr` 不在 `sys.modules`，且没有远端 cost-map 请求。
- [ ] `PERF-TAV-ROOMS-001` 完成 Tavern Room 历史分页时间门；`tavern-room-list-v1` 已实现 `(updated_at DESC, id DESC)` cursor、默认 30/最大 50、`limit + 1`、复合索引、每页最多 4 SQL、Web append/去重/selected pin 与 100 个按钮上限，1,000 Room 结构 fixture 已通过。剩余验收：按 `docs/performance-budgets-v1.md` 固化 50 次首/中/末页 server P95、30 次 React Profiler 与 machine-readable raw sample artifact；纯函数时间不能冒充 React 渲染门。

## 规划与工具演进

- [ ] `PLAN-ITER-001` 在既有 strict proposal ownership 与原子提交边界上支持逐步修订；验收：每轮基于明确 base revision 产生 patch proposal，冲突/回滚/恢复可判定，最终 committed plan 仍由应用分配 ID。
- [ ] `PLAN-TOOLS-PERF-001` 在 provider 支持时并行执行互不依赖的只读 Planning tools；验收：依赖图阻止写工具或有序工具误并行，同批结果稳定排序，调用轮次下降且 grounding/tool-correctness 基线不回退。
- [ ] `TOOL-CATALOG-001` 整理 Planning/Study tool ownership、输入 schema、读写/外部 effect 分类与 Prompt 契约；验收：重复/废弃工具有迁移路径，实际调用率和无效调用由 `HRN-EVAL-001` 报告，不以 prompt 鼓励代替证据。
- [ ] `SKILL-DISTILL-001` 评估可复用的项目工作流记忆是否应沉淀为仓库 skill；验收：仅抽取稳定、可验证、无密钥/用户数据的流程，版本、适用范围和退役方式明确；根 `AGENTS.md` 仍是当前仓库事实真源。
- [ ] `DOC-USER-001` 完善使用文档和功能介绍（依赖 `UX-001`）；验收：覆盖 mock/real provider、Document/Plan/Study/Persona/Scene/Tavern 主任务、恢复语义、数据位置与限制，并由首次使用者独立走查。

Debug 是全局 Overlay，不恢复已删除的 `/debug` 页面。启动性能由 `PERF-002` 跟踪。

## 研究候选（未排期）

- [ ] `RND-RUST-001` 评估以 Rust 重写性能敏感组件；验收标准在 profiling 证明 Python/TypeScript 热点后另立，不以“见新分支”作为实施依据。
- [ ] `RND-THEME-001` 研究按 Persona/Scene 动态调整 UI 主题；前置是可访问性对比度、用户关闭开关和稳定 design token contract。
- [ ] `RND-MEDIA-001` 研究 Live2D/TTS；前置是授权/隐私、资源预算、可取消传输、字幕与无动画降级方案。
