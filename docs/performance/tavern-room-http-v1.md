# Tavern Room pagination HTTP measurement v1

本协议验证 `tavern-room-list-v1` 的 SQL、payload 和 HTTP P95 门。React 渲染另见 [React Profiler 协议](tavern-room-react-v1.md)。

## 协议与夹具

严格采用 `docs/performance-budgets-v1.md` 的 `tavern-room-list-v1`，复用现有 `TavernRoomPaginationTests._seed_fixture`，contract `tavern-room-list-fixture-v1`，seed `vibe-learner-tavern-1000-v1`：

- 新建隔离 SQLite，1,000 个确定性 24 字符 Room ID；按 `(updated_at DESC, id DESC)` 排序。
- 每 7 个 Room 同 updated_at；分别验证 30/50 页界切开相同时间组。
- 3,640 Participants，分布覆盖 1–6；所有标题为 64 Unicode scalar，Persona ID 为 24 ASCII 字符，显示名为 48 Unicode scalar。
- 最大页首 50 Rooms 全部为 6 Participants。
- 3,496 条 Message，查询通过真实聚合统计；计数 SQL 检查未选择 Message content/payload。
- 用于真实前端的夹具包含合法、固定的 PersonaProfile snapshot，并要求 detail、runs、run-recovery 返回 HTTP 200。

两种 page size 均真实遍历完整 1,000 Rooms，并与按协议独立排序的 fixture ID 列表逐项比较：无重复、无遗漏，所有宽度与参与者形状通过。

## 环境与计时

参考环境为 Apple M4、10 核、16 GiB、macOS arm64、Python 3.12.13。精确依赖版本和源码摘要见[原始样本](../plans/acceptance/tavern-room-http-raw-2026-09-11.json)。使用 mock provider、隔离临时 SQLite 和 storage。

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

HTTP 非 200、压缩响应、遍历 ID/形状不符均失败。每组须有 50 个样本，每个响应条数与该页相等且不超过 limit；SQL/bytes 取组内最大值，耗时取 P95，并禁止选择 Message body。

## 复现

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

服务只监听 loopback。源码：[tavern_room_http_probe.py](../../services/ai/tests/acceptance/tavern_room_http_probe.py)。前端验收使用 `http://127.0.0.1:8897` 和 0/450/940 的 cursor 窗口；fixture 服务与生产服务隔离。

前端 profiling 服务使用 `http://127.0.0.1:3417` 时，给 fixture 服务追加 `--frontend-origin http://127.0.0.1:3417`。这是测试服务的 CORS 配置；结束后停止专属服务并清理临时数据库。
