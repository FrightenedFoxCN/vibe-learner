# Planning / OCR / Setting Generation Observability

## 统一口径

一次 Planning operation 以 operation id 关联 provider rounds、tool calls、schema repair、Token usage、耗时、finish reason、终态和 committed artifact。Model Usage 可按 workflow、operation、日期筛选并导出 CSV；供应商 usage 是观测值，实际费用以供应商账单为准。

Plan Workspace 将 Document 解析/OCR 与 Learning Plan 生成分成两个进度块。解析块只呈现服务端事件已证明的页数、阶段、速率和 ETA；失败时保留完成范围与建议，不把解析失败覆盖成泛化的计划错误。

## 输出预算与错误

结构化 Persona/Scene 生成使用统一的 runtime ceiling。Chat 的 `finish_reason` 与 Responses 的 `status=incomplete` / `incomplete_details.reason` 在命中输出上限时映射为 `setting_model_output_truncated`；结构化修复增加或保持预算，且不会降低用户配置。HTTP detail 保留稳定 error code，Web 根据 code 提供超时、截断、schema、限流和 provider 的行动提示。

## 数据边界

UI 展示计数、阶段和安全摘要，不展示完整 reasoning、原始教材或受保护供应商内容。诊断关联使用 operation/request identity；Token 记录的 workflow、operation、stage 仅用于聚合与定位。
