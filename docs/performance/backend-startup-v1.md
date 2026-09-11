# PERF-002：独立后端启动验收（2026-09-11）

**通过：10 个全新 mock 后端进程，从启动到完整 HTTP `/health` 响应均低于既定 2 秒门槛。** 最慢 0.708498 秒，平均 0.694960 秒。10 个进程健康时均未加载 `litellm`、`onnxtr` 或其子模块；启动期间捕获的非 loopback DNS/连接尝试均为 0。

执行者为独立子智能体。本次只新增验收脚本和证据文件，未修改产品实现或性能门槛。

## 口径与隔离

- 使用项目 uv 管理的 Python 3.12.13，机器为 macOS 26.6.2 / arm64。
- 10 次顺序采样，每次新建 Python 进程、空 SQLite 数据库、空 storage 目录。所有目录都位于本轮专属 `TemporaryDirectory` 下；没有复用上一次数据库，没有访问生产 data 或用户数据库。
- 子进程执行生产 `create_app(settings=Settings(...))`、完整 lifespan / Container 启动、真实 Uvicorn HTTP 服务。显式固定 mock provider、onnxtr OCR 配置、禁用 legacy 自动导入；使用显式 Settings 避免 `.env` 或用户运行时数据影响样本。
- 计时从父进程调用 `Popen` 前的 `perf_counter()` 开始，到首个 HTTP 200 `/health` 的响应完整读取并解码结束；包含 Python 进程创建、依赖导入、空库建表、启动服务和 HTTP 往返。未把 uv 调度、临时目录创建和端口选择算入后端启动时间。
- 父进程每 10ms 轮询，单次 HTTP 超时 100ms，禁止使用代理。轮询与证据写盘开销包含在所报告延迟中。
- 在导入 Uvicorn / app 前安装 CPython audit hook，记录非 loopback 的 `socket.getaddrinfo`、`socket.connect`、`socket.sendto`。外连尝试会被阻止且使该样本失败；不能通过拦截请求后继续启动来获得通过。
- `/health` 响应开始时采集子进程 `sys.modules` 与网络尝试。未设置 `LITELLM_LOCAL_MODEL_COST_MAP`；对子进程移除继承的 `LITELLM_*` 环境变量，避免用户环境开关掩盖行为。原始样本也记录该开关不存在。
- 每次取样后向专属子进程发送 SIGTERM 并等待退出，全部结束；原始 exit code 为 -15，属于验收主动停止。临时目录在完成后删除。

## 原始样本摘要

| 进程 | 秒 | `< 2s` | 禁止模块数 | 非 loopback 尝试 |
| --- | ---: | --- | ---: | ---: |
| 1 | 0.666580 | 通过 | 0 | 0 |
| 2 | 0.692630 | 通过 | 0 | 0 |
| 3 | 0.699688 | 通过 | 0 | 0 |
| 4 | 0.692638 | 通过 | 0 | 0 |
| 5 | 0.697391 | 通过 | 0 | 0 |
| 6 | 0.694897 | 通过 | 0 | 0 |
| 7 | 0.708498 | 通过 | 0 | 0 |
| 8 | 0.690136 | 通过 | 0 | 0 |
| 9 | 0.701981 | 通过 | 0 | 0 |
| 10 | 0.705161 | 通过 | 0 | 0 |

完整精度、PID、健康响应、模块列表、数据库和 storage 路径、退出状态及进程日志保存在 [machine-readable raw samples](../plans/acceptance/perf-002-startup-raw-2026-09-11.json)。

## 复跑

从 `services/ai` 目录执行，使用可绑定本机端口的环境：

```bash
UV_CACHE_DIR=/tmp/vibe-independent-uv uv run --offline python \
  tests/acceptance/backend_startup_probe.py \
  --output /tmp/perf-002-startup-raw.json
```

脚本固定 10 次、固定 2 秒门槛；全部样本通过时退出 0，任何样本不通过时退出 1，并保留逐项 JSON 证据。源码：[backend_startup_probe.py](../../services/ai/tests/acceptance/backend_startup_probe.py)。

## 范围限制

该结果证明本机固定空库 mock 启动门与当前 Python 启动路径未发起 cost-map 网络请求；不代表 OS 冷缓存、其他硬件、已有大型数据库、真实 provider 首次调用、OCR 首次执行或 SDK 初始化耗时。网络证据来自 CPython socket audit，不是操作系统级抓包；不认证未来代码通过原生扩展自行建立的不可见连接。首次 SDK 并发初始化和 provider callable 注入由主智能体的目标测试处理，不计入这里的 10 次性能样本。
