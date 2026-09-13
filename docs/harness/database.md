# 数据库映射

## 共享 Harness 表

| 表 | 作用 | 关键不变量 |
| --- | --- | --- |
| `harness_operation_bindings` | 领域 operation 到 workflow/stage 的不可变身份绑定 | domain kind/id 唯一；禁止更新和删除；Tavern retry 可带 parent binding |
| `harness_workflow_operations` | 没有独立领域 admission 表的 Document 子阶段、OCR、Study Unit、Persona、Scene、frontend decode operation | running/completed/failed；仍必须绑定真实 Harness operation |
| `harness_runtime_executions` | stage + trace slot 的 lease、claim、attempt、check、terminal trace | operation/stage/slot 唯一；最多 3 claims；terminal 后不可再 claim |
| `harness_artifact_principals` / `contracts` / `artifacts` | 本地 installation principal、允许的 artifact contract、原始 payload 与 digest | digest 是完整性证据，不是授权；retention 可删除 payload 但保留 tombstone 信息 |
| `harness_artifact_grants` / `grant_scopes` / `access_audits` | operation-scoped 精确授权和每次解析审计 | principal、operation、artifact、contract、permission 必须同时匹配 |
| `harness_effect_batches` / `harness_effect_journal` | typed durable effects | 每 operation 一个 batch、最多 128 slots；每 effect 最多 3 claims；terminal 为 committed/not_committed/uncertain |

SQLite 由 `services/ai/app/persistence/database.py` 安装不可变与外键触发器；PostgreSQL 对应规则由 Alembic migration 维护。SQLAlchemy 映射统一在 `services/ai/app/persistence/models.py`。

## 工作流到领域表

| 工作流 | admission / 主表 | Harness 绑定与提交语义 |
| --- | --- | --- |
| Document process | `document_process_operations`、`documents`、`document_debug_records` | admission 与 binding 同事务；Document + debug projection + receipt + terminal trace 原子提交 |
| OCR / Study Unit cleanup | `harness_workflow_operations`，结果进入 Document/debug projection | 子阶段 evidence 不能冒充整个 Document commit |
| Planning generation | `learning_plan_operations`、`learning_plans`、`planning_traces` | operation 记录 committed/not_committed/interrupted/uncertain；Plan projection 原子 finalize |
| Plan revision | `plan_revision_operations`、`learning_plan_revisions`、`learning_plans` | preview/acceptance 使用不同 trace slot；acceptance 事务执行 Plan CAS、history、receipt、terminal evidence |
| Persona generation | `harness_workflow_operations`；用户保存后写 `personas` / `persona_cards` | generation 只提交候选 projection；不得把候选误称为已保存 Persona |
| Scene generation | `harness_workflow_operations`；用户保存后写 `scene_setup_states`、`scene_library_entries`、`reusable_scene_nodes` | generation 与 user-authored CAS save 分离 |
| Study Chat | `study_chat_operations`、`study_sessions`、`harness_effect_*` | Session/Turn、DB effects、receipt、terminal trace 同事务；Scene/file/provider effect 保留各自 read-back/compensation 边界 |
| Tavern | `tavern_runs`、`tavern_run_steps`、`tavern_messages`，并关联 rooms/participants | 一个 actor step 对一个 Message projection；Message/Run/Step/Participant/read-anchor read-back 必须来自同一数据库快照 |

Study Session revision 和 Turn sequence 是应用拥有的 CAS 状态，不进入 model proposal。Tavern message sequence 是 room-scoped 单调值，一条 commit evidence 只能证明一个 sequence point，不能证明范围。

## 恢复状态

- `not_committed`：已证明主输出未提交，可安全按工作流规则重试。
- `committed`：authoritative read-back 与登记的 projection digest 一致。
- `uncertain`：外部 provider/effect 缺少 idempotency 或 read-back，不能猜测成功，也不能自动重复造成副作用。
- `compensated` 是 effect evidence，不等于主领域 projection 已 rollback。

Legacy v1/v2 trace 和旧 JSON 聚合只读兼容。新 Study Session 写入不得返回 `save_list("sessions", ...)`；Persona/Scene 当前仍经过兼容 store，但 generation admission 已是数据库中的 Harness operation。

