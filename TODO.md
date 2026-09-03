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

- [ ] `STUDY-OP-RECOVERY-UX-001` `[P2]` 覆盖超长轮询、终态刷新、断网和页面恢复文案，不放宽 same-key mismatch 或 `uncertain` 禁止重放。

## Harness roadmap

Harness 的未完成工作、依赖图、里程碑、评估基线和生产采用门统一维护在
`docs/harness-roadmap.md`。本文件不重复 Harness-owned checkbox；Tavern schema、
Study operation hardening、Plan CAS 等产品线前置任务继续在本文件维护，并由
Harness roadmap 按任务 ID 引用。

## Planning 迭代

Tool Manifest、Planning tool eval 和 parallel-safety 性能门属于 Harness roadmap；
本节只保留 Plan 聚合与用户修订流程。

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
- `STUDY-OP-HARDEN-001`：Clock 与 Scanner 已完成，剩余 Recovery UX 关闭本项。
- `PLAN-ITER-001`：由 Plan CAS、Patch Operation、Revision UX 三个子项关闭。

## Research parking lot（未排期）

以下候选只有在触发证据出现后才建立可领取任务；研究票必须写明假设、time-box、产出物和采用/放弃标准。

- `RND-RUST-001`：仅在 profiling 证明 Python/TypeScript 热点后评估 Rust 重写。
- `RND-THEME-001`：需要用户需求、稳定 design tokens、对比度基线和可关闭开关。
- `RND-LIVE2D-001`：需要授权、资源预算、动画降级和设备性能证据。
- `RND-TTS-001`：需要隐私、延迟、成本、可取消传输、字幕和静音降级证据。
- `SKILL-DISTILL-001`：只抽取稳定、可验证、无密钥/用户数据的仓库流程；`AGENTS.md` 仍是事实真源。

## 持续规则

- Harness-specific 持续规则、tracking epics 和 `QG-002` 扩展规则统一维护在 `docs/harness-roadmap.md`。
- Debug 是全局 Overlay，不恢复已删除的 `/debug` 页面。
- 性能任务必须记录 fixture、环境、raw samples 和 before/after；不得通过放宽既有预算关闭回归。
