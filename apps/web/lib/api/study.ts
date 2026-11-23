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
import { SETTINGS_RESPONSE_CONTRACTS } from "@vibe-learner/shared/settings-response-contracts";
import { decodeRuntimeSettings } from "../runtime-settings-decode";
import type {
  RuntimeSettings,
  StudyChatResponse,
  StudySessionRecord,
} from "@vibe-learner/shared";
import { decodeStudySession, decodeStudySessionList } from "../study-session-decode";
import { StudyChatOperationReceipt as StudyChatOperationReceipt } from "../study-chat-operation-decode";
import {
  decodeStudyQuestionAttemptResponse,
  type StudyQuestionAttemptResponse,
} from "../study-question-attempt";

import {
  serializeSceneProfile,
  AI_BASE_URL,
  request,
  readJson,
  sendStudyMessageRequest,
  getStudyChatOperationRequest,
} from "./_shared";

export interface StudyChatExchangeResponse extends StudyChatResponse {
  session: StudySessionRecord;
}

export type StudyChatOperationResponse =
  StudyChatOperationReceipt<StudyChatExchangeResponse>;

export interface StudyQuestionAttemptCommitResult {
  attempt: StudyQuestionAttemptResponse;
  session: StudySessionRecord;
}

export async function applyRuntimeSessionSecrets(
  patch: {
    openaiApiKey?: string;
    openaiPlanApiKey?: string;
    openaiSettingApiKey?: string;
    openaiChatApiKey?: string;
  },
  context?: DiagnosticContext,
): Promise<RuntimeSettings> {
  const diagnosticResponse = await request(
    `${AI_BASE_URL()}/runtime-settings/session-secrets`,
    {
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        openai_api_key: patch.openaiApiKey,
        openai_plan_api_key: patch.openaiPlanApiKey,
        openai_setting_api_key: patch.openaiSettingApiKey,
        openai_chat_api_key: patch.openaiChatApiKey,
      }),
    },
    context,
  );
  const payload = await readJson<unknown>(diagnosticResponse);
  return diagnosticDecode(
    diagnosticResponse,
    () => decodeRuntimeSettings(payload),
    SETTINGS_RESPONSE_CONTRACTS.runtimeSettings,
  );
}

export async function clearRuntimeSessionSecrets(): Promise<RuntimeSettings> {
  const diagnosticResponse = await request(
    `${AI_BASE_URL()}/runtime-settings/session-secrets`,
    {
      method: "DELETE",
    },
  );
  const payload = await readJson<unknown>(diagnosticResponse);
  return diagnosticDecode(
    diagnosticResponse,
    () => decodeRuntimeSettings(payload),
    SETTINGS_RESPONSE_CONTRACTS.runtimeSettings,
  );
}

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
): Promise<StudySessionRecord> {
  const diagnosticResponse = await request(
    `${AI_BASE_URL()}/study-sessions/${sessionId}`,
    undefined,
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
}): Promise<StudySessionRecord> {
  const diagnosticResponse = await request(
    `${AI_BASE_URL()}/study-sessions/${input.sessionId}/follow-ups/cancel`,
    {
      method: "POST",
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
  input: {
    sessionId: string;
    turnId: string;
    expectedSessionRevision: number;
    clientAttemptId: string;
    submittedAnswer: string;
  },
  context: DiagnosticContext = diagnosticContext(createDiagnosticId()),
): Promise<StudyQuestionAttemptCommitResult> {
  const diagnosticResponse = await request(
    `${AI_BASE_URL()}/study-sessions/${input.sessionId}/attempt`,
    {
      method: "POST",
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
  const attempt = diagnosticDecode(diagnosticResponse, () =>
    decodeStudyQuestionAttemptResponse(payload, {
      sessionId: input.sessionId,
      turnId: input.turnId,
      clientAttemptId: input.clientAttemptId,
      expectedSessionRevision: input.expectedSessionRevision,
    }),
  );
  const session = await getStudySession(input.sessionId, context);
  return { attempt, session };
}
