# 统一 Logging 与 Debug 实施计划

状态：实施中；按基础、流程、Debug 视图、审计四阶段分步提交。以下四项以本文件为唯一详细任务来源，根 TODO 仅链接。质量复核仍按用户要求暂缓。

### 统一 logging 与 Debug（按 1 → 2 → 3 → 4 实施）

- [x] `OBS-FOUNDATION-001` `[P1]` 建立统一诊断事件和关联上下文。
  - Python/TypeScript 共用版本化事件契约；区分客户端 action/page view、服务端 request、真实 Harness operation/trace/attempt 与持久资源身份。
  - 结构化 Python logging、前端请求入口及有界事件存储；在容器构造前初始化 logging。先打通 Persona 生成 → 保存 → 重载的纵向样例。
  - 关联 ID 仅用于诊断，不参与授权或幂等判断；跨线程、流式结束、取消和请求重放都必须正确关联。
  - 2026-09-10 完成：事件分类及 severity/outcome/error code 有 Python/TypeScript 共享样本；诊断 request、flow/action/page-view 与真实 Harness operation/trace/attempt、保存后的 Persona ID/revision 分开记录。浏览器上传不能伪造权威引用。
  - 验收：31 项后端诊断/生命周期/commit/Persona 测试、4 项客户端诊断测试、Persona 组合关联测试、shared contracts/Web 类型检查及生产构建通过。Chromium 使用独立临时数据库与真实 mock 后端走通生成→保存→刷新→重载；Debug 关闭仍记录，日志无提示词/人格正文。重放读请求分配新 request ID，取消与 worker context 传播有回归门。
  - 可复跑：`npm --workspace @vibe-learner/web run test:diagnostics:browser`（先 `npm run build:web`）；`services/ai/tests/test_diagnostics.py`、`apps/web/tests/diagnostics.test.ts` 与 `persona-diagnostics.test.jsx`。分步实现记录通过 Git 历史查询。跨流程重启索引、留存/导出与性能验收仍由后续三项负责。


- [ ] `OBS-FLOWS-001` `[P1]` 覆盖全部功能流程和 Harness 性能记录；依赖 `OBS-FOUNDATION-001`。
  - 覆盖 Document/OCR/清洗、Planning/tools、Persona/Scene、Study/题目/附件、Tavern、Settings/Vault、导入导出及桌面启动/sidecar 退出。
  - Harness/operation receipt 保持事实来源；诊断索引引用真实记录，不复制完整 trace 或把 HTTP 200 当提交成功。
  - 记录阶段、尝试、provider/tool 耗时、token 来源、预算、恢复和缺失数据；关联与终态索引支持重启补建和幂等去重。
  - 2026-09-10 索引切片：新增独立 `harness-index.sqlite3`，分页扫描 canonical runtime、原子保存 checkpoint 和受限指标投影，重启去重并周期补扫晚到提交；来源删除/异常有明确缺口。request→operation 关联单独持久化，事件列表清理后仍可查询。37 项诊断/index/生命周期/Harness runtime/commit 测试及 shared contracts/Web 类型门通过。模型、usage、费用当前诚实标记未被 canonical trace 记录；provider/tool 指标、完整流程覆盖、查询 UI 与性能量测仍待后续切片。

  - 2026-09-10 Provider 切片：统一 LiteLLM transport 记录父调用和逐次重试 span、monotonic 耗时、timeout/max-attempts、恢复次数及严格 provider-reported token；缺失/非法 token 保持 null，父调用不重复携带子 usage。指标引用已 prepare 的真实 Harness trace，退出 runtime 后恢复上下文。37 项 provider/SDK/diagnostic/runtime 测试、4 项客户端分类测试及 shared contracts/Web 类型门通过；没有真实上游费用证据，不声明 cost 或完整 endpoint 配置覆盖。

  - 2026-09-10 Tool 切片：Planning 六工具与 Study 三十一工具在原 decode/budget/runtime/result 边界记录 start/finish/failure、Manifest 契约/预算及耗时；未知名称脱敏，参数/结果/评分材料不记录，provider tool-call ID 只作独立关联。嵌套 provider span 归属工具 span，工具成功明确不声明效果提交。34 项后端专项测试（含全部 37 工具拒绝路径）和完整 `npm run check` 通过，包含全部 13 个 Harness suite。其余前端/桌面事件及完整配置、审计指标仍待完成。

  - 2026-09-10 本地动作切片：JSON 导入读取/导出交接、Settings 保存队列及六个 Vault 入口记录明确动作名和结果；保存上下文显式传入 Vault/HTTP，嵌套本地 span 保留父子关系。日志不包含文件名、正文、凭据或异常原文；诊断 ID 分配失败不阻止本地动作。9 项客户端诊断测试、1 项 Vault 入口测试、18 项后端诊断测试、完整 Web reliability 与 shared/type 门通过。Vault 测试覆盖不可用/锁定入口，真实 native 创建/解锁和桌面启动/退出仍待后续验收。

  - 2026-09-10 桌面切片：Rust 在 sidecar 就绪前写入 256 文件有界 spool，记录启动、就绪、异常退出与关闭；后端严格校验后持久化，再删除原文件，离线/重启沿用事件 ID 并去重。Rust/Python 共享协议样本，5 项 Rust 测试（含真实 Unix 子进程退出/清理）、20 项后端专项测试及 shared/Web 类型和 9 项客户端诊断测试通过。写盘/线程启动失败不阻断业务；日志不包含路径、命令参数或异常原文。当前验收限本机 Unix；跨平台、真实 native Vault 成功路径及 crash-safe 多进程丢失计数仍未认证。

  - 2026-09-10 页面切片：全部九个现有路由使用固定 page_path 白名单和独立 page-view 记录进入/离开；异步请求保留捕获时的页面，重复清理不会覆盖新页面。查询支持 page_path；不持久化任意 URL/query。21 项后端测试、11 项客户端诊断测试、实际 React Collector StrictMode/路由切换/卸载测试及 shared/Web 类型门通过；崩溃缺少离开事件不推断成功，缺口审计仍由第四阶段负责。

  - 2026-09-10 解码切片：API 响应以 Response 实例保留关联，JSON 语法、现有领域解码器和 Document/Planning 流契约拒绝记录独立 decode_failed；标量/null、页面切换后返回也关联原请求。原异常与 Tavern 明确终态重放边界保持，正文/异常/评分内容不进入诊断。5 项实际 API 诊断测试、21 项后端测试、完整 Web reliability、stream decoder 回归及 shared/Web 类型门通过；这些测试不证明尚未接入严格解码器的遗留 normalizer 已具备严格契约。

- [ ] `OBS-DEBUG-001` `[P1]` 改造 Debug 浮窗的页面和全局视图；依赖 `OBS-FLOWS-001`。
  - 独立 DebugProvider + 按 page-view 注册的快照/数据适配器；去除浮窗对 LearningWorkspaceProvider 的强依赖，与 `PERF-WEB-PROVIDER-001` 协同。
  - 页面视图展示当前实体、状态、请求/动作和错误；全局视图按流程、时间、页面、资源及 operation 过滤，并可展开完整关联链。
  - 浮窗关闭不停止记录，不预拉取全部领域数据；检查路由切换卸载竞争、StrictMode 和过期页面快照。

  - 2026-09-10 快照归属切片：Learning 与其他页面的快照共用稳定注册接口，按真实 page-view 与 owner fencing 发布；旧 owner 更新/卸载不可覆盖新页，路由变化立即隐藏不匹配快照。修复 PageDebug Context 更新反馈循环，以及设置加载前误清空浮窗打开偏好的问题。5 项 React 快照/StrictMode/路由测试、完整 Web reliability、生产构建及 Chromium Persona→Settings→Model Usage 切换/刷新验证通过；关闭浮窗仍记录的 Persona 纵向样例保持通过。全局诊断 timeline、关联筛选与 lazy query 尚待接入，本阶段保持未完成。

  - 2026-09-10 查询切片：事件查询新增 operation/workflow/stage、资源、severity 与显式时区范围筛选，持久 request 关联支持跨事件查询，游标增加有界 has_more。事件/关联内容读取重验，故障返回明确不可用状态并区分 read/write failure；索引查询只读并支持 workflow/stage。24 项后端诊断/index/生命周期测试及 shared/Web 类型门通过。历史关联缺少 workflow/stage 的覆盖限制、源时间语义与资源筛选范围已写入 API 文档；前端严格查询适配器和 timeline 尚待完成。

  - 2026-09-10 前端查询适配器切片：events/index/operation-links 使用后端模型生成的共享白名单，严格验证嵌套字段、分类、attempt 完整性及单页游标/重复身份；传输上限 2 MiB、5 秒 timeout 与调用方 abort 共存，查询不递归记录，故障不回显原文。6 项前端查询测试、3 项后端查询/模型漂移测试及 Web 类型门通过，覆盖真实 Python provider/tool/attempt/desktop DTO 样本。适配器尚未接入浮窗，timeline 与跨页结果合并仍待后续切片。

  - 2026-09-10 时间线 UI 切片：Debug 新增当前页面/全局视图，页面请求按需展开；全局事件支持页面、来源、级别、workflow/stage、operation/request/action/flow、资源与本地时间筛选，Harness 索引单独按需加载。operation→request→events 可展开；事件/索引分别最多显示 500/250 条，分页去重，切换/关闭中止请求且 fence 迟到响应。4 项 React 时间线测试、完整 Web reliability、生产构建和 3 项 Chromium 场景通过；浏览器发现的三行布局与控件标签问题已修复，390px 无横向溢出且截图已检查。全流程覆盖和独立总验收仍未结束，本阶段暂不关闭。

- [ ] `OBS-AUDIT-001` `[P2]` 完成诊断留存、导出与性能审计验收；依赖 `OBS-DEBUG-001`。
  - 本地 append 存储、游标分页、轮转/清理及诊断包导出；内容按白名单脱敏，受保护内容仍走 artifact resolver，凭据及未提交评分材料不得进入全局日志。
  - 样本按 workflow/stage、模型、配置/组件版本分组；输出原始指标、P50/P95、失败/恢复/unknown 数和缺口，父子耗时不能重复相加。
  - 注入离线、断进程、写盘失败、队列溢出、重复上传和大日志量；诊断故障不能改变业务提交结论，性能开销须量测。
  - 2026-09-10 事件留存切片：数据库入库时间驱动七天/一万行/64 MiB UTF-8 正文上限，启动、写入及空闲周期清理；删除计数/最高删除序号与清理同事务，查询与覆盖信息取同一快照。旧库未知入库时间明确标记，半完成迁移可恢复，前端展示历史缺口。30 项后端测试（含真实子进程在清理提交前后退出）、7 项查询/5 项时间线测试、shared/Web 类型门、生产构建和 3 项 Chromium 场景通过。此限制只覆盖事件正文；索引、关联表、WAL/物理空间、writer epoch、导出和开销量测仍待完成。



  - 2026-09-10 故障隔离切片：诊断 writer/index/spool 线程启动失败不阻断业务生命周期；重复启动不产生额外 writer，终止后拒收并清空未处理队列，失败事件事务回滚后可继续写入。34 项后端回归通过，其中真实应用在三个诊断线程均启动失败时仍完成设置持久化、人格生成与 canonical Harness 终态；重启读回和队列记账也通过。丢弃/失败计数目前仍为进程内状态，跨崩溃 writer epoch 和持久覆盖证据尚待下一步。

## Target architecture

Implementation is tracked by the four tasks above; the root [TODO](../../TODO.md) links here. This section is the target architecture,
not a claim that every component is implemented. The initial server event store
exists under `storage_root/diagnostics/events.sqlite3`; it retains at most 10,000
rows using a 1,000-event queue. Browser ingestion and cursor query are available at `/diagnostics/events`,
including writer health counters. Event payload retention now uses seven days,
10,000 rows or 64 MiB, with durable removal coverage; global UI health is visible.
Aggregate disk retention, other diagnostic-table retention and exports remain pending. Console logging intentionally excludes
unreviewed formatted messages and exception text.

```mermaid
flowchart TD
    Page[Page snapshot adapters] --> Debug[Independent DebugProvider]
    Browser[UI actions / requests / decoder failures] --> Buffer[Bounded client event buffer]
    Buffer --> Ingest[Validated diagnostic ingestion]
    Backend[HTTP / domain / provider logging] --> Store[Append diagnostic store]
    Desktop[Desktop startup / Vault status / sidecar exit] --> Store
    Ingest --> Store
    Harness[Canonical Harness traces / receipts / usage] --> Index[Restartable reference index]
    Index --> Query[Cursor query and correlated timeline]
    Store --> Query
    Query --> Debug
    Debug --> Current[Current page: state and related actions]
    Debug --> Global[Global history: flows and performance]
    Query --> Export[Redacted diagnostic export]
```

The collector, query API and Debug UI are separate components. Closing the
floating window does not disable collection. Register page snapshots by unique
page-view identity and ownership token, so cleanup from an old view cannot clear
its replacement. Page snapshots are current in-memory projections; only bounded,
reviewed state summaries or state changes enter persistent diagnostics.

Correlation distinguishes `event_id`, client instance/page-view, logical
`flow_id`/`action_id`, server `request_id`, optional `span_id`/parent span, and
actual Harness operation/trace/attempt and domain resource references. An action
can span requests, retries, streams and navigation. Different requests retain
different request IDs even when the admitted operation is replayed. Client
correlation fields are untrusted diagnostic hints, never authorization or
idempotency identities; resolve canonical Harness links on the server.

Events have a closed name/category, source, severity, outcome/error code,
source timestamp, monotonic duration, ingest sequence and bounded typed
attributes. HarnessStage, attempt phase and stream event remain separate fields.
Capture stream completion/disconnect separately from HTTP response creation;
propagate context explicitly across worker threads. Record app/runtime and model
configuration versions without secrets. Unavailable timings/tokens/costs remain
null with a reason, and measured versus estimated usage stays distinguishable.

Use a diagnostic append repository, not `LocalJsonStore.save_list`. The initial
implementation can use a dedicated local SQLite database with bounded async
writers and cursor indexes; separate it from business transaction scans. Durable
operation correlation links and existing Harness receipts/traces allow the
reference index to resume and deduplicate after restart. Diagnostic events do
not establish commit truth. A logging outage must not roll back or relabel an
already committed business operation. Missing starts/ends, interrupted writer
epochs, dropped events and retention expiry must be visible rather than inferred
as successful execution or complete audit coverage. Desktop events before
sidecar readiness use a bounded local spool and the same event identity when
forwarded later.

Candidate defaults to validate during implementation: 1,000 in-memory client
events, 100 events per upload batch, 16 KiB per event, and persistent retention
of seven days or 200 MiB, whichever is reached first. Diagnostic ingestion and
query traffic must not recursively log themselves. Queue backpressure, dropped
counts and writer health are observable; critical Harness evidence remains in
its existing authoritative storage regardless of diagnostic retention.

Default persistent events contain identifiers, counts, safe state, error codes
and metrics. Do not copy prompts, document/chat content, arbitrary request/response
bodies, credentials or private grading specifications into them. Rich page
inspection and optional content export use the existing authorized artifact
resolver and remain explicitly scoped. Validate safe attributes at emit and
server ingest boundaries, including exception-message sanitization.

The query layer supports page view, flow/action, resource, operation, time,
source and severity filters. Audit exports include schema/app versions, filters,
coverage/drop indicators, raw metric observations and available linked Harness
records. Group P50/P95 by workflow/stage, provider/model and configuration;
report sample counts and unknown/failed outcomes. Parent duration includes child
work, and parallel spans must not be summed as wall-clock time.

## Integration order

First establish application lifecycle logging (`ARCH-LIFECYCLE-001`) and a Persona generate/save/reload vertical slice. Add workflow emitters through adapters without moving domain transaction ownership. Coordinate DebugProvider routing with `ARCH-WEB-001` / `PERF-WEB-PROVIDER-001`; they are one ownership change, not duplicate implementations.
