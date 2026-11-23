# TODO

本文件是唯一未完成任务入口。运行约束见 [AGENTS](AGENTS.md)，架构与操作说明见 [docs](docs/README.md)。

- `P1`：用户可用性、数据一致性或跨工作流基础边界。
- `P2`：产品、性能或可靠性改进。
- `P3`：文档、账务和候选验证。

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
