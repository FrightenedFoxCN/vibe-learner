# 仓库占用与整理记录（2026-09-12）

本次按用户要求检查工作目录和现有资料，归档已完成记录，并清理确认未使用的构建缓存。磁盘数据为 macOS `du` 分配空间近似值；运行中的开发服务可能继续写入缓存。

## 占用

- 清理前工作目录约 12.4 GiB，清理后约 10.0 GiB；本次删除缓存合计 2,471,352 KiB（约 2.36 GiB）。清理前数值由清理后总量与删除前逐目录测量相加估算。
- Git 已跟踪的现存文件为 1,288 个，逻辑大小 37,642,525 字节（约 35.9 MiB）；不包含未跟踪的新研究资料。`.git` 本身约 86 MiB。
- 文档约 53 MiB，其中质量证据约 48 MiB，包含约 17.6 MiB 的 Hatcher 原始文件。
- `tools/model-quality/runs` 约 477 MiB，是本地实验结果与复现信息；保留，不按缓存清理。
- 根 `node_modules` 约 674 MiB、后端 `.venv` 约 598 MiB，属于依赖环境，保留。
- `apps/web/.next` 约 3.4 GiB，开发服务仍在运行，保留。桌面 debug sidecar 正在使用仓库路径，保留可执行程序及相关依赖。

## 资料分布

| 位置 | 信息与处理 |
| --- | --- |
| `apps/web`、`services/ai/app`、`packages/shared`、`apps/desktop/src-tauri/src` | 前端、后端、共享契约和桌面源码，未修改 |
| `docs/` | 架构、API、发布、验收和研究报告；新增阶段归档与本记录 |
| `docs/quality/evidence/` | 质量实验导出、失败、截图及书页素材，原位保留 |
| `tools/model-quality/` | 实验运行器、领域桥接及本地 runs，原位保留 |
| `services/ai/data/` | 运行数据库、上传和兼容数据，未清理 |
| `TODO.md`、`docs/quality/TODO.md` | 移出已完成过程记录，保留所有仍待独立验收的开放任务 |

## 已清理的缓存

删除前确认无 cargo/rustc/PyInstaller 构建进程；通过 `lsof` 检查对应目录无打开文件，并确认目录均被 Git 忽略且不含已跟踪文件。未停止任何服务。

| 目录 | 删除前 KiB |
| --- | ---: |
| `apps/desktop/src-tauri/target/debug/incremental` | 746,364 |
| `apps/desktop/src-tauri/target/release/deps` | 1,172,776 |
| `apps/desktop/src-tauri/target/release/build` | 310,824 |
| `apps/desktop/src-tauri/target/release/.fingerprint` | 10,308 |
| `services/ai/build/pyinstaller/work` | 231,080 |

保留 release bundle 安装包、PyInstaller dist、sidecar 二进制和当前 debug 产物。下一次相应构建会重建已删除的中间文件，首次重建时间可能增加。

## 已办结事项整理

[阶段归档](quality/completed-work-2026-09-12.md)收拢已完成的实验与修复记录，链接原始证据。更新实验图表报告的后续状态，避免已经完成的源码复核、live 交付和浏览器检查仍被描述为尚未执行。Bridge 与图表修复只在实验范围内完成，不关闭独立模型质量、生产 UI 或平台验收。

已有未提交代码、图标和实验资料保持原状；本次未提交 Git，未重跑模型或产品测试。验证范围为文件校验、文档链接与 Git diff 空白检查。

## 用户要求停服后的补充清理

已向三个 Web 服务及其启动器、验收后端、四组桌面 sidecar 发送 SIGTERM，并确认无残留匹配进程。再次使用 lsof 确认目录无占用后，继续清理：

| 目录 | 删除前 KiB |
| --- | ---: |
| `apps/web/.next` | 3,574,716 |
| `apps/desktop/src-tauri/target/debug/deps` | 2,568,324 |
| `apps/desktop/src-tauri/target/debug/build` | 450,320 |
| `apps/desktop/src-tauri/target/debug/.fingerprint` | 15,832 |
| `apps/desktop/src-tauri/target/debug/examples` | 121,320 |

最终工作目录约 3.60 GiB；两轮合计清理 8.78 GiB（9,201,864 KiB）。前述 10.0 GiB 是第一轮清理后的中间状态，Next.js 和 debug 的运行状态也已由本节更新。依赖环境、实验结果、运行数据、安装包与 sidecar 可执行文件仍保留；再次启动 Web 前需重新生成构建产物。
