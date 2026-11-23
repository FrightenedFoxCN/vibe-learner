# 学习计划链路与契约

本文覆盖学习计划的上下文组装、模型工具循环、Prompt 与文本字段契约、物理页范围、修订回滚与生成可观测性。Harness 边界见 [Planning Harness](harness/planning.md)。

## 1. Planning Context 与生成链路

### 上下文组装（`GET /documents/{id}/planning-context`）

由 `build_learning_plan_context()`（`services/ai/app/services/plan_prompt.py`）从已解析的 Document 与 Debug 报告生成：

| 字段 | 来源与用途 |
| --- | --- |
| `course_outline` | 原始 `debug_report.sections` 的一/二级目录，用于全局 Debug 对比与引用锚定 |
| `study_units` | 清洗后的 `StudyUnitRecord[]`，附加 `subsection_titles`、`related_section_ids` 与 `detail_tool_target_id`，作为模型可见规划骨架 |
| `detail_map` | 按 `study_unit_id` 索引的章节详情与 chunk 摘录，作为规划工具的本地数据源 |
| `available_tools` | 结合运行时模型工具配置与文档上下文过滤后的可用工具列表 |
| `document_revision` | 与 Debug 在单条 SQL 内一致读取的当前文档修订号 |

### 生成执行（`POST /learning-plans` / `/learning-plans/stream`）

1. **操作准入**：请求携带稳定 `client_request_id`，绑定教材时同时携带 `expected_document_updated_at` 水印，准入 `learning_plan_operations`（同文档不允许并发活动操作，同键不同载荷返回 `409`）。
2. **启发式基线**：`StudyArrangementService.build_plan()` 先生成确定性基础计划（含 `schedule[]` 与嵌套 `schedule_chapters[]`）。
3. **模型细化**：启用真实 Provider 时，`OpenAIPlanRunner` 以 `max_tokens=8192`、最多 24 rounds 运行，可串行调用 6 个注册工具收集证据并输出严格 JSON 提案 `LearningPlanProposalV3`（`extra="forbid"`）。
4. **领域对账**：应用分配所有 committed plan / schedule / chapter ID，严格校验 `unit_index`、物理页范围、章节锚点/切片顺序与来源 Section 引用，非法或重复引用直接 fail-closed。
5. **单事务原子提交**：同事务提交 `LearningPlanRecord`、关联 Document/Debug 投影、`PlanGenerationTraceRecord`、可选 Study Unit 修订预览与终态操作回执。

### 6 个后端规划工具

全部定义在 Tool Manifest 中，统一解码 `planning-tool-arguments-v1` 并投影为 `planning-tool-result-v1`（单操作每工具上限 4 次，串行执行）：

| 工具名 | 作用与约束 |
| --- | --- |
| `get_study_unit_detail` | 读取 `detail_map` 详情摘录（按修订后单元页范围限定，无本地证据返回空）；每轮最多 3 次 |
| `read_page_range_content` | 从 `debug_report.chunks` 读取物理页文本，严格计入字符预算与分隔符；每轮最多 3 次 |
| `read_page_range_images` | 仅在开启多模态且存在 PDF 时渲染指定物理页图像，整轮工具回执完成后统一附加 |
| `ask_planning_question` | 向学习者提出规划澄清问题（由父操作记录保存） |
| `estimate_plan_completion` | 产品名称“**学习单元结构估分**”；仅评估源页跨度、子标题数与覆盖元数据，不读取计划活动，不认证目标完成度或事实质量 |
| `revise_study_units` | 提出待确认的完整教材单元替换建议，不修改当前工具上下文与已保存教材 |

## 2. Prompt 契约与 `source-minimal-v3` 策略

- **模板与组装**：`services/ai/app/prompts/learning_plan_prompt.txt`（INI 分节 `[system]` 与 `[user_instructions]`）+ `services/ai/app/services/plan_prompt.py`。
- **注入 Schema**：`PLAN_JSON_SCHEMA` 对应 `learning-plan-proposal-v3`，要求每个 `schedule[]` 包含 `unit_index`、`title`、`focus`、`activity_type`（`learn` / `review`）、`duration_minutes`、`coverage_mode`（`complete` / `selective` / `overview`）、`workload_rationale` 与非空嵌套 `schedule_chapters[]`。
- **意图来源隔离**：用户未指定的规划参数在原始 `PlanningIntentV1` 中保持 `unknown`，只有 `user_explicit` 构成硬约束；模型推断的 `duration_minutes` 与 `output_language` 写入独立的 resolved projection（`model_inferred`）。
- **覆盖模式与时长基线**：常规 `learn` 课次按每独立物理页 ≥ 3 分钟、`review` 课次按 ≥ 1 分钟估算；超出保守基线时须声明 `selective` 或 `overview`，并在 `workload_rationale` 中写明教学取舍理由、压缩/省略内容与后续补回路径。
- **`source-minimal-v3` 文本策略**（登记为 `LearningPlanPrompt@planning-prompt-v8`）：
  1. 对 `focus`、`today_tasks` 与学习活动做忠于原文的最小必要改写，不截断会改变指称对象的限定修饰；
  2. 保留原文的认识与流程状态（如计划中、提议、已记录、观察到），不夸大为既成事实；
  3. 严格区分学习安排时长与原文事件真实持续时间；
  4. 不虚构原文或系统中不存在的审批、提交或流程机制。

## 3. 面向学习者的文本字段契约

跨后端模型、共享 TS 契约与前端展示的字段语义必须保持一致：

| 后端字段 | 前端字段 | 唯一语义与 UI 角色 | 禁止混用 |
| --- | --- | --- | --- |
| `course_title` | `courseTitle` | 贴合教材的计划主标题（`Plan Overview Panel` 主标题） | 不用学习目标或单条排期替代 |
| `objective` | `objective` | 学习者输入的学习目标（主标题下方的辅助目标文本） | 不被模型覆盖为概述或任务 |
| `overview` | `overview` | 1–2 句整轮计划摘要（摘要段落） | 不作标题或任务列表 |
| `today_tasks[]` | `todayTasks` | 当前可执行的行动清单（祈使/动作导向，纵向列表） | 不放章节目录 |
| `schedule[].title` | `schedule[].title` | 一级可执行学习块标题（`/plan` 与 `/study` 一级导航） | 不放原始 Section 标签 |
| `schedule[].focus` | `schedule[].focus` | 单条排期的精炼执行重点（排期标题下提示） | 不替代 `today_tasks` |
| `schedule[].schedule_chapters[].title` | `schedule[].scheduleChapters[].title` | 嵌套在排期下的具体章节/子节标签（二级导航与页码锚点） | 不作独立 Session 作用域 |
| `study_unit_progress[].objective_fragment` | `studyUnitProgress[].objectiveFragment` | 按 `study_unit.id` 聚合的派生进度摘要 | 非手写排期文本 |

## 4. 物理页范围与输出语言约束

- **物理 PDF 页范围**：Document Setup 支持输入如 `100–103, 110` 的 1-based 物理页范围（最多 64 个不重叠升序区间；拒绝 0、逆序、重叠与罗马数字；纯目标模式忽略此约束）。解析后前后端分别针对实际物理页数复检，区间进入 `PlanningIntentV1` 与操作指纹。所有规划工具、提案校验、原子提交与前端解码均强制锚点和切片落入请求区间并覆盖全部所选页。
- **输出语言**：支持 `auto`（优先级：学习目标语言 → 教材主语言 → Persona 语言，界面语言不作为信号）或显式 BCP-47 标签（≤ 35 ASCII 字符）。显式语言作为硬约束进入操作指纹与计划读回；原文引述、专有名词、公式与符号保持原文不翻译。

## 5. 计划修订、回滚与并发控制

`LearningPlanRepository` 拥有全部计划写操作（标题、进度、规划问题作答、Study 确认生效、单元改名同步与删除墓碑），全部执行行级 `revision` CAS 并在同事务归档前后快照至 `learning_plan_revisions`。回答规划问题仅保存答案，不自动改写计划。

**显式修订与回滚流程**：

1. **发起预览**：`POST /learning-plans/{plan_id}/revisions` 提交新 `client_request_id`、当前 `base_revision` 与修订指令（或 `rollback_revision`）。支持修订 `course_title`、`overview`、`today_tasks` 以及既有排期项的标题、重点与顺序；保持既有排期目标集、ID、引用、进度与 Study Session 关联不变。
2. **准入与生成**：同事务准入 `plan_revision_operations` 与 `learning_plan_revision` Harness 绑定，调用单次模型产出严格 `PlanRevisionProposalV1` 并持久化预览回执（trace slot 0），不改动当前 Plan。
3. **决策提交**：`POST /learning-plans/{plan_id}/revisions/{request_id}/decision` 接受 `accept` 或 `reject`。确认时在同一操作的 trace slot 1 上原子执行 Plan CAS、历史归档、确认回执与终态 v3 Trace；若 Plan 已变更或删除则返回冲突。回滚复用相同预览/确认流程，生成新修订号并保留当前进度。
4. **查询恢复**：`GET /learning-plans/{plan_id}/revisions/{request_id}` 仅做只读查询，永不重放模型调用；处于 `generating`/`applying` 超过 240 秒的操作在查询时围栏终结。前端在发起 POST 前持久化请求 ID，刷新或返回页面自动查询恢复。

## 6. 生成可观测性与错误边界

- 单次 Planning 操作通过 `operation_id` 关联全部 provider rounds、工具调用、schema 修复、Token 用量、耗时、`finish_reason`、终态与已提交投影。`/model-usage` 支持按工作流、操作与日期筛选并导出 CSV（用量来自供应商回报，实际计费以供应商账单为准）。
- `Plan Workspace` 将文档解析/OCR 与计划生成拆分为两个独立进度块：解析块仅展示服务端事件已证实的页数、阶段、速率与预计剩余时间，解析失败保留已完成范围与操作建议，不覆盖为泛化计划错误。
- 结构化生成触及输出上限时统一映射为 `setting_model_output_truncated`，HTTP detail 携带稳定错误码供前端提示行动建议；UI 只展示安全摘要与计数，不泄露完整 reasoning 或受保护上下文。
