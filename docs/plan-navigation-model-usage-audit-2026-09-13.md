# Planning 生命周期与 Model Usage 审计

日期：2026-09-13

## 已完成

### UX-MODEL-USAGE-001

- provider usage record 现在保留 `operation_id`、`workflow` 和 `stage`；存在 Harness 上下文时使用服务端正式 identity，没有 Harness 上下文时按 feature 使用明确的 `settings`、`embedding` 等 fallback workflow。
- `/model-usage` 提供显示时区、workflow、operation、起止日期筛选，结果按 50 条分页，并可导出当前筛选结果 CSV。
- 页面明确显示当前时区、Token 统计口径和供应商账单边界；未配置价格时不伪造金额。

### PLAN-NAVIGATION-LIFECYCLE-001

- Planning 生成期间所有统一应用导航会先确认；确认文案说明离页会中断任务，已发生 Token/费用不会撤销，实际金额以供应商账单为准。
- 浏览器刷新、关闭和离开页面由 `beforeunload` 提供保护；任务期间写入短生命周期活动标记，正常结束后清除。
- 生成状态继续由现有 Planning stream/debug 状态承载；本次选择的是票据允许的“离页前明确提示将取消”实现，而不是把模型请求迁移成跨页面后台任务。

## PLAN-PAGE-BOUNDS-001 审计结论：未完成

当前已有服务端基础：

- `PlanningIntentV1.pdf_page_ranges` 能表达用户显式的物理 PDF 页范围。
- `read_page_range_content` 与 `read_page_range_images` 会拒绝显式范围外的请求。
- proposal 校验和计划提交前的 `validate_schedule_against_intent` 会检查 schedule chapter anchor、content slice 以及显式范围完整覆盖。
- `resolved_planning_intent` 会保留显式页范围来源。

仍缺少的闭环：

1. Planning UI 没有让用户输入或编辑 PDF 物理页范围，也没有将该输入稳定地写入 `LearningGoal`。
2. 物理页与印刷页仍共享普通 `page_start/page_end` 整数，缺少明确的 page coordinate/numbering provenance。
3. 没有独立端到端验收证明用户指定 100–103 后，工具参数、schedule anchor、content slices、proposal 和 commit 全部受同一范围约束，并拒绝把印刷页 70–73 当作物理页成功提交。

因此不能将该票据标记为完成。下一步应先定义物理页/印刷页坐标契约，再补 UI 输入、请求 fingerprint、工具上下文、proposal/commit DTO 和独立 adversarial acceptance。

