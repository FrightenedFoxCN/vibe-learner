# Planning Harness

## 操作边界

- **计划生成**：`POST /learning-plans`（或 `/stream`）先准入 `learning_plan_generation`，执行 `planning:plan_generation` 与工具阶段 `planning:planning_tool_execution`。
- **计划修订**：使用独立的 `learning_plan_revision` 操作与 `planning:plan_revision` 阶段，不复用生成操作身份。
- **教材单元修订确认**：当模型通过 `revise_study_units` 提出重划建议时，系统在生成事务中原子保存保守计划、不可变预览与独立的 `study_unit_revision` 准入绑定；用户确认时在 `planning:study_unit_revision` 阶段执行 Document revision CAS 提交。

## 数据所有权与约束

- **受保护输入**：Document Debug、Study Unit 输入、Planning Context、Persona/Scene 快照。
- **模型提案**：严格解码为 `LearningPlanProposalV3`，不包含应用 ID、revision、时间戳或完成状态。
- **物理页范围与输出语言**：显式 PDF 物理页范围与输出语言偏好共同存入 `PlanningIntentV1`、操作指纹与计划读回；自动语言保持 `unknown` 意图并将模型选择写入独立 resolved projection。PDF 元数据印刷页码通过只读接口独立对照，不进入模型页码参数或提交范围。
- **工具清单**：全部 6 个 Planning 工具的 Schema、配额、适配器与脱敏 Trace 均来自 Tool Manifest。

## 生成与有界恢复

1. Runner 以 `max_tokens = 8192`、最多 24 rounds 运行；工具仅在最多 1 个 round 中开放且 `parallel_tool_calls = false`。
2. 未开放工具调用最多纠正 1 次；tool probe 最多 3 次；`content_filter` 最多重试 2 次；空响应最多重试 1 次。
3. Primary 出现空响应或工具轮次耗尽时，可切换 1 次配置的 fallback 模型（可配置关闭 fallback 工具）。
4. 最终提案先严格解码并允许 1 次本地 JSON 修复，仍不合法则发起 1 次无工具的 strict contract repair runner。
5. 章节引用、物理页范围、覆盖模式/工作量理由与意图约束全部通过领域校验后原子提交；失败记为 `not_committed`。

详细业务流、Prompt 契约、计划修订与单元确认见 [学习计划链路与契约](../learning-plan.md) 与 [教材解析与入库链路](../document-pipeline.md)；预算与调用上限见 [配置与预算](configuration.md)。
