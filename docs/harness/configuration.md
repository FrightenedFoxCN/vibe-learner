# 配置与预算

## 配置优先级

1. 启动时 `Settings.from_env()` 读取 `services/ai/.env` 与进程环境变量；
2. `RuntimeSettingsService` 从数据库 `runtime_settings` 载入可编辑设置，并在每次操作入口冻结一份配置快照，确保单次请求不会中途跨配置切换；
3. 桌面模式下 API 密钥仅保存在内存会话密钥中，接口响应不回显明文；
4. 数据库连接、存储目录、OCR 与版面引擎等基础设施配置始终以启动环境为准，不由运行时设置热切换。

浏览器可编辑参数的默认值与范围，以及界面展示的输出预算，统一定义在 `packages/shared/fixtures/model-runtime-config-v1.json`。修改后执行 `cd services/ai && uv run python ../../scripts/gen_model_runtime_config.py`，生成 Python 与 TypeScript 定义；`npm run check:contracts` 拒绝不同步的产物。服务端读回仍是当前运行时取值的权威。

## 可编辑模型配置

| 配置项 | 环境变量 | 默认值 | 运行时范围与说明 |
| --- | --- | ---: | --- |
| Setting 输出上限 | `OPENAI_SETTING_MAX_TOKENS` | 900 | 64–16384；用于 Persona 辅助编辑 |
| Chat 输出上限 | `OPENAI_CHAT_MAX_TOKENS` | 800 | 64–16384；用于 Study 与 Tavern 常规回复 |
| Study 初始对话历史 | `OPENAI_CHAT_HISTORY_MESSAGES` | 8 | 1–40 条消息；不影响 Tavern 或存储保留 |
| 受限工具轮次 | `OPENAI_CHAT_TOOL_MAX_ROUNDS` | 4 | 1–12；仅统计非豁免 Study 工具轮次 |
| Provider 超时 | `OPENAI_TIMEOUT_SECONDS` | 30 s | 5–300 s；同时受 Harness per-call timeout 与剩余 wall time 收紧 |
| Chat 温度 | `OPENAI_CHAT_TEMPERATURE` | 0.35 | 0–2 |
| Setting 温度 | `OPENAI_SETTING_TEMPERATURE` | 0.4 | 0–2 |
| Planning Provider | `VIBE_LEARNER_PLAN_PROVIDER` | `mock` | `mock` 或 `litellm`（`openai` 兼容别名归一为 `litellm`） |

Planning、Setting 与 Chat 可分别覆盖 API Key、Base URL 与 Model；专项 API Key 为空时回退至全局 `OPENAI_API_KEY`。

## 输出 Token 上限

| 请求类型 | 实际生效上限 |
| --- | --- |
| Planning 生成与修复 | `max_tokens = 8192` |
| Plan 修订 | `max_tokens = 8192` |
| Persona / Scene 长结构生成 | `max(setting_max_tokens, 8192)`（用户最高可设至 16384） |
| Persona 短辅助编辑 | 常规为 `setting_max_tokens`；Chat 结构修复为 `max(当前值, min(max(当前值 + 800, floor(当前值 × 1.5)), 8192))`；Responses 修复保留原输出上限 |
| Study Chat | 常规为 `chat_max_tokens`；无工具语义恢复为 `max(chat_max_tokens, 1600)` |
| Tavern 角色回复 | 常规为 `chat_max_tokens`；语义恢复为 `max(chat_max_tokens, 900)` |
| Provider 能力探测 | tool 32、JSON 48、Tavern schema 48 |

LiteLLM 兼容适配层可按模型要求将 `max_tokens` 映射为 `max_completion_tokens`，业务数值上限不变。

## 逻辑请求与重试上限

一次“逻辑请求”对应一次 Provider 适配调用；遇到可重试的瞬态传输错误时最多重试 2 次（共最多 3 次物理 HTTP 调用）。

| 工作流 | 逻辑请求上限 |
| --- | --- |
| Plan 修订 | 1 |
| Planning 生成 | 单个 runner 最多 24 rounds（其中最多 1 个工具 round）；primary 失败可切换 1 次 fallback 模型，最终提案无法本地修复时可发起 1 次无工具 strict repair（理论上限 72，通常先受 180 秒 Harness wall-time 截断） |
| Persona / Scene 生成 | 初始 1 次 + 结构修复 1 次；关键词搜索不兼容时可降级无网络 chat，最坏 3 次 |
| Study Chat | 最多 `max(tool_max_rounds + 12, tool_max_rounds * 3)` 个生成 round（默认 16）+ 1 次无工具最终恢复（默认最多 17） |
| Tavern 角色回复 | 初始 1 次 + JSON Schema 降级 `json_object` 1 次 + 语义修复 1 次，最多 3 次 |

Planning 的 6 个工具与 Study 的 32 个工具均以 Tool Manifest 为唯一配额权威：Planning 工具单次操作上限 4 次/工具，每轮一般 1 次（`get_study_unit_detail` 与 `read_page_range_content` 每轮最多 3 次）。

## Harness Manifest 预算执行状态

默认 Manifest 登记：`max_provider_calls=3`、`max_tool_calls=16`、`max_input_tokens=64000`、`max_output_tokens=8192`、`max_wall_time_ms=180000`、`per_call_timeout_ms=120000`（Tavern 覆盖为 provider 3、tool 0、input 24000、output 4000）。

- **通用强制执行**：wall-time、per-call timeout、runtime attempt 与 evidence 字节上限。
- **独立边界强制执行**：Tool Manifest 的 per-tool / per-round / per-operation 次数及参数/结果字节上限。
- **仅登记与审计（非通用硬计数）**：Manifest 中的 `max_provider_calls`、`max_input_tokens` 与 `max_output_tokens`，不会覆盖各工作流的实际 Provider 参数。
