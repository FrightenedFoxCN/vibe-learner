# Tavern Harness

Tavern 是独立于 Study Session 的领域。一次 direct/facilitated run 在 `tavern_runs` admission 时分配 Harness identity；facilitated targets 按 participant `display_order` 形成 server-owned schedule，每个 `tavern_run_steps` actor step 独立进入 `tavern:actor_reply`。

## Snapshot 和生成

- Room、participant snapshots、scene、transcript suffix 和 reply anchor 注册为 protected artifacts；grant 必须精确绑定本地 principal 与 operation。
- prompt preflight 限制 canonical 256 KiB、token estimate 48000、scene 64 KiB/depth 8、transcript 128 KiB、persona instruction 64 KiB、cast 64 KiB；超限先按确定性策略缩减 transcript，仍超限则失败关闭。
- actor 正常 `max_tokens=chat_max_tokens`。优先 strict JSON Schema；provider 明确不支持时退到 JSON object；语义输出无效再做一次 `max(chat_max_tokens, 900)` 的 strict actor repair。
- `TavernActorHarness` 检查 speaker identity、target binding、跨角色冒充、空文本和允许的结构；可安全裁剪的冒充尾部才修复，不可判定时失败关闭。

## Commit 和恢复

step 使用数据库时钟 lease、heartbeat、owner/claim fencing，最多 3 claims。取消会立即 fence 后续 persistence；已经发出的同步 provider 请求只能 best-effort 等待自身 timeout。

每个通过校验的 actor 单独 append 一个 monotonic room-sequence Message，并原子写 server-only operation/effect receipt。authoritative read-back 必须在一个数据库快照中核对 Message、Run、Step、Participant 和 reply anchor。commit policy 为 `primary_output_only`，只证明该 Message。

facilitated run 允许已完成 steps 保留、后续 steps failed/blocked；retry 创建带 parent Harness binding 的 scoped child，只调度未完成 participants，并验证原 room context、participant snapshot 和 retry chain 不变。缺少 provider idempotency/read-back 的已发请求不能自动宣称未执行。

更完整的房间和调度结构见 [Tavern architecture](../tavern-architecture.md)，共享预算见 [配置与预算](configuration.md)。

