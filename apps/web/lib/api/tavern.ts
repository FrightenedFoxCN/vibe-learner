import {
  createDiagnosticId,
  diagnosticContext,
  diagnosticDecode,
  DiagnosticContext as DiagnosticContext,
} from "../diagnostics";
import type {
  CreateTavernRoomInput,
  RetryTavernRunInput,
  TavernErrorDetail,
  TavernRoomDetail,
  TavernRoomPage,
  TavernRun,
  TavernRunRecoveryChain,
  TavernTurnInput,
  TavernTurnResult,
  UpdateTavernRoomInput,
} from "@vibe-learner/shared";
import { ApiHttpError } from "../http-error";
import {
  isTavernTerminalReplayDirective,
  normalizeTavernRoomDetail,
  normalizeTavernRoomList,
  normalizeTavernRunList,
  normalizeTavernRunRecovery,
  normalizeTavernTurnResult,
  normalizeTavernErrorDetail,
} from "../tavern-decode";

import { AI_BASE_URL, request, readJson } from "./_shared";
import { serializeSceneProfile } from "./scene-serialize";

export function decodeTavernHttpError(error: unknown): TavernErrorDetail | null {
  if (!(error instanceof ApiHttpError)) return null;
  try {
    return normalizeTavernErrorDetail(error.payload);
  } catch {
    return null;
  }
}

export async function listTavernRooms(
  input: { limit?: number; cursor?: string } = {},
  context?: DiagnosticContext,
): Promise<TavernRoomPage> {
  const params = new URLSearchParams();
  if (input.limit !== undefined) params.set("limit", String(input.limit));
  if (input.cursor) params.set("cursor", input.cursor);
  const suffix = params.toString();
  const diagnosticResponse = await request(
    `${AI_BASE_URL()}/tavern/rooms${suffix ? `?${suffix}` : ""}`,
    undefined,
    context,
  );
  const payload = await readJson<unknown>(diagnosticResponse);
  return diagnosticDecode(diagnosticResponse, () => normalizeTavernRoomList(payload));
}

export async function createTavernRoom(
  input: CreateTavernRoomInput,
  context?: DiagnosticContext,
): Promise<TavernRoomDetail> {
  const diagnosticResponse = await request(
    `${AI_BASE_URL()}/tavern/rooms`,
    {
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
    },
    context,
  );
  const payload = await readJson<any>(diagnosticResponse);
  return diagnosticDecode(diagnosticResponse, () => normalizeTavernRoomDetail(payload));
}

export async function getTavernRoom(
  input: {
    roomId: string;
    afterSequence?: number;
    beforeSequence?: number;
    tail?: boolean;
    limit?: number;
  },
  context?: DiagnosticContext,
): Promise<TavernRoomDetail> {
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
  const diagnosticResponse = await request(
    `${AI_BASE_URL()}/tavern/rooms/${input.roomId}${suffix ? `?${suffix}` : ""}`,
    undefined,
    context,
  );
  const payload = await readJson<any>(diagnosticResponse);
  return diagnosticDecode(diagnosticResponse, () =>
    normalizeTavernRoomDetail(payload, input.roomId),
  );
}

export async function updateTavernRoom(
  roomId: string,
  input: UpdateTavernRoomInput,
  context?: DiagnosticContext,
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
  const diagnosticResponse = await request(
    `${AI_BASE_URL()}/tavern/rooms/${roomId}`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    },
    context,
  );
  const payload = await readJson<any>(diagnosticResponse);
  return diagnosticDecode(diagnosticResponse, () =>
    normalizeTavernRoomDetail(payload, roomId),
  );
}

export async function deleteTavernRoom(
  roomId: string,
  expectedRoomRevision: number,
): Promise<void> {
  await readJson<{ deleted_room_id: string }>(
    await request(
      `${AI_BASE_URL()}/tavern/rooms/${roomId}?expected_revision=${expectedRoomRevision}`,
      { method: "DELETE" },
    ),
  );
}

export async function listTavernRuns(
  roomId: string,
  limit = 50,
  context?: DiagnosticContext,
): Promise<TavernRun[]> {
  const diagnosticResponse = await request(
    `${AI_BASE_URL()}/tavern/rooms/${roomId}/runs?limit=${limit}`,
    undefined,
    context,
  );
  const payload = await readJson<unknown>(diagnosticResponse);
  return diagnosticDecode(diagnosticResponse, () =>
    normalizeTavernRunList(payload, roomId),
  );
}

export async function getTavernRunRecovery(
  roomId: string,
  limit = 50,
  context?: DiagnosticContext,
): Promise<TavernRunRecoveryChain[]> {
  const diagnosticResponse = await request(
    `${AI_BASE_URL()}/tavern/rooms/${roomId}/run-recovery?limit=${limit}`,
    undefined,
    context,
  );
  const payload = await readJson<unknown>(diagnosticResponse);
  return diagnosticDecode(diagnosticResponse, () =>
    normalizeTavernRunRecovery(payload, roomId),
  );
}

export async function runTavernTurn(
  roomId: string,
  input: TavernTurnInput,
  context?: DiagnosticContext,
): Promise<TavernTurnResult> {
  const diagnosticResponse = await requestTavernMutationWithRecovery(
    `${AI_BASE_URL()}/tavern/rooms/${roomId}/turns`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(serializeTavernTurnInput(input)),
    },
    context,
  );
  const payload = await readJson<unknown>(diagnosticResponse);
  return diagnosticDecode(diagnosticResponse, () =>
    normalizeTavernTurnResult(payload, roomId),
  );
}

export async function retryTavernRun(
  roomId: string,
  runId: string,
  input: RetryTavernRunInput,
  context?: DiagnosticContext,
): Promise<TavernTurnResult> {
  const diagnosticResponse = await requestTavernMutationWithRecovery(
    `${AI_BASE_URL()}/tavern/rooms/${roomId}/runs/${runId}/retry`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        idempotency_key: input.idempotencyKey,
        expected_room_revision: input.expectedRoomRevision,
      }),
    },
    context,
  );
  const payload = await readJson<unknown>(diagnosticResponse);
  return diagnosticDecode(diagnosticResponse, () =>
    normalizeTavernTurnResult(payload, roomId),
  );
}

export async function resumeTavernRun(
  roomId: string,
  runId: string,
  context?: DiagnosticContext,
): Promise<TavernTurnResult> {
  const diagnosticResponse = await request(
    `${AI_BASE_URL()}/tavern/rooms/${roomId}/runs/${runId}/resume`,
    {
      method: "POST",
    },
    context,
  );
  const payload = await readJson<any>(diagnosticResponse);
  return diagnosticDecode(diagnosticResponse, () =>
    normalizeTavernTurnResult(payload, roomId),
  );
}

export async function cancelTavernRun(
  roomId: string,
  runId: string,
  context?: DiagnosticContext,
): Promise<TavernTurnResult> {
  const diagnosticResponse = await request(
    `${AI_BASE_URL()}/tavern/rooms/${roomId}/runs/${runId}/cancel`,
    {
      method: "POST",
    },
    context,
  );
  const payload = await readJson<any>(diagnosticResponse);
  return diagnosticDecode(diagnosticResponse, () =>
    normalizeTavernTurnResult(payload, roomId),
  );
}

async function requestTavernMutationWithRecovery(
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
