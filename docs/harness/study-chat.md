# Study Chat Harness

`POST /study-sessions/{id}/chat` 先创建 durable `study_chat_operations` admission 和 Harness binding，再解析 operation-scoped protected snapshot。服务端只进行一次上层 pedagogy orchestration；该调用内部可执行 bounded provider/tool rounds。

## 输入、输出与 effects

- protected snapshot 包含原始 learner message、Session、Document/Planning/Scene context 和 attachment metadata；artifact resolver 授权后才能读取。
- model proposal 是完整的 `StudyChatReplyProposalV1`：reply、citations、character events、interactive question proposal 和 tool results 必须一次严格解码。
- application projection 分配 Turn identity/sequence，隐藏 grading spec，并生成 typed DB/Scene/file/provider effects。
- Session/Turn、DB effects、operation receipt 和 terminal v3 trace 原子提交。Scene mutation、attachment staging 和外部 provider effect 分别要求 read-back、compensation 或 `uncertain`。

## 工具和恢复

32 个 Study tools 由 Tool Manifest 提供。每个 tool call 先严格解码 canonical arguments，再按 per-round/per-operation budget admission；provider tool-call ID 只作 transport correlation。模型最多运行 `max(tool_max_rounds + 12, tool_max_rounds * 3)` rounds，默认 16；exempt 只读/收尾工具不消耗 limited round，但仍受总 round 和 Tool Manifest 限制。

`StudySessionChatToolRuntime` 是其中 20 个 Session 工具的公共适配入口，保留原工具展示顺序、可用性判断、上下文和引用收集。实际执行分布在 `services/ai/app/services/study_tools/`：

| 模块 | 职责 |
| --- | --- |
| `memory.py`、`affinity.py`、`follow_up.py` | 临时记忆、好感、时间与自动续接提案 |
| `projection_read.py` | PDF 文本、图片与版面候选读取 |
| `projection_write.py` | 附件投影、焦点、标注与覆盖层提案 |
| `image_generation.py` | 外部图片生成及其操作/槽位关联 |
| `plan_confirmation.py` | 计划标题与进度的待确认提案 |
| `context.py` | 共享服务、附件解析、引用去重及同一 operation 的 effect collector |

入口按既有 Manifest 的 canonical name、owner 和 adapter 绑定分派到唯一处理器；处理器不维护第二份工具目录。参数解码、调用预算和结果投影继续由 `provider_study.py` 与既有 Tool Manifest 适配层负责。所有处理器共享同一个 `StudyToolContext`，因此跨领域读取能看到本轮准备的 overlay，而 `prepared` 结果不能冒充已提交状态。最终事务仍由 Session repository 统一提交；拆分不修改模型可见 schema、effect adapter/slot、回滚或 server-only 字段边界。

最终输出 invalid payload 或 content filter 时，只允许一次 tools-disabled、低温、`max(chat_max_tokens, 1600)` 的完整结构恢复。恢复仍失败则 operation 记为 not committed；上游请求已经发出但无法证明副作用状态时必须保留 uncertain。客户端遇到模糊网络结果只查询 operation read-back，不盲目重发。

Study commit policy 是 `primary_output_only`：证明 Session/Turn projection，不声称所有 Scene、文件或 provider effect 都成功。交互题必须等待持久化 Session read-back 后显示，浏览器永远不接收未作答 grading spec。

