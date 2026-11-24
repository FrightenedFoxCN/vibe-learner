import {
  withStudyRequestDeadline,
  STUDY_SEND_WAIT_MS,
  STUDY_QUERY_WAIT_MS,
} from "../study-request-deadline";
import {
  createDiagnosticId,
  diagnosticContext,
  diagnosticDecode,
  DiagnosticContext as DiagnosticContext,
} from "../diagnostics";
import { studyDiagnosticContext } from "../study-diagnostic-context";
import type { StudyChatResponse, StudySessionRecord } from "@vibe-learner/shared";
import {
  decodeStudyChatExchange,
  decodeStudySession,
  decodeStudySessionList,
} from "../study-session-decode";
import {
  decodeStudyChatOperationReceipt,
  type StudyChatOperationReceipt,
} from "../study-chat-operation-decode";
import {
  decodeStudyQuestionAttemptResponse,
  type StudyQuestionAttemptRequest,
  type StudyQuestionAttemptResponse,
} from "../study-question-attempt";

import { AI_BASE_URL, request, readJson } from "./_shared";
import { serializeSceneProfile } from "./scene-serialize";

export interface StudyChatExchangeResponse extends StudyChatResponse {
  session: StudySessionRecord;
}

export type StudyChatOperationResponse =
  StudyChatOperationReceipt<StudyChatExchangeResponse>;

export async function createStudySession(
  input: {
    documentId: string;
    personaId: string;
    planId?: string | null;
    sceneProfile?: import("@vibe-learner/shared").SceneProfile | null;
    studyUnitId: string;
    studyUnitTitle?: string;
    themeHint?: string;
    outputLanguage?: string;
  },
  context?: DiagnosticContext,
): Promise<StudySessionRecord> {
  const diagnosticResponse = await request(
    `${AI_BASE_URL()}/study-sessions`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
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
        theme_hint: input.themeHint ?? "",
        ...(input.outputLanguage !== undefined
          ? { output_language: input.outputLanguage }
          : {}),
      }),
    },
    context,
  );
  const payload = await readJson<unknown>(diagnosticResponse);
  return diagnosticDecode(
    diagnosticResponse,
    () =>
      decodeStudySession(payload, {
        expectedDocumentId: input.documentId,
        expectedPersonaId: input.personaId,
        expectedPlanId: input.planId ?? null,
        expectedStudyUnitId: input.studyUnitId,
      }),
    "study-session-public-v1",
  );
}

export async function listStudySessions(input: {
  documentId?: string;
  personaId?: string;
  planId?: string;
  studyUnitId?: string;
  signal?: AbortSignal;
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
  const diagnosticResponse = await request(
    `${AI_BASE_URL()}/study-sessions${suffix ? `?${suffix}` : ""}`,
    { signal: input.signal, cache: "no-store" },
  );
  const payload = await readJson<unknown>(diagnosticResponse);
  return diagnosticDecode(
    diagnosticResponse,
    () =>
      decodeStudySessionList(payload, {
        ...(input.documentId ? { expectedDocumentId: input.documentId } : {}),
        ...(input.personaId ? { expectedPersonaId: input.personaId } : {}),
        ...(input.planId ? { expectedPlanId: input.planId } : {}),
        ...(input.studyUnitId ? { expectedStudyUnitId: input.studyUnitId } : {}),
      }),
    "study-session-public-v1",
  );
}

export async function getStudySession(
  sessionId: string,
  context?: DiagnosticContext,
  signal?: AbortSignal,
): Promise<StudySessionRecord> {
  return readStudySession(sessionId, context, signal ? { signal } : undefined);
}

async function readStudySession(
  sessionId: string,
  context?: DiagnosticContext,
  init?: RequestInit,
): Promise<StudySessionRecord> {
  const diagnosticResponse = await request(
    `${AI_BASE_URL()}/study-sessions/${sessionId}`,
    init,
    context,
  );
  const payload = await readJson<unknown>(diagnosticResponse);
  return diagnosticDecode(
    diagnosticResponse,
    () => decodeStudySession(payload, { expectedSessionId: sessionId }),
    "study-session-public-v1",
  );
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
  const diagnosticResponse = await request(
    `${AI_BASE_URL()}/study-sessions/${input.sessionId}`,
    {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(body),
    },
  );
  const payload = await readJson<unknown>(diagnosticResponse);
  return diagnosticDecode(diagnosticResponse, () =>
    decodeStudySession(payload, {
      expectedSessionId: input.sessionId,
      ...(input.studyUnitId ? { expectedStudyUnitId: input.studyUnitId } : {}),
    }),
  );
}

export async function cancelStudySessionFollowUps(input: {
  sessionId: string;
  signal?: AbortSignal;
}): Promise<StudySessionRecord> {
  const diagnosticResponse = await request(
    `${AI_BASE_URL()}/study-sessions/${input.sessionId}/follow-ups/cancel`,
    {
      method: "POST",
      signal: input.signal,
    },
  );
  const payload = await readJson<unknown>(diagnosticResponse);
  return diagnosticDecode(diagnosticResponse, () =>
    decodeStudySession(payload, {
      expectedSessionId: input.sessionId,
      requireNoPendingFollowUps: true,
    }),
  );
}

export async function sendStudyMessage(input: {
  sessionId: string;
  clientRequestId: string;
  expectedSessionRevision: number;
  message: string;
  messageKind?: string;
  followUpId?: string;
  hiddenMessagePrefix?: string;
  outputLanguage?: string;
  attachments?: File[];
  diagnosticFlowId?: string | null;
}): Promise<StudyChatOperationResponse> {
  return withStudyRequestDeadline(STUDY_SEND_WAIT_MS, (signal) =>
    sendStudyMessageRequest(input, signal),
  );
}

export async function getStudyChatOperation(input: {
  sessionId: string;
  clientRequestId: string;
  diagnosticFlowId?: string | null;
}): Promise<StudyChatOperationResponse> {
  return withStudyRequestDeadline(STUDY_QUERY_WAIT_MS, (signal) =>
    getStudyChatOperationRequest(input, signal),
  );
}

export async function submitStudyQuestionAttempt(
  input: StudyQuestionAttemptRequest,
  context: DiagnosticContext = diagnosticContext(createDiagnosticId()),
): Promise<StudyQuestionAttemptResponse> {
  return withStudyRequestDeadline(STUDY_SEND_WAIT_MS, (signal) =>
    submitStudyQuestionAttemptRequest(input, context, signal),
  );
}

async function submitStudyQuestionAttemptRequest(
  input: StudyQuestionAttemptRequest,
  context: DiagnosticContext,
  signal: AbortSignal,
): Promise<StudyQuestionAttemptResponse> {
  const diagnosticResponse = await request(
    `${AI_BASE_URL()}/study-sessions/${input.sessionId}/attempt`,
    {
      method: "POST",
      signal,
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        turn_id: input.turnId,
        expected_session_revision: input.expectedSessionRevision,
        client_attempt_id: input.clientAttemptId,
        submitted_answer: input.submittedAnswer,
      }),
    },
    context,
  );
  const payload = await readJson<unknown>(diagnosticResponse);
  return diagnosticDecode(diagnosticResponse, () =>
    decodeStudyQuestionAttemptResponse(payload, input),
  );
}

export async function readStudyQuestionAttemptSession(
  sessionId: string,
  context?: DiagnosticContext,
): Promise<StudySessionRecord> {
  return withStudyRequestDeadline(STUDY_QUERY_WAIT_MS, (signal) =>
    readStudySession(sessionId, context, { cache: "no-store", signal }),
  );
}

async function sendStudyMessageRequest(
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

async function getStudyChatOperationRequest(
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

function decodeStudyChatOperationResponse(
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
