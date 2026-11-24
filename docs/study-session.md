# 学习会话与对话恢复

本文定义学习章节与排期的规范术语、Study Session 作用域、教学对话与交互题边界、输出语言策略以及浏览器恢复协议。Harness 执行细节见 [Study Chat Harness](harness/study-chat.md)。

## 1. 章节与排期核心术语

系统由**唯一内容骨架**（`Study Unit`）、**唯一执行骨架**（`Schedule Item`）与**嵌套目录层**（`Schedule Chapter`）构成：

| 规范中文 | 规范英文 | 字段位置 | 稳定 ID | 页范围 | 核心职责 |
| --- | --- | --- | :---: | :---: | --- |
| 原始章节 | Raw Section | `DocumentDebugRecord.sections[]` | 有 | 有 | 解析调试、文本取证、引用与规划工具 |
| 学习单元 | Study Unit | `DocumentRecord.study_units[]` | 有 | 有 | 规划骨架、**唯一 Session 作用域**、进度聚合键 |
| 学习排期项 | Schedule Item | `LearningPlanRecord.schedule[]` | 有 | 经 `unit_id` 关联 | 可执行学习块、状态跟踪、一级导航 |
| 学习章节 | Schedule Chapter | `schedule[].schedule_chapters[]` | 有 | 有 | 排期下的二级导航、页码锚点与预览定位 |
| 学习单元进度 | Study Unit Progress | `LearningPlanRecord.study_unit_progress[]` | — | — | 按 `study_unit.id` 聚合的派生进度视图 |
| 会话作用域 | Session Scope | `StudySessionRecord.study_unit_id` | — | 经学习单元关联 | 对话路由、记忆检索与会话归属 |

### 关键运行时边界

- **Session 作用域唯一性**：`StudySession.study_unit_id` 始终指向父排期项绑定的 `study_unit.id`，绝不指向 `schedule_chapter.id`。在 `/study` 切换嵌套 `Schedule Chapter` 只改变本地预览定位与页锚，切换父 `Schedule Item` 才切换或创建对应作用域的 Session。
- **`DocumentRecord.sections` 含义**：解析完成后，`DocumentRecord.sections` 是由可规划 Study Units 投影出的精简列表；原始解析章节树始终保存在 `DocumentDebugRecord.sections` 中。
- **`section_id` 与 `study_unit_id` 分工**：原始 `section_id` 仅用于解析章节、切块与教材引用；会话、记忆与进度一律使用 `study_unit_id`。

## 2. Study Chat、交互题与笔记

### 持久化准入与并发

- `StudySessionRepository` 以单行 `revision` CAS 管理并发写入，所有已提交 Turn 拥有服务端分配的 ID 与连续序号（`last_turn_sequence`），除交互题作答字段外前缀不可变。
- `POST /study-sessions/{id}/chat` 与 `/chat-with-attachments`（附件上限：≤ 4 个文件、单文件 ≤ 12 MiB、单次请求 ≤ 24 MiB）均要求稳定 `client_request_id` 与 `expected_session_revision`。
- 请求在调用模型或写入附件前先持久化至 `study_chat_operations`（含规范请求指纹与附件 SHA-256 清单）；回执状态机为 `admitted` → `running` → `committed` | `not_committed` | `uncertain`。
- `provider_started_at` 在进入模型调用前落盘；由于外部 Provider 缺乏幂等读回能力，此后的模糊传输结果保持 `uncertain`，不可自动重放。

### 交互题服务端隔离与判分

交互题严格分离五个对象：**模型提案**、**服务端私有评分规格**、**公开题面投影**、**已提交判分结果**与 **Turn 绑定作答输入**：

- 未作答的公开 Session DTO 仅暴露题干、选项与回调标记；答案、可接受答案集、归一化规则与解析仅存于服务端私有记录。
- `POST /study-sessions/{id}/attempt` 仅接收 `turn_id`、`expected_session_revision`、`client_attempt_id` 与 `submitted_answer`，使用 `unicode-nfkc-casefold-whitespace-v1` 判分并在同一事务内提交结果与 `study_question_attempts` 回执（同键同规范输入幂等读回，异输入或跨 Session/过期 revision 失败关闭）。
- 浏览器不展示本地预判结论：提交后必须读回持久化 Session，核验精确的 attempt/Session/Turn/revision/result 投影后才显示结果并据此触发自动续接。并发回答不同 Turn 时，过期低版本读回会被围栏拒绝。

### 用户笔记

Study Notes 以当前 Session ID 为边界，独立持久化、独立版本控制；写笔记不修改会话记忆或聊天回合，不需要模型。请在侧栏「笔记」中直接保存原文。已有会话记忆仍可按 key 复制为笔记，不会自动迁移或删除。接口与导入导出规则见 [Study Notes API 契约](api-contracts.md#study-notes)。

侧栏支持 Markdown 源码与预览；「打开 Markdown 编辑器」可使用宽幅分栏实时预览、格式工具栏和 `⌘/Ctrl+S` 保存，`Esc` 返回侧栏并保留同一草稿。「下载 .md」导出当前正文源码，不保存草稿；JSON 仍用于笔记归档。正文上限仍为 4,000 字符。预览支持表格、任务列表、代码块及 LaTeX，不执行原始 HTML，也不自动读取嵌入图片。

## 3. 输出语言策略

- **继承与覆盖**：新建 Study Session 默认继承关联 Learning Plan 的显式或模型解析语言；Study Dialog 的语言选择器可在下一条消息覆盖（提交 `output_language` 字段；省略保持当前偏好；显式传 `auto` 重置为自动模式）。
- **原子持久化**：显式语言进入 `study-chat-request-v3` 请求指纹，并在成功提交 Turn 时随 Session CAS 原子保存；失败或 `uncertain` 不提前改写已提交语言偏好。
- **自动优先级**：Study 处于 `auto` 且无已解析计划语言时，按“当前目标/消息 → 教材 → Persona”顺序选择指导语；引用的教材原文、公式与专有名词保持原样不翻译。
- **离线 Mock 覆盖**：本地 `mock` Provider 为中文（简/繁）、英、法、德、西、日、韩、葡、意、俄、阿提供确定性模板（地区标签回退至基础语言）；不支持的自定义标签在 mock 下返回可恢复拒绝，真实模型直接接收语言策略。

## 4. 浏览器操作恢复协议

前端严格遵循后端准入与幂等语义，不靠盲目重发解决模糊网络状态。

### 等待与轮询上限

| 动作 | 本地等待上限 | 恢复策略 |
| --- | ---: | --- |
| 发送 Study Chat POST（含响应解码） | 60 秒 | 超时仅中止本地传输并切入纯查询恢复，不证明服务端取消或失败 |
| 单次操作 GET 或显式 Session 刷新 | 15 秒 | 超时/网络/解码错误保留原身份并暂停后台读取，不授权重发 |
| `admitted` / `running` 后台恢复查询 | 最多 6 次/次挂载访问 | 退避间隔依次为 2 / 4 / 8 / 15 / 30 / 30 秒（串行不重叠）；耗尽后暂停并保留手动查询入口 |
| `uncertain` 终态 | 不自动轮询 | 永不自动轮询或重发，明确提示等待/刷新无法证明无副作用，仅支持按原身份手动读回 |

- 离线事件会暂停查询并提示结果未确认；恢复在线时对保留身份尝试 1 次合并查询（不重叠）。
- 切换 Session 或卸载控制器会清理定时器并围栏过期响应（不取消服务端执行）。

### 本地恢复元信息与终态处理

浏览器仅在 `localStorage` 存储最小身份元数据（`sessionId`、`clientRequestId`、`expectedRevision`、消息类型与 `studyUnitId`），**绝不存储**学习者正文、附件字节、隐藏前缀或评分数据：

- `vibe-learner:pending-study-chat-operation:v1`：未确认的在途操作身份；
- `vibe-learner:last-not-committed-study-chat:v1`：已确认 `not_committed` 的身份，再次访问时仅查询 1 次以恢复终态说明，不信任本地缓存作为重发许可。

终态动作规则：

- **`committed`**：清除对应待确认身份并渲染持久化 Session（旧回执不可覆盖更新版本的 Session）。
- **`not_committed` 且 `safe_to_retry=true`**：仅在内存中仍保留原草稿时提供使用**新请求 ID** 一键重发；页面刷新后因仅存身份元数据，引导用户核对输入框并重选附件。
- **明确准入前拒绝或精确 `404 study_chat_operation_not_found`**：停止查询并要求先刷新 Session 状态，再以新请求 ID 发送（普通网络/HTTP/解码错误不视为准入前拒绝）。
