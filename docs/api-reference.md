# API Reference（生成文件）

> 由 `scripts/gen_api_reference.py` 从 FastAPI OpenAPI 生成，**请勿手改**。
> 契约语义、版本与兼容说明见 [api-contracts.md](api-contracts.md)；
> 改动路由后运行 `npm run gen:api-reference` 重新生成。

共 19 个分组、99 个操作。

## diagnostics

### `GET /diagnostics/events`

Query Events

参数：`after`（query，可选: integer）、`limit`（query，可选: integer）、`request_id`（query，可选）、`action_id`（query，可选）、`page_view_id`（query，可选）、`flow_id`（query，可选）、`source`（query，可选）、`page_path`（query，可选）、`severity`（query，可选）、`operation_id`（query，可选）、`workflow`（query，可选）、`stage`（query，可选）、`resource_id`（query，可选）、`resource_type`（query，可选）、`since`（query，可选）、`until`（query，可选）

响应：200、422 `HTTPValidationError`

### `POST /diagnostics/events`

Ingest

响应：200

### `POST /diagnostics/export`

Export Diagnostics

响应：200

### `GET /diagnostics/harness-index`

Query Harness Index

参数：`after`（query，可选: string）、`limit`（query，可选: integer）、`operation_id`（query，可选）、`workflow`（query，可选）、`stage`（query，可选）、`resource_id`（query，可选）、`resource_type`（query，可选）、`resource_role`（query，可选）

响应：200、422 `HTTPValidationError`

### `GET /diagnostics/operation-links`

Query Operation Links

参数：`operation_id`（query，必填: string）、`after`（query，可选: string）、`limit`（query，可选: integer）

响应：200、422 `HTTPValidationError`

### `GET /diagnostics/storage`

Query Storage

响应：200

### `GET /diagnostics/writers`

Query Writers

参数：`after`（query，可选: integer）、`limit`（query，可选: integer）

响应：200、422 `HTTPValidationError`

## documents

### `GET /documents`

List Documents

响应：200 `DocumentListResponse`

### `POST /documents`

Create Document

请求体（`multipart/form-data`）：`Body_create_document_documents_post`

响应：200 `DocumentResponse`、422 `HTTPValidationError`

### `GET /documents/input-limits`

Get Document Input Limits

响应：200 `DocumentInputLimitsV1`

### `GET /documents/{document_id}/checkpoint`

Get Latest Document Checkpoint

参数：`document_id`（path，必填: string）

响应：200 `DocumentCheckpointResponseV1`、422 `HTTPValidationError`

### `GET /documents/{document_id}/checkpoints/{operation_id}`

Get Document Checkpoint

参数：`document_id`（path，必填: string）、`operation_id`（path，必填: string）

响应：200 `DocumentCheckpointResponseV1`、422 `HTTPValidationError`

### `GET /documents/{document_id}/debug`

Get Document Debug

参数：`document_id`（path，必填: string）

响应：200 `DocumentDebugResponse`、422 `HTTPValidationError`

### `GET /documents/{document_id}/file`

Get Document File

参数：`document_id`（path，必填: string）

响应：200、422 `HTTPValidationError`

### `GET /documents/{document_id}/page-numbering`

Get Document Page Numbering

参数：`document_id`（path，必填: string）、`page_numbers`（query，必填: array）

响应：200 `DocumentPageNumberingResponseV1`、422 `HTTPValidationError`

### `GET /documents/{document_id}/pages/{page_number}/image`

Get Document Page Image

参数：`document_id`（path，必填: string）、`page_number`（path，必填: integer）

响应：200、422 `HTTPValidationError`

### `GET /documents/{document_id}/plan-events`

Get Document Plan Events

参数：`document_id`（path，必填: string）

响应：200 `StreamReportResponse`、422 `HTTPValidationError`

### `GET /documents/{document_id}/planning-context`

Get Document Planning Context

参数：`document_id`（path，必填: string）

响应：200 `DocumentPlanningContextResponse`、422 `HTTPValidationError`

### `GET /documents/{document_id}/planning-trace`

Get Document Planning Trace

参数：`document_id`（path，必填: string）

响应：200 `DocumentPlanningTraceResponse`、422 `HTTPValidationError`

### `POST /documents/{document_id}/process`

Process Document

参数：`document_id`（path，必填: string）

响应：200 `DocumentProcessResponse`、422 `HTTPValidationError`

### `GET /documents/{document_id}/process-events`

Get Document Process Events

参数：`document_id`（path，必填: string）

响应：200 `StreamReportResponse`、422 `HTTPValidationError`

### `POST /documents/{document_id}/process/stream`

Process Document Stream

参数：`document_id`（path，必填: string）

响应：200、422 `HTTPValidationError`

### `GET /documents/{document_id}/status`

Get Document Status

参数：`document_id`（path，必填: string）

响应：200 `DocumentStatusResponse`、422 `HTTPValidationError`

### `PATCH /documents/{document_id}/study-units/{study_unit_id}`

Update Study Unit Title

参数：`document_id`（path，必填: string）、`study_unit_id`（path，必填: string）

请求体（`application/json`）：`StudyUnitTitleUpdateRequest`

响应：200 `DocumentStudyUnitUpdateResponse`、422 `HTTPValidationError`

## exercises

### `POST /exercises/generate`

Generate Exercise

请求体（`application/json`）：`ExerciseGenerateRequest`

响应：200 `ExerciseGenerateResponse`、422 `HTTPValidationError`

## health

### `GET /health`

Healthcheck

响应：200

## learning-plan-operations

### `GET /learning-plan-operations/{client_request_id}`

Get Learning Plan Operation

参数：`client_request_id`（path，必填: string）

响应：200 `LearningPlanOperationResponse`、422 `HTTPValidationError`

## learning-plans

### `GET /learning-plans`

List Learning Plans

响应：200 `LearningPlanListResponse`

### `POST /learning-plans`

Create Learning Plan

请求体（`application/json`）：`LearningPlanCreateRequest`

响应：200 `LearningPlanCreateResponse`、422 `HTTPValidationError`

### `POST /learning-plans/stream`

Create Learning Plan Stream

请求体（`application/json`）：`LearningPlanCreateRequest`

响应：200、422 `HTTPValidationError`

### `DELETE /learning-plans/{plan_id}`

Delete Learning Plan

参数：`plan_id`（path，必填: string）、`expected_revision`（query，可选）

响应：200、422 `HTTPValidationError`

### `GET /learning-plans/{plan_id}`

Get Learning Plan

参数：`plan_id`（path，必填: string）

响应：200 `LearningPlanResponse`、422 `HTTPValidationError`

### `PATCH /learning-plans/{plan_id}`

Update Learning Plan

参数：`plan_id`（path，必填: string）

请求体（`application/json`）：`LearningPlanUpdateRequest`

响应：200 `LearningPlanResponse`、422 `HTTPValidationError`

### `PATCH /learning-plans/{plan_id}/planning-questions/{question_id}`

Answer Learning Plan Question

参数：`plan_id`（path，必填: string）、`question_id`（path，必填: string）

请求体（`application/json`）：`PlanningQuestionAnswerRequest`

响应：200 `LearningPlanResponse`、422 `HTTPValidationError`

### `PATCH /learning-plans/{plan_id}/progress`

Update Learning Plan Progress

参数：`plan_id`（path，必填: string）

请求体（`application/json`）：`LearningPlanProgressUpdateRequest`

响应：200 `LearningPlanResponse`、422 `HTTPValidationError`

### `GET /learning-plans/{plan_id}/revision-history`

Plan Revision History

参数：`plan_id`（path，必填: string）

响应：200、422 `HTTPValidationError`

### `POST /learning-plans/{plan_id}/revisions`

Create Plan Revision

参数：`plan_id`（path，必填: string）

请求体（`application/json`）：`PlanRevisionRequestV1`

响应：200 `PlanRevisionResponseV1`、422 `HTTPValidationError`

### `GET /learning-plans/{plan_id}/revisions/{request_id}`

Get Plan Revision

参数：`plan_id`（path，必填: string）、`request_id`（path，必填: string）

响应：200 `PlanRevisionResponseV1`、422 `HTTPValidationError`

### `POST /learning-plans/{plan_id}/revisions/{request_id}/decision`

Decide Plan Revision

参数：`plan_id`（path，必填: string）、`request_id`（path，必填: string）

请求体（`application/json`）：`PlanRevisionDecisionV1`

响应：200 `PlanRevisionResponseV1`、422 `HTTPValidationError`

### `GET /learning-plans/{plan_id}/study-unit-revision`

Get Study Unit Revision

参数：`plan_id`（path，必填: string）

响应：200 `StudyUnitRevisionResponseV1`、422 `HTTPValidationError`

### `POST /learning-plans/{plan_id}/study-unit-revision/{operation_id}/decision`

Decide Study Unit Revision

参数：`plan_id`（path，必填: string）、`operation_id`（path，必填: string）

请求体（`application/json`）：`StudyUnitRevisionDecisionV1`

响应：200 `StudyUnitRevisionResponseV1`、422 `HTTPValidationError`

## model-tools

### `GET /model-tools/config`

Get Model Tool Config

响应：200 `ModelToolConfigResponse`

### `PATCH /model-tools/config`

Update Model Tool Config

请求体（`application/json`）：`UpdateModelToolConfigRequest`

响应：200 `ModelToolConfigResponse`、422 `HTTPValidationError`

## model-usage

### `GET /model-usage/stats`

Get Model Usage Stats

参数：`workflow`（query，可选: string）、`operation_id`（query，可选: string）、`date_from`（query，可选: string）、`date_to`（query，可选: string）

响应：200 `TokenUsageStatsResponse`、422 `HTTPValidationError`

## persona-cards

### `GET /persona-cards`

List Persona Cards

响应：200 `PersonaCardListResponse`

### `POST /persona-cards`

Create Persona Card

请求体（`application/json`）：`CreatePersonaCardRequest`

响应：200 `PersonaCardResponse`、422 `HTTPValidationError`

### `POST /persona-cards/batch`

Create Persona Cards Batch

请求体（`application/json`）：`BatchCreatePersonaCardsRequest`

响应：200 `PersonaCardListResponse`、422 `HTTPValidationError`

### `POST /persona-cards/generate`

Generate Persona Cards

请求体（`application/json`）：`PersonaCardGenerateRequest`

响应：200 `PersonaCardGenerateResponse`、422 `HTTPValidationError`

### `DELETE /persona-cards/{card_id}`

Delete Persona Card

参数：`card_id`（path，必填: string）

响应：200、422 `HTTPValidationError`

## personas

### `GET /personas`

List Personas

响应：200 `PersonaListResponse`

### `POST /personas`

Create Persona

请求体（`application/json`）：`CreatePersonaRequest`

响应：200 `PersonaResponse`、422 `HTTPValidationError`

### `POST /personas/assist-setting`

Assist Persona Setting

请求体（`application/json`）：`PersonaSettingAssistRequest`

响应：200 `PersonaSettingAssistResponse`、422 `HTTPValidationError`

### `POST /personas/assist-slot`

Assist Persona Slot

请求体（`application/json`）：`PersonaSlotAssistRequest`

响应：200 `PersonaSlotAssistResponse`、422 `HTTPValidationError`

### `DELETE /personas/{persona_id}`

Delete Persona

参数：`persona_id`（path，必填: string）、`expected_revision`（query，必填: integer）

响应：200、422 `HTTPValidationError`

### `PATCH /personas/{persona_id}`

Update Persona

参数：`persona_id`（path，必填: string）

请求体（`application/json`）：`UpdatePersonaRequest`

响应：200 `PersonaResponse`、422 `HTTPValidationError`

### `GET /personas/{persona_id}/assets`

Get Persona Assets

参数：`persona_id`（path，必填: string）

响应：200 `PersonaAssetsResponse`、422 `HTTPValidationError`

## reusable-scene-nodes

### `GET /reusable-scene-nodes`

List Reusable Scene Nodes

响应：200 `ReusableSceneNodeListResponse`

### `POST /reusable-scene-nodes`

Create Reusable Scene Node

请求体（`application/json`）：`CreateReusableSceneNodeRequest`

响应：200 `ReusableSceneNodeResponse`、422 `HTTPValidationError`

### `DELETE /reusable-scene-nodes/{node_id}`

Delete Reusable Scene Node

参数：`node_id`（path，必填: string）

响应：200、422 `HTTPValidationError`

## runtime-settings

### `GET /runtime-settings`

Get Runtime Settings

响应：200 `RuntimeSettingsResponse`

### `PATCH /runtime-settings`

Update Runtime Settings

请求体（`application/json`）：`UpdateRuntimeSettingsRequest`

响应：200 `RuntimeSettingsResponse`、422 `HTTPValidationError`

### `POST /runtime-settings/check-openai-models`

Check Openai Models

请求体（`application/json`）：`RuntimeSettingsProbeRequest`

响应：200 `RuntimeSettingsProbeResponse`、422 `HTTPValidationError`

### `DELETE /runtime-settings/session-secrets`

Clear Runtime Session Secrets

响应：200 `RuntimeSettingsResponse`

### `PUT /runtime-settings/session-secrets`

Apply Runtime Session Secrets

请求体（`application/json`）：`RuntimeSessionSecretsRequest`

响应：200 `RuntimeSettingsResponse`、422 `HTTPValidationError`

## scene-library

### `GET /scene-library`

List Scene Library

响应：200 `SceneLibraryListResponse`

### `POST /scene-library`

Create Scene Library Item

请求体（`application/json`）：`UpsertSceneLibraryRequest`

响应：200 `SceneLibraryResponse`、422 `HTTPValidationError`

### `DELETE /scene-library/{scene_id}`

Delete Scene Library Item

参数：`scene_id`（path，必填: string）、`expected_revision`（query，必填: integer）

响应：200、422 `HTTPValidationError`

### `GET /scene-library/{scene_id}`

Get Scene Library Item

参数：`scene_id`（path，必填: string）

响应：200 `SceneLibraryResponse`、422 `HTTPValidationError`

### `PUT /scene-library/{scene_id}`

Update Scene Library Item

参数：`scene_id`（path，必填: string）

请求体（`application/json`）：`UpsertSceneLibraryRequest`

响应：200 `SceneLibraryResponse`、422 `HTTPValidationError`

## scene-setup

### `GET /scene-setup`

Get Scene Setup

响应：200 `SceneSetupResponse`

### `PUT /scene-setup`

Update Scene Setup

请求体（`application/json`）：`UpdateSceneSetupRequest`

响应：200 `SceneSetupResponse`、422 `HTTPValidationError`

### `POST /scene-setup/generate`

Generate Scene Tree

请求体（`application/json`）：`SceneTreeGenerateRequest`

响应：200 `SceneTreeGenerateResponse`、422 `HTTPValidationError`

## storage

### `POST /storage/cleanup`

Cleanup Storage

请求体（`application/json`）：`StorageCleanupRequest`

响应：200 `StorageCleanupResponse`、422 `HTTPValidationError`

### `GET /storage/summary`

Get Storage Summary

响应：200 `StorageSummaryResponse`

## stream-runs

### `POST /stream-runs/{stream_id}/cancel`

Cancel Stream Run

参数：`stream_id`（path，必填: string）

响应：200、422 `HTTPValidationError`

## study-sessions

### `GET /study-sessions`

List Study Sessions

参数：`document_id`（query，可选）、`persona_id`（query，可选）、`plan_id`（query，可选）、`study_unit_id`（query，可选）、`section_id`（query，可选）

响应：200 `StudySessionListResponse`、422 `HTTPValidationError`

### `POST /study-sessions`

Create Study Session

请求体（`application/json`）：`CreateStudySessionRequest`

响应：200 `StudySessionResponse`、422 `HTTPValidationError`

### `GET /study-sessions/{session_id}`

Get Study Session

参数：`session_id`（path，必填: string）

响应：200 `StudySessionResponse`、422 `HTTPValidationError`

### `PATCH /study-sessions/{session_id}`

Update Study Session

参数：`session_id`（path，必填: string）

请求体（`application/json`）：`UpdateStudySessionRequest`

响应：200 `StudySessionResponse`、422 `HTTPValidationError`

### `GET /study-sessions/{session_id}/attachments/{attachment_id}/file`

Get Study Session Attachment File

参数：`session_id`（path，必填: string）、`attachment_id`（path，必填: string）

响应：200、422 `HTTPValidationError`

### `GET /study-sessions/{session_id}/attachments/{attachment_id}/pages/{page_number}/image`

Get Study Session Attachment Page Image

参数：`session_id`（path，必填: string）、`attachment_id`（path，必填: string）、`page_number`（path，必填: integer）

响应：200、422 `HTTPValidationError`

### `POST /study-sessions/{session_id}/attempt`

Record Study Question Attempt

参数：`session_id`（path，必填: string）

请求体（`application/json`）：`StudyQuestionAttemptRequest`

响应：200 `StudyQuestionAttemptResponse`、422 `HTTPValidationError`

### `POST /study-sessions/{session_id}/chat`

Study Chat

参数：`session_id`（path，必填: string）

请求体（`application/json`）：`StudyChatRequest`

响应：200 `StudyChatOperationReceiptResponse`、422 `HTTPValidationError`

### `GET /study-sessions/{session_id}/chat-operations/{client_request_id}`

Get Study Chat Operation

参数：`session_id`（path，必填: string）、`client_request_id`（path，必填: string）

响应：200 `StudyChatOperationReceiptResponse`、422 `HTTPValidationError`

### `POST /study-sessions/{session_id}/chat-with-attachments`

Study Chat With Attachments

参数：`session_id`（path，必填: string）

请求体（`multipart/form-data`）：`Body_study_chat_with_attachments_study_sessions__session_id__chat_with_attachments_post`

响应：200 `StudyChatOperationReceiptResponse`、422 `HTTPValidationError`

### `POST /study-sessions/{session_id}/follow-ups/cancel`

Cancel Study Session Follow Ups

参数：`session_id`（path，必填: string）

响应：200 `StudySessionResponse`、422 `HTTPValidationError`

### `POST /study-sessions/{session_id}/plan-confirmations/{confirmation_id}`

Resolve Study Session Plan Confirmation

参数：`session_id`（path，必填: string）、`confirmation_id`（path，必填: string）

请求体（`application/json`）：`StudySessionPlanConfirmationDecisionRequest`

响应：200 `StudySessionPlanConfirmationDecisionResponse`、422 `HTTPValidationError`

## submissions

### `POST /submissions/grade`

Grade Submission

请求体（`application/json`）：`SubmissionGradeRequest`

响应：200 `SubmissionGradeResponse`、422 `HTTPValidationError`

## tavern

### `GET /tavern/rooms`

List Tavern Rooms

参数：`limit`（query，可选: integer）、`cursor`（query，可选）

响应：200 `TavernRoomListResponse`、422 `HTTPValidationError`

### `POST /tavern/rooms`

Create Tavern Room

请求体（`application/json`）：`CreateTavernRoomRequest`

响应：200 `TavernRoomDetail`、422 `HTTPValidationError`

### `DELETE /tavern/rooms/{room_id}`

Delete Tavern Room

参数：`room_id`（path，必填: string）、`expected_revision`（query，必填: integer）

响应：200、422 `HTTPValidationError`

### `GET /tavern/rooms/{room_id}`

Get Tavern Room

参数：`room_id`（path，必填: string）、`after_sequence`（query，可选: integer）、`before_sequence`（query，可选）、`tail`（query，可选: boolean）、`limit`（query，可选: integer）

响应：200 `TavernRoomDetail`、422 `HTTPValidationError`

### `PATCH /tavern/rooms/{room_id}`

Update Tavern Room

参数：`room_id`（path，必填: string）

请求体（`application/json`）：`UpdateTavernRoomRequest`

响应：200 `TavernRoomDetail`、422 `HTTPValidationError`

### `GET /tavern/rooms/{room_id}/run-recovery`

Get Tavern Run Recovery

参数：`room_id`（path，必填: string）、`limit`（query，可选: integer）

响应：200 `TavernRunRecoveryResponse`、422 `HTTPValidationError`

### `GET /tavern/rooms/{room_id}/runs`

List Tavern Runs

参数：`room_id`（path，必填: string）、`limit`（query，可选: integer）

响应：200 `TavernRunListResponse`、422 `HTTPValidationError`

### `POST /tavern/rooms/{room_id}/runs/{run_id}/cancel`

Cancel Tavern Run

参数：`room_id`（path，必填: string）、`run_id`（path，必填: string）

响应：200 `TavernTurnResponse`、422 `HTTPValidationError`

### `POST /tavern/rooms/{room_id}/runs/{run_id}/resume`

Resume Tavern Run

参数：`room_id`（path，必填: string）、`run_id`（path，必填: string）

响应：200 `TavernTurnResponse`、422 `HTTPValidationError`

### `POST /tavern/rooms/{room_id}/runs/{run_id}/retry`

Retry Tavern Run

参数：`room_id`（path，必填: string）、`run_id`（path，必填: string）

请求体（`application/json`）：`RetryTavernRunRequest`

响应：200 `TavernTurnResponse`、422 `HTTPValidationError`

### `POST /tavern/rooms/{room_id}/turns`

Run Tavern Turn

参数：`room_id`（path，必填: string）

请求体（`application/json`）：`TavernTurnRequest`

响应：200 `TavernTurnResponse`、422 `HTTPValidationError`
