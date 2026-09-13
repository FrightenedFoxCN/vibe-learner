# Planning Harness

`GET /documents/{id}/planning-context` 准备清洗后的 Study Units；`POST /learning-plans` 或 stream 入口先 admission `learning_plan_generation`，再进入 `planning:plan_generation`。Plan revision 使用独立的 `learning_plan_revision` operation 和 `planning:plan_revision`，不复用 generation identity。

## 数据和所有权

- protected input：Document debug、Study Unit input、planning context、Persona/Scene snapshot。
- model proposal：`LearningPlanProposalV2/V3`；不得产生 committed ID、revision、timestamp 或完成度。
- committed projection：`LearningPlanCommittedProjection`，由 repository 在同一事务写 Plan、operation receipt 和 terminal trace。
- tools：6 个 Planning 工具，schema、预算、runtime adapter 和 trace projection 全部来自 Tool Manifest。

## 生成与恢复

1. runner 以 `max_tokens=8192`、最多 24 rounds 运行；工具仅在最多 1 个 round 提供，且 `parallel_tool_calls=false`。
2. 对未提供工具的调用最多纠正 1 次；tool probe 最多 3 次；content filter 最多重试 2 次；空响应最多重试 1 次。
3. primary 空响应或 tool-loop exhausted 可切换一次 configured fallback model；可按配置关闭 fallback tools。
4. 最终 proposal 先严格解码，再允许一次本地 JSON repair；仍不合法才发起一次 tools-disabled strict contract repair runner。
5. chapter refs、页范围、coverage/workload 和 planning intent 再做领域校验；失败为 not committed，不把部分 proposal 写成 Plan。

工具造成的 Study Unit revision/question state 是 parent-operation 作用域；纯读工具不产生 durable effect。页范围错误只允许附带应用拥有的 recovery metadata，provider trace/public projection 不泄露该 metadata。

调用和 token 预算见 [配置与预算](configuration.md)，Plan CAS 细节见 [Plan revision](../plan-revision.md)。

