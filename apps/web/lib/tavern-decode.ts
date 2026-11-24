import type {
  HarnessTraceV2,
  HarnessTraceWire,
  PersonaProfile,
  SceneObjectSnapshot,
  SceneProfile,
  SceneTreeNode,
  TavernErrorDetail,
  TavernHarnessPolicy,
  TavernMessage,
  TavernParticipant,
  TavernRoom,
  TavernRoomDetail,
  TavernRoomPage,
  TavernRoomState,
  TavernRun,
  TavernRunRecoveryChain,
  TavernSpeakerStep,
  TavernTurnResult,
} from "@vibe-learner/shared";

import { decodeHarnessTraceV3 } from "./harness-trace-decode.ts";
import { StrictResponseDecoder } from "./strict-response-decode.ts";

export class TavernDecodeError extends Error {
  readonly code = "tavern_response_decode_error";
  readonly path: string;

  constructor(path: string, reason: string) {
    super(`${reason} at ${path}`);
    this.name = "TavernDecodeError";
    this.path = path;
  }
}

const decoder = new StrictResponseDecoder((path, reason) => {
  // Keep Tavern's existing error reasons while sharing the numeric checks.
  if (reason.startsWith("expected_safe_integer_")) {
    throw new TavernDecodeError(
      path,
      reason.replace("expected_safe_integer_", "expected_integer_"),
    );
  }
  if (reason.startsWith("expected_finite_number_")) {
    throw new TavernDecodeError(path, "expected_finite_number");
  }
  throw new TavernDecodeError(path, reason);
});

function optionalStringField(
  value: Record<string, unknown>,
  key: string,
  path: string,
): string | undefined {
  const decoded = decoder.string(
    decoder.field(value, key, path),
    `${path}.${key}`,
    true,
  );
  return decoded || undefined;
}

function nullableField<T>(
  value: Record<string, unknown>,
  key: string,
  path: string,
  decode: (raw: unknown, valuePath: string) => T,
): T | null {
  return decoder.nullable(decoder.field(value, key, path), `${path}.${key}`, decode);
}

function decodePersonaSlot(
  raw: unknown,
  path: string,
): PersonaProfile["slots"][number] {
  const value = decoder.record(raw, path);
  return {
    kind: decoder.string(decoder.field(value, "kind", path), `${path}.kind`),
    label: decoder.string(decoder.field(value, "label", path), `${path}.label`, true),
    content: decoder.string(
      decoder.field(value, "content", path),
      `${path}.content`,
      true,
    ),
    weight: decoder.finiteNumber(
      decoder.field(value, "weight", path),
      `${path}.weight`,
    ),
    locked: decoder.boolean(decoder.field(value, "locked", path), `${path}.locked`),
    sortOrder: decoder.integer(
      decoder.field(value, "sort_order", path),
      `${path}.sort_order`,
    ),
  };
}

function decodePersona(raw: unknown, path: string): PersonaProfile {
  const value = decoder.record(raw, path);
  return {
    id: decoder.string(decoder.field(value, "id", path), `${path}.id`),
    revision:
      value.revision === undefined
        ? 0
        : decoder.integer(decoder.field(value, "revision", path), `${path}.revision`),
    name: decoder.string(decoder.field(value, "name", path), `${path}.name`, true),
    source: decoder.enumeration(
      decoder.field(value, "source", path),
      ["builtin", "user"] as const,
      `${path}.source`,
    ),
    summary: decoder.string(
      decoder.field(value, "summary", path),
      `${path}.summary`,
      true,
    ),
    relationship: decoder.string(
      decoder.field(value, "relationship", path),
      `${path}.relationship`,
      true,
    ),
    learnerAddress: decoder.string(
      decoder.field(value, "learner_address", path),
      `${path}.learner_address`,
      true,
    ),
    systemPrompt: decoder.string(
      decoder.field(value, "system_prompt", path),
      `${path}.system_prompt`,
      true,
    ),
    referenceHints: decoder.stringArray(
      decoder.field(value, "reference_hints", path),
      `${path}.reference_hints`,
    ),
    slots: decoder.array(
      decoder.field(value, "slots", path),
      `${path}.slots`,
      decodePersonaSlot,
    ),
    availableEmotions: decoder.stringArray(
      decoder.field(value, "available_emotions", path),
      `${path}.available_emotions`,
    ),
    availableActions: decoder.stringArray(
      decoder.field(value, "available_actions", path),
      `${path}.available_actions`,
    ),
    defaultSpeechStyle: decoder.string(
      decoder.field(value, "default_speech_style", path),
      `${path}.default_speech_style`,
      true,
    ),
  };
}

function decodeSceneObject(raw: unknown, path: string): SceneObjectSnapshot {
  const value = decoder.record(raw, path);
  return {
    id: decoder.string(decoder.field(value, "id", path), `${path}.id`, true),
    name: decoder.string(decoder.field(value, "name", path), `${path}.name`, true),
    description: decoder.string(
      decoder.field(value, "description", path),
      `${path}.description`,
      true,
    ),
    interaction: decoder.string(
      decoder.field(value, "interaction", path),
      `${path}.interaction`,
      true,
    ),
    tags: decoder.string(decoder.field(value, "tags", path), `${path}.tags`, true),
    reuseId: decoder.string(
      decoder.field(value, "reuse_id", path),
      `${path}.reuse_id`,
      true,
    ),
    reuseHint: decoder.string(
      decoder.field(value, "reuse_hint", path),
      `${path}.reuse_hint`,
      true,
    ),
  };
}

function decodeSceneNode(raw: unknown, path: string): SceneTreeNode {
  const value = decoder.record(raw, path);
  return {
    id: decoder.string(decoder.field(value, "id", path), `${path}.id`, true),
    title: decoder.string(decoder.field(value, "title", path), `${path}.title`, true),
    scopeLabel: decoder.string(
      decoder.field(value, "scope_label", path),
      `${path}.scope_label`,
      true,
    ),
    summary: decoder.string(
      decoder.field(value, "summary", path),
      `${path}.summary`,
      true,
    ),
    atmosphere: decoder.string(
      decoder.field(value, "atmosphere", path),
      `${path}.atmosphere`,
      true,
    ),
    rules: decoder.string(decoder.field(value, "rules", path), `${path}.rules`, true),
    entrance: decoder.string(
      decoder.field(value, "entrance", path),
      `${path}.entrance`,
      true,
    ),
    tags: decoder.string(decoder.field(value, "tags", path), `${path}.tags`, true),
    reuseId: decoder.string(
      decoder.field(value, "reuse_id", path),
      `${path}.reuse_id`,
      true,
    ),
    reuseHint: decoder.string(
      decoder.field(value, "reuse_hint", path),
      `${path}.reuse_hint`,
      true,
    ),
    objects: decoder.array(
      decoder.field(value, "objects", path),
      `${path}.objects`,
      decodeSceneObject,
    ),
    children: decoder.array(
      decoder.field(value, "children", path),
      `${path}.children`,
      decodeSceneNode,
    ),
  };
}

function decodeScene(raw: unknown, path: string): SceneProfile {
  const value = decoder.record(raw, path);
  return {
    sceneName: decoder.string(
      decoder.field(value, "scene_name", path),
      `${path}.scene_name`,
      true,
    ),
    sceneId: decoder.string(
      decoder.field(value, "scene_id", path),
      `${path}.scene_id`,
      true,
    ),
    title: decoder.string(decoder.field(value, "title", path), `${path}.title`, true),
    summary: decoder.string(
      decoder.field(value, "summary", path),
      `${path}.summary`,
      true,
    ),
    tags: decoder.stringArray(decoder.field(value, "tags", path), `${path}.tags`),
    selectedPath: decoder.stringArray(
      decoder.field(value, "selected_path", path),
      `${path}.selected_path`,
    ),
    focusObjectNames: decoder.stringArray(
      decoder.field(value, "focus_object_names", path),
      `${path}.focus_object_names`,
    ),
    sceneTree: decoder.array(
      decoder.field(value, "scene_tree", path),
      `${path}.scene_tree`,
      decodeSceneNode,
    ),
  };
}

export function decodeHarnessTrace(raw: unknown, path: string): HarnessTraceWire {
  const value = decoder.record(raw, path);
  if (Object.prototype.hasOwnProperty.call(value, "trace_schema_version")) {
    const schema = decoder.string(
      value.trace_schema_version,
      `${path}.trace_schema_version`,
    );
    if (schema === "harness-trace-v3") {
      return decodeHarnessTraceV3(value, path, (field, reason) => {
        throw new TavernDecodeError(field, reason);
      });
    }
    if (schema === "harness-trace-v2") return decodeLegacyHarnessTraceV2(value, path);
    throw new TavernDecodeError(
      `${path}.trace_schema_version`,
      `unsupported_harness_trace_schema_version_${String(value.trace_schema_version)}`,
    );
  }
  const version = decoder.string(
    decoder.field(value, "version", path),
    `${path}.version`,
  );
  if (version.startsWith("harness-trace-")) {
    throw new TavernDecodeError(
      `${path}.version`,
      "harness_trace_schema_version_discriminator_required",
    );
  }
  return {
    version,
    workflow: decoder.string(
      decoder.field(value, "workflow", path),
      `${path}.workflow`,
    ),
    stage: decoder.string(decoder.field(value, "stage", path), `${path}.stage`),
    status: decoder.enumeration(
      decoder.field(value, "status", path),
      ["passed", "repaired", "failed", "skipped"] as const,
      `${path}.status`,
    ),
    schemaName: decoder.string(
      decoder.field(value, "schema_name", path),
      `${path}.schema_name`,
    ),
    inputDigest: decoder.string(
      decoder.field(value, "input_digest", path),
      `${path}.input_digest`,
      true,
    ),
    contextDigest: decoder.string(
      decoder.field(value, "context_digest", path),
      `${path}.context_digest`,
      true,
    ),
    checks: decoder.array(
      decoder.field(value, "checks", path),
      `${path}.checks`,
      (rawCheck, checkPath) => {
        const check = decoder.record(rawCheck, checkPath);
        return {
          name: decoder.string(
            decoder.field(check, "name", checkPath),
            `${checkPath}.name`,
          ),
          status: decoder.enumeration(
            decoder.field(check, "status", checkPath),
            ["passed", "failed", "warning", "skipped"] as const,
            `${checkPath}.status`,
          ),
          code: decoder.string(
            decoder.field(check, "code", checkPath),
            `${checkPath}.code`,
            true,
          ),
          message: decoder.string(
            decoder.field(check, "message", checkPath),
            `${checkPath}.message`,
            true,
          ),
        };
      },
    ),
    attempts: decoder.integer(
      decoder.field(value, "attempts", path),
      `${path}.attempts`,
      1,
      3,
    ),
    recoveryStrategy: decoder.string(
      decoder.field(value, "recovery_strategy", path),
      `${path}.recovery_strategy`,
    ),
    durationMs: decoder.integer(
      decoder.field(value, "duration_ms", path),
      `${path}.duration_ms`,
    ),
  };
}

// Historical compatibility only. Never route invalid v3 evidence here.
function decodeLegacyHarnessTraceV2(
  value: Record<string, unknown>,
  path: string,
): HarnessTraceV2 {
  const traceId = decoder.string(
    decoder.field(value, "trace_id", path),
    `${path}.trace_id`,
  );
  const operationId = decoder.string(
    decoder.field(value, "operation_id", path),
    `${path}.operation_id`,
  );
  if (!/^harness-trace-[0-9a-f]{32}$/.test(traceId))
    throw new TavernDecodeError(`${path}.trace_id`, "invalid_harness_trace_id");
  if (!/^harness-operation-[0-9a-f]{32}$/.test(operationId))
    throw new TavernDecodeError(`${path}.operation_id`, "invalid_harness_operation_id");
  const workflow = decoder.string(
    decoder.field(value, "workflow", path),
    `${path}.workflow`,
  );
  const stage = decoder.string(decoder.field(value, "stage", path), `${path}.stage`);
  const context = decoder.record(
    decoder.field(value, "context", path),
    `${path}.context`,
  );
  const checks = decoder.array(
    decoder.field(value, "checks", path),
    `${path}.checks`,
    (item, itemPath) => {
      const check = decoder.record(item, itemPath);
      return {
        name: decoder.string(
          decoder.field(check, "name", itemPath),
          `${itemPath}.name`,
        ),
        status: decoder.enumeration(
          decoder.field(check, "status", itemPath),
          ["passed", "failed", "warning", "skipped"] as const,
          `${itemPath}.status`,
        ),
        code: decoder.string(
          decoder.field(check, "code", itemPath),
          `${itemPath}.code`,
          true,
        ),
        message: decoder.string(
          decoder.field(check, "message", itemPath),
          `${itemPath}.message`,
          true,
        ),
      };
    },
  );
  const rawAttempts = decoder.array(
    decoder.field(value, "attempt_records", path),
    `${path}.attempt_records`,
    (item, itemPath) => decoder.record(item, itemPath),
  );
  rawAttempts.forEach((item, index) => {
    if (
      item.attempt_index !== index + 1 ||
      typeof item.attempt_id !== "string" ||
      !/^harness-attempt-[0-9a-f]{32}$/.test(item.attempt_id)
    ) {
      throw new TavernDecodeError(
        `${path}.attempt_records[${index}]`,
        "invalid_attempt_ordering",
      );
    }
  });
  const attempts = rawAttempts as never;
  const base = {
    traceSchemaVersion: "harness-trace-v2",
    traceId,
    operationId,
    parentTraceId: nullableField(value, "parent_trace_id", path, (item, itemPath) =>
      decoder.string(item, itemPath, true),
    ),
    workflow: workflow as HarnessTraceV2["workflow"],
    stage: stage as HarnessTraceV2["stage"],
    status: decoder.enumeration(
      decoder.field(value, "status", path),
      ["passed", "repaired", "failed", "skipped"] as const,
      `${path}.status`,
    ),
    contract: value.contract as never,
    context: context as never,
    outputDigest: typeof value.output_digest === "string" ? value.output_digest : null,
    checks: checks as never,
    attemptRecords: attempts,
    recoveryStrategy: decoder.string(
      decoder.field(value, "recovery_strategy", path),
      `${path}.recovery_strategy`,
    ),
    errorCode: decoder.string(
      decoder.field(value, "error_code", path),
      `${path}.error_code`,
      true,
    ),
    durationMs: decoder.integer(
      decoder.field(value, "duration_ms", path),
      `${path}.duration_ms`,
    ),
    commitEvidence: value.commit_evidence as never,
    startedAt: decoder.string(
      decoder.field(value, "started_at", path),
      `${path}.started_at`,
    ),
    completedAt: decoder.string(
      decoder.field(value, "completed_at", path),
      `${path}.completed_at`,
    ),
  };
  return base as unknown as HarnessTraceV2;
}

function decodePolicy(raw: unknown, path: string): TavernHarnessPolicy {
  const value = decoder.record(raw, path);
  return {
    version: decoder.string(decoder.field(value, "version", path), `${path}.version`),
    maxCharacterMessages: decoder.integer(
      decoder.field(value, "max_character_messages", path),
      `${path}.max_character_messages`,
      1,
      4,
    ),
    maxReplyCharacters: decoder.integer(
      decoder.field(value, "max_reply_characters", path),
      `${path}.max_reply_characters`,
      120,
      4000,
    ),
    contextMessageLimit: decoder.integer(
      decoder.field(value, "context_message_limit", path),
      `${path}.context_message_limit`,
      4,
      40,
    ),
    preventSpeakerImpersonation: decoder.boolean(
      decoder.field(value, "prevent_speaker_impersonation", path),
      `${path}.prevent_speaker_impersonation`,
    ),
  };
}

function decodeRoom(raw: unknown, path: string): TavernRoom {
  const value = decoder.record(raw, path);
  return {
    id: decoder.string(decoder.field(value, "id", path), `${path}.id`),
    creationKey: optionalStringField(value, "creation_key", path),
    creationInputDigest: optionalStringField(value, "creation_input_digest", path),
    title: decoder.string(decoder.field(value, "title", path), `${path}.title`),
    sceneProfile: nullableField(value, "scene_profile", path, decodeScene) ?? undefined,
    harnessPolicy: decodePolicy(
      decoder.field(value, "harness_policy", path),
      `${path}.harness_policy`,
    ),
    status: decoder.enumeration(
      decoder.field(value, "status", path),
      ["active", "archived"] as const,
      `${path}.status`,
    ),
    revision: decoder.integer(
      decoder.field(value, "revision", path),
      `${path}.revision`,
    ),
    lastSequence: decoder.integer(
      decoder.field(value, "last_sequence", path),
      `${path}.last_sequence`,
    ),
    createdAt: decoder.string(
      decoder.field(value, "created_at", path),
      `${path}.created_at`,
    ),
    updatedAt: decoder.string(
      decoder.field(value, "updated_at", path),
      `${path}.updated_at`,
    ),
  };
}

function decodeRoomState(raw: unknown, path: string): TavernRoomState {
  const value = decoder.record(raw, path);
  return {
    id: decoder.string(decoder.field(value, "id", path), `${path}.id`),
    status: decoder.enumeration(
      decoder.field(value, "status", path),
      ["active", "archived"] as const,
      `${path}.status`,
    ),
    revision: decoder.integer(
      decoder.field(value, "revision", path),
      `${path}.revision`,
    ),
    lastSequence: decoder.integer(
      decoder.field(value, "last_sequence", path),
      `${path}.last_sequence`,
    ),
    updatedAt: decoder.string(
      decoder.field(value, "updated_at", path),
      `${path}.updated_at`,
    ),
  };
}

function decodeParticipant(raw: unknown, path: string): TavernParticipant {
  const value = decoder.record(raw, path);
  return {
    roomId: decoder.string(decoder.field(value, "room_id", path), `${path}.room_id`),
    personaId: decoder.string(
      decoder.field(value, "persona_id", path),
      `${path}.persona_id`,
    ),
    displayOrder: decoder.integer(
      decoder.field(value, "display_order", path),
      `${path}.display_order`,
    ),
    displayName: decoder.string(
      decoder.field(value, "display_name", path),
      `${path}.display_name`,
      true,
    ),
    personaSnapshot: decodePersona(
      decoder.field(value, "persona_snapshot", path),
      `${path}.persona_snapshot`,
    ),
    promptHash: decoder.string(
      decoder.field(value, "prompt_hash", path),
      `${path}.prompt_hash`,
    ),
    joinedAt: decoder.string(
      decoder.field(value, "joined_at", path),
      `${path}.joined_at`,
    ),
  };
}

function decodeMessage(raw: unknown, path: string): TavernMessage {
  const value = decoder.record(raw, path);
  const trace = nullableField(value, "harness_trace", path, decodeHarnessTrace);
  return {
    id: decoder.string(decoder.field(value, "id", path), `${path}.id`),
    roomId: decoder.string(decoder.field(value, "room_id", path), `${path}.room_id`),
    sequence: decoder.integer(
      decoder.field(value, "sequence", path),
      `${path}.sequence`,
      1,
    ),
    runId: optionalStringField(value, "run_id", path),
    authorKind: decoder.enumeration(
      decoder.field(value, "author_kind", path),
      ["user", "persona", "director", "system"] as const,
      `${path}.author_kind`,
    ),
    personaId: optionalStringField(value, "persona_id", path),
    personaName: optionalStringField(value, "persona_name", path),
    content: decoder.string(
      decoder.field(value, "content", path),
      `${path}.content`,
      true,
    ),
    emotion: decoder.string(
      decoder.field(value, "emotion", path),
      `${path}.emotion`,
      true,
    ),
    action: optionalStringField(value, "action", path),
    speechStyle: optionalStringField(value, "speech_style", path),
    addressedParticipantIds: decoder.stringArray(
      decoder.field(value, "addressed_participant_ids", path),
      `${path}.addressed_participant_ids`,
    ),
    replyToMessageId: optionalStringField(value, "reply_to_message_id", path),
    clientRequestId: optionalStringField(value, "client_request_id", path),
    createdAt: decoder.string(
      decoder.field(value, "created_at", path),
      `${path}.created_at`,
    ),
    harnessTrace: trace ?? undefined,
  };
}

function decodeStep(raw: unknown, path: string): TavernSpeakerStep {
  const value = decoder.record(raw, path);
  const trace = nullableField(value, "harness_trace", path, decodeHarnessTrace);
  return {
    runId: decoder.string(decoder.field(value, "run_id", path), `${path}.run_id`),
    stepIndex: decoder.integer(
      decoder.field(value, "step_index", path),
      `${path}.step_index`,
      0,
      3,
    ),
    personaId: decoder.string(
      decoder.field(value, "persona_id", path),
      `${path}.persona_id`,
    ),
    participantPromptHash: decoder.string(
      decoder.field(value, "participant_prompt_hash", path),
      `${path}.participant_prompt_hash`,
      true,
    ),
    status: decoder.enumeration(
      decoder.field(value, "status", path),
      ["pending", "generating", "completed", "failed", "blocked", "canceled"] as const,
      `${path}.status`,
    ),
    messageId: optionalStringField(value, "message_id", path),
    replyToMessageId: optionalStringField(value, "reply_to_message_id", path),
    errorCode: optionalStringField(value, "error_code", path),
    harnessTrace: trace ?? undefined,
    claimCount: decoder.integer(
      decoder.field(value, "claim_count", path),
      `${path}.claim_count`,
      0,
      5,
    ),
    startedAt: optionalStringField(value, "started_at", path),
    completedAt: optionalStringField(value, "completed_at", path),
  };
}

function decodeRun(raw: unknown, path: string): TavernRun {
  const value = decoder.record(raw, path);
  const inputMessageId = nullableField(
    value,
    "input_message_id",
    path,
    (item, itemPath) => decoder.string(item, itemPath),
  );
  const run: TavernRun = {
    id: decoder.string(decoder.field(value, "id", path), `${path}.id`),
    roomId: decoder.string(decoder.field(value, "room_id", path), `${path}.room_id`),
    idempotencyKey: decoder.string(
      decoder.field(value, "idempotency_key", path),
      `${path}.idempotency_key`,
    ),
    requestDigest: optionalStringField(value, "request_digest", path),
    contextDigest: optionalStringField(value, "context_digest", path),
    mode: decoder.enumeration(
      decoder.field(value, "mode", path),
      ["direct", "facilitated"] as const,
      `${path}.mode`,
    ),
    triggerKind: decoder.enumeration(
      decoder.field(value, "trigger_kind", path),
      ["user_message", "continue", "retry"] as const,
      `${path}.trigger_kind`,
    ),
    parentRunId: optionalStringField(value, "parent_run_id", path),
    rootRunId: optionalStringField(value, "root_run_id", path),
    inputMessageId,
    anchorMessageId: optionalStringField(value, "anchor_message_id", path),
    scheduledParticipantIds: decoder.stringArray(
      decoder.field(value, "scheduled_participant_ids", path),
      `${path}.scheduled_participant_ids`,
    ),
    speakerSteps: decoder.array(
      decoder.field(value, "speaker_steps", path),
      `${path}.speaker_steps`,
      decodeStep,
    ),
    guidance: decoder.string(
      decoder.field(value, "guidance", path),
      `${path}.guidance`,
      true,
    ),
    status: decoder.enumeration(
      decoder.field(value, "status", path),
      ["pending", "completed", "partial", "failed", "canceled"] as const,
      `${path}.status`,
    ),
    expectedRoomRevision: decoder.integer(
      decoder.field(value, "expected_room_revision", path),
      `${path}.expected_room_revision`,
    ),
    generatedMessageIds: decoder.stringArray(
      decoder.field(value, "generated_message_ids", path),
      `${path}.generated_message_ids`,
    ),
    harnessTrace: decoder.array(
      decoder.field(value, "harness_trace", path),
      `${path}.harness_trace`,
      decodeHarnessTrace,
    ),
    errorCode: optionalStringField(value, "error_code", path),
    terminalSequence: decoder.integer(
      decoder.field(value, "terminal_sequence", path),
      `${path}.terminal_sequence`,
    ),
    createdAt: decoder.string(
      decoder.field(value, "created_at", path),
      `${path}.created_at`,
    ),
    completedAt: optionalStringField(value, "completed_at", path),
  };
  for (const [index, step] of run.speakerSteps.entries()) {
    decoder.equal(step.runId, run.id, `${path}.speaker_steps[${index}].run_id`);
    if (step.stepIndex !== index) {
      throw new TavernDecodeError(
        `${path}.speaker_steps[${index}].step_index`,
        `schedule_index_mismatch_expected_${index}`,
      );
    }
    decoder.equal(
      step.personaId,
      run.scheduledParticipantIds[index] ?? "",
      `${path}.speaker_steps[${index}].persona_id`,
    );
    if (step.status === "completed" && !step.messageId) {
      throw new TavernDecodeError(
        `${path}.speaker_steps[${index}].message_id`,
        "completed_step_message_required",
      );
    }
    if (step.status !== "completed" && step.messageId) {
      throw new TavernDecodeError(
        `${path}.speaker_steps[${index}].message_id`,
        "non_completed_step_message_forbidden",
      );
    }
  }
  if (
    run.scheduledParticipantIds.length < 1 ||
    run.scheduledParticipantIds.length !== run.speakerSteps.length
  ) {
    throw new TavernDecodeError(
      `${path}.speaker_steps`,
      "schedule_step_count_mismatch",
    );
  }
  decoder.unique(run.scheduledParticipantIds, `${path}.scheduled_participant_ids`);
  decoder.unique(
    run.speakerSteps.map((step) => step.stepIndex),
    `${path}.speaker_steps.step_index`,
  );
  decoder.unique(
    run.speakerSteps.map((step) => step.personaId),
    `${path}.speaker_steps.persona_id`,
  );
  decoder.unique(run.generatedMessageIds, `${path}.generated_message_ids`);
  return run;
}

export function normalizeTavernRoomDetail(
  raw: unknown,
  expectedRoomId?: string,
): TavernRoomDetail {
  const path = "tavern.room_detail";
  const value = decoder.record(raw, path);
  const room = decodeRoom(decoder.field(value, "room", path), `${path}.room`);
  if (expectedRoomId !== undefined) {
    decoder.equal(room.id, expectedRoomId, `${path}.room.id`);
  }
  const participants = decoder.array(
    decoder.field(value, "participants", path),
    `${path}.participants`,
    decodeParticipant,
  );
  const messages = decoder.array(
    decoder.field(value, "messages", path),
    `${path}.messages`,
    decodeMessage,
  );
  for (const [index, participant] of participants.entries()) {
    decoder.equal(
      participant.roomId,
      room.id,
      `${path}.participants[${index}].room_id`,
    );
    decoder.equal(
      participant.personaSnapshot.id,
      participant.personaId,
      `${path}.participants[${index}].persona_snapshot.id`,
    );
  }
  for (const [index, message] of messages.entries()) {
    decoder.equal(message.roomId, room.id, `${path}.messages[${index}].room_id`);
  }
  decoder.unique(
    participants.map((item) => item.personaId),
    `${path}.participants.persona_id`,
  );
  decoder.unique(
    participants.map((item) => item.displayOrder),
    `${path}.participants.display_order`,
  );
  decoder.unique(
    messages.map((item) => item.id),
    `${path}.messages.id`,
  );
  decoder.unique(
    messages.map((item) => item.sequence),
    `${path}.messages.sequence`,
  );
  return {
    room,
    participants,
    messages,
    messageCount: decoder.integer(
      decoder.field(value, "message_count", path),
      `${path}.message_count`,
    ),
    nextAfterSequence: nullableField(
      value,
      "next_after_sequence",
      path,
      (item, itemPath) => decoder.integer(item, itemPath, 1),
    ),
    nextBeforeSequence: nullableField(
      value,
      "next_before_sequence",
      path,
      (item, itemPath) => decoder.integer(item, itemPath, 1),
    ),
  };
}

export function normalizeTavernTurnResult(
  raw: unknown,
  expectedRoomId?: string,
): TavernTurnResult {
  const path = "tavern.turn_result";
  const value = decoder.record(raw, path);
  const run = decodeRun(decoder.field(value, "run", path), `${path}.run`);
  const inputMessage = nullableField(value, "input_message", path, decodeMessage);
  const generatedMessages = decoder.array(
    decoder.field(value, "generated_messages", path),
    `${path}.generated_messages`,
    decodeMessage,
  );
  const roomState = decodeRoomState(
    decoder.field(value, "room_state", path),
    `${path}.room_state`,
  );
  if (expectedRoomId !== undefined) {
    decoder.equal(roomState.id, expectedRoomId, `${path}.room_state.id`);
  }
  decoder.equal(run.roomId, roomState.id, `${path}.run.room_id`);
  if (run.triggerKind === "user_message") {
    if (!run.inputMessageId || !inputMessage) {
      throw new TavernDecodeError(
        `${path}.input_message`,
        "user_message_trigger_requires_input_message",
      );
    }
  } else if (inputMessage) {
    throw new TavernDecodeError(
      `${path}.input_message`,
      `${run.triggerKind}_trigger_forbids_input_message`,
    );
  }
  if (run.triggerKind === "continue" && run.inputMessageId !== null) {
    throw new TavernDecodeError(
      `${path}.run.input_message_id`,
      "continue_trigger_forbids_input_message_id",
    );
  }
  if (inputMessage) {
    decoder.equal(inputMessage.roomId, roomState.id, `${path}.input_message.room_id`);
    decoder.equal(
      inputMessage.id,
      run.inputMessageId ?? "",
      `${path}.input_message.id`,
    );
    decoder.equal(inputMessage.runId ?? "", run.id, `${path}.input_message.run_id`);
    if (inputMessage.authorKind !== "user") {
      throw new TavernDecodeError(`${path}.input_message.author_kind`, "expected_user");
    }
  }
  const completedSteps = run.speakerSteps.filter((step) => step.status === "completed");
  const completedStepByMessageId = new Map(
    completedSteps.map((step) => [step.messageId as string, step]),
  );
  for (const [index, message] of generatedMessages.entries()) {
    decoder.equal(
      message.roomId,
      roomState.id,
      `${path}.generated_messages[${index}].room_id`,
    );
    decoder.equal(
      message.runId ?? "",
      run.id,
      `${path}.generated_messages[${index}].run_id`,
    );
    if (message.authorKind !== "persona") {
      throw new TavernDecodeError(
        `${path}.run.speaker_steps[${index}].message_id`,
        "message_not_in_generated_messages",
      );
    }
    const step = completedStepByMessageId.get(message.id);
    if (!step) {
      throw new TavernDecodeError(
        `${path}.generated_messages[${index}].id`,
        "message_not_owned_by_completed_step",
      );
    }
    decoder.equal(
      message.personaId ?? "",
      step.personaId,
      `${path}.generated_messages[${index}].persona_id`,
    );
  }
  decoder.unique(
    generatedMessages.map((message) => message.id),
    `${path}.generated_messages.id`,
  );
  decoder.unique(
    generatedMessages.map((message) => message.sequence),
    `${path}.generated_messages.sequence`,
  );
  const returnedMessageIds = generatedMessages.map((message) => message.id);
  const completedMessageIds = completedSteps.map((step) => step.messageId as string);
  if (
    JSON.stringify(run.generatedMessageIds) !== JSON.stringify(completedMessageIds) ||
    JSON.stringify(returnedMessageIds) !== JSON.stringify(completedMessageIds)
  ) {
    throw new TavernDecodeError(
      `${path}.generated_messages`,
      "generated_messages_do_not_match_completed_steps",
    );
  }
  if (roomState.lastSequence < run.terminalSequence) {
    throw new TavernDecodeError(
      `${path}.room_state.last_sequence`,
      "before_run_terminal_sequence",
    );
  }
  return { run, inputMessage, generatedMessages, roomState };
}

export function normalizeTavernRoomList(raw: unknown): TavernRoomPage {
  const path = "tavern.room_list";
  const value = decoder.record(raw, path);
  const contractVersion = decoder.enumeration(
    decoder.field(value, "contract_version", path),
    ["tavern-room-list-v1"] as const,
    `${path}.contract_version`,
  );
  const rooms = decoder.array(
    decoder.field(value, "items", path),
    `${path}.items`,
    (rawItem, itemPath) => {
      const item = decoder.record(rawItem, itemPath);
      return {
        id: decoder.string(decoder.field(item, "id", itemPath), `${itemPath}.id`),
        title: decoder.string(
          decoder.field(item, "title", itemPath),
          `${itemPath}.title`,
        ),
        participantPersonaIds: decoder.stringArray(
          decoder.field(item, "participant_persona_ids", itemPath),
          `${itemPath}.participant_persona_ids`,
        ),
        participantNames: decoder.stringArray(
          decoder.field(item, "participant_names", itemPath),
          `${itemPath}.participant_names`,
        ),
        messageCount: decoder.integer(
          decoder.field(item, "message_count", itemPath),
          `${itemPath}.message_count`,
        ),
        revision: decoder.integer(
          decoder.field(item, "revision", itemPath),
          `${itemPath}.revision`,
        ),
        status: decoder.enumeration(
          decoder.field(item, "status", itemPath),
          ["active", "archived"] as const,
          `${itemPath}.status`,
        ),
        createdAt: decoder.string(
          decoder.field(item, "created_at", itemPath),
          `${itemPath}.created_at`,
        ),
        updatedAt: decoder.string(
          decoder.field(item, "updated_at", itemPath),
          `${itemPath}.updated_at`,
        ),
      };
    },
  );
  if (rooms.length > 50) {
    throw new TavernDecodeError(`${path}.items`, "room_page_exceeds_maximum");
  }
  decoder.unique(
    rooms.map((room) => room.id),
    `${path}.items.id`,
  );
  for (let index = 1; index < rooms.length; index += 1) {
    const previous = rooms[index - 1]!;
    const current = rooms[index]!;
    if (
      previous.updatedAt < current.updatedAt ||
      (previous.updatedAt === current.updatedAt && previous.id <= current.id)
    ) {
      throw new TavernDecodeError(
        `${path}.items[${index}]`,
        "room_page_not_monotonic_updated_at_id_desc",
      );
    }
  }
  const nextCursor = nullableField(value, "next_cursor", path, (cursor, cursorPath) => {
    const decoded = decoder.string(cursor, cursorPath);
    if (decoded.length > 512) {
      throw new TavernDecodeError(cursorPath, "cursor_exceeds_maximum_length");
    }
    return decoded;
  });
  if (!rooms.length && nextCursor !== null) {
    throw new TavernDecodeError(`${path}.next_cursor`, "empty_page_has_next_cursor");
  }
  return { contractVersion, items: rooms, nextCursor };
}

export function normalizeTavernRunList(
  raw: unknown,
  expectedRoomId?: string,
): TavernRun[] {
  const path = "tavern.run_list";
  const value = decoder.record(raw, path);
  const runs = decoder.array(
    decoder.field(value, "items", path),
    `${path}.items`,
    decodeRun,
  );
  if (expectedRoomId !== undefined) {
    for (const [index, run] of runs.entries()) {
      decoder.equal(run.roomId, expectedRoomId, `${path}.items[${index}].room_id`);
    }
  }
  decoder.unique(
    runs.map((run) => run.id),
    `${path}.items.id`,
  );
  return runs;
}

export function normalizeTavernRunRecovery(
  raw: unknown,
  expectedRoomId?: string,
): TavernRunRecoveryChain[] {
  const path = "tavern.run_recovery";
  const value = decoder.record(raw, path);
  const chains = decoder.array(
    decoder.field(value, "items", path),
    `${path}.items`,
    (rawItem, itemPath) => {
      const item = decoder.record(rawItem, itemPath);
      const rootRunId = decoder.string(
        decoder.field(item, "root_run_id", itemPath),
        `${itemPath}.root_run_id`,
      );
      const runIds = decoder.stringArray(
        decoder.field(item, "run_ids", itemPath),
        `${itemPath}.run_ids`,
      );
      const leafRun = decodeRun(
        decoder.field(item, "leaf_run", itemPath),
        `${itemPath}.leaf_run`,
      );
      if (
        !runIds.length ||
        runIds[0] !== rootRunId ||
        runIds[runIds.length - 1] !== leafRun.id
      ) {
        throw new TavernDecodeError(
          `${itemPath}.run_ids`,
          "retry_chain_identity_mismatch",
        );
      }
      decoder.unique(runIds, `${itemPath}.run_ids`);
      if (expectedRoomId !== undefined) {
        decoder.equal(leafRun.roomId, expectedRoomId, `${itemPath}.leaf_run.room_id`);
      }
      const chainStatus = decoder.enumeration(
        decoder.field(item, "chain_status", itemPath),
        ["active", "recoverable", "recovered", "completed", "canceled"] as const,
        `${itemPath}.chain_status`,
      );
      const recoveryAction = decoder.enumeration(
        decoder.field(item, "recovery_action", itemPath),
        [
          "none",
          "replay_same_request",
          "reload_room",
          "wait_and_resume",
          "retry_leaf",
        ] as const,
        `${itemPath}.recovery_action`,
      );
      if ((chainStatus === "recoverable") !== (recoveryAction === "retry_leaf")) {
        throw new TavernDecodeError(
          `${itemPath}.recovery_action`,
          "chain_action_mismatch",
        );
      }
      return {
        rootRunId,
        runIds,
        rootStatus: decoder.enumeration(
          decoder.field(item, "root_status", itemPath),
          ["pending", "completed", "partial", "failed", "canceled"] as const,
          `${itemPath}.root_status`,
        ),
        leafRun,
        chainStatus,
        recoveryAction,
        completedParticipantIds: decoder.stringArray(
          decoder.field(item, "completed_participant_ids", itemPath),
          `${itemPath}.completed_participant_ids`,
        ),
        unfinishedParticipantIds: decoder.stringArray(
          decoder.field(item, "unfinished_participant_ids", itemPath),
          `${itemPath}.unfinished_participant_ids`,
        ),
      };
    },
  );
  decoder.unique(
    chains.map((chain) => chain.rootRunId),
    `${path}.items.root_run_id`,
  );
  return chains;
}

export function normalizeTavernErrorDetail(raw: unknown): TavernErrorDetail {
  const path = "tavern.error";
  const envelope = decoder.record(raw, path);
  const detailPath = `${path}.detail`;
  const value = decoder.record(decoder.field(envelope, "detail", path), detailPath);
  return {
    code: decoder.string(
      decoder.field(value, "code", detailPath),
      `${detailPath}.code`,
    ),
    runId: optionalStringField(value, "run_id", detailPath),
    childRunId: optionalStringField(value, "child_run_id", detailPath),
    currentRevision: nullableField(
      value,
      "current_revision",
      detailPath,
      (item, itemPath) => decoder.integer(item, itemPath, 0),
    ),
    recoveryAction: decoder.enumeration(
      decoder.field(value, "recovery_action", detailPath),
      [
        "none",
        "replay_same_request",
        "reload_room",
        "wait_and_resume",
        "retry_leaf",
      ] as const,
      `${detailPath}.recovery_action`,
    ),
  };
}

export function isTavernTerminalReplayDirective(
  status: number,
  detail: TavernErrorDetail | null,
): boolean {
  return (
    status === 502 &&
    detail?.recoveryAction === "replay_same_request" &&
    Boolean(detail.runId)
  );
}
