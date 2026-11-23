# 教材解析与入库链路

本文说明教材从上传、输入校验、PDF/OCR 解析、Study Unit 清洗、断点续跑到单元修订确认的完整后端与前端边界。对应的 Harness 生命周期见 [Document Harness](harness/document-processing.md)。

## 1. 输入上限与无损分块

契约 `document-input-limits-v1` 由 `services/ai/app/models/document_input_limits.py` 权威定义，前端镜像与共享 golden 夹具（`packages/shared/fixtures/document-input-limits-v1.json`）保持同步；`GET /documents/input-limits` 只读返回当前契约。

| 输入维度 | 上限（含） | 校验位置 |
| --- | ---: | --- |
| 单个上传 PDF 文件 | 64 MiB（67,108,864 字节） | 浏览器选文件校验 + 服务端有界读取（读至上限 +1 字节即止） |
| 完整 multipart 请求体 | 65 MiB（68,157,440 字节） | ASGI 中间件在解析 multipart 前拦截（额外 1 MiB 留给帧与表单头） |
| PDF 物理页数 | 512 页 | 落盘/准入前 PyMuPDF 元数据预检，解析入口二次复检 |
| 单个不可分割文本单元 | 65,536 Python 字符 | 分块器在段落/句子切分后校验 |

- **请求体拦截**：中间件统计实际接收字节（不受缺失或虚报 `Content-Length` 欺骗）；通过的请求体最多在内存缓存 1 MiB，超出后转入临时磁盘并在完成、断连或拒绝时关闭清理。
- **无损分块策略**：1,400 字符仅为分块打包目标，**不静默截断文本**。超过 1,400 且不超过 65,536 字符的不可分割单元完整保留并记录 `oversized_text_unit_preserved` 告警；超过 65,536 字符则在提交前以 `document_text_unit_too_large` 拒绝解析，已完成页断点仍保留为 `checkpoint_only`。
- **超限拒绝**：上传阶段返回 HTTP 413 与 `document-input-error-v1` 结构化 detail（错误码为 `document_upload_too_large`、`document_upload_body_too_large`、`document_page_limit_exceeded` 或 `document_text_unit_too_large`，含 `limit`、`actual` 与 `recovery_action: "split_or_reexport_pdf"`），不创建上传文件或 Document 行。已启动的流式处理通过 `stream_error` 返回可读恢复说明。

## 2. 上传与解析流水线

### 上传入库

- **入口**：`POST /documents` → `DocumentService.create_document()`
- **行为**：通过上限预检后将 PDF 写入 `services/ai/data/uploads/{document_id}.pdf`，经 `DocumentRepository` 单行插入初始记录（`status="uploaded"`、`ocr_status="pending"`、`debug_ready=False`、`revision=0`）。

### 解析与 OCR

- **入口**：`POST /documents/{id}/process` 或 `POST /documents/{id}/process/stream`
- **准入**：同一事务写入 `document_process_operations` 与不可变 Harness 绑定，并将 Document 标记为 `processing`（推进 `revision`）；并发处理同文档返回 `409`。
- **解析步骤**（`services/ai/app/services/document_parser.py`）：
  1. 使用 PyMuPDF 读取 PDF，优先尝试基于目录（TOC）构建原始章节；
  2. 逐页提取文本；当 `force_ocr=True` 或文本密度低于 `TEXT_DENSITY_THRESHOLD` 时调用 OCR 引擎（`ocr_engine.py`）；
  3. 识别并剥离高频重复页眉页脚，从正文与 OCR 文本抽取标题候选；
  4. 构建原始 `sections` 与按章节感知切分的 `chunks`，生成完整 `DocumentDebugRecord`（含 `pages`、`sections`、`chunks`、`warnings`、`ocr_applied`、`extraction_method`）。

### Study Unit 清洗与原子提交

`StudyArrangementService.build_study_units()` 将原始 `sections` 与 `pages` 清洗为面向学习计划的 `StudyUnitRecord[]`：

- 优先以一级章节为锚点，标题薄弱时从页预览或标题候选中恢复；
- 分类为 `chapter`、`front_matter` 或 `back_matter`，设置 `include_in_plan`；
- 按需合并相邻零碎单元，保证至少产出一个可规划单元。

解析与清洗完成后，**单个数据库事务**原子提交：

1. `documents` 行：更新状态、计数、`study_units` 以及由可规划单元投影而成的 `sections`，推进 `revision`；
2. `document_debug_records` 行：保存完整解析产物（含原始 `sections` 与清洗后的 `study_units`）；
3. 投影摘要、终态操作回执与 v3 Trace。

失败或中断时记为 `not_committed` 并仅恢复本操作占用的 processing revision；服务启动恢复会终结意外遗留的 `running` 操作。`documents.json` 与 `document_debug/` 文件镜像仅在数据库提交后尽力写入，不构成提交边界。

## 3. OCR 断点与显式续跑

解析过程将中间成果持久化在操作围栏内，失败或超时不会把未完成文档投影为已处理教材：

- **落盘粒度**：每完成一页抽取/OCR 即在回调与预算检查前落盘；完整解析报告在清洗前落盘；清洗输出在外层 Harness 截止时间检查前落盘。
- **失败不抄近道**：OCR 失败页、强制 OCR 降级报告与空清洗结果不会被复用跳过。
- **容量上限**：单个操作最多保存 8 MiB 暂存内容与 10,000 条原始页记录。若完整报告/清洗结果可容纳但原始页行超出预算，事务会压缩废弃页行；若仍放不下则保留已有前缀并标记 `storage_limited=true`。
- **显式续跑**：用户在 `Document Checkpoint Panel` 选择“从保存进度继续处理”，携带 `resume_from_operation_id` 与相同 `force_ocr` 调用处理接口。服务端校验上传文件 SHA-256、组件契约版本、解析器与 OCR 引擎/模型目录摘要以及精确的 Document revision 后，在同一事务内创建新操作、Harness 绑定与唯一 `source → child` 映射（`document_checkpoint_resumes`）。
  - 每个失败源最多对应 1 个子操作，重复提交只读回该子操作结果或返回 `409`，不重复启动解析；
  - 已完成阶段通过授权快照注入子操作，最终仍走完整严格校验与原子提交；
  - `GET /documents/{id}/checkpoint` 与 `GET /documents/{id}/checkpoints/{operation_id}` 返回 `document-checkpoint-response-v1`（区分 `checkpoint_only` 与 `committed`，最多含 64 条最近页预览与已保存单元），GET 永不触发解析。

## 4. 物理页坐标与印刷页码对照

- 系统内部一切读取、渲染、规划范围与提交校验均以 **1-based PDF 物理页**（`pdf_physical_1_based`）为准。
- `GET /documents/{id}/page-numbering?page_numbers=...` 接受 1–64 个去重物理页码，返回 `document-page-numbering-v1`，为每个物理页附带可选的 `printed_page`（`source="pdf_metadata"`）。
- 印刷页码**仅**来自上传 PDF 显式携带的页码标签元数据，不从 OCR 推断，也不假设固定偏移量；缺失标签返回 `null` 且不影响规划使用。该接口只读，不修改 Document 或 Debug 记录。

## 5. Study Unit 修订确认

规划阶段模型调用 `revise_study_units` 时，提案只作为待确认建议保存，不静默替换当前教材、工具上下文或已生成计划：

- **独立预览与准入**：计划生成事务同步保存保守计划、不可变预览（绑定源 Document revision 与 Debug 摘要）及独立的 `study_unit_revision` Harness 绑定，按 Plan ID 可跨刷新读回。
- **显式决策**：`GET /learning-plans/{plan_id}/study-unit-revision` 读取预览与状态；`POST /learning-plans/{plan_id}/study-unit-revision/{operation_id}/decision` 接受 `accept` 或 `reject`。
- **状态机**：`ready → applying → accepted | conflict | failed` 或 `ready → rejected`。并发决策仅有一方胜出；相同终态重复提交幂等返回，相反决策返回 `409`；中断滞留超过 240 秒的 `applying` 操作在查询时自动围栏终结。
- **提交效果**：确认（`accept`）在 `planning:study_unit_revision` 阶段校验基础 Document/Debug 未漂移后，推进一次 Document revision，同步更新 `documents.sections`、`study_units` 与 Debug 单元（物理页范围不变的单元保留原 ID，变动范围分配操作级新 ID）。既有学习计划与 Study Session 保留各自原始快照，后续新规划自动使用更新后的教材。
