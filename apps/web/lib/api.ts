import { diagnosticFetch } from "./diagnostics";
import type {
  CreatePersonaInput,
  CreatePersonaCardInput,
  CreateTavernRoomInput,
  DocumentPlanningContext,
  DocumentPlanningTraceResponse,
  ModelToolConfig,
  ModelToolToggle,
  DocumentDebugRecord,
  DocumentRecord,
  LearningGoal,
  LearningPlan,
  PersonaCard,
  PersonaCardGenerationMode,
  PersonaProfile,
  RuntimeOpenAIProbeResult,
  RuntimeFeatureProbeName,
  RuntimeSettings,
  RuntimeSettingsPatch,
  RetryTavernRunInput,
  StreamEvent,
  StreamReport,
  StudyChatResponse,
  StudySessionRecord,
  TavernErrorDetail,
  TavernRoomDetail,
  TavernRoomPage,
  TavernRun,
  TavernRunRecoveryChain,
  TavernTurnInput,
  TavernTurnResult,
  TokenUsageStats,
  UpdatePersonaInput,
  UpdateTavernRoomInput
} from "@vibe-learner/shared";

import { compactPreviewString, compactPreviewValue } from "./preview";
import { getAiBaseUrl, getDesktopRuntimeConfig } from "./runtime-config";
import { ApiHttpError, extractApiErrorCode } from "./http-error";
import {
  decodeStudyChatExchange,
  decodeStudyPlanConfirmationDecisionResponse,
  decodeStudySession,
  decodeStudySessionList,
} from "./study-session-decode";
import {
  decodeDocumentDebugRecord,
  decodeDocumentList,
  decodeDocumentRecord,
  DocumentDecodeError,
} from "./document-decode";
import {
  decodeDocumentPlanningContext,
  decodeDocumentPlanningTraceResponse,
  decodeDocumentStudyUnitUpdate,
  decodeLearningPlan,
  decodeLearningPlanList,
} from "./planning-decode";
import {
  decodeStudyChatOperationReceipt,
  type StudyChatOperationReceipt,
} from "./study-chat-operation-decode";
import {
  decodeStudyQuestionAttemptResponse,
  type StudyQuestionAttemptResponse,
} from "./study-question-attempt";
import {
  decodeDeletedIdentity,
  decodePersonaAssets,
  decodePersonaCardGenerateResult,
  decodePersonaCardList,
  decodePersonaList,
  decodePersonaProfile,
  decodePersonaSettingAssistOutput,
  decodePersonaSlotAssistOutput,
  decodeReusableSceneNode,
  decodeReusableSceneNodeList,
  decodeSceneLibraryItem,
  decodeSceneLibraryList,
  decodeSceneSetupState,
  decodeSceneTreeGenerateResult,
} from "./persona-scene-decode";
import {
  consumeVersionedStream,
  decodeStreamReport,
  StrictStreamStateMachine,
} from "./stream-decode";

export {
  normalizeTavernRoomDetail,
  normalizeTavernErrorDetail,
  normalizeTavernRunRecovery,
  normalizeTavernTurnResult,
  TavernDecodeError,
} from "./tavern-decode";
export { StudySessionDecodeError } from "./study-session-decode";
export { DocumentDecodeError } from "./document-decode";
export { PlanningDecodeError } from "./planning-decode";
export { PersonaSceneDecodeError } from "./persona-scene-decode";
export type {
  StudyChatOperationReceipt,
  StudyChatOperationStatus,
} from "./study-chat-operation-decode";
import {
  normalizeTavernRoomDetail,
  normalizeTavernRoomList,
  normalizeTavernRunList,
  normalizeTavernRunRecovery,
  normalizeTavernTurnResult,
  normalizeTavernErrorDetail,
  isTavernTerminalReplayDirective,
} from "./tavern-decode";

export interface StudyChatExchangeResponse extends StudyChatResponse {
  session: StudySessionRecord;
}

export type StudyChatOperationResponse = StudyChatOperationReceipt<StudyChatExchangeResponse>;

export interface StudyPlanConfirmationDecisionResponse {
  session: StudySessionRecord;
  plan: LearningPlan | null;
}

export interface StudyQuestionAttemptCommitResult {
  attempt: StudyQuestionAttemptResponse;
  session: StudySessionRecord;
}

export interface PersonaAssets {
  personaId: string;
  renderer: string;
  assetManifest: Record<string, unknown>;
}

export interface PersonaCardGenerateResult {
  mode: PersonaCardGenerationMode;
  usedModel: string;
  usedWebSearch: boolean;
  summary: string;
  relationship: string;
  learnerAddress: string;
  items: PersonaCard[];
  modelRecoveries?: import("@vibe-learner/shared").ModelRecovery[];
}

export interface SceneTreeGenerateResult {
  mode: "keywords" | "long_text";
  usedModel: string;
  usedWebSearch: boolean;
  sceneName: string;
  sceneSummary: string;
  selectedLayerId: string;
  sceneLayers: import("@vibe-learner/shared").SceneTreeNode[];
  modelRecoveries?: import("@vibe-learner/shared").ModelRecovery[];
}

export interface PersonaSettingAssistInput {
  name: string;
  summary: string;
  slots: import("@vibe-learner/shared").PersonaSlot[];
  rewriteStrength: number;
}

export interface PersonaSettingAssistOutput {
  slots: import("@vibe-learner/shared").PersonaSlot[];
  systemPromptSuggestion: string;
  modelRecoveries?: import("@vibe-learner/shared").ModelRecovery[];
}

export interface PersonaSlotAssistInput {
  name: string;
  summary: string;
  slot: import("@vibe-learner/shared").PersonaSlot;
  rewriteStrength: number;
}

export interface PersonaSlotAssistOutput {
  slot: import("@vibe-learner/shared").PersonaSlot;
  modelRecoveries?: import("@vibe-learner/shared").ModelRecovery[];
}

export interface SceneSetupStatePayload {
  revision: number;
  updatedAt: string;
  sceneName: string;
  sceneSummary: string;
  sceneLayers: import("@vibe-learner/shared").SceneTreeNode[];
  selectedLayerId: string;
  collapsedLayerIds: string[];
  sceneProfile?: import("@vibe-learner/shared").SceneProfile;
}

export interface SceneLibraryItemPayload {
  sceneId: string;
  revision: number;
  createdAt: string;
  updatedAt: string;
  sceneName: string;
  sceneSummary: string;
  sceneLayers: import("@vibe-learner/shared").SceneTreeNode[];
  selectedLayerId: string;
  collapsedLayerIds: string[];
  sceneProfile?: import("@vibe-learner/shared").SceneProfile;
}

export interface ReusableSceneNodePayload {
  nodeId: string;
  nodeType: "layer" | "object";
  title: string;
  summary: string;
  tags: string[];
  reuseId: string;
  reuseHint: string;
  sourceSceneId: string;
  sourceSceneName: string;
  layerNode?: import("@vibe-learner/shared").SceneTreeNode;
  objectNode?: import("@vibe-learner/shared").SceneObjectSnapshot;
  createdAt: string;
  updatedAt: string;
}

export interface DocumentStudyUnitUpdatePayload {
  document: DocumentRecord;
  plans: LearningPlan[];
}

function serializeSceneTree(
  nodes: import("@vibe-learner/shared").SceneTreeNode[] | undefined
): Array<Record<string, unknown>> {
  return (nodes ?? []).map((node) => ({
    id: node.id,
    title: node.title,
    scope_label: node.scopeLabel,
    summary: node.summary,
    atmosphere: node.atmosphere,
    rules: node.rules,
    entrance: node.entrance,
    tags: node.tags,
    reuse_id: node.reuseId,
    reuse_hint: node.reuseHint,
    objects: (node.objects ?? []).map((object) => ({
      id: object.id,
      name: object.name,
      description: object.description,
      interaction: object.interaction,
      tags: object.tags,
      reuse_id: object.reuseId,
      reuse_hint: object.reuseHint,
    })),
    children: serializeSceneTree(node.children),
  }));
}

function serializeSceneProfile(
  sceneProfile: import("@vibe-learner/shared").SceneProfile | null | undefined
) {
  if (!sceneProfile) {
    return null;
  }
  return {
    scene_name: sceneProfile.sceneName,
    scene_id: sceneProfile.sceneId,
    title: sceneProfile.title,
    summary: sceneProfile.summary,
    tags: sceneProfile.tags,
    selected_path: sceneProfile.selectedPath,
    focus_object_names: sceneProfile.focusObjectNames,
    scene_tree: serializeSceneTree(sceneProfile.sceneTree),
  };
}

function extractErrorMessage(payload: unknown, fallbackMessage: string) {
  if (typeof payload === "string") {
    const trimmed = payload.trim();
    return trimmed || fallbackMessage;
  }
  if (!payload || typeof payload !== "object") {
    return fallbackMessage;
  }
  const record = payload as Record<string, unknown>;
  const detail = record.detail ?? record.error ?? record.message;
  if (typeof detail === "string") {
    const trimmed = detail.trim();
    return trimmed || fallbackMessage;
  }
  if (detail && typeof detail === "object") {
    return extractErrorMessage(detail, fallbackMessage);
  }
  if (detail !== undefined && detail !== null) {
    const text = String(detail).trim();
    if (text) {
      return text;
    }
  }
  return fallbackMessage;
}

const AI_BASE_URL = () => getAiBaseUrl();

async function request(input: string, init?: RequestInit): Promise<Response> {
  try {
    return await diagnosticFetch(input, init);
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    const startupError = getDesktopRuntimeConfig()?.startupError.trim();
    const detail = startupError ? ` (${startupError})` : "";
    throw new Error(`Cannot reach AI service at ${AI_BASE_URL()}${detail}`);
  }
}

async function readJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const text = await response.text();
    const fallbackMessage = text.trim() || `HTTP ${response.status}`;
    let message = fallbackMessage;
    let payload: unknown = text;
    try {
      payload = JSON.parse(text) as unknown;
      message = extractErrorMessage(payload, fallbackMessage);
    } catch {
      // Keep the raw body when it is not JSON.
    }
    throw new ApiHttpError({
      status: response.status,
      code: extractApiErrorCode(payload),
      message,
      payload,
    });
  }
  return (await response.json()) as T;
}

export function decodeTavernHttpError(error: unknown): TavernErrorDetail | null {
  if (!(error instanceof ApiHttpError)) return null;
  try {
    return normalizeTavernErrorDetail(error.payload);
  } catch {
    return null;
  }
}

async function requestTavernMutationWithRecovery(
  input: string,
  init: RequestInit
): Promise<unknown> {
  try {
    return await readJson<unknown>(await request(input, init));
  } catch (error) {
    const detail = decodeTavernHttpError(error);
    if (
      !(error instanceof ApiHttpError) ||
      !isTavernTerminalReplayDirective(error.status, detail)
    ) {
      throw error;
    }
    // The server has already committed terminal evidence. Replaying the exact
    // request key is query-only recovery and must not invoke the model again.
    return await readJson<unknown>(await request(input, init));
  }
}

function formatStreamErrorPayload(
  payload: Record<string, unknown> | undefined,
  fallbackCode: string
): string {
  const detail = String(payload?.detail ?? payload?.error ?? fallbackCode);
  const internal = payload?.internal_error_code;
  const statusCode = payload?.status_code;
  const retryAttempts = payload?.retry_attempts;
  const suffixParts: string[] = [];
  if (internal) {
    suffixParts.push(`internal=${String(internal)}`);
  }
  if (statusCode) {
    suffixParts.push(`status=${String(statusCode)}`);
  }
  if (typeof retryAttempts === "number" && retryAttempts > 1) {
    suffixParts.push(`retries=${String(retryAttempts - 1)}`);
  }
  if (!suffixParts.length) {
    return detail;
  }
  return `${detail} (${suffixParts.join(", ")})`;
}

function serializeSlot(slot: any) {
  return {
    kind: slot.kind,
    label: slot.label,
    content: slot.content,
    weight: slot.weight ?? 1,
    locked: slot.locked ?? false,
    sort_order: slot.sortOrder ?? 0
  };
}

function serializePersonaCardInput(input: CreatePersonaCardInput) {
  return {
    title: input.title,
    kind: input.kind,
    label: input.label,
    content: input.content,
    tags: input.tags ?? [],
    search_keywords: input.searchKeywords ?? "自定义",
    source: input.source ?? "manual",
    source_note: input.sourceNote ?? ""
  };
}

function serializePersonaInput(input: CreatePersonaInput | UpdatePersonaInput) {
  return {
    name: input.name,
    summary: input.summary,
    relationship: input.relationship,
    learner_address: input.learnerAddress,
    system_prompt: input.systemPrompt,
    reference_hints: input.referenceHints ?? [],
    slots: input.slots.map(serializeSlot),
    available_emotions: input.availableEmotions,
    available_actions: input.availableActions,
    default_speech_style: input.defaultSpeechStyle,
    ...("expectedRevision" in input
      ? { expected_revision: input.expectedRevision }
      : {}),
  };
}

function normalizeDocument(document: unknown, expectedDocumentId?: string): DocumentRecord {
  const decoded = decodeDocumentRecord(document, expectedDocumentId);
  return {
    ...decoded,
    previewExcerpt: compactPreviewString(decoded.previewExcerpt, 240),
  };
}

function normalizeDebugRecord(record: unknown, expectedDocumentId?: string): DocumentDebugRecord {
  const decoded = decodeDocumentDebugRecord(record, expectedDocumentId);
  return {
    ...decoded,
    pages: decoded.pages.map((page) => ({
      ...page,
      textPreview: compactPreviewString(page.textPreview, 320),
    })),
    chunks: decoded.chunks.map((chunk) => ({
      ...chunk,
      textPreview: compactPreviewString(chunk.textPreview, 240),
      content: compactPreviewString(chunk.content, 600),
    })),
  };
}

function normalizePlanningContext(
  record: unknown,
  expectedDocumentId?: string,
): DocumentPlanningContext {
  const decoded = decodeDocumentPlanningContext(record, expectedDocumentId);
  return {
    ...decoded,
    detailMap: Object.fromEntries(
      Object.entries(decoded.detailMap).map(([unitId, detail]) => [
        unitId,
        {
          ...detail,
          chunkExcerpts: detail.chunkExcerpts.map((chunk) => ({
            ...chunk,
            content: compactPreviewString(chunk.content, 600),
          })),
        },
      ]),
    ),
  };
}

function normalizePlanningTraceResponse(
  record: unknown,
  expectedDocumentId?: string,
): DocumentPlanningTraceResponse {
  const decoded = decodeDocumentPlanningTraceResponse(record, expectedDocumentId);
  if (!decoded.trace) return decoded;
  return {
    ...decoded,
    trace: {
      ...decoded.trace,
      rounds: decoded.trace.rounds.map((round) => ({
        ...round,
        assistantContent: compactPreviewString(round.assistantContent, 800),
        thinking: compactPreviewString(round.thinking, 800),
        toolCalls: round.toolCalls.map((toolCall) => ({
          ...toolCall,
          argumentsJson: compactPreviewString(toolCall.argumentsJson, 800),
          resultJson: compactPreviewString(toolCall.resultJson, 800),
        })),
      })),
    },
  };
}

function normalizeModelToolConfig(record: any): ModelToolConfig {
  return {
    updatedAt: String(record.updated_at ?? ""),
    stages: (record.stages ?? []).map((stage: any) => ({
      name: String(stage.name ?? ""),
      label: String(stage.label ?? stage.name ?? ""),
      description: String(stage.description ?? ""),
      stageEnabled: Boolean(stage.stage_enabled),
      auditBasis: Array.isArray(stage.audit_basis)
        ? stage.audit_basis.map((item: unknown) => String(item))
        : [],
      stageDisabledReason: String(stage.stage_disabled_reason ?? ""),
      tools: (stage.tools ?? []).map((tool: any) => ({
        name: String(tool.name ?? ""),
        label: String(tool.label ?? tool.name ?? ""),
        description: String(tool.description ?? ""),
        category: String(tool.category ?? ""),
        categoryLabel: String(tool.category_label ?? tool.category ?? ""),
        enabled: Boolean(tool.enabled),
        available: Boolean(tool.available),
        effectiveEnabled: Boolean(tool.effective_enabled),
        auditBasis: Array.isArray(tool.audit_basis)
          ? tool.audit_basis.map((item: unknown) => String(item))
          : [],
        unavailableReason: String(tool.unavailable_reason ?? "")
      }))
    }))
  };
}

function normalizeRuntimeSettings(record: any): RuntimeSettings {
  return {
    updatedAt: String(record.updated_at ?? ""),
    planProvider: (record.plan_provider === "mock" ? "mock" : "litellm") as "mock" | "litellm",
    openaiApiKey: String(record.openai_api_key ?? ""),
    openaiApiKeyConfigured: Boolean(record.openai_api_key_configured),
    openaiBaseUrl: String(record.openai_base_url ?? "https://api.openai.com/v1"),
    openaiPlanApiKey: String(record.openai_plan_api_key ?? ""),
    openaiPlanApiKeyConfigured: Boolean(record.openai_plan_api_key_configured),
    openaiPlanBaseUrl: String(record.openai_plan_base_url ?? "https://api.openai.com/v1"),
    openaiPlanModel: String(record.openai_plan_model ?? "gpt-4.1-mini"),
    openaiSettingApiKey: String(record.openai_setting_api_key ?? ""),
    openaiSettingApiKeyConfigured: Boolean(record.openai_setting_api_key_configured),
    openaiSettingBaseUrl: String(record.openai_setting_base_url ?? "https://api.openai.com/v1"),
    openaiSettingModel: String(record.openai_setting_model ?? "gpt-4.1-mini"),
    openaiSettingWebSearchEnabled: Boolean(record.openai_setting_web_search_enabled ?? true),
    openaiChatApiKey: String(record.openai_chat_api_key ?? ""),
    openaiChatApiKeyConfigured: Boolean(record.openai_chat_api_key_configured),
    openaiChatBaseUrl: String(record.openai_chat_base_url ?? "https://api.openai.com/v1"),
    openaiChatModel: String(record.openai_chat_model ?? "gpt-4.1-mini"),
    openaiChatTemperature: Number(record.openai_chat_temperature ?? 0.35),
    openaiSettingTemperature: Number(record.openai_setting_temperature ?? 0.4),
    openaiSettingMaxTokens: Number(record.openai_setting_max_tokens ?? 900),
    openaiChatMaxTokens: Number(record.openai_chat_max_tokens ?? 800),
    openaiChatHistoryMessages: Number(record.openai_chat_history_messages ?? 8),
    openaiChatToolMaxRounds: Number(record.openai_chat_tool_max_rounds ?? 4),
    openaiEmbeddingModel: String(record.openai_embedding_model ?? "text-embedding-3-small"),
    openaiChatModelMultimodal: Boolean(record.openai_chat_model_multimodal),
    openaiTimeoutSeconds: Number(record.openai_timeout_seconds ?? 30),
    openaiPlanModelMultimodal: Boolean(record.openai_plan_model_multimodal),
    openaiPlanFallbackModel: String(record.openai_plan_fallback_model ?? ""),
    openaiPlanFallbackDisableTools: Boolean(record.openai_plan_fallback_disable_tools),
    showDebugInfo: Boolean(record.show_debug_info)
  };
}

function normalizeRuntimeCapabilitySignal(record: any): import("@vibe-learner/shared").RuntimeCapabilitySignal {
  const status = String(record?.status ?? "unknown");
  const source = String(record?.source ?? "unavailable");
  return {
    status:
      status === "supported" || status === "unsupported" || status === "unknown"
        ? status
        : "unknown",
    source:
      source === "metadata" || source === "model_name" || source === "unavailable"
        ? source
        : "unavailable",
    note: String(record?.note ?? "")
  };
}

function normalizeStreamReport(
  record: unknown,
  expectedDocumentId: string,
  expectedStreamKind: "document_process" | "learning_plan",
): StreamReport {
  const decoded = decodeStreamReport(record, {
    expectedDocumentId,
    expectedStreamKind,
  });
  for (const event of decoded.events) {
    if (event.stage !== "stream_completed" || event.committedProjection === null) {
      continue;
    }
    if (expectedStreamKind === "document_process") {
      normalizeDocument(event.committedProjection, expectedDocumentId);
    } else {
      normalizePlan(event.committedProjection, {
        expectedPlanId: event.terminalEvidence?.resourceId ?? undefined,
        expectedDocumentId,
        path: "stream_report.committed_projection",
      });
    }
  }
  return {
    ...decoded,
    events: decoded.events.map((event) => ({
      ...event,
      payload: compactPreviewValue(event.payload) as Record<string, unknown>,
      committedProjection:
        event.committedProjection === null
          ? null
          : compactPreviewValue(event.committedProjection) as Record<string, unknown>,
    })),
  };
}

function normalizePlan(
  plan: unknown,
  options: {
    expectedPlanId?: string;
    expectedDocumentId?: string;
    path?: string;
    requireHarnessTrace?: boolean;
  } = {},
): LearningPlan {
  return decodeLearningPlan(plan, options);
}

export async function listPersonas(): Promise<PersonaProfile[]> {
  const payload = await readJson<unknown>(
    await request(`${AI_BASE_URL()}/personas`)
  );
  return decodePersonaList(payload);
}

export async function listTavernRooms(
  input: { limit?: number; cursor?: string } = {}
): Promise<TavernRoomPage> {
  const params = new URLSearchParams();
  if (input.limit !== undefined) params.set("limit", String(input.limit));
  if (input.cursor) params.set("cursor", input.cursor);
  const suffix = params.toString();
  const payload = await readJson<unknown>(
    await request(`${AI_BASE_URL()}/tavern/rooms${suffix ? `?${suffix}` : ""}`)
  );
  return normalizeTavernRoomList(payload);
}

export async function createTavernRoom(
  input: CreateTavernRoomInput
): Promise<TavernRoomDetail> {
  const payload = await readJson<any>(
    await request(`${AI_BASE_URL()}/tavern/rooms`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        title: input.title,
        persona_ids: input.personaIds,
        scene_profile: serializeSceneProfile(input.sceneProfile),
        opening_prompt: input.openingPrompt ?? "",
        harness_policy: input.harnessPolicy
          ? {
              version: input.harnessPolicy.version,
              max_character_messages: input.harnessPolicy.maxCharacterMessages,
              max_reply_characters: input.harnessPolicy.maxReplyCharacters,
              context_message_limit: input.harnessPolicy.contextMessageLimit,
              prevent_speaker_impersonation:
                input.harnessPolicy.preventSpeakerImpersonation,
            }
          : undefined,
        idempotency_key: input.idempotencyKey,
      }),
    })
  );
  return normalizeTavernRoomDetail(payload);
}

export async function getTavernRoom(input: {
  roomId: string;
  afterSequence?: number;
  beforeSequence?: number;
  tail?: boolean;
  limit?: number;
}): Promise<TavernRoomDetail> {
  const query = new URLSearchParams();
  if (input.afterSequence !== undefined) {
    query.set("after_sequence", String(input.afterSequence));
  }
  if (input.beforeSequence !== undefined) {
    query.set("before_sequence", String(input.beforeSequence));
  }
  if (input.tail) {
    query.set("tail", "true");
  }
  if (input.limit !== undefined) {
    query.set("limit", String(input.limit));
  }
  const suffix = query.toString();
  const payload = await readJson<any>(
    await request(
      `${AI_BASE_URL()}/tavern/rooms/${input.roomId}${suffix ? `?${suffix}` : ""}`
    )
  );
  return normalizeTavernRoomDetail(payload, input.roomId);
}

export async function updateTavernRoom(
  roomId: string,
  input: UpdateTavernRoomInput
): Promise<TavernRoomDetail> {
  const body: Record<string, unknown> = {
    expected_revision: input.expectedRoomRevision,
  };
  if (input.title !== undefined) body.title = input.title;
  if (input.personaIds !== undefined) body.persona_ids = input.personaIds;
  if (Object.prototype.hasOwnProperty.call(input, "sceneProfile")) {
    body.scene_profile = serializeSceneProfile(input.sceneProfile ?? null);
  }
  if (input.status !== undefined) body.status = input.status;
  const payload = await readJson<any>(
    await request(`${AI_BASE_URL()}/tavern/rooms/${roomId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    })
  );
  return normalizeTavernRoomDetail(payload, roomId);
}

export async function deleteTavernRoom(
  roomId: string,
  expectedRoomRevision: number
): Promise<void> {
  await readJson<{ deleted_room_id: string }>(
    await request(
      `${AI_BASE_URL()}/tavern/rooms/${roomId}?expected_revision=${expectedRoomRevision}`,
      { method: "DELETE" }
    )
  );
}

export async function listTavernRuns(
  roomId: string,
  limit = 50
): Promise<TavernRun[]> {
  const payload = await readJson<unknown>(
    await request(`${AI_BASE_URL()}/tavern/rooms/${roomId}/runs?limit=${limit}`)
  );
  return normalizeTavernRunList(payload, roomId);
}

export async function getTavernRunRecovery(
  roomId: string,
  limit = 50
): Promise<TavernRunRecoveryChain[]> {
  const payload = await readJson<unknown>(
    await request(`${AI_BASE_URL()}/tavern/rooms/${roomId}/run-recovery?limit=${limit}`)
  );
  return normalizeTavernRunRecovery(payload, roomId);
}

function serializeTavernTurnInput(input: TavernTurnInput) {
  return {
    input:
      input.input.kind === "user_message"
        ? { kind: "user_message", content: input.input.content }
        : { kind: "continue", anchor_message_id: input.input.anchorMessageId },
    mode: input.mode,
    target_persona_ids: input.targetPersonaIds,
    guidance: input.guidance ?? "",
    idempotency_key: input.idempotencyKey,
    expected_room_revision: input.expectedRoomRevision,
  };
}

export async function runTavernTurn(
  roomId: string,
  input: TavernTurnInput
): Promise<TavernTurnResult> {
  const payload = await requestTavernMutationWithRecovery(
    `${AI_BASE_URL()}/tavern/rooms/${roomId}/turns`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(serializeTavernTurnInput(input)),
    }
  );
  return normalizeTavernTurnResult(payload, roomId);
}

export async function retryTavernRun(
  roomId: string,
  runId: string,
  input: RetryTavernRunInput
): Promise<TavernTurnResult> {
  const payload = await requestTavernMutationWithRecovery(
    `${AI_BASE_URL()}/tavern/rooms/${roomId}/runs/${runId}/retry`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        idempotency_key: input.idempotencyKey,
        expected_room_revision: input.expectedRoomRevision,
      }),
    }
  );
  return normalizeTavernTurnResult(payload, roomId);
}

export async function resumeTavernRun(
  roomId: string,
  runId: string
): Promise<TavernTurnResult> {
  const payload = await readJson<any>(
    await request(`${AI_BASE_URL()}/tavern/rooms/${roomId}/runs/${runId}/resume`, {
      method: "POST",
    })
  );
  return normalizeTavernTurnResult(payload, roomId);
}

export async function cancelTavernRun(
  roomId: string,
  runId: string
): Promise<TavernTurnResult> {
  const payload = await readJson<any>(
    await request(`${AI_BASE_URL()}/tavern/rooms/${roomId}/runs/${runId}/cancel`, {
      method: "POST",
    })
  );
  return normalizeTavernTurnResult(payload, roomId);
}

export async function createPersona(input: CreatePersonaInput): Promise<PersonaProfile> {
  const payload = await readJson<unknown>(
    await request(`${AI_BASE_URL()}/personas`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify(serializePersonaInput(input))
    })
  );
  return decodePersonaProfile(payload, { expectedSource: "user" });
}

export async function updatePersona(
  personaId: string,
  input: UpdatePersonaInput
): Promise<PersonaProfile> {
  const encodedPersonaId = encodeURIComponent(personaId);
  const payload = await readJson<unknown>(
    await request(`${AI_BASE_URL()}/personas/${encodedPersonaId}`, {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify(serializePersonaInput(input))
    })
  );
  return decodePersonaProfile(payload, {
    expectedPersonaId: personaId,
    expectedSource: "user",
  });
}

export async function deletePersona(personaId: string, expectedRevision: number): Promise<void> {
  const encodedPersonaId = encodeURIComponent(personaId);
  const payload = await readJson<unknown>(
    await request(
      `${AI_BASE_URL()}/personas/${encodedPersonaId}?expected_revision=${expectedRevision}`,
      {
      method: "DELETE"
      },
    )
  );
  decodeDeletedIdentity(payload, {
    wireField: "deleted_persona_id",
    expectedId: personaId,
    path: "persona_delete",
  });
}

export async function getPersonaAssets(personaId: string): Promise<PersonaAssets> {
  const encodedPersonaId = encodeURIComponent(personaId);
  const payload = await readJson<unknown>(
    await request(`${AI_BASE_URL()}/personas/${encodedPersonaId}/assets`)
  );
  return decodePersonaAssets(payload, personaId);
}

export async function listPersonaCards(): Promise<PersonaCard[]> {
  const payload = await readJson<unknown>(
    await request(`${AI_BASE_URL()}/persona-cards`)
  );
  return decodePersonaCardList(payload);
}

export async function createPersonaCardsBatch(
  items: CreatePersonaCardInput[]
): Promise<PersonaCard[]> {
  const payload = await readJson<unknown>(
    await request(`${AI_BASE_URL()}/persona-cards/batch`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        items: items.map(serializePersonaCardInput)
      })
    })
  );
  return decodePersonaCardList(payload, "persona_card_batch");
}

export async function deletePersonaCard(cardId: string): Promise<void> {
  const payload = await readJson<unknown>(
    await request(`${AI_BASE_URL()}/persona-cards/${cardId}`, {
      method: "DELETE"
    })
  );
  decodeDeletedIdentity(payload, {
    wireField: "deleted_persona_card_id",
    expectedId: cardId,
    path: "persona_card_delete",
  });
}

export async function generatePersonaCards(input: {
  mode: PersonaCardGenerationMode;
  inputText: string;
  count?: number | null;
}): Promise<PersonaCardGenerateResult> {
  const requestBody: Record<string, unknown> = {
    mode: input.mode,
    input_text: input.inputText
  };
  if (typeof input.count === "number" && Number.isFinite(input.count)) {
    requestBody.count = input.count;
  }
  const payload = await readJson<unknown>(
    await request(`${AI_BASE_URL()}/persona-cards/generate`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify(requestBody)
    })
  );
  return decodePersonaCardGenerateResult(payload, { expectedMode: input.mode });
}

export async function generateSceneTree(input: {
  mode: "keywords" | "long_text";
  inputText: string;
  layerCount?: number | null;
}): Promise<SceneTreeGenerateResult> {
  const requestBody: Record<string, unknown> = {
    mode: input.mode,
    input_text: input.inputText
  };
  if (typeof input.layerCount === "number" && Number.isFinite(input.layerCount)) {
    requestBody.layer_count = input.layerCount;
  }
  const payload = await readJson<unknown>(
    await request(`${AI_BASE_URL()}/scene-setup/generate`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify(requestBody)
    })
  );
  return decodeSceneTreeGenerateResult(payload, { expectedMode: input.mode });
}

export async function assistPersonaSetting(
  input: PersonaSettingAssistInput
): Promise<PersonaSettingAssistOutput> {
  const payload = await readJson<unknown>(
    await request(`${AI_BASE_URL()}/personas/assist-setting`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        name: input.name,
        summary: input.summary,
        slots: input.slots.map(serializeSlot),
        rewrite_strength: input.rewriteStrength
      })
    })
  );
  return decodePersonaSettingAssistOutput(payload);
}

export async function assistPersonaSlot(
  input: PersonaSlotAssistInput
): Promise<PersonaSlotAssistOutput> {
  const payload = await readJson<unknown>(
    await request(`${AI_BASE_URL()}/personas/assist-slot`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        name: input.name,
        summary: input.summary,
        slot: serializeSlot(input.slot),
        rewrite_strength: input.rewriteStrength
      })
    })
  );
  return decodePersonaSlotAssistOutput(payload, input.slot);
}

export async function listDocuments(): Promise<DocumentRecord[]> {
  const payload = await readJson<unknown>(
    await request(`${AI_BASE_URL()}/documents`)
  );
  return decodeDocumentList(payload).map((document) => ({
    ...document,
    previewExcerpt: compactPreviewString(document.previewExcerpt, 240),
  }));
}

export async function getDocumentDebug(documentId: string): Promise<DocumentDebugRecord> {
  const payload = await readJson<unknown>(
    await request(`${AI_BASE_URL()}/documents/${documentId}/debug`)
  );
  return normalizeDebugRecord(payload, documentId);
}

export async function getDocumentPlanningContext(
  documentId: string
): Promise<DocumentPlanningContext> {
  const payload = await readJson<unknown>(
    await request(`${AI_BASE_URL()}/documents/${documentId}/planning-context`)
  );
  return normalizePlanningContext(payload, documentId);
}

export async function getDocumentPlanningTrace(
  documentId: string
): Promise<DocumentPlanningTraceResponse> {
  const payload = await readJson<unknown>(
    await request(`${AI_BASE_URL()}/documents/${documentId}/planning-trace`)
  );
  return normalizePlanningTraceResponse(payload, documentId);
}

export async function getModelToolConfig(): Promise<ModelToolConfig> {
  const payload = await readJson<any>(
    await request(`${AI_BASE_URL()}/model-tools/config`)
  );
  return normalizeModelToolConfig(payload);
}

export async function updateModelToolConfig(
  toggles: ModelToolToggle[]
): Promise<ModelToolConfig> {
  const payload = await readJson<any>(
    await request(`${AI_BASE_URL()}/model-tools/config`, {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        toggles: toggles.map((toggle) => ({
          stage_name: toggle.stageName,
          tool_name: toggle.toolName,
          enabled: toggle.enabled
        }))
      })
    })
  );
  return normalizeModelToolConfig(payload);
}

export async function getRuntimeSettings(): Promise<RuntimeSettings> {
  const payload = await readJson<any>(
    await request(`${AI_BASE_URL()}/runtime-settings`)
  );
  return normalizeRuntimeSettings(payload);
}

export async function getSceneSetupState(): Promise<SceneSetupStatePayload> {
  const payload = await readJson<unknown>(
    await request(`${AI_BASE_URL()}/scene-setup`)
  );
  return decodeSceneSetupState(payload);
}

export async function updateSceneSetupState(input: {
  expectedRevision: number;
  sceneLayers: unknown[];
  selectedLayerId: string;
  collapsedLayerIds: string[];
  sceneName?: string;
  sceneSummary?: string;
}): Promise<SceneSetupStatePayload> {
  const payload = await readJson<unknown>(
    await request(`${AI_BASE_URL()}/scene-setup`, {
      method: "PUT",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        contract_version: "scene-committed-save-v1",
        expected_revision: input.expectedRevision,
        scene_name: input.sceneName ?? "",
        scene_summary: input.sceneSummary ?? "",
        scene_layers: serializeSceneTree(input.sceneLayers as import("@vibe-learner/shared").SceneTreeNode[]),
        selected_layer_id: input.selectedLayerId,
        collapsed_layer_ids: input.collapsedLayerIds
      })
    })
  );
  return decodeSceneSetupState(payload, {
    expectedRevision: input.expectedRevision + 1,
  });
}

export async function listSceneLibrary(): Promise<SceneLibraryItemPayload[]> {
  const payload = await readJson<unknown>(
    await request(`${AI_BASE_URL()}/scene-library`)
  );
  return decodeSceneLibraryList(payload);
}

export async function getSceneLibraryItem(sceneId: string): Promise<SceneLibraryItemPayload> {
  const payload = await readJson<unknown>(
    await request(`${AI_BASE_URL()}/scene-library/${sceneId}`)
  );
  return decodeSceneLibraryItem(payload, { expectedSceneId: sceneId });
}

export async function createSceneLibraryItem(input: {
  sceneName: string;
  sceneSummary: string;
  sceneLayers: unknown[];
  selectedLayerId: string;
  collapsedLayerIds: string[];
}): Promise<SceneLibraryItemPayload> {
  const payload = await readJson<unknown>(
    await request(`${AI_BASE_URL()}/scene-library`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        contract_version: "scene-committed-save-v1",
        expected_revision: 0,
        scene_name: input.sceneName,
        scene_summary: input.sceneSummary,
        scene_layers: serializeSceneTree(input.sceneLayers as import("@vibe-learner/shared").SceneTreeNode[]),
        selected_layer_id: input.selectedLayerId,
        collapsed_layer_ids: input.collapsedLayerIds
      })
    })
  );
  return decodeSceneLibraryItem(payload, { expectedRevision: 1 });
}

export async function updateSceneLibraryItem(sceneId: string, input: {
  expectedRevision: number;
  sceneName: string;
  sceneSummary: string;
  sceneLayers: unknown[];
  selectedLayerId: string;
  collapsedLayerIds: string[];
}): Promise<SceneLibraryItemPayload> {
  const payload = await readJson<unknown>(
    await request(`${AI_BASE_URL()}/scene-library/${sceneId}`, {
      method: "PUT",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        contract_version: "scene-committed-save-v1",
        expected_revision: input.expectedRevision,
        scene_name: input.sceneName,
        scene_summary: input.sceneSummary,
        scene_layers: serializeSceneTree(input.sceneLayers as import("@vibe-learner/shared").SceneTreeNode[]),
        selected_layer_id: input.selectedLayerId,
        collapsed_layer_ids: input.collapsedLayerIds
      })
    })
  );
  return decodeSceneLibraryItem(payload, {
    expectedSceneId: sceneId,
    expectedRevision: input.expectedRevision + 1,
  });
}

export async function deleteSceneLibraryItem(sceneId: string): Promise<{ deletedSceneId: string }> {
  const payload = await readJson<unknown>(
    await request(`${AI_BASE_URL()}/scene-library/${sceneId}`, {
      method: "DELETE"
    })
  );
  return {
    deletedSceneId: decodeDeletedIdentity(payload, {
      wireField: "deleted_scene_id",
      expectedId: sceneId,
      path: "scene_library_delete",
    }),
  };
}

export async function listReusableSceneNodes(): Promise<ReusableSceneNodePayload[]> {
  const payload = await readJson<unknown>(
    await request(`${AI_BASE_URL()}/reusable-scene-nodes`)
  );
  return decodeReusableSceneNodeList(payload);
}

export async function createReusableSceneNode(input: {
  nodeType: "layer" | "object";
  title: string;
  summary?: string;
  tags?: string[];
  reuseId?: string;
  reuseHint?: string;
  sourceSceneId?: string;
  sourceSceneName?: string;
  layerNode?: import("@vibe-learner/shared").SceneTreeNode | null;
  objectNode?: import("@vibe-learner/shared").SceneObjectSnapshot | null;
}): Promise<ReusableSceneNodePayload> {
  const payload = await readJson<unknown>(
    await request(`${AI_BASE_URL()}/reusable-scene-nodes`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        node_type: input.nodeType,
        title: input.title,
        summary: input.summary ?? "",
        tags: input.tags ?? [],
        reuse_id: input.reuseId ?? "",
        reuse_hint: input.reuseHint ?? "",
        source_scene_id: input.sourceSceneId ?? "",
        source_scene_name: input.sourceSceneName ?? "",
        layer_node: input.layerNode ? serializeSceneTree([input.layerNode])[0] : null,
        object_node: input.objectNode
          ? {
              id: input.objectNode.id,
              name: input.objectNode.name,
              description: input.objectNode.description,
              interaction: input.objectNode.interaction,
              tags: input.objectNode.tags,
              reuse_id: input.objectNode.reuseId,
              reuse_hint: input.objectNode.reuseHint,
            }
          : null,
      })
    })
  );
  return decodeReusableSceneNode(payload);
}

export async function deleteReusableSceneNode(nodeId: string): Promise<{ deletedReusableSceneNodeId: string }> {
  const payload = await readJson<unknown>(
    await request(`${AI_BASE_URL()}/reusable-scene-nodes/${nodeId}`, {
      method: "DELETE"
    })
  );
  return {
    deletedReusableSceneNodeId: decodeDeletedIdentity(payload, {
      wireField: "deleted_reusable_scene_node_id",
      expectedId: nodeId,
      path: "reusable_scene_node_delete",
    }),
  };
}

export async function updateRuntimeSettings(
  patch: RuntimeSettingsPatch
): Promise<RuntimeSettings> {
  const payload = await readJson<any>(
    await request(`${AI_BASE_URL()}/runtime-settings`, {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        plan_provider: patch.planProvider,
        openai_api_key: patch.openaiApiKey,
        openai_base_url: patch.openaiBaseUrl,
        openai_plan_api_key: patch.openaiPlanApiKey,
        openai_plan_base_url: patch.openaiPlanBaseUrl,
        openai_plan_model: patch.openaiPlanModel,
        openai_setting_api_key: patch.openaiSettingApiKey,
        openai_setting_base_url: patch.openaiSettingBaseUrl,
        openai_setting_model: patch.openaiSettingModel,
        openai_setting_web_search_enabled: patch.openaiSettingWebSearchEnabled,
        openai_chat_api_key: patch.openaiChatApiKey,
        openai_chat_base_url: patch.openaiChatBaseUrl,
        openai_chat_model: patch.openaiChatModel,
        openai_chat_temperature: patch.openaiChatTemperature,
        openai_setting_temperature: patch.openaiSettingTemperature,
        openai_setting_max_tokens: patch.openaiSettingMaxTokens,
        openai_chat_max_tokens: patch.openaiChatMaxTokens,
        openai_chat_history_messages: patch.openaiChatHistoryMessages,
        openai_chat_tool_max_rounds: patch.openaiChatToolMaxRounds,
        openai_embedding_model: patch.openaiEmbeddingModel,
        openai_chat_model_multimodal: patch.openaiChatModelMultimodal,
        openai_timeout_seconds: patch.openaiTimeoutSeconds,
        openai_plan_model_multimodal: patch.openaiPlanModelMultimodal,
        openai_plan_fallback_model: patch.openaiPlanFallbackModel,
        openai_plan_fallback_disable_tools: patch.openaiPlanFallbackDisableTools,
        show_debug_info: patch.showDebugInfo
      })
    })
  );
  return normalizeRuntimeSettings(payload);
}

export async function applyRuntimeSessionSecrets(patch: {
  openaiApiKey?: string;
  openaiPlanApiKey?: string;
  openaiSettingApiKey?: string;
  openaiChatApiKey?: string;
}): Promise<RuntimeSettings> {
  const payload = await readJson<any>(
    await request(`${AI_BASE_URL()}/runtime-settings/session-secrets`, {
      method: "PUT",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        openai_api_key: patch.openaiApiKey,
        openai_plan_api_key: patch.openaiPlanApiKey,
        openai_setting_api_key: patch.openaiSettingApiKey,
        openai_chat_api_key: patch.openaiChatApiKey
      })
    })
  );
  return normalizeRuntimeSettings(payload);
}

export async function clearRuntimeSessionSecrets(): Promise<RuntimeSettings> {
  const payload = await readJson<any>(
    await request(`${AI_BASE_URL()}/runtime-settings/session-secrets`, {
      method: "DELETE"
    })
  );
  return normalizeRuntimeSettings(payload);
}

export async function probeRuntimeOpenAIModels(input: {
  apiKey: string;
  baseUrl: string;
  model?: string;
  features?: RuntimeFeatureProbeName[];
}): Promise<RuntimeOpenAIProbeResult> {
  const payload = await readJson<any>(
    await request(`${AI_BASE_URL()}/runtime-settings/check-openai-models`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        api_key: input.apiKey,
        base_url: input.baseUrl,
        model: input.model ?? "",
        features: input.features ?? []
      })
    })
  );
  return {
    available: Boolean(payload.available),
    models: Array.isArray(payload.models)
      ? payload.models.map((item: unknown) => String(item))
      : [],
    capabilities:
      payload.capabilities && typeof payload.capabilities === "object"
        ? Object.fromEntries(
            Object.entries(payload.capabilities).map(([modelId, capability]) => [
              String(modelId),
              {
                inputModalities: Array.isArray((capability as any)?.input_modalities)
                  ? (capability as any).input_modalities.map((item: unknown) => String(item))
                  : [],
                outputModalities: Array.isArray((capability as any)?.output_modalities)
                  ? (capability as any).output_modalities.map((item: unknown) => String(item))
                  : [],
                toolTypes: Array.isArray((capability as any)?.tool_types)
                  ? (capability as any).tool_types.map((item: unknown) => String(item))
                  : [],
                multimodal: normalizeRuntimeCapabilitySignal((capability as any)?.multimodal),
                webSearch: normalizeRuntimeCapabilitySignal((capability as any)?.web_search)
              }
            ])
          )
        : {},
    featureReadiness:
      payload.feature_readiness && typeof payload.feature_readiness === "object"
        ? Object.fromEntries(
            Object.entries(payload.feature_readiness).map(([feature, readiness]) => {
              const status = String((readiness as any)?.status ?? "not_tested");
              return [
                feature,
                {
                  model: String((readiness as any)?.model ?? ""),
                  status:
                    status === "ready" || status === "unsupported" || status === "failed"
                      ? status
                      : "not_tested",
                  code: String((readiness as any)?.code ?? ""),
                  note: String((readiness as any)?.note ?? ""),
                  parameterAdjustments: Array.isArray((readiness as any)?.parameter_adjustments)
                    ? (readiness as any).parameter_adjustments.map((item: unknown) => String(item))
                    : []
                }
              ];
            })
          )
        : {},
    error: String(payload.error ?? "")
  };
}

export async function getDocumentProcessEvents(documentId: string): Promise<StreamReport> {
  const payload = await readJson<unknown>(
    await request(`${AI_BASE_URL()}/documents/${documentId}/process-events`)
  );
  return normalizeStreamReport(payload, documentId, "document_process");
}

export async function getDocumentPlanEvents(documentId: string): Promise<StreamReport> {
  const payload = await readJson<unknown>(
    await request(`${AI_BASE_URL()}/documents/${documentId}/plan-events`)
  );
  return normalizeStreamReport(payload, documentId, "learning_plan");
}

export async function uploadDocument(
  file: File,
  options?: { signal?: AbortSignal }
): Promise<DocumentRecord> {
  const form = new FormData();
  form.append("file", file);
  const payload = await readJson<unknown>(
    await request(`${AI_BASE_URL()}/documents`, {
      method: "POST",
      body: form,
      signal: options?.signal,
    })
  );
  return normalizeDocument(payload);
}

export async function uploadAndProcessDocument(file: File): Promise<DocumentRecord> {
  const uploaded = await uploadDocument(file);
  return processDocument(uploaded.id);
}

export async function processDocument(
  documentId: string,
  options?: {
    forceOcr?: boolean;
  }
): Promise<DocumentRecord> {
  const payload = await readJson<unknown>(
    await request(`${AI_BASE_URL()}/documents/${documentId}/process`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        force_ocr: Boolean(options?.forceOcr)
      })
    })
  );
  const decoded = decodeDocumentRecord(payload, documentId, "document", true);
  return {
    ...decoded,
    previewExcerpt: compactPreviewString(decoded.previewExcerpt, 240),
  };
}

export async function processDocumentStream(
  documentId: string,
  options: {
    forceOcr?: boolean;
    signal?: AbortSignal;
  },
  onEvent: (event: StreamEvent) => void
): Promise<DocumentRecord> {
  const response = await request(`${AI_BASE_URL()}/documents/${documentId}/process/stream`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    signal: options.signal,
    body: JSON.stringify({
      force_ocr: Boolean(options.forceOcr)
    })
  });
  if (!response.ok || !response.body) {
    const text = await response.text();
    throw new Error(text || `HTTP ${response.status}`);
  }

  let finalDocument: DocumentRecord | null = null;
  const machine = new StrictStreamStateMachine({
    streamKind: "document_process",
    subject: { subjectType: "document", subjectId: documentId },
  });
  const terminal = await consumeVersionedStream(response.body, machine, (event) => {
    if (event.stage === "stream_completed") {
      const decoded = decodeDocumentRecord(
        event.committedProjection,
        documentId,
        "stream.document",
        true,
      );
      finalDocument = {
        ...decoded,
        previewExcerpt: compactPreviewString(decoded.previewExcerpt, 240),
      };
    }
    onEvent(event);
  });
  if (terminal.stage === "stream_cancelled") {
    throw new DOMException("stream_interrupted", "AbortError");
  }
  if (terminal.stage === "stream_error") {
    throw new Error(formatStreamErrorPayload(terminal.payload, "processing_stream_error"));
  }
  if (!finalDocument) {
    throw new Error("processing_stream_committed_terminal_without_document");
  }
  return finalDocument;
}

function createLearningPlanRequestId(): string {
  const suffix = typeof globalThis.crypto?.randomUUID === "function"
    ? globalThis.crypto.randomUUID()
    : `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`;
  return `learning-plan-${suffix}`;
}

export async function createLearningPlan(goal: LearningGoal): Promise<LearningPlan> {
  const clientRequestId = goal.clientRequestId?.trim() || createLearningPlanRequestId();
  const sceneSummary = goal.sceneProfileSummary ?? goal.sceneProfile?.summary ?? "";
  const payload = await readJson<unknown>(
    await request(`${AI_BASE_URL()}/learning-plans`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        document_id: goal.documentId ?? "",
        persona_id: goal.personaId,
        client_request_id: clientRequestId,
        expected_document_updated_at: goal.expectedDocumentUpdatedAt ?? "",
        objective: goal.objective,
        scene_profile_summary: sceneSummary,
        scene_profile: serializeSceneProfile(goal.sceneProfile)
      })
    })
  );
  return normalizePlan(payload, {
    expectedDocumentId: goal.documentId ?? "",
    requireHarnessTrace: true,
  });
}

export async function listLearningPlans(): Promise<LearningPlan[]> {
  const payload = await readJson<unknown>(
    await request(`${AI_BASE_URL()}/learning-plans`)
  );
  return decodeLearningPlanList(payload);
}

export async function updateDocumentStudyUnitTitle(
  documentId: string,
  studyUnitId: string,
  title: string
): Promise<DocumentStudyUnitUpdatePayload> {
  const payload = await readJson<unknown>(
    await request(`${AI_BASE_URL()}/documents/${documentId}/study-units/${studyUnitId}`, {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        title
      })
    })
  );
  const decoded = decodeDocumentStudyUnitUpdate(payload, documentId);
  if (!decoded.document.studyUnits.some((unit) => unit.id === studyUnitId)) {
    throw new DocumentDecodeError(
      "document_study_unit_update.document.study_units",
      `missing_updated_study_unit_${studyUnitId}`,
    );
  }
  return decoded;
}

export async function updateLearningPlanTitle(
  planId: string,
  courseTitle: string
): Promise<LearningPlan> {
  const payload = await readJson<unknown>(
    await request(`${AI_BASE_URL()}/learning-plans/${planId}`, {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        course_title: courseTitle
      })
    })
  );
  return normalizePlan(payload, { expectedPlanId: planId });
}

export async function updateLearningPlanProgress(input: {
  planId: string;
  scheduleIds: string[];
  status: string;
  note?: string;
}): Promise<LearningPlan> {
  const payload = await readJson<unknown>(
    await request(`${AI_BASE_URL()}/learning-plans/${input.planId}/progress`, {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        schedule_ids: input.scheduleIds,
        status: input.status,
        note: input.note ?? ""
      })
    })
  );
  return normalizePlan(payload, { expectedPlanId: input.planId });
}

export async function answerLearningPlanQuestion(input: {
  planId: string;
  questionId: string;
  answer: string;
}): Promise<LearningPlan> {
  const payload = await readJson<unknown>(
    await request(
      `${AI_BASE_URL()}/learning-plans/${input.planId}/planning-questions/${input.questionId}`,
      {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          answer: input.answer
        })
      }
    )
  );
  return normalizePlan(payload, { expectedPlanId: input.planId });
}

export async function deleteLearningPlan(planId: string): Promise<void> {
  await readJson<{ deleted_plan_id: string }>(
    await request(`${AI_BASE_URL()}/learning-plans/${planId}`, {
      method: "DELETE"
    })
  );
}

export async function createLearningPlanStream(
  goal: LearningGoal,
  onEvent: (event: StreamEvent) => void,
  options?: { signal?: AbortSignal }
): Promise<LearningPlan> {
  const clientRequestId = goal.clientRequestId?.trim() || createLearningPlanRequestId();
  const sceneSummary = goal.sceneProfileSummary ?? goal.sceneProfile?.summary ?? "";
  const response = await request(`${AI_BASE_URL()}/learning-plans/stream`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    signal: options?.signal,
    body: JSON.stringify({
      document_id: goal.documentId ?? "",
      persona_id: goal.personaId,
      client_request_id: clientRequestId,
      expected_document_updated_at: goal.expectedDocumentUpdatedAt ?? "",
      objective: goal.objective,
      scene_profile_summary: sceneSummary,
      scene_profile: serializeSceneProfile(goal.sceneProfile)
    })
  });
  if (!response.ok || !response.body) {
    const text = await response.text();
    throw new Error(text || `HTTP ${response.status}`);
  }

  let finalPlan: LearningPlan | null = null;
  const expectedDocumentId = goal.documentId ?? "";
  const machine = new StrictStreamStateMachine({
    streamKind: "learning_plan",
    subject: expectedDocumentId
      ? { subjectType: "document", subjectId: expectedDocumentId }
      : { subjectType: "learning_plan_request", subjectId: clientRequestId },
  });
  const terminal = await consumeVersionedStream(response.body, machine, (event) => {
    if (event.stage === "stream_completed") {
      finalPlan = normalizePlan(event.committedProjection, {
        expectedPlanId: event.terminalEvidence?.resourceId ?? undefined,
        expectedDocumentId,
        path: "stream.committed_projection",
        requireHarnessTrace: true,
      });
    }
    onEvent(event);
  });
  if (terminal.stage === "stream_cancelled") {
    throw new DOMException("stream_interrupted", "AbortError");
  }
  if (terminal.stage === "stream_error") {
    throw new Error(formatStreamErrorPayload(terminal.payload, "learning_plan_stream_error"));
  }
  if (!finalPlan) {
    throw new Error("learning_plan_stream_committed_terminal_without_plan");
  }
  return finalPlan;
}

export async function createStudySession(input: {
  documentId: string;
  personaId: string;
  planId?: string | null;
  sceneProfile?: import("@vibe-learner/shared").SceneProfile | null;
  studyUnitId: string;
  studyUnitTitle?: string;
  themeHint?: string;
}): Promise<StudySessionRecord> {
  const payload = await readJson<unknown>(
    await request(`${AI_BASE_URL()}/study-sessions`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        document_id: input.documentId,
        persona_id: input.personaId,
        plan_id: input.planId ?? null,
        scene_profile: serializeSceneProfile(input.sceneProfile),
        study_unit_id: input.studyUnitId,
        study_unit_title: input.studyUnitTitle ?? "",
        section_id: input.studyUnitId,
        section_title: input.studyUnitTitle ?? "",
        theme_hint: input.themeHint ?? ""
      })
    })
  );
  return decodeStudySession(payload, {
    expectedDocumentId: input.documentId,
    expectedPersonaId: input.personaId,
    expectedPlanId: input.planId ?? null,
    expectedStudyUnitId: input.studyUnitId,
  });
}

export async function cancelStreamRun(streamId: string): Promise<void> {
  await readJson<{ stream_id: string }>(
    await request(`${AI_BASE_URL()}/stream-runs/${streamId}/cancel`, {
      method: "POST",
    })
  );
}

export async function listStudySessions(input: {
  documentId?: string;
  personaId?: string;
  planId?: string;
  studyUnitId?: string;
}): Promise<StudySessionRecord[]> {
  const query = new URLSearchParams();
  if (input.documentId) query.set("document_id", input.documentId);
  if (input.personaId) query.set("persona_id", input.personaId);
  if (input.planId) query.set("plan_id", input.planId);
  if (input.studyUnitId) {
    query.set("study_unit_id", input.studyUnitId);
    query.set("section_id", input.studyUnitId);
  }
  const suffix = query.toString();
  const payload = await readJson<unknown>(
    await request(`${AI_BASE_URL()}/study-sessions${suffix ? `?${suffix}` : ""}`)
  );
  return decodeStudySessionList(payload, {
    ...(input.documentId ? { expectedDocumentId: input.documentId } : {}),
    ...(input.personaId ? { expectedPersonaId: input.personaId } : {}),
    ...(input.planId ? { expectedPlanId: input.planId } : {}),
    ...(input.studyUnitId ? { expectedStudyUnitId: input.studyUnitId } : {}),
  });
}

export async function getStudySession(sessionId: string): Promise<StudySessionRecord> {
  const payload = await readJson<unknown>(
    await request(`${AI_BASE_URL()}/study-sessions/${sessionId}`)
  );
  return decodeStudySession(payload, { expectedSessionId: sessionId });
}

export async function updateStudySessionStudyUnit(input: {
  sessionId: string;
  studyUnitId?: string;
  sceneProfile?: import("@vibe-learner/shared").SceneProfile | null;
}): Promise<StudySessionRecord> {
  const body: Record<string, unknown> = {};
  if (typeof input.studyUnitId === "string") {
    body.study_unit_id = input.studyUnitId;
    body.section_id = input.studyUnitId;
  }
  if (Object.prototype.hasOwnProperty.call(input, "sceneProfile")) {
    body.scene_profile = serializeSceneProfile(input.sceneProfile ?? null);
  }
  const payload = await readJson<unknown>(
    await request(`${AI_BASE_URL()}/study-sessions/${input.sessionId}`, {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify(body)
    })
  );
  return decodeStudySession(payload, {
    expectedSessionId: input.sessionId,
    ...(input.studyUnitId ? { expectedStudyUnitId: input.studyUnitId } : {}),
  });
}

export async function cancelStudySessionFollowUps(input: {
  sessionId: string;
}): Promise<StudySessionRecord> {
  const payload = await readJson<unknown>(
    await request(`${AI_BASE_URL()}/study-sessions/${input.sessionId}/follow-ups/cancel`, {
      method: "POST",
    })
  );
  return decodeStudySession(payload, {
    expectedSessionId: input.sessionId,
    requireNoPendingFollowUps: true,
  });
}

export async function sendStudyMessage(input: {
  sessionId: string;
  clientRequestId: string;
  expectedSessionRevision: number;
  message: string;
  messageKind?: string;
  followUpId?: string;
  hiddenMessagePrefix?: string;
  attachments?: File[];
}): Promise<StudyChatOperationResponse> {
  const hasAttachments = Boolean(input.attachments?.length);
  const response = hasAttachments
    ? await request(`${AI_BASE_URL()}/study-sessions/${input.sessionId}/chat-with-attachments`, {
        method: "POST",
        body: (() => {
          const form = new FormData();
          form.set("message", input.message);
          form.set("client_request_id", input.clientRequestId);
          form.set("expected_session_revision", String(input.expectedSessionRevision));
          form.set("message_kind", input.messageKind ?? "learner");
          form.set("follow_up_id", input.followUpId ?? "");
          form.set("hidden_message_prefix", input.hiddenMessagePrefix ?? "");
          (input.attachments ?? []).forEach((file) => {
            form.append("files", file);
          });
          return form;
        })()
      })
    : await request(`${AI_BASE_URL()}/study-sessions/${input.sessionId}/chat`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          client_request_id: input.clientRequestId,
          expected_session_revision: input.expectedSessionRevision,
          message: input.message,
          message_kind: input.messageKind ?? "learner",
          follow_up_id: input.followUpId ?? "",
          hidden_message_prefix: input.hiddenMessagePrefix ?? "",
        })
      });
  const payload = await readJson<unknown>(response);
  return decodeStudyChatOperationResponse(payload, {
    sessionId: input.sessionId,
    clientRequestId: input.clientRequestId,
  });
}

export async function getStudyChatOperation(input: {
  sessionId: string;
  clientRequestId: string;
}): Promise<StudyChatOperationResponse> {
  const payload = await readJson<unknown>(
    await request(
      `${AI_BASE_URL()}/study-sessions/${encodeURIComponent(input.sessionId)}/chat-operations/${encodeURIComponent(input.clientRequestId)}`,
    ),
  );
  return decodeStudyChatOperationResponse(payload, input);
}

function decodeStudyChatOperationResponse(
  payload: unknown,
  expected: { sessionId: string; clientRequestId: string },
): StudyChatOperationResponse {
  return decodeStudyChatOperationReceipt(payload, {
    path: "study_chat_operation",
    expectedSessionId: expected.sessionId,
    expectedClientRequestId: expected.clientRequestId,
    decodeResult: (raw, path, evidence) => decodeStudyChatExchange(raw, {
      path,
      expectedSessionId: expected.sessionId,
      evidence,
    }),
  });
}

export async function submitStudyQuestionAttempt(input: {
  sessionId: string;
  turnId: string;
  expectedSessionRevision: number;
  clientAttemptId: string;
  submittedAnswer: string;
}): Promise<StudyQuestionAttemptCommitResult> {
  const payload = await readJson<unknown>(
    await request(`${AI_BASE_URL()}/study-sessions/${input.sessionId}/attempt`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        turn_id: input.turnId,
        expected_session_revision: input.expectedSessionRevision,
        client_attempt_id: input.clientAttemptId,
        submitted_answer: input.submittedAnswer,
      })
    })
  );
  const attempt = decodeStudyQuestionAttemptResponse(payload, {
    sessionId: input.sessionId,
    turnId: input.turnId,
    clientAttemptId: input.clientAttemptId,
    expectedSessionRevision: input.expectedSessionRevision,
  });
  const session = await getStudySession(input.sessionId);
  return { attempt, session };
}

export async function resolveStudyPlanConfirmation(input: {
  sessionId: string;
  confirmationId: string;
  decision: "approve" | "reject";
  note?: string;
}): Promise<StudyPlanConfirmationDecisionResponse> {
  const payload = await readJson<unknown>(
    await request(
      `${AI_BASE_URL()}/study-sessions/${input.sessionId}/plan-confirmations/${input.confirmationId}`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          decision: input.decision,
          note: input.note ?? "",
        })
      }
    )
  );
  return decodeStudyPlanConfirmationDecisionResponse(payload, {
    expectedSessionId: input.sessionId,
    expectedConfirmationId: input.confirmationId,
    expectedDecision: input.decision,
    decodePlan: (rawPlan, path, expectedPlanId, expectedDocumentId) => normalizePlan(rawPlan, {
      path,
      expectedPlanId,
      expectedDocumentId,
    }),
  });
}

export async function getModelUsageStats(): Promise<TokenUsageStats> {
  const response = await request(`${AI_BASE_URL()}/model-usage/stats`);
  const raw = await readJson<any>(response);
  return {
    buckets: (raw.buckets ?? []).map((b: any) => ({
      date: String(b.date ?? ""),
      feature: String(b.feature ?? ""),
      model: String(b.model ?? ""),
      promptTokens: Number(b.prompt_tokens ?? 0),
      completionTokens: Number(b.completion_tokens ?? 0),
      totalTokens: Number(b.total_tokens ?? 0),
    })),
    records: (raw.records ?? []).map((item: any) => ({
      id: String(item.id ?? ""),
      createdAt: String(item.created_at ?? ""),
      feature: String(item.feature ?? ""),
      model: String(item.model ?? ""),
      promptTokens: Number(item.prompt_tokens ?? 0),
      completionTokens: Number(item.completion_tokens ?? 0),
      totalTokens: Number(item.total_tokens ?? 0),
    })),
    totalPromptTokens: Number(raw.total_prompt_tokens ?? 0),
    totalCompletionTokens: Number(raw.total_completion_tokens ?? 0),
    totalTokens: Number(raw.total_tokens ?? 0),
  };
}
