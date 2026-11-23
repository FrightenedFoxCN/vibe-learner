# Persona Generation Harness

Persona Spectrum 的关键词生成、长文本提取、整体设定辅助编辑与单槽位改写共享 Setting Provider，生产 Harness 阶段为 `persona:persona_generation`，准入记录存于 `harness_workflow_operations`。生成结果仅为未持久化候选，用户保存属于独立的 Persona 写边界。

## 输出约束

- `PersonaGenerationProposalV1` 严格禁止额外字段（`extra="forbid"`）：最多 24 张 cards、64 个 slots。
- 单张卡片 title/label ≤ 500 字符、content ≤ 8000 字符、tags ≤ 24 个；system prompt 建议 ≤ 16000 字符。
- 请求指定生成数量时，返回条目数必须精确匹配，否则 fail-closed。
- 模型仅产出内容字段；Persona ID、revision、source 与时间戳由应用在保存时分配。

## 恢复与预算

- 结构化输出遇到 invalid JSON、invalid payload、空响应或可恢复的 content filter 时，最多执行 1 次低温结构修复（与初始校验共享恢复预算）。
- 关键词模式联网搜索在 Provider 明确不支持时降级为无网络 chat，并记录强类型 `feature_fallback`，不掩盖普通内容质量失败。
- 短辅助编辑使用 `setting_max_tokens`；Persona Card 长结构生成使用 `max(setting_max_tokens, 8192)`（完整次数见 [配置与预算](configuration.md)）。
- 候选内容经 `PersonaGenerationWorkflowAdapter` 严格解码返回，保存至 `personas` / `persona_cards` 须通过带 `expected_revision` 的独立保存接口。
