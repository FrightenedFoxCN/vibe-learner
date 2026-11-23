# 关键入口清单

按子域列出核心代码入口与所有权。修改某子域前先定位入口，再阅读对应的领域文档。

## 应用与传输入口

| 职责 | 路径 |
| --- | --- |
| Web 根布局与全局 Debug Overlay | `apps/web/app/layout.tsx`、`apps/web/components/debug/debug-overlay.tsx` |
| Web 导航首页 | `apps/web/app/page.tsx` |
| 前端领域数据入口 | `apps/web/lib/data/*.ts`（说明见 [`apps/web/lib/data/README.md`](../apps/web/lib/data/README.md)） |
| 前端域级 API 传输模块 | `apps/web/lib/api/_shared.ts`、`apps/web/lib/api/*.ts`（按域导入，无全域聚合入口） |
| 后端应用工厂与容器引导 | `services/ai/app/app_factory.py`、`services/ai/app/core/bootstrap.py` |
| 后端路由汇总与域路由 | `services/ai/app/api/routes.py`、`services/ai/app/api/routers/*.py`、`services/ai/app/api/tavern_routes.py`、`services/ai/app/api/diagnostic_routes.py` |
| 外部输入归一化（coerce） | `services/ai/app/core/coerce.py` |
| 共享 TypeScript 契约与夹具 | `packages/shared/src/`、`packages/shared/fixtures/` |

## 教材与解析（Document / OCR / Study Unit）

| 职责 | 路径 |
| --- | --- |
| 上传上限契约与请求体拦截 | `services/ai/app/models/document_input_limits.py`、`services/ai/app/api/document_upload_limit.py`、`apps/web/lib/document-upload-validation.ts` |
| PDF 解析与 OCR 流水线 | `services/ai/app/services/document_parser.py`、`services/ai/app/services/ocr_engine.py` |
| Study Unit 清洗与启发式排期 | `services/ai/app/services/study_arrangement.py` |
| Document 持久化与 CAS | `services/ai/app/persistence/document_repository.py`、`services/ai/app/persistence/document_process_operation_repository.py` |
| OCR 断点与显式续跑 | `services/ai/app/models/document_checkpoint.py`、`services/ai/app/persistence/document_checkpoint_repository.py`、`apps/web/components/plan/document-checkpoint-panel.tsx` |
| 物理页与印刷页码对照 | `services/ai/app/models/pdf_page_scope.py`、`services/ai/app/services/document_page_numbering.py`、`apps/web/lib/planning-page-scope.ts` |
| Study Unit 修订确认 | `services/ai/app/models/study_unit_revision.py`、`services/ai/app/services/study_unit_revision.py`、`services/ai/app/persistence/study_unit_revision_repository.py`、`apps/web/components/plan/study-unit-revision-panel.tsx` |

## 学习计划（Planning）

| 职责 | 路径 |
| --- | --- |
| Prompt 组装与模板 | `services/ai/app/services/plan_prompt.py`、`services/ai/app/prompts/learning_plan_prompt.txt` |
| 规划运行器与工具执行 | `services/ai/app/services/openai_plan_runner.py`、`services/ai/app/services/provider_planning.py`、`services/ai/app/services/plan_tool_runtime.py` |
| 计划服务与操作持久化 | `services/ai/app/services/plans.py`、`services/ai/app/persistence/learning_plan_repository.py`、`services/ai/app/persistence/learning_plan_operation_repository.py` |
| 计划修订与回滚 | `services/ai/app/services/plan_revision.py`、`services/ai/app/persistence/plan_revision_repository.py`、`apps/web/components/plan/plan-revision-panel.tsx` |
| 输出语言偏好 | `services/ai/app/models/output_language.py`、`services/ai/app/services/output_language.py`、`apps/web/lib/output-language.ts` |
| 前端 Plan / Study 编排 | `apps/web/components/layout/learning-workspace-provider.tsx`、`apps/web/hooks/use-learning-workspace-controller.ts`、`apps/web/lib/learning-workspace-reducer.ts` |

## 学习对话（Study Session & Chat）

| 职责 | 路径 |
| --- | --- |
| Study Chat 应用编排 | `services/ai/app/services/study_chat_application.py`、`services/ai/app/services/study_v3.py` |
| 32 个 Study 工具与分派 | `services/ai/app/services/study_session_chat_runtime.py`、`services/ai/app/services/study_tools/` |
| 强类型效果与附件暂存 | `services/ai/app/models/study_chat_effect.py`、`services/ai/app/services/study_chat_effects.py`、`services/ai/app/services/study_chat_attachments.py` |
| Session CAS 与操作持久化 | `services/ai/app/persistence/study_session_repository.py`、`services/ai/app/persistence/study_chat_operation_repository.py` |
| 交互题判分与前端解码 | `services/ai/app/models/study_question.py`、`apps/web/lib/study-question-attempt.ts`、`apps/web/lib/study-session-decode.ts` |
| 浏览器恢复与等待上限 | `apps/web/hooks/use-study-chat-recovery.ts`、`apps/web/lib/study-request-deadline.ts`、`apps/web/lib/study-chat-operation-decode.ts` |

## Persona、Scene 与 Tavern

| 职责 | 路径 |
| --- | --- |
| Persona 服务与生成 | `services/ai/app/services/persona.py`、`services/ai/app/services/persona_cards.py`、`services/ai/app/services/persona_harness_adapter.py` |
| Scene 契约、服务与生成 | `services/ai/app/models/scene.py`、`services/ai/app/services/scene_setup.py`、`services/ai/app/services/scene_library.py`、`services/ai/app/services/scene_harness_adapter.py` |
| Persona / Scene 前端工作区 | `apps/web/components/persona/`、`apps/web/components/scene/`、`apps/web/hooks/use-persona-*.ts`、`apps/web/hooks/use-scene-*.ts` |
| Tavern 契约与编排 | `services/ai/app/models/tavern.py`、`services/ai/app/models/tavern_commit.py`、`services/ai/app/services/tavern.py`、`services/ai/app/services/tavern_harness.py`、`services/ai/app/services/tavern_v3.py` |
| Tavern 持久化（拆分模块） | `services/ai/app/persistence/tavern_repository.py`、`tavern_room_ops.py`、`tavern_msg_ops.py`、`tavern_run_ops.py`、`tavern_rows.py`、`transaction_validation.py` |
| Tavern 可取消 HTTP 传输 | `services/ai/app/services/provider_cancellation.py`、`services/ai/app/services/provider_http_chat.py` |
| Tavern 前端工作区 | `apps/web/components/tavern/tavern-workspace.tsx`、`apps/web/hooks/use-tavern-*.ts`、`apps/web/lib/tavern-decode.ts` |

## Harness、模型运行时与诊断

| 职责 | 路径 |
| --- | --- |
| Harness 契约、清单与运行时 | `services/ai/app/models/harness.py`、`harness_manifest.py`、`harness_operation.py`、`services/ai/app/services/harness_runtime.py`、`harness_broad_adoption.py` |
| 受保护制品与效果日志 | `services/ai/app/models/harness_artifact_access.py`、`harness_effect.py`、`services/ai/app/persistence/harness_artifact_repository.py`、`harness_effect_repository.py` |
| Tool Manifest 与 Provider 投影 | `services/ai/app/models/tool_manifest.py`、`services/ai/app/services/tool_provider_projection.py`、`packages/shared/src/tool-manifest.ts` |
| 模型运行时配置与 Provider | `services/ai/app/core/model_runtime_limits.py`、`services/ai/app/services/model_provider.py`、`provider_transport.py`、`runtime_settings.py` |
| 诊断采集、存储、审计与导出 | `services/ai/app/core/diagnostics.py`、`diagnostic_quota.py`、`diagnostic_retention.py`、`services/ai/app/services/diagnostic_*.py`、`apps/web/lib/diagnostic*.ts` |
| 桌面壳、Vault 与原生导出/Spool | `apps/desktop/src-tauri/src/lib.rs`、`diagnostics.rs`、`diagnostic_counter.rs`、`json_export.rs`、`json_export_file.rs` |
