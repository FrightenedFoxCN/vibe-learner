# TODO

本文件是唯一未完成任务入口。运行约束见 `AGENTS.md`，架构与操作说明见 `docs/`。

- `P1`：用户可用性、数据一致性或跨工作流基础边界。
- `P2`：产品、性能或可靠性改进。
- `P3`：文档、账务和候选验证。

## UX 与文档

- [ ] `UX-DENSITY-SENSORY-001` `[P2]` 补真实触控设备上的密度、长错误及慢网连续保存复核，检查滚动与焦点稳定性（人工实机验收暂缓）。桌面与窄屏 Chromium 回归入口见 `docs/frontend-test-boundaries.md`。
- [ ] `UX-DENSITY-PERSONA-001` `[P2]` 补真实设备的保存/错误焦点、滚动和触控复核，包含候选选择/拒绝、字段 diff、名称必填定位及危险操作分层（人工实机验收暂缓）。
- [ ] `UX-DENSITY-SCENE-001` `[P2]` 补真实设备的保存/错误定位、滚动和触控复核，包含结构/字段 diff、冲突提示及危险操作分层。实机及规则语义人工验收暂缓。
- [ ] `DOC-USER-001` `[P2]` 独立走查 `/manual` 用户手册。
  - 真实 provider 首次配置与 real 主流程验收暂缓；新数据 mock 路线复跑入口为 `playwright.manual-acceptance.config.ts`。
  - 补原生安装/Vault、Windows NSIS 与 Linux AppImage 安装、含密钥及浏览器草稿的设备级完整恢复；Vault 人工恢复验收暂缓。同路径 SQLite/文件恢复入口见 `docs/backend-test-boundaries.md`；手册中的路径/留存、unsigned 和 SHA-256 说明仍需与各平台实测对照。

## 性能、可靠性与部署

- [ ] `REL-DESKTOP-001` `[P2]` 完成真实桌面/浏览器恢复验收。
  - 补原生桌面安装/退出及设备级慢网/断网、刷新/离页、未保存/异步返回、删除/归档组合；设备级 IME 和完整焦点顺序的人工实机验收暂缓。
  - 浏览器 Settings 在途离页/丢响应、Tavern 空状态/整页键盘/删除归档组合，以及编辑器异步保存和 Study 恢复的回归入口见 `docs/frontend-test-boundaries.md`；合成 API 的浏览器结果不替代实机或真实 provider 验收。
- [ ] `PERF-TAV-LIVE-001` `[P2]` 验收代表性真实 provider 的 Tavern 性能。
  - 暂缓验收；开始前需明确 provider 配置与调用/费用上限。
  - 使用六人名册、每次最多四个调度目标及长对话，记录 token、实际计费、P50/P95、修复/失败率及 retry/cancel 行为。
- [ ] `DESKTOP-RELEASE-001` `[P2]` 完成生产签名、公证和跨平台安装验收。
  - 当前暂无 Windows/Linux 桌面设备及 Apple Developer ID/公证配置。
  - macOS sidecar/native dependencies 使用同一 Developer ID Team，验证后开启 hardened runtime；验证 Windows/Linux 安装、退出与校验和。
  - 签名、公证与跨平台安装不能由打包成功代替；预览版允许 runtime OCR fallback 的现行策略见 `docs/desktop-packaging.md`，离线 OCR 分发须提供模型并启用 strict gate。
- [ ] `DIAG-INSTALLATION-BUDGET-001` `[P2]` 验收诊断数据的安装级磁盘预算与恢复。
  - 将 event、Harness index、桌面 spool、WAL/SHM/journal、锁文件和文件系统分配开销纳入同一 200 MiB 口径。
  - 补 Windows 文件语义、外部写入/文件系统分配开销、安装级整体约束及真实工作流开销；复用现有 macOS Rust/Python 并发压力及 Linux 容器配额/恢复测试，避免重复将局部测量当作安装硬上限。
  - 跨进程、跨平台证据齐全后，导出的 `disk_size_limit_certified` 才可为 true。
- [ ] `DIAG-NATIVE-EXPORT-001` `[P2]` 补真实原生保存对话框的取消/覆盖确认、IPC、桌面应用满盘及 Windows/Linux 文件落盘验收；macOS 自动化需可用的 System Events/辅助功能权限。32 MiB JSON/原子文件替换回归与 HFS+/APFS 真实 ENOSPC 协议见 `docs/diagnostic-audit.md`，helper 验收不能替代 dialog/IPC 验收。
  - 原生对话框验收暂缓。

## 未排期研究

研究任务须有触发证据、假设、time-box、产出物和采用/放弃标准：

- `RND-RUST-001`：profiling 证明 Python/TypeScript 热点后再评估 Rust 重写。
- `RND-THEME-001`：先确定用户需求、design tokens、对比度基线与关闭开关。
- `RND-LIVE2D-001`：先确定授权、资源预算、动画降级和设备性能。
- `RND-TTS-001`：先确定隐私、延迟、成本、可取消传输、字幕和静音降级。
- 桌面自动更新、崩溃上报及 sidecar 打包形态：先确定发布策略并测量性能。
- `SKILL-DISTILL-001`：只抽取稳定、可验证、无密钥/用户数据的流程；`AGENTS.md` 仍是事实真源。

性能任务须记录 fixture、环境、raw samples 和 before/after；预算变更遵循 `docs/performance-budgets-v1.md`。`QG-002` / `web-strict-decode-adversarial-v1` 保持不可变，扩展使用新版本。
