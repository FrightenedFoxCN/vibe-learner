# Study Chat Harness

`POST /study-sessions/{id}/chat` 先创建 durable `study_chat_operations` admission 和 Harness binding，再解析 operation-scoped protected snapshot。服务端只进行一次上层 pedagogy orchestration；该调用内部可执行 bounded provider/tool rounds。

## 输入、输出与 effects

- protected snapshot 包含原始 learner message、Session、Document/Planning/Scene context 和 attachment metadata；artifact resolver 授权后才能读取。
- model proposal 是完整的 `StudyChatReplyProposalV1`：reply、citations、character events、interactive question proposal 和 tool results 必须一次严格解码。
- application projection 分配 Turn identity/sequence，隐藏 grading spec，并生成 typed DB/Scene/file/provider effects。
- Session/Turn、DB effects、operation receipt 和 terminal v3 trace 原子提交。Scene mutation、attachment staging 和外部 provider effect 分别要求 read-back、compensation 或 `uncertain`。

## 工具和恢复

31 个 Study tools 由 Tool Manifest 提供。每个 tool call 先严格解码 canonical arguments，再按 per-round/per-operation budget admission；provider tool-call ID 只作 transport correlation。模型最多运行 `max(tool_max_rounds + 12, tool_max_rounds * 3)` rounds，默认 16；exempt 只读/收尾工具不消耗 limited round，但仍受总 round 和 Tool Manifest 限制。

最终输出 invalid payload 或 content filter 时，只允许一次 tools-disabled、低温、`max(chat_max_tokens, 1600)` 的完整结构恢复。恢复仍失败则 operation 记为 not committed；上游请求已经发出但无法证明副作用状态时必须保留 uncertain。客户端遇到模糊网络结果只查询 operation read-back，不盲目重发。

Study commit policy 是 `primary_output_only`：证明 Session/Turn projection，不声称所有 Scene、文件或 provider effect 都成功。交互题必须等待持久化 Session read-back 后显示，浏览器永远不接收未作答 grading spec。

