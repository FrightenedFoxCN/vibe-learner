# 待办核对与独立验收（2026-09-11）

本轮关闭两项，统一 TODO 从 27 项减为 25 项，其中质量复核 1 项继续暂缓。没有修改产品逻辑；新增独立验收测试、复现脚本和证据。未接触用户业务数据或调用真实模型。

## 口径及结论

此前“9 项已实现但缺验收”是主体功能存在、工作以验收为主的宽口径；其中只有 Scene Dialog 和 Provider ownership 明确已完成实现及开发验收、仅缺独立复核。不能把其余七项理解为补签字即可关闭。

| 待办 | 本轮核对与实际验收 | 处置 |
| --- | --- | --- |
| `UX-A11Y-SCENE-DIALOG-001` | 独立子智能体新增 3 项边界场景；当前源码生产 Chromium 原有 2 项 + 新增 3 项全部通过，覆盖模态、双向焦点循环、重复取消、确认删除、背景点击/focus 阻断及 390px | 关闭，范围为条目要求的 Dialog 行为 |
| `PERF-WEB-PROVIDER-001` | 独立子智能体实际核对 10 个页面 + 404，复跑路由/恢复并新增 2 项迟到响应、跨页 uncertain/断网查询场景，当前构建 18/18 通过 | 关闭，保留综合平台/网络恢复待办 |
| `DOC-USER-001` | 主智能体静态对照手册内容，并用隔离真实 mock 后端走通纯目标计划 → 自动创建 Session → Study Dialog 提问 → 刷新保留用户 Turn | 保留；首次 Settings 配置、教材/其他领域完整路线和桌面安装未验收 |
| `PERF-TAV-ROOMS-001` | 已有分页、SQL/payload/DOM 结构门；未找到满足本项协议的首/中/末页完整服务端样本及 React Profiler commits 证据 | 保留；不把其他 Debug 性能报告当作分页时间门 |
| `REL-DESKTOP-001` | Debug 归档有 macOS Vault/原生保存及浏览器恢复切片；本轮 Scene/Provider 浏览器证据增加覆盖 | 保留；真实慢网/断网、设备级 IME、完整焦点及跨页面/桌面组合矩阵仍缺 |
| `REL-POSTGRES-001` | 独立子智能体在隔离 PG17 复跑原 22 项，并补空库迁移、强制并发 Study CAS、回滚和数据库重启新进程读回 | 保留并缩小范围；旧数据迁移、全领域操作中断与 HTTP 恢复未覆盖 |
| `REL-REPLAY-001` | 独立子智能体完成四领域合成制品解析/拒绝矩阵，另 29 项运行时/解析器/commit 回归通过 | 保留并缩小范围；真实历史制品及完整 adapter 重放仍缺 |
| `OCR-STRESS-001` | Debug 归档存在真实本机 OCR 与阶段引用证据，及 CPU fallback 回归；它们不是多语言大型扫描件压力集合 | 保留；本轮未新增 OCR 压力实测 |
| `PERF-TAV-LIVE-001` | 已有 mock 性能/恢复和历史 MiniMax 529 记录，不能替代代表性真实 provider 六人名册/长对话性能验收 | 保留；本轮未发真实 provider 请求 |
| `QG-MODEL-QUALITY-001` | 确定性运行时评测与独立真实模型质量是不同验收范围 | 继续用户暂缓，不开展或关闭 |

因此，宽口径验收为主的在排期待办剩 **7 项**，另有质量复核 **1 项暂缓**。其他实现尚未完成的待办不计入这个小计。

## 可复跑证据

- [Scene 独立报告](scene-dialog-independent-acceptance-2026-09-11.md)：5/5，当前构建 1.4 秒。
- [Provider 独立报告](provider-independent-acceptance-2026-09-11.md)：18/18，当前构建 15.1 秒；含归档请求 JSON。
- [PostgreSQL / 制品重放独立报告](postgres-replay-independent-acceptance-2026-09-11.md)：明确每个实测边界及复现脚本；隔离 PostgreSQL 容器已清理。
- 当前源码 `5117bc3c64425e1777cb6ce795700f4db91a5e2f` 的 `npm run build:web` 通过（含 TypeScript），生产构建 ID `R4NvcnDWh8WLl9x6TOx9t`。两组子智能体先验旧构建后，在这个新构建上分别完整复跑；最终关闭结论使用新构建结果。
- 本轮只修改测试和文档，不重复完整 release gate。原有桌面图标改动不属于本次工作。

## 手册走查的范围

后端使用 `Settings(...)` 显式 mock、禁用 OCR、临时 SQLite 和临时 storage root，不读取部署密钥；生产 Web 监听 3430，后端监听 19001。浏览器只注入后端地址，所有业务请求进入真实 FastAPI、持久化和 Harness 流程，没有拦截业务响应。

新建临时库后，按手册的“仅学习目标”输入“一周 Python 循环，每天 30 分钟”，生成三个 Study Unit，并观察“目标计划已生成，会话已创建”。随后通过 UI 进入 Study Dialog，输入“请用简单例子解释 for 循环”，聊天 POST 返回 200；刷新后仍显示同一用户提问和两轮对话。没有以 API 预置计划或 Session。

复现脚本：[mock 后端](acceptance/manual_mock_server_20260911.py)、[浏览器路线](acceptance/manual_mock_20260911.mjs)。从 `services/ai` 运行 `PYTHONPATH=. UV_CACHE_DIR=/tmp/vibe-learner-uv-cache LITELLM_LOCAL_MODEL_COST_MAP=True uv run python ../../docs/plans/acceptance/manual_mock_server_20260911.py`；前端从 `apps/web` 运行 `npm run start -- --hostname 127.0.0.1 --port 3430`；仓库根运行 `node docs/plans/acceptance/manual_mock_20260911.mjs`。仅用于上述一次性后端。

前期探查使用 `getByLabel(..., exact: true)` 未匹配创建方式/学习目标，改为实际 role/name 选择后流程通过，没有修改产品。此项是主智能体的局部路线走查，不等同于子智能体的独立完整手册验收；未从 Settings 配置开始，也未打开安装包或执行 Windows/Linux 安装。

## PostgreSQL 账目差异

架构归档的 22 项真实 PostgreSQL 测试没有记错，但仅测试事务校验与 Tavern 引用范围，建库方式不是完整升级已有数据库；它和统一 TODO 仍开放并不矛盾。本次补测进一步建立 PostgreSQL 证据，仍没有把普通记录经数据库重启保留等同于领域操作的中断恢复。
