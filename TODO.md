# TODO

本文件是产品、Harness 和桌面工作的统一待办入口；用户指定的专项计划独立维护明细并在此链接，不复制 checkbox。运行约束见 `AGENTS.md`，架构见 `docs/`，已完成过程记录通过 Git 历史查询。

2026-09-10：本文件保留 27 项产品/验收待办；下方专项计划还有 2 项解耦和 4 项 Debug 工作，合计 33 项，其中 1 项质量复核暂缓。研究候选不计入任务数。

优先级表示下一阶段排程，不追溯为 v0.2.1 发布缺陷：

- `P1`：用户可用性、数据一致性或跨工作流基础边界，应优先处理。
- `P2`：明确且有收益的产品、性能或可靠性工作。
- `P3`：文档、账务和候选验证。

## Now（下一批可领取）

专项计划已独立落盘，在 0.3.0 之后逐步实施，不计为本次发布已实现功能：

- [代码解耦重构](docs/plans/architecture-refactor.md)：7 项中 5 项已完成，剩余前端领域拆分与测试边界；保留现有事务/恢复语义。
- [统一 Logging 与 Debug](docs/plans/unified-debug.md)：4 项，打通页面视图、全局记录和性能审计。

- [ ] `UX-A11Y-STUDY-QUESTION-001` `[P1]` 完成 Interactive Question 无障碍语义。
  - 补齐题组 busy 状态、单选/多选选择语义、填空显式 label、错误播报、焦点恢复和至少 44px 触控目标。
  - 验收：键盘、屏幕阅读语义和持久化 read-back 流程均通过独立验收。

- [ ] `UX-A11Y-SCENE-DIALOG-001` `[P1]` 完成 Scene 删除层级 Dialog 的模态行为。
  - 补齐初始焦点、focus trap、Escape、背景 inert，以及取消/确认后的焦点恢复。
  - 验收：键盘无法逃逸到背景，取消后焦点回到发起控件；确认删除移除控件时回到 Scene 标题。
  - 2026-09-10：独立 SceneDeleteDialog 使用原生 showModal 背景 inert，补齐初始焦点、Tab 循环、Escape 与焦点恢复。生产 Chromium 2 项完整键盘/删除测试通过；仍待独立复核后关闭。

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
  - 已实现：学习 Provider 限于 Plan/Study，Debug Overlay 独立；默认教师/空业务数据下，十个顶级页面及 focus 的 Chromium 网络清单通过。
  - 剩余：有历史 Plan/Session、在途操作和离页恢复的完整路由矩阵；不以空数据初始化验收代替恢复场景。
  - 验收：为每个顶级路由冻结允许请求清单，并以浏览器网络记录和自动化测试验证。

## Next（已定义、待排期）

### UX 与文档

Persona/Scene 编辑、异步反馈和 Scene 删除 Dialog 与 `ARCH-WEB-001` 同步实施；以下 checkbox 仍以各自完整验收范围为准。

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

- [ ] `STUDY-OP-RECOVERY-UX-001` `[P2]` 覆盖超长轮询、终态刷新、断网和页面恢复文案，不放宽 same-key mismatch 或 `uncertain` 禁止重放。

## Planning 迭代

当前 Planning 创建、Tool Manifest 和确定性评测已实现；以下是 Plan 后续修订能力。

- [ ] `SCH-PLAN-CAS-001` `[P1]` 建立数据库权威 Plan revision/CAS。
  - 覆盖全部计划写入口、旧数据迁移，以及既有 Study Session、进度和 schedule identity 的并发语义。

- [ ] `PLAN-PATCH-001` `[P2]` 建立 strict patch proposal 与 durable operation；依赖 Plan CAS 和 Planning Harness lifecycle。
  - 覆盖 base revision、冲突、回滚、恢复，以及 ID/progress 映射。

- [ ] `PLAN-REV-UX-001` `[P2]` 增加修订 diff、接受/拒绝、冲突刷新、回滚和恢复 UX；依赖 `PLAN-PATCH-001`。

## 可靠性、部署与输入边界

- [ ] `REL-DESKTOP-001` `[P2]` 完成真实桌面/浏览器恢复验收。
  - 覆盖慢网、断网、刷新/离页、Settings 未保存变更、编辑器异步返回、删除/归档组合、桌面安装/退出；覆盖 Tavern 无 Persona/无 Room、设备级 IME 和完整焦点顺序。
  - 已有进程退出、事务回滚、HTTP 重启读回测试作为回归门；不得重复列为待实现。Study 文案由 `STUDY-OP-RECOVERY-UX-001` 负责。

- [ ] `REL-POSTGRES-001` `[P2]` 在实际 PostgreSQL 上完成迁移、并发 CAS、事务回滚和重启恢复验收。
  - 当前完整恢复矩阵在 SQLite 上通过；SQLite 结果不能替代 PostgreSQL 实测。

- [ ] `REL-REPLAY-001` `[P2]` 独立复核 Document、Planning、Persona/Scene 的受保护制品重放。
  - 覆盖授权、保留/删除、摘要损坏和版本兼容；复用现有运行时、解析器和测试，不新增一套 Harness 基础设施。

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

## 暂缓：质量复核

- [ ] `QG-MODEL-QUALITY-001` `[P2 · 用户暂缓]` 建立独立复核的真实模型质量与 held-out 评测基线。
  - 重点覆盖填空题语义判分、人格关系/称呼 grounding、规划引用和生成内容质量。
  - 十个阶段的 64 个确定性案例及原有三个 pilot 已完成；不重做注册，不把技术恢复测试当作模型质量验收。
  - 模型 grader 用于门禁前必须有独立人工校准；用户恢复此项后再开展，不因文档清理自动视为通过。

## Research parking lot（未排期）

以下候选只有在触发证据出现后才建立可领取任务；研究票必须写明假设、time-box、产出物和采用/放弃标准。

- `RND-RUST-001`：仅在 profiling 证明 Python/TypeScript 热点后评估 Rust 重写。
- `RND-THEME-001`：需要用户需求、稳定 design tokens、对比度基线和可关闭开关。
- `RND-LIVE2D-001`：需要授权、资源预算、动画降级和设备性能证据。
- `RND-TTS-001`：需要隐私、延迟、成本、可取消传输、字幕和静音降级证据。
- 桌面自动更新、崩溃上报及 sidecar 打包形态调整：先确定发布策略并通过性能测量再立项。
- `SKILL-DISTILL-001`：只抽取稳定、可验证、无密钥/用户数据的仓库流程；`AGENTS.md` 仍是事实真源。

## 持续规则

- 本文件是统一待办索引，专项明细见上述链接；已实现的 Harness 基础设施、13 个阶段评测套件、SQLite 恢复和已定义输入上限测试不再列为待办。
- 架构见 `docs/harness-architecture.md`，工程约束见 `AGENTS.md`。`QG-002` / `web-strict-decode-adversarial-v1` 保持不可变，扩展使用新版本。
- Debug 是全局 Overlay，不恢复已删除的 `/debug` 页面。
- 性能任务必须记录 fixture、环境、raw samples 和 before/after；不得通过放宽既有预算关闭回归。
