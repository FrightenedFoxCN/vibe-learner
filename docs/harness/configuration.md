# 配置与预算

## 配置优先级

启动时 `Settings.from_env()` 读取 `services/ai/.env` 和进程环境；随后 `RuntimeSettingsService` 从数据库 `runtime_settings` 载入可编辑值并生成一次操作快照。运行中的 provider 使用该快照，避免一次请求跨越配置修改。桌面模式的密钥仅保存在 session secret 中，API 描述不回显明文。

后端默认值、校验范围和 provider 恢复常量统一定义在 `services/ai/app/core/model_runtime_limits.py`。`Settings`、`RuntimeSettingsRecord` 和 provider 构造器引用这些常量。浏览器需要的默认值与范围集中在 `packages/shared/src/model-runtime-config.ts`，Python/TypeScript 通过 `packages/shared/fixtures/model-runtime-config-v1.json` golden 测试防止漂移；服务端返回值仍是运行时权威。

## 可编辑模型配置

| 配置 | 环境变量 | 默认值 | 运行时范围 / 用途 |
| --- | --- | ---: | --- |
| setting output tokens | `OPENAI_SETTING_MAX_TOKENS` | 900 | 64–16384；短 Persona 辅助编辑直接使用 |
| chat output tokens | `OPENAI_CHAT_MAX_TOKENS` | 800 | 64–16384；Study 和 Tavern 正常生成使用 |
| chat history messages | `OPENAI_CHAT_HISTORY_MESSAGES` | 8 | 1–40 |
| limited tool rounds | `OPENAI_CHAT_TOOL_MAX_ROUNDS` | 4 | 1–12；只计算非 exempt Study tool round |
| provider timeout | `OPENAI_TIMEOUT_SECONDS` | 30 s | 5–300 s；还会被 Harness per-call timeout 和剩余 wall time收紧 |
| chat temperature | `OPENAI_CHAT_TEMPERATURE` | 0.35 | 0–2 |
| setting temperature | `OPENAI_SETTING_TEMPERATURE` | 0.4 | 0–2 |
| Planning provider | `VIBE_LEARNER_PLAN_PROVIDER` | `mock` | `openai` 兼容别名会归一为 `litellm` |

Planning、setting、chat 可分别覆盖 API key、base URL 和 model；空的专项 key 回退到全局 `OPENAI_API_KEY`。数据库 runtime setting 覆盖启动默认，但数据库连接、存储目录、OCR/layout 等基础设施项仍以启动配置为准。

## 输出 token 上限

| 请求 | 实际请求字段和值 |
| --- | --- |
| Planning generation / repair | `max_tokens=8192` |
| Plan revision | `max_tokens=8192` |
| Persona / Scene 长结构生成 | `max(setting_max_tokens, 8192)`；用户可将 setting 上限调到 16384 |
| Persona 短辅助编辑 | `max_tokens=setting_max_tokens`；结构修复时至少增加 800 或乘 1.5，且不会把用户配置的更大值降到 8192 |
| Study Chat | 正常为 `chat_max_tokens`；无工具语义恢复为 `max(chat_max_tokens, 1600)` |
| Tavern actor | 正常为 `chat_max_tokens`；语义恢复为 `max(chat_max_tokens, 900)` |
| provider probes | tool 32、JSON 48、Tavern schema 48 |

LiteLLM compatibility adapter 可把 `max_tokens` 改写为 `max_completion_tokens`，原始业务上限不变。

## 调用次数

“逻辑请求”是一次 provider adapter 调用；一次逻辑请求遇到可重试的 transport 错误时最多再试 2 次，所以最多产生 3 次物理 SDK 调用。

| 工作流 | 逻辑请求上限 |
| --- | --- |
| Plan revision | 1 |
| Planning generation | 每个 runner 最多 24 rounds；最多 1 个 tool round。primary 失败可运行一次 fallback，最终 proposal 无法本地修复时可再运行一次 strict repair，因此理论结构上限为 72；180 秒 Harness wall-time 通常先截断 |
| Persona / Scene | 一次初始请求 + 一次结构修复；关键词 web-search 不兼容时可改走 chat fallback，最坏为 3 次逻辑请求 |
| Study Chat | `max(tool_max_rounds + 12, tool_max_rounds * 3)` 个生成 round，默认 16；最终严格解码失败可再做 1 次无工具恢复，默认最多 17 |
| Tavern actor | 初始 1 次；JSON Schema transport 不兼容可 fallback 1 次；随后仍不合法可语义修复 1 次，最多 3 |

Planning 的 6 个工具由 Tool Manifest 分别限制：每个工具每 operation 最多 4 次；每 round 一般最多 1 次，`get_study_unit_detail` 与 `read_page_range_content` 最多 3 次。Study 的 31 个工具同样以 Tool Manifest 为权威，不使用散落在 prompt 中的数字。

## Harness manifest 预算的执行状态

默认 manifest 登记 `max_provider_calls=3`、`max_tool_calls=16`、`max_input_tokens=64000`、`max_output_tokens=8192`、`max_wall_time_ms=180000`、`per_call_timeout_ms=120000`。Tavern 覆盖为 provider 3、tool 0、input 24000、output 4000。这里的 token 数是工作流审计预算，不会覆盖 provider 请求参数。

- 已通用执行：wall-time、per-call timeout、runtime attempt/evidence byte limits。
- 已在独立边界执行：Tool Manifest 的 per-tool/per-round/per-operation 次数和参数/结果字节数。
- 尚未成为通用硬计数器：manifest 的 provider call/input token/output token 总量。诊断或文档不能把它们表述成已强制执行；若要启用，必须先为 Planning/Study 的多 round 语义定义计数口径并补回归测试。
