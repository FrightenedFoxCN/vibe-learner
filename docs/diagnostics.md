# 诊断与审计体系

诊断子系统用于排障、耗时观测与问题复盘，与业务持久化及 Harness 提交真源**严格分离**：任何诊断事件、索引、统计或导出成功均不构成业务提交证明。

## 1. 采集架构与关联模型

诊断事件遵循闭集契约 `diagnostic-event-v1`（`packages/shared/src/diagnostic.ts`），按三大来源采集：

- **浏览器端（`apps/web/lib/diagnostics.ts`）**：页面生命周期（`page_entered` / `page_left`，仅限 9 个业务路由闭集，不采集查询参数）、前端解码失败（`decode_failed`）、本地业务动作（`action_*`：JSON 导入读文件/应用、导出交接、设置保存、Vault 操作）与传输请求。
- **服务端（`services/ai/app/core/diagnostics.py`）**：HTTP 中间件、Provider 调用/重试（`provider_*`）、Planning/Study 工具调用（`tool_*`）、已保存资源引用（`resource_reference`）与 Harness 引用（`harness_reference`）。
- **桌面端（`apps/desktop/src-tauri/src/diagnostics.rs`）**：启动、Sidecar 生命周期与关停事件，先落盘至原生 Spool 再由后端消费。

### 关联传递与脱敏边界

- 客户端通过 `X-Debug-Client-Instance-Id`、`X-Debug-Page-View-Id`、`X-Debug-Flow-Id` 与 `X-Debug-Action-Id` 传递无内容关联头；服务端每次请求独立分配 `request_id`，并将请求与操作的映射持久化在操作关联表中（`GET /diagnostics/operation-links`）。
- **跨请求流程关联**：上传→解析→计划生成共享同一 flow；Study Chat 请求与查询恢复通过标签页级 `sessionStorage`（上限 128 条 / 64 KiB / 7 天）按 `(sessionId, clientRequestId)` 关联 flow；交互题提交与读回、Persona/Scene 生成→保存、Tavern 变更→列表/恢复读回各自捕获并显式传递上下文，不使用全局隐式异步状态。
- **严禁采集私有内容**：事件载荷不含教材原文、Prompt、工具参数/结果正文、评分材料、密钥、文件路径或原始异常堆栈。浏览器上报接口拒绝服务端/桌面端专用事件名与指标字段。
- **非阻塞隔离**：诊断队列满、写线程启动失败或磁盘配额拒绝仅记录丢失计数，绝不阻断或改写任何业务事务结果。

### 事件分类与口径

- 事件通过共享夹具 `packages/shared/fixtures/diagnostics/event-classification-v1.json` 统一推导 `category`、`severity`、`outcome` 与闭集 `error_code`。
- `provider_*`、`tool_*`、`harness_reference` 各自构成独立统计总体：父调用耗时已包含子重试或子调用，**禁止跨层级累加耗时**。
- Token 统计仅汇总 Provider 返回的原始非负整数，缺失记为 `null`（不推断、不求和补算），供应商成本字段显式标记为不可用。

## 2. 存储配额、留存与空间回收

诊断数据存储在独立于业务库的 `storage_root/diagnostics/` 下（`events.sqlite3`、`harness_index.sqlite3` 与 `desktop-spool/`）。各存储各自强制配额，不宣称全目录原子硬上限（`disk_size_limit_certified = false`）：

| 存储对象 | 正常强制策略 | 权威代码 |
| --- | --- | --- |
| 浏览器环形缓冲 / 服务端内存队列 | 各 1,000 条，溢出计数 | `apps/web/lib/diagnostics.ts`、`app/core/diagnostics.py` |
| 浏览器批量上报接口 | 单批 ≤ 100 条，单条序列化 ≤ 16 KiB | `app/api/diagnostic_routes.py` |
| 事件表留存（`events.sqlite3`） | 入库起 7 天 / 10,000 行 / 64 MiB UTF-8 载荷（先到者触发） | `app/core/diagnostic_retention.py` |
| 操作关联表留存（共享事件库） | 7 天 / 10,000 行 / 4 MiB 载荷 | `app/core/diagnostic_record_retention.py` |
| Harness 诊断索引留存 | 7 天 / 5,000 行 / 32 MiB 载荷 | `app/services/diagnostic_index.py` |
| 事件库物理准入包络 | 128 MiB（含 DB / WAL / SHM / journal / 锁文件） | `app/core/diagnostic_quota.py` |
| 索引库物理准入包络 | 64 MiB（含 DB / WAL / SHM / journal / 锁文件） | `app/services/diagnostic_index.py` |
| 桌面原生事件 Spool | 256 文件 / 7 天 / 单条 ≤ 16 KiB / 总载荷 ≤ 4 MiB | `apps/desktop/src-tauri/src/diagnostics.rs` |

- **写前预留与锁**：生产诊断写入持进程文件锁与 SQLite `BEGIN IMMEDIATE`，强制 WAL 模式、禁用 cache spill，在写前与提交前双检物理包络（含保守重写余量），超限回滚诊断写入而不影响业务。
- **增量回收**：新建诊断 SQLite 启用 `incremental` auto-vacuum（256 页 WAL autocheckpoint）；每次维护最多回收 256 空闲页并执行非阻塞 `WAL TRUNCATE`（单次维护间隔 ≥ 1 分钟，协作预算 250 ms，有长读事务时安全顺延）。超限历史库恢复共享安装级 `recovery.quota-lock`，额外允许最多 512 MiB 瞬态工作区与 5 秒协作 SQL 预算。
- **采集覆盖与存储观测**：
  - `GET /diagnostics/writers`（`diagnostic-writer-coverage-v1`）保留最多 256 条写线程 epoch 检查点（反映已观测丢弃/失败下界，`counts_are_lower_bounds=true`、`complete_collection_claim=false`）；
  - `GET /diagnostics/storage`（`diagnostic-storage-v1`）实时观测事件库与索引库文件长度、配额拒绝与维护计数，不创建缺失文件且不暴露本地路径。

## 3. 桌面原生 Spool 与双槽校验计数器

- 桌面 Rust 端与 Python 消费端共享 `spool.quota-lock`（Rust 写端最多等待 50 ms，Python 消费端遇忙延后扫描，双方均不删除锁 inode）。
- 消费端每秒最多处理 100 个事件文件（目录扫描上限 1,024 项），可恢复生产者崩溃遗留的完整 `.pending` 文件；仅在同步诊断提交或确认幂等重复后，经文件身份核验才删除源文件（拒绝符号链接与非普通文件）。
- **双槽驱逐计数协议（`diagnostic-counter-v1`）**：`drops.count` 与 `drops.alternate` 两个固定长度校验槽保存累计驱逐下界，格式为 `diagnostic-counter-v1:<20位零填充十进制>:<lowercase-sha256>\n`：
  - 加载时取有效槽位中的最大值；更新时禁止递减，仅覆写较旧或损坏的另一槽并 `sync_all`，始终保留一份完好基线；
  - 遇到未知新版本前缀时停止写入而不覆写；全部槽位损坏时拒绝归零重置；
  - 降级到不支持 v1 格式的旧版原生写入器时会拒绝写入原生诊断（已落盘事件仍可被后端正常消费），不影响业务功能。

## 4. 审计查询、快照导出与原生原子保存

### 查询与审计统计

- `GET /diagnostics/events` 按入库序号升序游标分页，支持时间（`since` 含 / `until` 排，按带时区源时间戳比较）、来源、页面、级别、操作、工作流、阶段与资源过滤；存储损坏或不可用返回 `503 diagnostic_query_unavailable`。
- `GET /diagnostics/harness-index` 提供最终一致的 Harness Trace 摘要索引（支持按 `workflow` / `stage` / `resource_type` / `resource_id` / `resource_role` 筛选，`coverage.canonical_read_back_required` 恒为 `true`）。
- 浏览器查询适配器（`apps/web/lib/diagnostic-query.ts`）对照 `packages/shared/fixtures/diagnostics/query-schemas-v1.json` 严格校验所有返回 DTO，单次响应限制 2 MiB / 5 秒。
- 审计聚合（`services/ai/app/services/diagnostic_audit.py`）按观测类型、工作流/阶段/相位、Provider、模型与组件版本分组计算 nearest-rank P50/P95、结果分布与 Token 样本数，显式保留配置缺口与冲突归因。

### 快照导出（`POST /diagnostics/export`）

- 接受与事件查询一致的筛选条件，返回 `diagnostic-export-v1` 紧凑 JSON 附件（含事件、操作关联、留存计数、写线程覆盖、审计分组、存储观测与独立快照读取的 Harness 索引）。
- 硬上限：请求 ≤ 8 KiB、事件 ≤ 10,000、关联 ≤ 5,000、索引 ≤ 5,000、输入载荷 ≤ 16 MiB、序列化输出 ≤ 32 MiB、协作读超时 5 秒；超限返回 `413`，绝不返回截断半成品。
- 前端仅在用户显式点击“生成诊断快照”时按当前筛选发起 POST（客户端限制 32 MiB / 15 秒），下载直接复用已验证快照，不二次请求后端。

### 桌面端原子 JSON 保存（`desktop_export_json`）

- 仅接收 JSON 内容与建议文件名，目标路径完全由原生保存对话框选择（渲染进程不可传入任意路径）；`src/json_export.rs` 在弹窗前校验 UTF-8 长度（≤ 32 MiB）与合法 JSON，失败仅返回固定错误码（`export_json_too_large` / `export_json_invalid` / `export_path_invalid` / `export_write_failed` / `export_dialog_failed`）。
- `src/json_export_file.rs` 在目标同目录创建独占临时文件（Unix 权限 `0600`），写满原始字节并 `sync_all` 后关闭句柄，再调用操作系统原子重命名替换（拒绝符号链接与非普通文件，不预截断目标文件）；替换前失败保留原文件并尽力清理本次临时文件。
