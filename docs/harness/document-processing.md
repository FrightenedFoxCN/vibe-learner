# Document / OCR / Study Unit Harness

## 阶段与词汇边界

文档处理的主操作为 `document_parse:document_parse`，内部登记 `page_extraction`、`section_detection`、`chunk_building`、`ocr_page` 与 `study_unit_cleanup` 五个独立子阶段。

三套词汇严格区分：

- **Operation Stage**（如 `page_extraction`）：Harness 登记的领域阶段；
- **Attempt Phase**（`generate` / `decode` / `validate` / `repair` / `commit`）：单个阶段内的执行步骤；
- **Stream Event**（如 `page_parsed`）：面向 UI 的进度事件名。

## 准入、受保护制品与提交

1. **输入预检**：在存储或准入前强制校验 64 MiB 单文件、65 MiB 完整 multipart 请求、512 物理页以及 65,536 字符单不可分割文本块上限（1,400 字符为分块打包目标，不静默截断）。详见 [教材解析与入库链路](../document-pipeline.md)。
2. **原子准入**：写 `document_process_operations` 与不可变 Harness 绑定，并在同事务将 Document 标记为 `processing` 并推进 `revision`。
3. **受保护制品**：原始上传文件、OCR 页与调试/上下文载荷作为受保护制品受授权访问；解析与清洗输出经有界 DTO 适配器严格校验。
4. **原子提交与失败恢复**：Document、Debug 报告、操作回执与终态 Trace 在同一 Repository 事务中提交；失败或中断时仅恢复自己占用的 processing revision（不覆盖更晚写入），并保留原基线。子阶段证据不代表整个文档已提交。

## 并发与断点续跑

- `DocumentRepository` 全部走单行写入与 SQL revision CAS；Study Unit 改名要求 `expected_revision` 并拒绝在处理期间修改；Planning 的 Document 写入同样持有 revision 围栏。
- 解析过程将已完成页、完整解析报告与清洗输出保存为有界 Checkpoint（`document_checkpoints`），不将其提前投影为已提交教材。
- 显式续跑在同一事务分配新的处理操作、Harness 绑定与唯一 source-child 关系（`document_checkpoint_resumes`），经授权快照复用已完成阶段后仍执行完整严格校验与原子提交。

不变量回归由 `npm run test:baseline`（含 `test_document_checkpoints`）覆盖。
