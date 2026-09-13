# Document / OCR / Study Unit Harness

Document processing 的主 operation 为 `document_parse:document_parse`；page extraction、section detection、chunk building、OCR page 和 Study Unit cleanup 是独立登记的 stage，不把 stream event 名称当作 Harness stage。

主 admission 写 `document_process_operations` 与 immutable Harness binding。上传文件、OCR page 和 debug/context 数据作为 protected artifacts；parser/heuristic 结果经 bounded DTO adapter 校验。Document、debug report、operation receipt 与 terminal trace 在 repository transaction 中 finalize；子阶段 evidence 只证明对应 stage，不等于整个文档已提交。

OCR 和清洗目前仍以 heuristic 为主，是质量风险而不是绕开 Harness 的理由。proposal 中不能生成 committed Document/Study Unit identity、revision 或 timestamp。失败时保留原 Document 基线并把 operation 标成 failed/interrupted；post-cutoff legacy rows 无真实 binding 时只能只读，不能伪造 v3 trace。

Document stream 的 `page_parsed` 等名称是 UI progress event；`page_extraction` 等才是 operation stage；generate/decode/validate/repair/commit 是 stage 内 attempt phase。三套词汇不得混用。

