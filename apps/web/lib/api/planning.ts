import { decodePlanRevision } from "../plan-revision-decode";
import { decodeStudyUnitRevision } from "../study-unit-revision-decode";
import {
  diagnosticDecode,
  DiagnosticContext as DiagnosticContext,
} from "../diagnostics";
import type {
  LearningGoal,
  LearningPlan,
  StreamEvent,
  StudySessionRecord,
} from "@vibe-learner/shared";
import { decodeStudyPlanConfirmationDecisionResponse } from "../study-session-decode";
import {
  PlanningDecodeError,
  decodeLearningPlan,
  decodeLearningPlanList,
} from "../planning-decode";
import { DocumentDecodeError } from "../document-decode";
import { StrictStreamStateMachine } from "../stream-decode";
import {
  decodePlanGenerationOperation,
  PlanStreamTerminalError,
  type PlanGenerationIdentity,
} from "../plan-generation-outcome";

import { AI_BASE_URL, request, readJson } from "./_shared";
import { serializeSceneProfile } from "./scene-serialize";
import { consumeDiagnosticStream, formatStreamErrorPayload } from "./stream";

export interface StudyPlanConfirmationDecisionResponse {
  session: StudySessionRecord;
  plan: LearningPlan | null;
}

export async function createLearningPlan(goal: LearningGoal): Promise<LearningPlan> {
  const clientRequestId = goal.clientRequestId?.trim() || createLearningPlanRequestId();
  const sceneSummary = goal.sceneProfileSummary ?? goal.sceneProfile?.summary ?? "";
  const diagnosticResponse = await request(`${AI_BASE_URL()}/learning-plans`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      document_id: goal.documentId ?? "",
      persona_id: goal.personaId,
      client_request_id: clientRequestId,
      expected_document_updated_at: goal.expectedDocumentUpdatedAt ?? "",
      objective: goal.objective,
      scene_profile_summary: sceneSummary,
      scene_profile: serializeSceneProfile(goal.sceneProfile),
      planning_intent: serializePlanningIntent(goal.planningIntent),
    }),
  });
  const payload = await readJson<unknown>(diagnosticResponse);
  return diagnosticDecode(diagnosticResponse, () =>
    decodeLearningPlan(payload, {
      expectedDocumentId: goal.documentId ?? "",
      requireHarnessTrace: true,
    }),
  );
}

export async function listLearningPlans(): Promise<LearningPlan[]> {
  const diagnosticResponse = await request(`${AI_BASE_URL()}/learning-plans`);
  const payload = await readJson<unknown>(diagnosticResponse);
  return diagnosticDecode(diagnosticResponse, () => decodeLearningPlanList(payload));
}

export async function getPlanGenerationOperation(
  identity: PlanGenerationIdentity,
  options?: { signal?: AbortSignal; diagnostic?: DiagnosticContext },
) {
  const response = await request(
    `${AI_BASE_URL()}/learning-plan-operations/${encodeURIComponent(identity.clientRequestId)}`,
    { signal: options?.signal, cache: "no-store" },
    options?.diagnostic,
  );
  const payload = await readJson<unknown>(response);
  return diagnosticDecode(response, () =>
    decodePlanGenerationOperation(
      payload,
      identity,
      decodeLearningPlan,
      (path, reason) => {
        throw new PlanningDecodeError(path, reason);
      },
    ),
  );
}

export async function getRecoveredLearningPlan(
  planId: string,
  identity: PlanGenerationIdentity,
  options?: { signal?: AbortSignal; diagnostic?: DiagnosticContext },
) {
  const response = await request(
    `${AI_BASE_URL()}/learning-plans/${encodeURIComponent(planId)}`,
    { signal: options?.signal, cache: "no-store" },
    options?.diagnostic,
  );
  const payload = await readJson<unknown>(response);
  return diagnosticDecode(response, () => {
    const plan = decodeLearningPlan(payload, {
      expectedPlanId: planId,
      expectedDocumentId: identity.documentId,
    });
    if (plan.personaId !== identity.personaId)
      throw new PlanningDecodeError("learning_plan.persona_id", "identity_mismatch");
    return plan;
  });
}

export async function updateLearningPlanTitle(
  planId: string,
  courseTitle: string,
  expectedRevision?: number,
): Promise<LearningPlan> {
  const diagnosticResponse = await request(
    `${AI_BASE_URL()}/learning-plans/${planId}`,
    {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        expected_revision: expectedRevision,
        course_title: courseTitle,
      }),
    },
  );
  const payload = await readJson<unknown>(diagnosticResponse);
  return diagnosticDecode(diagnosticResponse, () =>
    decodeLearningPlan(payload, { expectedPlanId: planId }),
  );
}

export async function updateLearningPlanProgress(input: {
  planId: string;
  scheduleIds: string[];
  expectedRevision?: number;
  status: string;
  note?: string;
}): Promise<LearningPlan> {
  const diagnosticResponse = await request(
    `${AI_BASE_URL()}/learning-plans/${input.planId}/progress`,
    {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        expected_revision: input.expectedRevision,
        schedule_ids: input.scheduleIds,
        status: input.status,
        note: input.note ?? "",
      }),
    },
  );
  const payload = await readJson<unknown>(diagnosticResponse);
  return diagnosticDecode(diagnosticResponse, () =>
    decodeLearningPlan(payload, { expectedPlanId: input.planId }),
  );
}

export async function answerLearningPlanQuestion(input: {
  planId: string;
  questionId: string;
  expectedRevision?: number;
  answer: string;
}): Promise<LearningPlan> {
  const diagnosticResponse = await request(
    `${AI_BASE_URL()}/learning-plans/${input.planId}/planning-questions/${input.questionId}`,
    {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        expected_revision: input.expectedRevision,
        answer: input.answer,
      }),
    },
  );
  const payload = await readJson<unknown>(diagnosticResponse);
  return diagnosticDecode(diagnosticResponse, () =>
    decodeLearningPlan(payload, { expectedPlanId: input.planId }),
  );
}

export async function deleteLearningPlan(
  planId: string,
  expectedRevision?: number,
): Promise<void> {
  await readJson<{ deleted_plan_id: string }>(
    await request(
      `${AI_BASE_URL()}/learning-plans/${planId}${expectedRevision === undefined ? "" : `?expected_revision=${expectedRevision}`}`,
      {
        method: "DELETE",
      },
    ),
  );
}

export async function createLearningPlanStream(
  goal: LearningGoal,
  onEvent: (event: StreamEvent) => void,
  options?: { signal?: AbortSignal; diagnostic?: DiagnosticContext },
): Promise<LearningPlan> {
  const clientRequestId = goal.clientRequestId?.trim() || createLearningPlanRequestId();
  const sceneSummary = goal.sceneProfileSummary ?? goal.sceneProfile?.summary ?? "";
  const response = await request(
    `${AI_BASE_URL()}/learning-plans/stream`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      signal: options?.signal,
      body: JSON.stringify({
        document_id: goal.documentId ?? "",
        persona_id: goal.personaId,
        client_request_id: clientRequestId,
        expected_document_updated_at: goal.expectedDocumentUpdatedAt ?? "",
        objective: goal.objective,
        scene_profile_summary: sceneSummary,
        scene_profile: serializeSceneProfile(goal.sceneProfile),
        planning_intent: serializePlanningIntent(goal.planningIntent),
      }),
    },
    options?.diagnostic,
  );
  if (!response.ok || !response.body) {
    if (!response.ok) await readJson<unknown>(response);
    throw new Error("learning_plan_stream_body_missing");
  }

  let finalPlan: LearningPlan | null = null;
  const expectedDocumentId = goal.documentId ?? "";
  const machine = new StrictStreamStateMachine({
    streamKind: "learning_plan",
    subject: expectedDocumentId
      ? { subjectType: "document", subjectId: expectedDocumentId }
      : { subjectType: "learning_plan_request", subjectId: clientRequestId },
  });
  const terminal = await consumeDiagnosticStream(
    response,
    (error) =>
      error instanceof PlanningDecodeError || error instanceof DocumentDecodeError,
    response.body,
    machine,
    (event) => {
      if (event.stage === "stream_completed") {
        finalPlan = decodeLearningPlan(event.committedProjection, {
          expectedPlanId: event.terminalEvidence?.resourceId ?? undefined,
          expectedDocumentId,
          path: "stream.committed_projection",
          requireHarnessTrace: true,
        });
      }
      onEvent(event);
    },
  );
  if (terminal.stage === "stream_cancelled") {
    throw new PlanStreamTerminalError(
      "stream_interrupted",
      true,
      terminal.terminalEvidence?.commitStatus,
    );
  }
  if (terminal.stage === "stream_error") {
    throw new PlanStreamTerminalError(
      formatStreamErrorPayload(terminal.payload, "learning_plan_stream_error"),
      false,
      terminal.terminalEvidence?.commitStatus,
    );
  }
  if (!finalPlan) {
    throw new Error("learning_plan_stream_committed_terminal_without_plan");
  }
  return finalPlan;
}

export async function resolveStudyPlanConfirmation(input: {
  sessionId: string;
  confirmationId: string;
  decision: "approve" | "reject";
  note?: string;
}): Promise<StudyPlanConfirmationDecisionResponse> {
  const diagnosticResponse = await request(
    `${AI_BASE_URL()}/study-sessions/${input.sessionId}/plan-confirmations/${input.confirmationId}`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        decision: input.decision,
        note: input.note ?? "",
      }),
    },
  );
  const payload = await readJson<unknown>(diagnosticResponse);
  return diagnosticDecode(diagnosticResponse, () =>
    decodeStudyPlanConfirmationDecisionResponse(payload, {
      expectedSessionId: input.sessionId,
      expectedConfirmationId: input.confirmationId,
      expectedDecision: input.decision,
      decodePlan: (rawPlan, path, expectedPlanId, expectedDocumentId) =>
        decodeLearningPlan(rawPlan, {
          path,
          expectedPlanId,
          expectedDocumentId,
        }),
    }),
  );
}

export async function createPlanRevision(
  planId: string,
  input: {
    clientRequestId: string;
    baseRevision: number;
    instruction?: string;
    rollbackRevision?: number;
  },
) {
  const response = await request(
    `${AI_BASE_URL()}/learning-plans/${planId}/revisions`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        client_request_id: input.clientRequestId,
        base_revision: input.baseRevision,
        instruction: input.instruction ?? "",
        rollback_revision: input.rollbackRevision ?? null,
      }),
    },
  );
  const raw = await readJson<unknown>(response);
  return diagnosticDecode(response, () =>
    decodePlanRevision(raw, planId, input.clientRequestId, input),
  );
}

export async function getPlanRevision(planId: string, requestId: string) {
  const response = await request(
    `${AI_BASE_URL()}/learning-plans/${planId}/revisions/${requestId}`,
  );
  const raw = await readJson<unknown>(response);
  return diagnosticDecode(response, () => decodePlanRevision(raw, planId, requestId));
}

export async function decidePlanRevision(
  planId: string,
  requestId: string,
  decision: "accept" | "reject",
) {
  const response = await request(
    `${AI_BASE_URL()}/learning-plans/${planId}/revisions/${requestId}/decision`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ decision }),
    },
  );
  const raw = await readJson<unknown>(response);
  return diagnosticDecode(response, () => decodePlanRevision(raw, planId, requestId));
}

export async function listPlanRevisions(planId: string): Promise<number[]> {
  const response = await request(
    `${AI_BASE_URL()}/learning-plans/${planId}/revision-history`,
  );
  const raw = await readJson<unknown>(response);
  if (
    !raw ||
    typeof raw !== "object" ||
    !("revisions" in raw) ||
    !Array.isArray(raw.revisions) ||
    raw.revisions.some((value) => !Number.isSafeInteger(value) || value < 0) ||
    raw.revisions.some(
      (value, index, values) => index > 0 && value >= values[index - 1],
    )
  ) {
    throw new PlanningDecodeError("plan_revision_history", "invalid_history");
  }
  return raw.revisions as number[];
}

export async function getStudyUnitRevision(planId: string, documentId: string) {
  const response = await request(
    `${AI_BASE_URL()}/learning-plans/${planId}/study-unit-revision`,
  );
  const raw = await readJson<unknown>(response);
  return diagnosticDecode(response, () =>
    decodeStudyUnitRevision(raw, planId, documentId),
  );
}

export async function decideStudyUnitRevision(
  planId: string,
  documentId: string,
  operationId: string,
  decision: "accept" | "reject",
) {
  const response = await request(
    `${AI_BASE_URL()}/learning-plans/${planId}/study-unit-revision/${operationId}/decision`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ decision }),
    },
  );
  const raw = await readJson<unknown>(response);
  return diagnosticDecode(response, () => {
    const value = decodeStudyUnitRevision(raw, planId, documentId);
    if (value.preview.operationId !== operationId)
      throw new PlanningDecodeError("study_unit_revision", "identity_mismatch");
    return value;
  });
}

function createLearningPlanRequestId(): string {
  const suffix =
    typeof globalThis.crypto?.randomUUID === "function"
      ? globalThis.crypto.randomUUID()
      : `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`;
  return `learning-plan-${suffix}`;
}

function serializePlanningIntent(
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
