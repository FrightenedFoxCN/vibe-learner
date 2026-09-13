# Persona Generation Harness

Persona Spectrum 的关键词生成、长文本生成、整体辅助编辑和单 slot 辅助编辑共享 setting provider，但 Harness production stage 是 `persona:persona_generation`。admission 使用 `harness_workflow_operations`；结果是候选内容，不是已保存 Persona。

## 输出限制

- `PersonaGenerationProposalV1` 严格禁止额外字段；cards 最多 24、slots 最多 64。
- card title/label 最多 500 字符、content 最多 8000、tags 最多 24；system prompt suggestion 最多 16000。
- 指定 count 时必须精确返回该数量，否则失败关闭。
- 模型只生成内容字段；Persona ID、revision、source、保存时间由应用在用户保存时分配。

## 恢复

结构化 chat/Responses 输出遇到 invalid JSON、invalid payload、empty response 或允许恢复的 content filter 时，只做一次低温结构修复。关键词 web search 在 provider 明确不支持时回退为无网络 chat，并记录 typed `feature_fallback`；不能把普通内容质量失败伪装成 capability fallback。

短辅助编辑使用可配置 `setting_max_tokens`；Persona card 长生成使用 `max(setting_max_tokens, 8192)`。完整次数见 [配置与预算](configuration.md)。候选经 `PersonaGenerationWorkflowAdapter` 严格解码后返回；真正写 `personas` / `persona_cards` 是后续 user-authored persistence boundary。

