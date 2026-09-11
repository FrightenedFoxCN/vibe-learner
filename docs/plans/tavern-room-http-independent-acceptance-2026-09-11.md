# Tavern Room 分页 HTTP 独立验收（2026-09-11）

**Server 部分通过：最终共享夹具的 300 个真实 HTTP 样本满足 v1 SQL、payload 和 P95 时间门。** 没有修改产品分页代码或性能预算。本报告不代替 React Profiler / DOM 验收。

## 协议与夹具

严格采用 `docs/performance-budgets-v1.md` 的 `tavern-room-list-v1`，复用现有 `TavernRoomPaginationTests._seed_fixture`，contract `tavern-room-list-fixture-v1`，seed `vibe-learner-tavern-1000-v1`：

- 新建隔离 SQLite，1,000 个确定性 24 字符 Room ID；按 `(updated_at DESC, id DESC)` 排序。
- 每 7 个 Room 同 updated_at；分别验证 30/50 页界切开相同时间组。
- 3,640 Participants，分布覆盖 1–6；所有标题为 64 Unicode scalar，Persona ID 为 24 ASCII 字符，显示名为 48 Unicode scalar。
- 最大页首 50 Rooms 全部为 6 Participants。
- 3,496 条 Message，查询通过真实聚合统计；计数 SQL 检查未选择 Message content/payload。
- 为共享给真实前端，最终夹具将既有测试的空 `persona_snapshot={}` 补成合法、固定的 PersonaProfile。未改变 Room/Participant 数量、字符串宽度、排序或 Message 数量；detail、runs、run-recovery 读取实际 HTTP 200。

两种 page size 均真实遍历完整 1,000 Rooms，并与按协议独立排序的 fixture ID 列表逐项比较：无重复、无遗漏，所有宽度与参与者形状通过。

## 环境与计时

Apple M4、10 核、16 GiB；macOS 26.6.2 arm64；Python 3.12.13；uv 0.12.10；Node 26.8.1。与 v1 参考硬件一致，OS/Node/uv 补丁版本不同，未调整门槛。现有 production Next 构建 ID 为 `ZfnwP5lK6iKQz54x_yQKS`；本子任务直接测 FastAPI HTTP，不把后端测量作为 production frontend 或 React 渲染证据。

记录的 HEAD：`26f59d49ecadb5033aae248afea0a0295bf46abe`；Tavern repository/API 生产文件无本任务修改。provider 为 mock，storage 与数据库均在专用 `/tmp/vibe-tavern-room-http-full-20260911`，未访问用户 data。

测量通过真实 Uvicorn/FastAPI 完整应用；对 `/tavern/rooms` 设 request ContextVar，在同一请求传播到同步线程池的上下文内计数 SQLAlchemy 主数据库 statements。后台 diagnostics 不计入该领域查询数。没有启用 coverage/debug profiler。

HTTP elapsed 从发出请求前到完整读取未压缩 JSON body，使用 `perf_counter`；`Accept-Encoding: identity` 并验证无压缩，payload 为实际响应原始 bytes。另记录服务端到 response-start 的计时作辅助，正式 gate 使用包含序列化和本机 HTTP 往返的更保守 elapsed。

每个 page size 的首、中、末页各显式预热 5 次，然后测 50 次，共 6 组 / 300 样本。为定位 cursor，预热前做过完整遍历，不计入样本；没有从 50 次正式样本中剔除慢值。P50/P95 使用 nearest-rank `ceil(p*n)`，50 个样本的 P95 是第 48 个有序值。

## 最终结果

| Page size / 位置 | offset / 实际条数 | 样本 | HTTP P50 ms | HTTP P95 ms | 最大 ms | 最大 SQL | 原始 bytes |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 30 / 首 | 0 / 30 | 50 | 2.884 | 3.434 | 3.953 | 3 | 44,101 |
| 30 / 中 | 480 / 30 | 50 | 2.564 | 3.183 | 31.367 | 4 | 32,095 |
| 30 / 末 | 990 / **10** | 50 | 1.778 | 2.095 | 2.506 | 4 | 10,689 |
| 50 / 首 | 0 / 50 | 50 | 4.109 | 5.207 | 34.954 | 3 | 73,341 |
| 50 / 中 | 450 / 50 | 50 | 3.263 | 4.303 | 4.587 | 4 | 52,287 |
| 50 / 末 | 950 / 50 | 50 | 3.207 | 3.918 | 4.252 | 4 | 51,769 |

30 的真实末页只有 10 summaries；这符合对实际末页的 server 协议，不能拿来冒充“末尾 append 30”的 React 门。前端独立验收另提供 offset 940 初始 30 + offset 970 追加 30 的真实 cursor 窗口。

所有组的 P95 均满足 30-item ≤100ms / 50-item ≤120ms；SQL≤4，payload 分别≤192/320KiB。31–35ms 慢样本保留在最大值与原始文件中。

脚本判定核对：HTTP 非200、压缩响应、完整遍历ID/形状不符会失败；正式样本每组数量50、实际条数与该页相等且不超过请求limit；SQL/bytes使用每组最大值，耗时使用P95，Message body选择禁止。收尾强化了每样本条数谓词，并用已有 raw 的全部600个已记录 item_count（baseline+final）离线重算通过，未改动任何计时样本。

## Before / after 的含义

既有产品分页实现未修改：本任务补齐验收证据，不声称获得性能优化。首次使用已有空 Persona snapshot 测得 300 样本通过，随后为了真实前端详情读取而补合法 snapshot，并完整重测 300 样本。首次记录仍保留为 [minimal-snapshot baseline](acceptance/tavern-room-http-minimal-snapshot-baseline-2026-09-11.json)，最终 gate 以 [完整共享夹具 raw samples](acceptance/tavern-room-http-raw-2026-09-11.json) 为准。两轮50-item首组P95分别为3.913ms和5.207ms；未控制其他运行噪声，不能将差值归因于snapshot变化。两组都通过，未选择性丢弃较慢最终结果。

## 重放与前端交接

从 `services/ai` 启动专属服务，`--root` 必须是新的、空的专用路径：

```bash
UV_CACHE_DIR=/tmp/vibe-independent-uv uv run --offline python \
  tests/acceptance/tavern_room_http_probe.py --serve \
  --root /tmp/tavern-room-list-replay --port 8897
```

在另一个终端测量：

```bash
UV_CACHE_DIR=/tmp/vibe-independent-uv uv run --offline python \
  tests/acceptance/tavern_room_http_probe.py \
  --base-url http://127.0.0.1:8897 \
  --fixture /tmp/tavern-room-list-replay/fixture.json \
  --output /tmp/tavern-room-http-raw.json
```

服务只监听 loopback。源码：[tavern_room_http_probe.py](../../services/ai/tests/acceptance/tavern_room_http_probe.py)。本轮最终服务通过 `http://127.0.0.1:8897` 交给前端独立验收子智能体；0/450/940 的 cursor 和 initial/append 预期 ID 在 `/tmp/tavern-frontend-profile-windows.json`。进程由本子智能体保管，等前端完成后停止；不与生产服务混用。

前端交接时发现 profiling 页面使用 `http://127.0.0.1:3417`，而 fixture 默认 CORS 只允许 3000。脚本增加测试专用 `--frontend-origin` 参数，并在同端口用相同协议的全新夹具 `/tmp/vibe-tavern-room-http-profile-20260911` 重启。需要重放前端时追加 `--frontend-origin http://127.0.0.1:3417`。这只调整测试服务允许的来源，不改变产品或本报告的 server 测量路径；前端子任务将此前 CORS 不完整的运行标为配置失败，独立全量重跑。

前端子智能体完成有效的 90 个 append 样本、15 次预热与独立 DOM cap 验证后，已停止最终 fixture 服务，并清理本轮三个专属 `/tmp/vibe-tavern-room-http-*20260911` 目录。前端已归档 cursor 窗口文件；临时窗口副本也已清理。没有遗留本任务启动的 HTTP 服务或临时数据库。
