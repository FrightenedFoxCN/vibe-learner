# API 契约说明

> 全部 HTTP 端点的路径、参数、请求体与响应模型清单由 FastAPI OpenAPI 自动生成，见 [API 参考](api-reference.md)。本文件只定义 OpenAPI 无法表达的**协议语义、版本兼容规则、流式信封、并发控制与错误码**。

## 1. 基础传输约定

- **默认地址**：本地后端监听 `http://127.0.0.1:8000`；前端通过 `NEXT_PUBLIC_AI_BASE_URL` 读取；当前无账号认证层。
- **内容类型**：标准接口返回 `application/json`；流式接口返回 `application/x-ndjson`；PDF 原文接口（`GET /documents/{id}/file`）以内联 `application/pdf` 返回，支持 `#page=N` 片段定位。
- **错误结构**：FastAPI 错误遵循 `{"detail": ...}`；涉及冲突、输入超限或恢复语义的接口返回包含稳定 `code` 字段的结构化 detail。
- **客户端严格解码**：前端通过 `apps/web/lib/data/*.ts` 与 `apps/web/lib/*-decode.ts` 从 `unknown` 做 fail-closed 解码，绑定请求主体、校验枚举/有限数值/可空性/跨字段引用与去重，不在解码层发明业务默认值；解码失败统一上报无内容 `decode_failed` 诊断事件。

## 2. Settings 与模型可观测响应版本

以下接口显式携带 `contract_version`，枚举与版本对齐 `packages/shared/fixtures/settings/responses-v1.json`：

| 接口组 | 契约版本 | 关键解码约束 |
| --- | --- | --- |
| 运行时设置 | `runtime-settings-response-v1` | 严格布尔与有限边界数值；不回显明文密钥；`openai` 兼容别名归一为 `litellm` |
| 模型工具配置 | `model-tool-config-response-v1` | 校验阶段/分类可用性与覆盖值；工具开关完全由此配置管理 |
| 模型连通性探测 | `runtime-model-probe-response-v1` | 探测 `/models` 并可选针对 `plan`/`study`/`persona`/`scene`/`tavern` 发送最小代表请求，返回各功能 `ready` / `unsupported` / `failed`；列模型失败与功能可调用结果相互独立 |
| 用量统计 | `model-usage-stats-response-v1` | 计数器均为非负安全整数；汇总须与分桶及明细一致，各计数器独立（不假定 `total_tokens = prompt + completion`） |

**历史无版本响应兼容**：仅当 `contract_version` 缺失时，对缺失字段启用显式兼容默认值（Settings `*_api_key_configured=false`、工具原因串 `""`、探测映射/数组为空与状态 `unknown/unavailable`、Usage `records=[]`）；显式 `null` 或类型错误一律拒绝。

## 3. NDJSON 流式传输契约（`stream-event-v1`）

`POST /documents/{id}/process/stream` 与 `POST /learning-plans/stream` 逐行输出 `stream-event-v1` 信封：

```json
{
  "event_schema_version": "stream-event-v1",
  "operation_id": "stream-...",
  "event_id": "stream-...:event:9",
  "event_sequence": 9,
  "stream_kind": "document_process | learning_plan",
  "subject": { "subject_type": "document | learning_plan_request", "subject_id": "..." },
  "stage": "stream_completed",
  "payload_contract_version": "document-process-stream-payload-v1 | learning-plan-stream-payload-v1",
  "payload_digest": "<python-canonical-sha256>",
  "payload": {},
  "terminal_evidence": {
    "commit_status": "committed | not_committed | uncertain",
    "domain_operation_id": "...",
    "domain_operation_status": "committed",
    "evidence_scope": "primary_output_only",
    "resource_type": "document | learning_plan",
    "resource_id": "...",
    "commit_contract_version": "...",
    "projection_contract_version": "...",
    "projection_digest": "<sha256>"
  },
  "committed_projection": {},
  "created_at": "2026-01-01T00:00:00+00:00"
}
```

- **序列与摘要**：`operation_id`、`event_id` 与单调递增 `event_sequence` 均由服务端分配；`payload_digest` 由 Python 规范序列化计算（浏览器不以 `JSON.stringify` 重算跨语言摘要）。
- **终态事件**：
  - `stream_completed` 仅在 `terminal_evidence.commit_status === "committed"` 且携带完整 `committed_projection` 与精确摘要时有效；
  - `stream_error` 与 `stream_cancelled` 携带 `not_committed` 或 `uncertain` 且 `committed_projection` 为 `null`；
  - 取消流接口为 `POST /stream-runs/{stream_id}/cancel`。
- **持久化流报告（`stream-report-v1`）**：保留最近 120 条事件与累计 `last_event_sequence`，供重连或调试面板检测事件缺口；`terminal_evidence` 为 `primary_output_only` 传输读回，不等同于整笔事务的全部副作用证明。

## 4. 各领域写语义、并发控制与错误码

### Persona（`/personas`）

- **全量替换**：`PATCH /personas/{persona_id}` 虽沿用 PATCH 动词，但语义为整条用户 Persona 替换，必填 `expected_revision`；创建时服务端分配不透明 `persona-<uuid>`（`revision=0`），改名不改变 ID。
- **并发与保护**：内置 Persona 只读（`403 persona_readonly_builtin`）；过期修改/删除返回 `409 persona_revision_conflict`（附当前 revision）；被引用的 Persona 删除返回 `409 persona_in_use`。

### Scene（`/scene-setup`、`/scene-library`）

- 保存接口强制使用严格 `scene-committed-save-v1` 与 `expected_revision`（新建传 `0`），拒绝调用方提交 `scene_profile` 或提案字段；服务端按树重建 `SceneProfile`。
- 过期写入返回 `409 scene_revision_conflict`；非法生成提案返回 `502 setting_model_invalid_payload`。详见 [场景编辑器](scene-setup.md)。

### Documents（`/documents`）

- 上传与处理遵循 `document-input-limits-v1`（64 MiB 文件 / 65 MiB 请求体 / 512 物理页 / 65,536 字符单文本单元），超限返回 `413` 与 `document-input-error-v1` detail。
- Study Unit 改名（`PATCH /documents/{id}/study-units/{unit_id}`）必填 `expected_revision`，处理期间或过期返回 `409`。
- 断点查询（`GET /documents/{id}/checkpoint`）、显式续跑（`resume_from_operation_id`）与印刷页码对照（`GET /documents/{id}/page-numbering`）语义见 [教材解析与入库链路](document-pipeline.md)。

### Learning Plans（`/learning-plans`）

- 创建计划（`POST /learning-plans` / `/stream`）要求稳定 `client_request_id`，绑定文档时需带 `expected_document_updated_at`；重复提交读取原提交快照，冲突/活动操作/过期文档返回 `409`（`learning_plan_stale_document`、`learning_plan_operation_active`、`learning_plan_request_conflict`、`learning_plan_projection_prerequisite_missing`）。
- 模型上游错误映射为稳定状态码：`503 plan_model_rate_limited`、`504 plan_model_timeout`、`502 plan_model_network_error / plan_model_upstream_error / plan_model_invalid_json / plan_model_invalid_payload`、`500 plan_generation_failed`。
- 计划修订预览/确认、历史回滚、Study Unit 修订确认与纯查询恢复（`GET /learning-plan-operations/{client_request_id}`）见 [学习计划链路与契约](learning-plan.md)。

### Study Sessions（`/study-sessions`）

- 对话（`POST /study-sessions/{id}/chat` 与 `/chat-with-attachments`）要求稳定 `client_request_id` 与 `expected_session_revision`，返回 `StudyChatOperationReceipt`（状态 `admitted` / `running` / `committed` / `not_committed` / `uncertain`；可空字段显式输出 `null`，仅 `committed` 时 `result` 非空）。
- 上游调用开始后的模型/网络/超时失败落库为 `HTTP 200` 的 `uncertain` 回执（携带 `error_code`），避免客户端误将 HTTP 错误当成可安全重放信号；纯查询读回使用 `GET /study-sessions/{id}/chat-operations/{client_request_id}`。
- 交互题作答（`POST /study-sessions/{id}/attempt`）仅接收 `turn_id`、`expected_session_revision`、`client_attempt_id` 与 `submitted_answer`，返回 `study-question-attempt-response-v1`，浏览器随后通过 `GET /study-sessions/{id}` 读回持久化 Session 核验。
- `PATCH /study-sessions/{id}` 至少需提供 `study_unit_id` 或 `scene_profile` 之一，否则返回 `400 update_payload_empty`。详见 [学习会话与对话恢复](study-session.md)。

### Tavern（`/tavern`）

- **房间列表分页（`GET /tavern/rooms`）**：返回 `tavern-room-list-v1`，按 `(updated_at DESC, id DESC)` 稳定排序，`limit` 1–50（默认 30），`cursor` 经版本与完整性校验（篡改或失效返回 `400`）。
- **消息分页（`GET /tavern/rooms/{id}`）**：`tail=true`、非零 `after_sequence` 与 `before_sequence` 互斥，`limit` 1–200，所有方向均按消息序号升序返回。
- **回合、取消、恢复与子重试**：创建与回合均需 `idempotency_key` 与 `expected_room_revision`；同键异载荷、过期修订号、进行中 Run 或过期续接锚点返回 `409`；终态失败返回 `502` 与结构化 `{code, run_id, child_run_id, current_revision, recovery_action}`，仅 `replay_same_request` 允许前端自动单次原样重放读取 `200` 终态回执。详见 [Tavern 多角色互动](tavern.md)。

### Diagnostics（`/diagnostics`）

- 批量上报（`POST /diagnostics/events`）、游标查询（`GET /diagnostics/events`、`/harness-index`、`/operation-links`、`/writers`）、存储观测（`GET /diagnostics/storage`）与快照导出（`POST /diagnostics/export`）的契约、配额与脱敏边界见 [诊断与审计体系](diagnostics.md)。

## 5. 契约对齐清单

改动 HTTP 契约时保持以下位置同步：

- 后端路由与模型：`services/ai/app/api/routers/*.py`、`tavern_routes.py`、`diagnostic_routes.py`、`services/ai/app/models/*.py`
- 自动生成参考：运行 `npm run gen:api-reference` 更新 [docs/api-reference.md](api-reference.md)
- 共享与前端解码：`packages/shared/src/`、`apps/web/lib/api/*.ts`、`apps/web/lib/data/*.ts`、`apps/web/lib/*-decode.ts`
