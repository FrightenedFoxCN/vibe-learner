# Tavern Harness

Tavern 拥有独立于 Study Session 的持久化与执行域。每次直接或引导式回合在 `tavern_runs` 准入时分配 Harness 身份；服务端按参与者 `display_order` 生成固定说话顺序，每个 `tavern_run_steps` 角色步骤独立进入 `tavern:actor_reply`。

## 受保护快照与预检

- Room、Participant 快照、Scene、Transcript 后缀与 Reply Anchor 均注册为受保护制品；`tavern-actor-workflow-adapter-v2` 在调用前授权解析并严格比对当前持久化 Run/Step 投影，防止任何篡改或过期上下文进入 Provider。
- Prompt 预检预算上限：规范总字节 256 KiB、估算 token 48,000、Scene 64 KiB（树深 8）、Transcript 128 KiB、Persona 指令 64 KiB、阵容信息 64 KiB。超限时仅按确定性规则从最旧消息裁剪 Transcript 前缀，仍超限则 fail-closed。
- 角色回复常规使用 `max_tokens = chat_max_tokens`：优先请求严格 `json_schema`；Provider 明确不支持时降级 `json_object`；语义无效时允许最多 1 次 `max(chat_max_tokens, 900)` 低温结构修复。
- `TavernActorHarness` 校验说话人身份、目标成员归属、必需前置目标、Prompt 泄漏与非空内容，仅对可安全裁剪的跨角色冒充尾部执行修复，不可判定时 fail-closed。

## 租约、取消、提交与子重试

- 每个 Speaker Step 使用数据库时钟租约、心跳与 `(owner, claim_count)` 围栏，最多 3 次认领（初始 + 2 次接管）。
- 取消操作立即在数据库侧落栏阻止后续提交与恢复；对兼容的 OpenAI Chat Completions 路由同时通过独立 `httpx.AsyncClient` 取消本地 HTTP 请求并关闭连接，其他同步协议保留超时与提交围栏；本地断连不代表上游停止计算或计费。
- 每个通过校验的角色逐条追加单调 `(room_id, sequence)` 消息，并原子写入服务端私有操作/效果回执。权威读回在同一数据库快照内核对 Message、Run、Step、Participant 与 reply anchor；Commit Policy 为 `primary_output_only`。
- 部分失败的引导式回合保留已提交角色消息；子重试（`retry`）创建绑定父 Harness 身份的子 Run，仅调度未完成参与者，并校验 Room 修订号、消息序号、上下文摘要与参与者 Prompt Hash 未发生变化。

完整房间架构、交互面板顺序契约与取消传输细节见 [Tavern 多角色互动](../tavern.md)，共享预算见 [配置与预算](configuration.md)。
