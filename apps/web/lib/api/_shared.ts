import { studyDiagnosticContext } from "../study-diagnostic-context";
import {
  createDiagnosticId,
  diagnosticContext,
  diagnosticDecode,
  recordDecodeFailure,
  diagnosticFetch,
  type DiagnosticContext,
} from "../diagnostics";
import type {
  CreatePersonaInput,
  CreatePersonaCardInput,
  DocumentPlanningContext,
  DocumentPlanningTraceResponse,
  DocumentDebugRecord,
  DocumentRecord,
  LearningGoal,
  LearningPlan,
  StreamReport,
  TavernTurnInput,
  UpdatePersonaInput,
} from "@vibe-learner/shared";
import { compactPreviewString, compactPreviewValue } from "../preview";
import { getAiBaseUrl, getDesktopRuntimeConfig } from "../runtime-config";
import { ApiHttpError, extractApiErrorCode } from "../http-error";
import { decodeStudyChatExchange } from "../study-session-decode";
import {
  decodeDocumentDebugRecord,
  decodeDocumentRecord,
  DocumentDecodeError,
} from "../document-decode";
import {
  PlanningDecodeError,
  decodeDocumentPlanningContext,
  decodeDocumentPlanningTraceResponse,
  decodeLearningPlan,
} from "../planning-decode";
import { decodeStudyChatOperationReceipt } from "../study-chat-operation-decode";
import {
  StreamDecodeError,
  consumeVersionedStream,
  decodeStreamReport,
} from "../stream-decode";
import { isTavernTerminalReplayDirective } from "../tavern-decode";

import { decodeTavernHttpError } from "./tavern";
import {
  StudyChatOperationResponse,
  sendStudyMessage,
  getStudyChatOperation,
} from "./study";

export function serializeSceneTree(
  nodes: import("@vibe-learner/shared").SceneTreeNode[] | undefined,
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

export function serializeSceneProfile(
  sceneProfile: import("@vibe-learner/shared").SceneProfile | null | undefined,
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

export function extractErrorMessage(payload: unknown, fallbackMessage: string) {
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

export const AI_BASE_URL = () => getAiBaseUrl();

export async function request(
  input: string,
  init?: RequestInit,
  context?: DiagnosticContext,
): Promise<Response> {
  try {
    return await diagnosticFetch(input, init, context);
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    const startupError = getDesktopRuntimeConfig()?.startupError.trim();
    const detail = startupError ? ` (${startupError})` : "";
    throw new Error(`Cannot reach AI service at ${AI_BASE_URL()}${detail}`);
  }
}

export async function readJson<T>(response: Response): Promise<T> {
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
  const started = performance.now();
  try {
    return (await response.json()) as T;
  } catch (error) {
    if (error instanceof SyntaxError)
      recordDecodeFailure(response, performance.now() - started);
    throw error;
  }
}

export async function requestTavernMutationWithRecovery(
  input: string,
  init: RequestInit,
  context = diagnosticContext(createDiagnosticId()),
): Promise<Response> {
  try {
    const response = await request(input, init, context);
    if (!response.ok) await readJson<unknown>(response);
    return response;
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
    return await request(input, init, context);
  }
}

export async function consumeDiagnosticStream(
  response: Response,
  ...args: Parameters<typeof consumeVersionedStream>
) {
  const started = performance.now();
  try {
    return await consumeVersionedStream(...args);
  } catch (error) {
    if (
      error instanceof StreamDecodeError ||
      error instanceof DocumentDecodeError ||
      error instanceof PlanningDecodeError
    ) {
      recordDecodeFailure(response, performance.now() - started);
    }
    throw error;
  }
}

export function formatStreamErrorPayload(
  payload: Record<string, unknown> | undefined,
  fallbackCode: string,
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

export function serializeSlot(slot: any) {
  return {
    kind: slot.kind,
    label: slot.label,
    content: slot.content,
    weight: slot.weight ?? 1,
    locked: slot.locked ?? false,
    sort_order: slot.sortOrder ?? 0,
  };
}

export function serializePersonaCardInput(input: CreatePersonaCardInput) {
  return {
    title: input.title,
    kind: input.kind,
    label: input.label,
    content: input.content,
    tags: input.tags ?? [],
    search_keywords: input.searchKeywords ?? "自定义",
    source: input.source ?? "manual",
    source_note: input.sourceNote ?? "",
  };
}

export function serializePersonaInput(input: CreatePersonaInput | UpdatePersonaInput) {
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

export function normalizeDocument(
  document: unknown,
  expectedDocumentId?: string,
): DocumentRecord {
  const decoded = decodeDocumentRecord(document, expectedDocumentId);
  return {
    ...decoded,
    previewExcerpt: compactPreviewString(decoded.previewExcerpt, 240),
  };
}

export function normalizeDebugRecord(
  record: unknown,
  expectedDocumentId?: string,
): DocumentDebugRecord {
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

export function normalizePlanningContext(
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

export function normalizePlanningTraceResponse(
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

export function normalizeStreamReport(
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
          : (compactPreviewValue(event.committedProjection) as Record<string, unknown>),
    })),
  };
}

export function normalizePlan(
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

export function serializeTavernTurnInput(input: TavernTurnInput) {
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

export function createLearningPlanRequestId(): string {
  const suffix =
    typeof globalThis.crypto?.randomUUID === "function"
      ? globalThis.crypto.randomUUID()
      : `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`;
  return `learning-plan-${suffix}`;
}

export function serializePlanningIntent(
  intent: LearningGoal["planningIntent"],
): object | undefined {
  if (!intent) return undefined;
  const serializeValue = <T, U>(
    item: { status: "unknown"; value: null } | { status: "user_explicit"; value: T },
    map: (value: T) => U,
  ) =>
    item.status === "unknown"
      ? { status: "unknown", value: null }
      : { status: "user_explicit", value: map(item.value) };
  return {
    schema_version: intent.schemaVersion,
    pdf_page_ranges: serializeValue(intent.pdfPageRanges, (ranges) =>
      ranges.map((range) => ({
        page_start: range.pageStart,
        page_end: range.pageEnd,
      })),
    ),
    outline_targets: serializeValue(intent.outlineTargets, (targets) => targets),
    session_count: serializeValue(intent.sessionCount, (value) => value),
    minutes_per_session: serializeValue(intent.minutesPerSession, (value) => value),
    output_language: serializeValue(intent.outputLanguage, (value) => value),
  };
}

export async function sendStudyMessageRequest(
  input: Parameters<typeof sendStudyMessage>[0],
  signal: AbortSignal,
): Promise<StudyChatOperationResponse> {
  const context = studyDiagnosticContext(
    input.sessionId,
    input.clientRequestId,
    input.diagnosticFlowId,
  );
  const hasAttachments = Boolean(input.attachments?.length);
  const response = hasAttachments
    ? await request(
        `${AI_BASE_URL()}/study-sessions/${input.sessionId}/chat-with-attachments`,
        {
          method: "POST",
          signal,
          body: (() => {
            const form = new FormData();
            form.set("message", input.message);
            form.set("client_request_id", input.clientRequestId);
            form.set(
              "expected_session_revision",
              String(input.expectedSessionRevision),
            );
            form.set("message_kind", input.messageKind ?? "learner");
            form.set("follow_up_id", input.followUpId ?? "");
            form.set("hidden_message_prefix", input.hiddenMessagePrefix ?? "");
            if (input.outputLanguage !== undefined)
              form.set("output_language", input.outputLanguage);
            (input.attachments ?? []).forEach((file) => {
              form.append("files", file);
            });
            return form;
          })(),
        },
        context,
      )
    : await request(
        `${AI_BASE_URL()}/study-sessions/${input.sessionId}/chat`,
        {
          method: "POST",
          signal,
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            client_request_id: input.clientRequestId,
            expected_session_revision: input.expectedSessionRevision,
            message: input.message,
            message_kind: input.messageKind ?? "learner",
            follow_up_id: input.followUpId ?? "",
            hidden_message_prefix: input.hiddenMessagePrefix ?? "",
            ...(input.outputLanguage !== undefined
              ? { output_language: input.outputLanguage }
              : {}),
          }),
        },
        context,
      );
  const diagnosticResponse = response;
  const payload = await readJson<unknown>(diagnosticResponse);
  return diagnosticDecode(diagnosticResponse, () =>
    decodeStudyChatOperationResponse(payload, {
      sessionId: input.sessionId,
      clientRequestId: input.clientRequestId,
    }),
  );
}

export async function getStudyChatOperationRequest(
  input: Parameters<typeof getStudyChatOperation>[0],
  signal: AbortSignal,
): Promise<StudyChatOperationResponse> {
  const diagnosticResponse = await request(
    `${AI_BASE_URL()}/study-sessions/${encodeURIComponent(input.sessionId)}/chat-operations/${encodeURIComponent(input.clientRequestId)}`,
    {
      cache: "no-store",
      signal,
      headers: { "Cache-Control": "no-cache" },
    },
    studyDiagnosticContext(
      input.sessionId,
      input.clientRequestId,
      input.diagnosticFlowId,
    ),
  );
  const payload = await readJson<unknown>(diagnosticResponse);
  return diagnosticDecode(diagnosticResponse, () =>
    decodeStudyChatOperationResponse(payload, input),
  );
}

export function decodeStudyChatOperationResponse(
  payload: unknown,
  expected: { sessionId: string; clientRequestId: string },
): StudyChatOperationResponse {
  return decodeStudyChatOperationReceipt(payload, {
    path: "study_chat_operation",
    expectedSessionId: expected.sessionId,
    expectedClientRequestId: expected.clientRequestId,
    decodeResult: (raw, path, evidence) =>
      decodeStudyChatExchange(raw, {
        path,
        expectedSessionId: expected.sessionId,
        evidence,
      }),
  });
}
