# TODO

本文件是唯一未完成任务入口。运行约束见 `AGENTS.md`，架构与操作说明见 `docs/`。

- `P1`：用户可用性、数据一致性或跨工作流基础边界。
- `P2`：产品、性能或可靠性改进。
- `P3`：文档、账务和候选验证。

## UX 与文档

- [ ] `UX-DENSITY-SENSORY-001` `[P2]` 独立验收 Sensory Tools 的密度与保存反馈，覆盖真实设备、长错误及慢网连续保存，检查滚动与焦点稳定性。
- [ ] `UX-DENSITY-PERSONA-001` `[P2]` 独立复核 Persona 的保存反馈、错误焦点、滚动保持与真实设备操作；检查生成候选选择/拒绝、字段 diff、清空范围、名称必填定位及批量/删除动作分层。
- [ ] `UX-DENSITY-SCENE-001` `[P2]` 独立复核 Scene 的保存/错误定位与真实设备操作；检查覆盖前的结构/字段 diff、冲突候选、搜索筛选及危险操作分层。规则语义仍需人工检查。
- [ ] `DOC-USER-001` `[P2]` 独立走查 `/manual` 用户手册。
  - 使用全新临时数据目录走通 Settings 首次配置、goal-only、教材与 mock/real 路线，以及 Document/Plan/Study/Persona/Scene/Tavern 主任务。
  - 核对恢复语义、数据位置与留存、产品限制，以及 DMG/NSIS/AppImage 安装、unsigned 限制和 SHA-256 校验。

## 性能、可靠性与部署

- [x] `PERF-WEB-BUNDLE-001` `[P2]` 建立 `/`、Settings、Model Usage、Tavern 的 production gzip 基线和 5% 回退门。
  - 已加入 `npm run bench:web-bundle` 及 Release Gate 检查；基线与复跑协议见 `docs/performance/web-bundle-v1.md`。
- [ ] `REL-DESKTOP-001` `[P2]` 完成真实桌面/浏览器恢复验收。
  - 覆盖慢网、断网、刷新/离页、Settings 未保存变更、编辑器异步返回、删除/归档组合、桌面安装/退出。
  - 覆盖 Tavern 无 Persona/无 Room、设备级 IME 和完整焦点顺序。
- [ ] `OCR-STRESS-001` `[P2]` 测试真实 OCR 多语言、大型扫描件和失败恢复；复用 CPU fallback，记录内存、时延及错误状态，区分压力样本与正式支持上限。
- [ ] `PERF-TAV-LIVE-001` `[P2]` 验收代表性真实 provider 的 Tavern 性能。
  - 使用六人名册、每次最多四个调度目标及长对话，记录 token、实际计费、P50/P95、修复/失败率及 retry/cancel 行为。
- [ ] `DESKTOP-RELEASE-001` `[P2]` 完成生产签名、公证和跨平台安装验收。
  - macOS sidecar/native dependencies 使用同一 Developer ID Team，验证后开启 hardened runtime；验证 Windows/Linux 安装、退出与校验和。
  - 明确预览版缺少打包 OCR 模型时允许 fallback 还是阻止发布。
- [ ] `DIAG-INSTALLATION-BUDGET-001` `[P2]` 验收诊断数据的安装级磁盘预算与恢复。
  - 将 event、Harness index、桌面 spool、WAL/SHM/journal、锁文件和文件系统分配开销纳入同一 200 MiB 口径。
  - 验证并发桌面/外部写入、超限旧库、长读者占用 WAL 及 Windows/macOS/Linux 文件语义，提供可恢复清理/迁移路径和真实工作流开销。
  - 跨进程、跨平台证据齐全后，导出的 `disk_size_limit_certified` 才可为 true。
- [ ] `DIAG-NATIVE-EXPORT-001` `[P2]` 独立验收诊断快照原生保存，覆盖取消、覆盖、权限/磁盘失败及最终文件校验；与桌面恢复共用设备矩阵，分别记录 DTO 正确性和文件落盘结果。

## 未排期研究

研究任务须有触发证据、假设、time-box、产出物和采用/放弃标准：

- `RND-RUST-001`：profiling 证明 Python/TypeScript 热点后再评估 Rust 重写。
- `RND-THEME-001`：先确定用户需求、design tokens、对比度基线与关闭开关。
- `RND-LIVE2D-001`：先确定授权、资源预算、动画降级和设备性能。
- `RND-TTS-001`：先确定隐私、延迟、成本、可取消传输、字幕和静音降级。
- 桌面自动更新、崩溃上报及 sidecar 打包形态：先确定发布策略并测量性能。
- `SKILL-DISTILL-001`：只抽取稳定、可验证、无密钥/用户数据的流程；`AGENTS.md` 仍是事实真源。

性能任务须记录 fixture、环境、raw samples 和 before/after；预算变更遵循 `docs/performance-budgets-v1.md`。`QG-002` / `web-strict-decode-adversarial-v1` 保持不可变，扩展使用新版本。
