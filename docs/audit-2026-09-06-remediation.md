# 审计修复记录（2026-09-07）

本记录对应 `docs/audit-2026-09-06.md`，基线为 `8f5ff0f`。审计原文和
`audit-2026-09-06-evidence/` 保留为不可变的发现证据；下面记录本轮实现修复和
验证结果。

## 修复范围

- **A01 / A03 / A16**：Study 章节切换按目标串行、同目标去重，并在异步完成前后
  检查最新目标；深链接计划和排期在首次应用后消费，手工选择会清除待处理请求；
  自动开场失败会进入失败闸门，只有明确的手动重试才会重新提交。
- **A02**：纯目标计划使用安全的流存储键，领域 subject 仍保持独立；同步和流式
  请求都覆盖安全键和报告读回。
- **A04**：子阶段 trace 明确标记为 `observed_runtime`，保留真实调用的计时、计数
  和结果摘要；`failed` / `unavailable` 会产生失败 check 和失败终态，不再把失败
  证据标成 PASSED。子阶段仍不声称重新执行 parser、OCR 或工具，独立 live-wire
  执行证据仍是验收缺口。
- **A05**：Tavern 名册更新若会移除已有 Message 或 Run Step 引用的 Participant，
  返回结构化 409，并保留历史快照以便读回和继续互动。
- **A06**：桌面在 Tauri `RunEvent::ExitRequested` / `Exit` 中显式 kill/wait sidecar，
  `Drop` 继续作为兜底清理。
- **A07 / A08 / A09 / A14**：强制 OCR 在不可用或失败时不生成伪 Study Unit 并使
  操作失败；Document Page、Section、Chunk、Study Unit 的计数、排序、范围、文档
  身份和引用严格校验（保留格式化的系统 Study Anchor）；Persona 输出先严格解码，
  不再通过字符串或默认值转换掩盖错误；英文 `Chapter` 标题保持可规划。
- **A10 / A11 / A12 / A13**：Sensory Tools 保存串行化；工作区刷新、Persona
  reload 使用请求/草稿 fence；Settings 的 900ms debounce 在 pagehide 和卸载时
  flush 待保存快照。
- **A15**：desktop release workflow 在打包前新增 `npm run check:release` job，
  并将打包和发布依赖到该门禁。

## 验证

以下命令在本地工作树通过：

- `npm run check:release`（shared contracts、Web 类型、160 个 Web 可靠性用例
  （158 pass、2 个明确 live skip）、Harness PR eval、515 个后端测试、production
  Web build）；
- `cargo fmt --manifest-path apps/desktop/src-tauri/Cargo.toml -- --check`；
- `cargo check --manifest-path apps/desktop/src-tauri/Cargo.toml --locked --offline`；
- 针对审计边界的 19 个后端测试，以及 OCR、Tavern 历史名册、Persona 严格解码、
  英文章节和 goal-only 流报告回放测试。

浏览器首次验收、真实桌面安装/退出、真实上游 provider、PostgreSQL 并发和其余
未注册 Harness eval suite 仍按原审计保持开放；本记录不把实现接入等同于这些
独立验收已经完成。
