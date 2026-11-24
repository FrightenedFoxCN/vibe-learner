# Study Chat Harness

`POST /study-sessions/{id}/chat` 与 `/chat-with-attachments` 先持久准入 `study_chat_operations` 与 Harness 绑定，再解析 operation-scoped 受保护快照，随后由 `StudyChatApplication` 执行单次教学编排与有界工具循环。

## 输入、输出与强类型效果

- **受保护快照**：包含原始学习者消息、Session、Document/Planning/Scene 上下文、输出语言偏好与附件清单，经制品解析器授权后读取。
- **模型提案**：单次严格解码完整 `StudyChatReplyProposalV1`（正文、引用、Character Events、交互题提案与工具结果）。
- **应用投影与提交**：应用分配 Turn ID 与连续序号，隔离服务端私有交互题评分规格，并汇集强类型 DB/Scene/文件/外部 Provider 效果。
- **原子边界**：Session/Turn、数据库效果、操作回执与终态 v3 Trace 在同一事务提交；Scene 变更附加行级 CAS 与快照读回；附件采用操作自有暂存与摘要校验；外部图片生成与上游模型调用无幂等读回能力，模糊结果保留 `uncertain`。
- **Commit Policy**：`primary_output_only`，仅证明 Session/Turn 主输出，不声称所有外部副作用均成功。

## 33 个 Study 工具与分发结构

全部 33 个 Study 工具以 Tool Manifest 为唯一注册目录（Schema、预算、适配器与脱敏 Trace）。单个对话最多运行 `max(tool_max_rounds + 12, tool_max_rounds * 3)` 个生成 round（默认 16）；只读/收尾豁免工具不消耗受限轮次，但仍受总轮次与 Tool Manifest 上限约束。

其中 21 个 Session 领域工具由 `StudySessionChatToolRuntime` 统一适配，实际处理器位于 `services/ai/app/services/study_tools/`：

| 模块 | 职责 |
| --- | --- |
| `memory.py`、`affinity.py`、`follow_up.py` | 临时记忆、好感、系统时间与自动续接提案 |
| `note_search.py` | 只读搜索本次操作已准入会话内的笔记 |
| `projection_read.py` | PDF 文本、页面图片与版面图形候选读取 |
| `projection_write.py` | 附件投射、焦点定位、标注与覆盖层提案 |
| `image_generation.py` | 外部图片生成及其操作/槽位关联 |
| `plan_confirmation.py` | 计划标题与进度的待确认提案 |
| `context.py` | 共享服务上下文、附件解析、引用去重与同操作 effect collector |

所有处理器共享同一个 `StudyToolContext`：本轮已准备（`effect_state=prepared`）的变更可被同轮后续读取叠加看到（read-your-writes），但在最终事务提交前绝不改变持久化状态。

### Study Notes 读取边界

学习者回合可调用只读工具 `search_study_notes`；查询最多 120 字符，每次最多 5 条，每个聊天操作最多 2 次。范围由已准入会话 ID 决定，不接受模型指定会话；笔记不会自动加入对话上下文。工具只返回 ID、版本、标题和有界正文片段，并标注为不受信任的内容。普通诊断 Trace 不记录查询或正文片段。

服务端从本次成功读取中提取去重后的笔记 ID、版本和标题，最多 10 条，随聊天回合持久化。该字段不是模型提案，由提交投影和读回校验绑定。它表示「检索到的笔记」，不声称具体句子已获笔记支持。没有命中时省略字段，保持历史回合兼容。

## 恢复与输出语言

- 最终回复遇到 invalid payload 或 content filter 时，允许 1 次无工具、低温、`max(chat_max_tokens, 1600)` 的完整结构恢复；仍失败则记为 `not_committed`。已发出上游请求但无法证实副作用时保留 `uncertain`。
- 显式 `output_language` 进入 `study-chat-request-v3` 规范指纹并在成功提交 Turn 时与 Session 一并 CAS 持久化，不进入模型提案 schema。
- 浏览器恢复协议（60 秒等待上限、15 秒查询上限、6 次退避查询与 `uncertain` 不重放规则）详见 [学习会话与对话恢复](../study-session.md)。
