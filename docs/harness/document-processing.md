# Document / OCR / Study Unit Harness

Document processing 的主 operation 为 `document_parse:document_parse`；page extraction、section detection、chunk building、OCR page 和 Study Unit cleanup 是独立登记的 stage，不把 stream event 名称当作 Harness stage。

主 admission 写 `document_process_operations` 与 immutable Harness binding。上传文件、OCR page 和 debug/context 数据作为 protected artifacts；parser/heuristic 结果经 bounded DTO adapter 校验。Document、debug report、operation receipt 与 terminal trace 在 repository transaction 中 finalize；子阶段 evidence 只证明对应 stage，不等于整个文档已提交。

Document 写入由 `DocumentRepository` 以单行插入和 revision CAS 承接。解析 admission 与终态投影分别推进 revision；失败恢复只可恢复自己占用的 processing revision，不能覆盖更晚投影。Study Unit 标题更新要求 `expected_revision`，并在同一事务提交 Document/Debug；processing 期间拒绝改名。Planning 的 Document 写入也使用同一 SQL revision fence，保留既有 admission、摘要校验和原子终态边界。revision 是应用拥有的并发元数据，不进入模型 proposal；历史 revision 0 不加入原 v1 快照序列化。

OCR 和清洗目前仍以 heuristic 为主，是质量风险而不是绕开 Harness 的理由。proposal 中不能生成 committed Document/Study Unit identity、revision 或 timestamp。失败时保留原 Document 基线并把 operation 标成 failed/interrupted；post-cutoff legacy rows 无真实 binding 时只能只读，不能伪造 v3 trace。

Document stream 的 `page_parsed` 等名称是 UI progress event；`page_extraction` 等才是 operation stage；generate/decode/validate/repair/commit 是 stage 内 attempt phase。三套词汇不得混用。

Document CAS 的必要回归为 `tests.test_document_repository`、`tests.test_document_process_operation` 和 `tests.test_learning_plan_operation`。可在 `services/ai` 运行 `LITELLM_LOCAL_MODEL_COST_MAP=True PYTHONPATH=. uv run python tests/acceptance/document_cas_probe.py`，用临时 SQLite、真实 PDF parser 和 HTTP 接口复核并发上传、过期/缺失 revision 拒绝及应用实例重启后的 Document/Debug 读回；该探针不调用真实 provider。


Document parser v3 延续 v2 的完成页、完整 report 和清洗输出的独立有界 checkpoint；外层超时/失败不把这些中间成果投影为已提交教材。显式续跑在同一事务分配新 process operation/Harness binding 与唯一 source-child 关系，复用授权快照内的已完成工作，再走原有严格验证与 CAS 原子提交。重复来源请求只读同一 child，不重放 parser；输入/配置变化、过期 revision、摘要损坏和终态旧写者失败关闭。API、容量、UI 和进程退出验证见 [Document OCR checkpoints](../document-checkpoints.md)。

Parser v3 / chunk builder v2 在上传与处理 admission 前执行 64 MiB 文件、512 个物理页上限；multipart 全请求为 65 MiB，实际 body 超限时在解析 multipart 前拒绝。1,400 字符是打包目标，较大不可分割单元保持原文并告警；超过独立的 65,536 字符硬上限才拒绝解析。失败保留页 checkpoint，不提交 Document/Debug。契约、错误和定向检查见 [Document input limits](../document-input-limits.md)。
