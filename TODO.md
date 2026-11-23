# TODO

本文件是唯一未完成任务入口。运行约束见 [AGENTS](AGENTS.md)，架构与操作说明见 [docs](docs/README.md)。

- `P1`：用户可用性、数据一致性或跨工作流基础边界。
- `P2`：产品、性能或可靠性改进。
- `P3`：文档、账务和候选验证。

标记 `暂缓` 表示当前缺设备或权限，不是遗漏。

## UX 与文档

- [ ] `UX-DENSITY-SENSORY-001` `[P2]` 真实触控设备上的密度、长错误与慢网连续保存复核：滚动与焦点稳定性。暂缓（无实机）。
- [ ] `UX-DENSITY-PERSONA-001` `[P2]` 真实设备上 Persona 编辑的保存/错误焦点、滚动与触控复核，覆盖候选选择/拒绝、字段 diff、名称必填定位与危险操作分层。暂缓（无实机）。
- [ ] `UX-DENSITY-SCENE-001` `[P2]` 真实设备上 Scene 编辑的保存/错误定位、滚动与触控复核，覆盖结构/字段 diff、冲突提示与危险操作分层。暂缓（无实机）。
- [ ] `DOC-USER-001` `[P2]` 独立走查 `/manual` 用户手册。
  - 真实 provider 首次配置与主流程走查暂缓；mock 路线复跑入口为 `playwright.manual-acceptance.config.ts`。
  - 补原生安装/Vault、Windows NSIS 与 Linux AppImage 安装、含密钥与浏览器草稿的设备级恢复；手册中的路径/留存、unsigned 与 SHA-256 说明需与各平台实测对照。

## 性能、可靠性与部署

- [ ] `REL-DESKTOP-001` `[P2]` 完成真实桌面/浏览器恢复验收。
  - 覆盖原生桌面安装/退出、设备级慢网/断网、刷新/离页、未保存/异步返回、删除/归档组合，以及设备级 IME 与完整焦点顺序。暂缓（无实机）。
  - 覆盖浏览器 Settings 在途离页/丢响应、Tavern 空状态/整页键盘/删除归档组合、编辑器异步保存与 Study 恢复。
- [ ] `PERF-TAV-LIVE-001` `[P2]` 验收代表性真实 provider 的 Tavern 性能。开始前需明确 provider 配置与调用/费用上限。
  - 使用六人名册、每次最多四个调度目标及长对话，记录 token、实际计费、P50/P95、修复/失败率及 retry/cancel 行为。
- [ ] `DESKTOP-RELEASE-001` `[P2]` 完成生产签名、公证和跨平台安装验收。
  - 当前缺 Windows/Linux 桌面设备与 Apple Developer ID/公证配置。
  - macOS sidecar/native dependencies 使用同一 Developer ID Team，验证后开启 hardened runtime；验证 Windows/Linux 安装、退出与校验和。
  - 验收标准：签名、公证与跨平台安装实测通过。预览版允许 runtime OCR fallback 的策略见 `docs/desktop-packaging.md`；离线 OCR 分发须提供模型并启用 strict gate。
- [ ] `DIAG-INSTALLATION-BUDGET-001` `[P2]` 验收诊断数据的安装级磁盘预算与恢复。
  - 将 event、Harness index、桌面 spool、WAL/SHM/journal、锁文件与文件系统分配开销纳入同一 200 MiB 口径。
  - 补 Windows 文件语义、外部写入与安装级整体约束；复用现有 macOS Rust/Python 并发压力与 Linux 容器配额/恢复测试。
  - 跨进程、跨平台证据齐全后，导出的 `disk_size_limit_certified` 才可为 true。
- [ ] `DIAG-NATIVE-EXPORT-001` `[P2]` 补真实原生保存对话框的取消/覆盖确认、IPC、桌面满盘及 Windows/Linux 文件落盘验收；macOS 自动化需可用的 System Events/辅助功能权限。32 MiB JSON/原子文件替换回归与 HFS+/APFS ENOSPC 协议见 `docs/diagnostic-audit.md`。暂缓（缺权限）。

## 未排期研究

研究任务须有触发证据、假设、time-box、产出物和采用/放弃标准：

- `RND-RUST-001`：profiling 证明 Python/TypeScript 热点后再评估 Rust 重写。
- `RND-THEME-001`：先确定用户需求、design tokens、对比度基线与关闭开关。
- `RND-LIVE2D-001`：先确定授权、资源预算、动画降级和设备性能。
- `RND-TTS-001`：先确定隐私、延迟、成本、可取消传输、字幕和静音降级。
- 桌面自动更新、崩溃上报及 sidecar 打包形态：先确定发布策略并测量性能。
- `SKILL-DISTILL-001`：只抽取稳定、可验证、无密钥/用户数据的流程；[AGENTS](AGENTS.md) 与 [docs](docs/README.md) 仍是事实真源。

性能任务须记录 fixture、环境、raw samples 和 before/after；预算变更遵循 `docs/performance-budgets-v1.md`。`QG-002` / `web-strict-decode-adversarial-v1` 保持不可变，扩展使用新版本。

## 已知风险

- OCR cleanup 仍是启发式主导，是规划噪声的主要来源。
- 工具化规划会增加 provider 延迟与超时压力。
- 前端依赖历史 debug 与 plan 产物；改本地存储形状需谨慎。
- Study Session 聚合写入使用 revision CAS 与连续 turn 序号；已提交 Turn 内容除交互题答案字段外不可变。provider exactly-once 不支持。
- 生产工作流使用 v3 Harness runtime；剩余范围任务即本文件。
- Harness 资源引用必须有 evidence policy；无权威 revision 的资源不得传常量 `revision=0`。
- 构造 v3 context 或 commit evidence 前使用 `HARNESS_RESOURCE_EVIDENCE_POLICIES`。Tavern Room revision 覆盖元数据与 run 准入 CAS，不覆盖 transcript 漂移；Tavern Message 在能解析房间级受保护 transcript 快照前不支持作为 context subject。
- 生产 v3 commit evidence 必须匹配注册的 workflow/stage/output/payload key、允许的资源集合，以及能证明全部应用自有 scope 字段的版本化 committed-projection DTO；当前 Tavern actor policy 只证明一条 `primary_output_only` Message。
- 门禁入口：`npm run check`（style + contract types + Web types + API reference 同步 + 不变量基线）；`npm run check:release` 额外构建生产 Web。`npm run style:check -- --base <commit>` 做改动文件的格式与 lint 检查，见 `docs/code-style.md`。
