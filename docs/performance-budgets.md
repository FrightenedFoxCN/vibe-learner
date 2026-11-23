# 性能预算与基准

本文汇总当前生效的性能预算、结构化硬上限与本地可执行基准命令。

## 1. Web 生产包首屏传输预算

发布门禁（`.github/workflows/release-gate.yml` 与 `desktop-release.yml`）校验下列六个生产路由的首屏 HTML + 静态 JS/CSS 压缩传输字节。任一路由相对 [当前基线](performance/web-bundle-v1.json) 回归超过 **5%** 即失败。

| 路由 | 懒加载前 gzip 字节 | 基线首屏 gzip 字节 | 变化 | 5% 上限字节 |
| --- | ---: | ---: | ---: | ---: |
| `/` | 278,008 | 221,686 | −20.3% | 232,771 |
| `/settings` | 284,004 | 227,763 | −19.8% | 239,152 |
| `/model-usage` | 280,380 | 224,070 | −20.1% | 235,274 |
| `/tavern` | 431,268 | 257,533 | −40.3% | 270,410 |
| `/study` | 474,987 | 317,380 | −33.2% | 333,249 |
| `/plan` | 350,936 | 318,939 | −9.1% | 334,886 |

对照样本：[懒加载前原始报告](performance/web-bundle-p1-fe-02-before.json)（`2e320d3`）与当前基线使用同一六路由探针，在 macOS 27.0.1 arm64、Node.js 26.13.1、npm 11.20.0、Next.js 16.2.3（Turbopack）下以本地生产构建采集。每个路由直接请求静态预渲染页面及其 HTML 引用的同源 JS/CSS，使用相同的锁定依赖、不启动后端、不注入数据、不打开调试浮窗；两次样本中的 HTML 与资产均返回 HTTP 200、gzip。原 4 条路由也全部低于旧基线的门槛。两次分别使用回环端口 13417 与 3417，现统一为 3417。

本地执行方式：

```bash
npm run build:web
npm --workspace @vibe-learner/web run start -- --hostname 127.0.0.1 --port 3417
npm run bench:web-bundle -- --base-url http://127.0.0.1:3417 --baseline docs/performance/web-bundle-v1.json
```

该门禁只衡量生产首屏传输体积，不替代浏览器渲染帧率或后端接口延迟评估。

## 2. Harness 运行时硬上限与本地基准

### 生产执行硬上限（`harness-performance-budget-v1`）

由 `services/ai/app/models/harness_performance.py` 拥有，作用于单个已准入运行时阶段（等于上限视为通过）：

| 维度 | 硬上限 | 检查时机 |
| --- | ---: | --- |
| 规范上下文 UTF-8 字节 | 256 KiB | 解析器/执行器运行前 |
| Subject + Snapshot 引用总数 | 64 | 解析器/执行器运行前 |
| 单个已解析快照大小 | 64 MiB | 授权解析后、Worker 执行前 |
| 全部已解析快照总大小 | 128 MiB | 授权解析后、Worker 执行前 |
| 已有 Runtime Attempts 数 | 64 | 心跳回调开始前 |
| 已有 Attempt/Check 规范字节 | 1 MiB | 心跳回调开始前 |

- 预检超限记录无敏感内容的 `HarnessBudgetViolationV1`（`version`、`dimension`、`actual`、`limit`）；已过期的 wall-time 预算阻止发起下一轮回调。
- 批量快照解析共享单次数据库会话/事务（SQL 上限 `6 * reference_count + 3` 条），仍逐项校验授权、契约、权限、留存与摘要。
- 6 个 Planning 工具保持串行执行（`parallel_safe = false`）。

### 本地基准命令与回归上限

```bash
npm run bench:harness -- --samples 30 --output /tmp/harness-local.json
```

使用隔离临时 SQLite 与合成数据（无 Provider 调用，需本地 `cl100k_base` tokenizer 缓存），每项 5 次预热 + ≥30 次采样：

| 测量项 | 本地 P95 上限 |
| --- | ---: |
| 已准入 Persona 运行时（8 KiB 受保护输入 + 严格解码 + Trace） | 500 ms |
| 1 次快照授权解析 | 100 ms |
| 8 次批量快照解析 | 300 ms |
| 64 次批量快照解析 | 1,500 ms |
| Tavern Prompt 预检 + Tokenizer | 1,500 ms |
| Planning 双工具串行轮次 | 100 ms |

## 3. 诊断与桌面端本地基准

### 诊断中间件、查询与存储基准

```bash
npm run bench:diagnostics -- --samples 100 --output /tmp/diagnostic-benchmark.json
```

在隔离临时 SQLite 上测量中间件配对开销、分页查询、操作过滤、快照导出与 WAL 回收表现；不调用外部模型。

### 桌面端可选 Rust 探针

`apps/desktop/src-tauri/Cargo.toml` 为 `scrypt`、`salsa20` 与 `argon2` 启用了 `profile.dev` 优化（`opt-level = 3`），以保证开发构建下 Stronghold Vault 加密参数不变且解锁响应可用。

可选本地探针命令（均标记 `#[ignore]` 或独立 example，使用临时目录，不接触用户数据）：

```bash
# 原生 Spool 写入与驱逐计数探针（成功 P95 ≤ 25 ms，锁争用拒绝 P95 ≤ 100 ms）
DIAGNOSTIC_SPOOL_BENCH_OUTPUT=/tmp/diagnostic-native-spool.json \
  cargo test --manifest-path apps/desktop/src-tauri/Cargo.toml --lib spool_performance_probe -- --ignored

# Stronghold Vault 加解密探针
cargo test --manifest-path apps/desktop/src-tauri/Cargo.toml --lib vault_performance_probe -- --ignored --nocapture --test-threads=1

# 原生 WebView 诊断时间线渲染示例
cargo build --manifest-path apps/desktop/src-tauri/Cargo.toml --example diagnostic_render
```

## 4. 关键架构级性能约束

除上述可执行基准外，系统在架构设计上遵守以下稳定预算：

- **Tavern Room 分页**：单页 SQL ≤ 4 条（禁止读取 Message 正文）、30 项默认页未压缩 JSON ≤ 192 KiB / 50 项最大页 ≤ 320 KiB、热响应 P95 ≤ 100 ms（30 项）/ ≤ 120 ms（50 项）、前端单次追加 30 项 React Commit `actualDuration` P95 ≤ 50 ms、DOM 最多保留 100 个房间摘要按钮。
- **后端冷启动隔离**：空库 mock 启动至首次 `GET /health` 返回 200 须小于 2 秒；启动边界不得导入 `litellm` 或 `onnxtr`，不得发起非 loopback 网络连接。
- **前端资源读取收敛**：`WorkspaceSnapshotLoader.loadOnFocus()` 与 `useWorkspaceLibraries` 合并同一所有者的在途聚焦刷新（显式刷新与变更恢复仍发起独立新鲜读，不跨操作/所有者边界共享纯 URL 缓存）；Tavern 前台轮询严格单在途不重叠，终态或恢复交接前立即释放轮询所有权。
- **文档输入上限**：详见 [教材解析与入库链路](document-pipeline.md#1-输入上限与无损分块)（64 MiB 文件 / 65 MiB 请求体 / 512 物理页 / 65,536 字符单元）。

## 5. 预算调整规则

性能回退不得通过直接调松预算掩盖。若需更新基线或放宽门禁，须说明原门禁不再具代表性的客观证据、记录完整夹具与运行环境，并经独立评审后同步更新基线文件与本文档。
