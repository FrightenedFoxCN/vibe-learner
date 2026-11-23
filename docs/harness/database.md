# 数据库映射

SQLAlchemy 模型统一定义在 `services/ai/app/persistence/models.py`。SQLite 由 `services/ai/app/persistence/database.py` 安装不可变与外键触发器；PostgreSQL 由 Alembic 迁移维护等价约束（含 JSONB 不可变触发器比较）。

## 共享 Harness 表

| 表名 | 职责 | 核心不变量 |
| --- | --- | --- |
| `harness_operation_bindings` | 领域操作到 `workflow:stage` 的不可变身份绑定 | `(domain_kind, domain_id)` 唯一；禁止更新和删除；Tavern 子重试携带 `parent_binding` |
| `harness_workflow_operations` | Document 子阶段、OCR、Study Unit、Persona、Scene、Frontend Decode 等操作准入表 | 状态为 `running` / `completed` / `failed`；必须绑定真实 Harness 操作 |
| `harness_runtime_executions` | `(operation, stage, trace_slot)` 的租约、认领计数、attempt、check 与终态 Trace | 三元组唯一；每执行最多 3 次认领；终态后禁止再认领 |
| `harness_artifact_principals` / `contracts` / `artifacts` | 本地安装主体、允许的制品契约、受保护载荷与 SHA-256 摘要 | 摘要只证完整性，不代替授权；留存清理可移除载荷并保留墓碑元信息 |
| `harness_artifact_grants` / `grant_scopes` / `access_audits` | Operation 级精确授权与访问审计日志 | `principal`、`operation`、`artifact`、`contract`、`permission` 全部匹配方可读 |
| `harness_effect_batches` / `harness_effect_journal` | 强类型持久效果批次与日志 | 每操作最多 1 个 batch、128 个 slot；每效果最多 3 次认领；终态为 `committed` / `not_committed` / `uncertain` |

历史 v3 上下文通过精确登记的兼容 profile 支持只读解析；所有新执行与非终态认领均要求当前 Manifest。

## 工作流到领域表映射

| 工作流 | 准入表与业务主表 | 绑定与提交语义 |
| --- | --- | --- |
| Document 解析 | `document_process_operations`、`documents`、`document_debug_records`、`document_checkpoints`、`document_checkpoint_resumes` | 准入与绑定同事务；Document + Debug 投影 + 回执 + 终态 Trace 原子提交 |
| OCR / Study Unit 清洗 | `harness_workflow_operations` | 子阶段证据仅证明对应阶段，不代表整个 Document 提交 |
| Learning Plan 生成 | `learning_plan_operations`、`learning_plans`、`planning_traces` | 单事务原子提交 Plan、关联 Document/Debug 投影、Trace 与操作回执 |
| Plan 修订 | `plan_revision_operations`、`learning_plan_revisions`、`learning_plans` | 预览（slot 0）与确认（slot 1）分槽；确认事务执行 Plan CAS、历史归档与回执提交 |
| Study Unit 修订 | `study_unit_revision_operations`、`documents`、`document_debug_records` | 独立准入绑定；确认事务执行 Document revision CAS、Debug 更新与回执提交 |
| Persona 生成 | `harness_workflow_operations`（保存写 `personas` / `persona_cards`） | 生成仅提交候选投影，用户保存属于独立写边界 |
| Scene 生成 | `harness_workflow_operations`（保存写 `scene_setup_states` / `scene_library_entries` / `reusable_scene_nodes`） | 生成提案与用户 CAS 保存严格分离 |
| Study Chat | `study_chat_operations`、`study_sessions`、`study_question_attempts`、`harness_effect_*` | Session/Turn、数据库效果、回执与终态 Trace 同事务；Scene/文件/外部 Provider 各自保留读回与补偿边界 |
| Tavern | `tavern_rooms`、`tavern_participants`、`tavern_messages`、`tavern_runs`、`tavern_run_steps` | 单 actor step 对应单条消息投影；Message/Run/Step/Participant/reply-anchor 读回来自同一数据库快照 |

## 终态与恢复语义

- **`not_committed`**：已证明主输出未提交，可按对应工作流规则安全重试。
- **`committed`**：权威读回与已登记的投影摘要一致。
- **`uncertain`**：外部 Provider 或副作用缺少幂等键/读回证据，不得猜测成功，也不得自动重放。
- **`compensated`**：仅表示某项副作用已补偿，不等同于主领域投影回滚。

历史 v1/v2 Trace 与旧 JSON 聚合仅做只读兼容；新业务写入均以数据库 Repository 为权威。
