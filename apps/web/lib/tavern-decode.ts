import type {
  HarnessTraceV1,
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
  TavernRoomSummary,
  TavernRun,
  TavernRunRecoveryChain,
  TavernSpeakerStep,
  TavernTurnResult,
} from "@vibe-learner/shared";

export class TavernDecodeError extends Error {
  readonly code = "tavern_response_decode_error";
  readonly path: string;

  constructor(path: string, reason: string) {
    super(`${reason} at ${path}`);
    this.name = "TavernDecodeError";
    this.path = path;
  }
}

function record(raw: unknown, path: string): Record<string, unknown> {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) {
    throw new TavernDecodeError(path, "expected_object");
  }
  return raw as Record<string, unknown>;
}

function field(value: Record<string, unknown>, key: string, path: string): unknown {
  if (!Object.prototype.hasOwnProperty.call(value, key)) {
    throw new TavernDecodeError(`${path}.${key}`, "missing_required_field");
  }
  return value[key];
}

function string(raw: unknown, path: string, allowEmpty = false): string {
  if (typeof raw !== "string" || (!allowEmpty && raw.length === 0)) {
    throw new TavernDecodeError(
      path,
      allowEmpty ? "expected_string" : "expected_non_empty_string"
    );
  }
  return raw;
}

function optionalStringField(
  value: Record<string, unknown>,
  key: string,
  path: string
): string | undefined {
  const decoded = string(field(value, key, path), `${path}.${key}`, true);
  return decoded || undefined;
}

function integer(
  raw: unknown,
  path: string,
  minimum = 0,
  maximum = Number.MAX_SAFE_INTEGER
): number {
  if (
    !Number.isSafeInteger(raw) ||
    (raw as number) < minimum ||
    (raw as number) > maximum
  ) {
    throw new TavernDecodeError(path, `expected_integer_${minimum}_to_${maximum}`);
  }
  return raw as number;
}

function finiteNumber(raw: unknown, path: string): number {
  if (typeof raw !== "number" || !Number.isFinite(raw)) {
    throw new TavernDecodeError(path, "expected_finite_number");
  }
  return raw;
}

function boolean(raw: unknown, path: string): boolean {
  if (typeof raw !== "boolean") throw new TavernDecodeError(path, "expected_boolean");
  return raw;
}

function enumeration<T extends string>(
  raw: unknown,
  values: readonly T[],
  path: string
): T {
  if (typeof raw !== "string" || !values.includes(raw as T)) {
    throw new TavernDecodeError(path, `unexpected_enum_${String(raw)}`);
  }
  return raw as T;
}

function array<T>(
  raw: unknown,
  path: string,
  decode: (value: unknown, itemPath: string) => T
): T[] {
  if (!Array.isArray(raw)) throw new TavernDecodeError(path, "expected_array");
  return raw.map((item, index) => decode(item, `${path}[${index}]`));
}

function stringArray(raw: unknown, path: string): string[] {
  return array(raw, path, (item, itemPath) => string(item, itemPath));
}

function nullableField<T>(
  value: Record<string, unknown>,
  key: string,
  path: string,
  decode: (raw: unknown, valuePath: string) => T
): T | null {
  const raw = field(value, key, path);
  return raw === null ? null : decode(raw, `${path}.${key}`);
}

function assertUnique<T extends string | number>(values: T[], path: string): void {
  if (new Set(values).size !== values.length) {
    throw new TavernDecodeError(path, "expected_unique_values");
  }
}

function assertEqual(actual: string, expected: string, path: string): void {
  if (actual !== expected) {
    throw new TavernDecodeError(path, `identity_mismatch_expected_${expected}`);
  }
}

function decodePersonaSlot(raw: unknown, path: string): PersonaProfile["slots"][number] {
  const value = record(raw, path);
  return {
    kind: string(field(value, "kind", path), `${path}.kind`),
    label: string(field(value, "label", path), `${path}.label`, true),
    content: string(field(value, "content", path), `${path}.content`, true),
    weight: finiteNumber(field(value, "weight", path), `${path}.weight`),
    locked: boolean(field(value, "locked", path), `${path}.locked`),
    sortOrder: integer(field(value, "sort_order", path), `${path}.sort_order`),
  };
}

function decodePersona(raw: unknown, path: string): PersonaProfile {
  const value = record(raw, path);
  return {
    id: string(field(value, "id", path), `${path}.id`),
    name: string(field(value, "name", path), `${path}.name`, true),
    source: enumeration(field(value, "source", path), ["builtin", "user"] as const, `${path}.source`),
    summary: string(field(value, "summary", path), `${path}.summary`, true),
    relationship: string(field(value, "relationship", path), `${path}.relationship`, true),
    learnerAddress: string(field(value, "learner_address", path), `${path}.learner_address`, true),
    systemPrompt: string(field(value, "system_prompt", path), `${path}.system_prompt`, true),
    referenceHints: stringArray(field(value, "reference_hints", path), `${path}.reference_hints`),
    slots: array(field(value, "slots", path), `${path}.slots`, decodePersonaSlot),
    availableEmotions: stringArray(field(value, "available_emotions", path), `${path}.available_emotions`),
    availableActions: stringArray(field(value, "available_actions", path), `${path}.available_actions`),
    defaultSpeechStyle: string(field(value, "default_speech_style", path), `${path}.default_speech_style`, true),
  };
}

function decodeSceneObject(raw: unknown, path: string): SceneObjectSnapshot {
  const value = record(raw, path);
  return {
    id: string(field(value, "id", path), `${path}.id`, true),
    name: string(field(value, "name", path), `${path}.name`, true),
    description: string(field(value, "description", path), `${path}.description`, true),
    interaction: string(field(value, "interaction", path), `${path}.interaction`, true),
    tags: string(field(value, "tags", path), `${path}.tags`, true),
    reuseId: string(field(value, "reuse_id", path), `${path}.reuse_id`, true),
    reuseHint: string(field(value, "reuse_hint", path), `${path}.reuse_hint`, true),
  };
}

function decodeSceneNode(raw: unknown, path: string): SceneTreeNode {
  const value = record(raw, path);
  return {
    id: string(field(value, "id", path), `${path}.id`, true),
    title: string(field(value, "title", path), `${path}.title`, true),
    scopeLabel: string(field(value, "scope_label", path), `${path}.scope_label`, true),
    summary: string(field(value, "summary", path), `${path}.summary`, true),
    atmosphere: string(field(value, "atmosphere", path), `${path}.atmosphere`, true),
    rules: string(field(value, "rules", path), `${path}.rules`, true),
    entrance: string(field(value, "entrance", path), `${path}.entrance`, true),
    tags: string(field(value, "tags", path), `${path}.tags`, true),
    reuseId: string(field(value, "reuse_id", path), `${path}.reuse_id`, true),
    reuseHint: string(field(value, "reuse_hint", path), `${path}.reuse_hint`, true),
    objects: array(field(value, "objects", path), `${path}.objects`, decodeSceneObject),
    children: array(field(value, "children", path), `${path}.children`, decodeSceneNode),
  };
}

function decodeScene(raw: unknown, path: string): SceneProfile {
  const value = record(raw, path);
  return {
    sceneName: string(field(value, "scene_name", path), `${path}.scene_name`, true),
    sceneId: string(field(value, "scene_id", path), `${path}.scene_id`, true),
    title: string(field(value, "title", path), `${path}.title`, true),
    summary: string(field(value, "summary", path), `${path}.summary`, true),
    tags: stringArray(field(value, "tags", path), `${path}.tags`),
    selectedPath: stringArray(field(value, "selected_path", path), `${path}.selected_path`),
    focusObjectNames: stringArray(field(value, "focus_object_names", path), `${path}.focus_object_names`),
    sceneTree: array(field(value, "scene_tree", path), `${path}.scene_tree`, decodeSceneNode),
  };
}

function decodeHarnessTrace(raw: unknown, path: string): HarnessTraceV1 {
  const value = record(raw, path);
  if (Object.prototype.hasOwnProperty.call(value, "trace_schema_version")) {
    throw new TavernDecodeError(
      `${path}.trace_schema_version`,
      `unsupported_harness_trace_schema_version_${String(value.trace_schema_version)}`
    );
  }
  const version = string(field(value, "version", path), `${path}.version`);
  if (version.startsWith("harness-trace-")) {
    throw new TavernDecodeError(
      `${path}.version`,
      "harness_trace_schema_version_discriminator_required"
    );
  }
  return {
    version,
    workflow: string(field(value, "workflow", path), `${path}.workflow`),
    stage: string(field(value, "stage", path), `${path}.stage`),
    status: enumeration(
      field(value, "status", path),
      ["passed", "repaired", "failed", "skipped"] as const,
      `${path}.status`
    ),
    schemaName: string(field(value, "schema_name", path), `${path}.schema_name`),
    inputDigest: string(field(value, "input_digest", path), `${path}.input_digest`, true),
    contextDigest: string(field(value, "context_digest", path), `${path}.context_digest`, true),
    checks: array(field(value, "checks", path), `${path}.checks`, (rawCheck, checkPath) => {
      const check = record(rawCheck, checkPath);
      return {
        name: string(field(check, "name", checkPath), `${checkPath}.name`),
        status: enumeration(
          field(check, "status", checkPath),
          ["passed", "failed", "warning", "skipped"] as const,
          `${checkPath}.status`
        ),
        code: string(field(check, "code", checkPath), `${checkPath}.code`, true),
        message: string(field(check, "message", checkPath), `${checkPath}.message`, true),
      };
    }),
    attempts: integer(field(value, "attempts", path), `${path}.attempts`, 1, 3),
    recoveryStrategy: string(field(value, "recovery_strategy", path), `${path}.recovery_strategy`),
    durationMs: integer(field(value, "duration_ms", path), `${path}.duration_ms`),
  };
}

function decodePolicy(raw: unknown, path: string): TavernHarnessPolicy {
  const value = record(raw, path);
  return {
    version: string(field(value, "version", path), `${path}.version`),
    maxCharacterMessages: integer(field(value, "max_character_messages", path), `${path}.max_character_messages`, 1, 4),
    maxReplyCharacters: integer(field(value, "max_reply_characters", path), `${path}.max_reply_characters`, 120, 4000),
    contextMessageLimit: integer(field(value, "context_message_limit", path), `${path}.context_message_limit`, 4, 40),
    preventSpeakerImpersonation: boolean(field(value, "prevent_speaker_impersonation", path), `${path}.prevent_speaker_impersonation`),
  };
}

function decodeRoom(raw: unknown, path: string): TavernRoom {
  const value = record(raw, path);
  return {
    id: string(field(value, "id", path), `${path}.id`),
    creationKey: optionalStringField(value, "creation_key", path),
    creationInputDigest: optionalStringField(value, "creation_input_digest", path),
    title: string(field(value, "title", path), `${path}.title`),
    sceneProfile: nullableField(value, "scene_profile", path, decodeScene) ?? undefined,
    harnessPolicy: decodePolicy(field(value, "harness_policy", path), `${path}.harness_policy`),
    status: enumeration(field(value, "status", path), ["active", "archived"] as const, `${path}.status`),
    revision: integer(field(value, "revision", path), `${path}.revision`),
    lastSequence: integer(field(value, "last_sequence", path), `${path}.last_sequence`),
    createdAt: string(field(value, "created_at", path), `${path}.created_at`),
    updatedAt: string(field(value, "updated_at", path), `${path}.updated_at`),
  };
}

function decodeRoomState(raw: unknown, path: string): TavernRoomState {
  const value = record(raw, path);
  return {
    id: string(field(value, "id", path), `${path}.id`),
    status: enumeration(field(value, "status", path), ["active", "archived"] as const, `${path}.status`),
    revision: integer(field(value, "revision", path), `${path}.revision`),
    lastSequence: integer(field(value, "last_sequence", path), `${path}.last_sequence`),
    updatedAt: string(field(value, "updated_at", path), `${path}.updated_at`),
  };
}

function decodeParticipant(raw: unknown, path: string): TavernParticipant {
  const value = record(raw, path);
  return {
    roomId: string(field(value, "room_id", path), `${path}.room_id`),
    personaId: string(field(value, "persona_id", path), `${path}.persona_id`),
    displayOrder: integer(field(value, "display_order", path), `${path}.display_order`),
    displayName: string(field(value, "display_name", path), `${path}.display_name`, true),
    personaSnapshot: decodePersona(field(value, "persona_snapshot", path), `${path}.persona_snapshot`),
    promptHash: string(field(value, "prompt_hash", path), `${path}.prompt_hash`),
    joinedAt: string(field(value, "joined_at", path), `${path}.joined_at`),
  };
}

function decodeMessage(raw: unknown, path: string): TavernMessage {
  const value = record(raw, path);
  const trace = nullableField(value, "harness_trace", path, decodeHarnessTrace);
  return {
    id: string(field(value, "id", path), `${path}.id`),
    roomId: string(field(value, "room_id", path), `${path}.room_id`),
    sequence: integer(field(value, "sequence", path), `${path}.sequence`, 1),
    runId: optionalStringField(value, "run_id", path),
    authorKind: enumeration(field(value, "author_kind", path), ["user", "persona", "director", "system"] as const, `${path}.author_kind`),
    personaId: optionalStringField(value, "persona_id", path),
    personaName: optionalStringField(value, "persona_name", path),
    content: string(field(value, "content", path), `${path}.content`, true),
    emotion: string(field(value, "emotion", path), `${path}.emotion`, true),
    action: optionalStringField(value, "action", path),
    speechStyle: optionalStringField(value, "speech_style", path),
    addressedParticipantIds: stringArray(field(value, "addressed_participant_ids", path), `${path}.addressed_participant_ids`),
    replyToMessageId: optionalStringField(value, "reply_to_message_id", path),
    clientRequestId: optionalStringField(value, "client_request_id", path),
    createdAt: string(field(value, "created_at", path), `${path}.created_at`),
    harnessTrace: trace ?? undefined,
  };
}

function decodeStep(raw: unknown, path: string): TavernSpeakerStep {
  const value = record(raw, path);
  const trace = nullableField(value, "harness_trace", path, decodeHarnessTrace);
  return {
    runId: string(field(value, "run_id", path), `${path}.run_id`),
    stepIndex: integer(field(value, "step_index", path), `${path}.step_index`, 0, 3),
    personaId: string(field(value, "persona_id", path), `${path}.persona_id`),
    participantPromptHash: string(field(value, "participant_prompt_hash", path), `${path}.participant_prompt_hash`, true),
    status: enumeration(field(value, "status", path), ["pending", "generating", "completed", "failed", "blocked", "canceled"] as const, `${path}.status`),
    messageId: optionalStringField(value, "message_id", path),
    replyToMessageId: optionalStringField(value, "reply_to_message_id", path),
    errorCode: optionalStringField(value, "error_code", path),
    harnessTrace: trace ?? undefined,
    claimCount: integer(field(value, "claim_count", path), `${path}.claim_count`, 0, 5),
    startedAt: optionalStringField(value, "started_at", path),
    completedAt: optionalStringField(value, "completed_at", path),
  };
}

function decodeRun(raw: unknown, path: string): TavernRun {
  const value = record(raw, path);
  const inputMessageId = nullableField(
    value,
    "input_message_id",
    path,
    (item, itemPath) => string(item, itemPath)
  );
  const run: TavernRun = {
    id: string(field(value, "id", path), `${path}.id`),
    roomId: string(field(value, "room_id", path), `${path}.room_id`),
    idempotencyKey: string(field(value, "idempotency_key", path), `${path}.idempotency_key`),
    requestDigest: optionalStringField(value, "request_digest", path),
    contextDigest: optionalStringField(value, "context_digest", path),
    mode: enumeration(field(value, "mode", path), ["direct", "facilitated"] as const, `${path}.mode`),
    triggerKind: enumeration(field(value, "trigger_kind", path), ["user_message", "continue", "retry"] as const, `${path}.trigger_kind`),
    parentRunId: optionalStringField(value, "parent_run_id", path),
    rootRunId: optionalStringField(value, "root_run_id", path),
    inputMessageId,
    anchorMessageId: optionalStringField(value, "anchor_message_id", path),
    scheduledParticipantIds: stringArray(field(value, "scheduled_participant_ids", path), `${path}.scheduled_participant_ids`),
    speakerSteps: array(field(value, "speaker_steps", path), `${path}.speaker_steps`, decodeStep),
    guidance: string(field(value, "guidance", path), `${path}.guidance`, true),
    status: enumeration(field(value, "status", path), ["pending", "completed", "partial", "failed", "canceled"] as const, `${path}.status`),
    expectedRoomRevision: integer(field(value, "expected_room_revision", path), `${path}.expected_room_revision`),
    generatedMessageIds: stringArray(field(value, "generated_message_ids", path), `${path}.generated_message_ids`),
    harnessTrace: array(field(value, "harness_trace", path), `${path}.harness_trace`, decodeHarnessTrace),
    errorCode: optionalStringField(value, "error_code", path),
    terminalSequence: integer(field(value, "terminal_sequence", path), `${path}.terminal_sequence`),
    createdAt: string(field(value, "created_at", path), `${path}.created_at`),
    completedAt: optionalStringField(value, "completed_at", path),
  };
  for (const [index, step] of run.speakerSteps.entries()) {
    assertEqual(step.runId, run.id, `${path}.speaker_steps[${index}].run_id`);
    if (step.stepIndex !== index) {
      throw new TavernDecodeError(
        `${path}.speaker_steps[${index}].step_index`,
        `schedule_index_mismatch_expected_${index}`
      );
    }
    assertEqual(
      step.personaId,
      run.scheduledParticipantIds[index] ?? "",
      `${path}.speaker_steps[${index}].persona_id`
    );
    if (step.status === "completed" && !step.messageId) {
      throw new TavernDecodeError(
        `${path}.speaker_steps[${index}].message_id`,
        "completed_step_message_required"
      );
    }
    if (step.status !== "completed" && step.messageId) {
      throw new TavernDecodeError(
        `${path}.speaker_steps[${index}].message_id`,
        "non_completed_step_message_forbidden"
      );
    }
  }
  if (
    run.scheduledParticipantIds.length < 1 ||
    run.scheduledParticipantIds.length !== run.speakerSteps.length
  ) {
    throw new TavernDecodeError(
      `${path}.speaker_steps`,
      "schedule_step_count_mismatch"
    );
  }
  assertUnique(run.scheduledParticipantIds, `${path}.scheduled_participant_ids`);
  assertUnique(run.speakerSteps.map((step) => step.stepIndex), `${path}.speaker_steps.step_index`);
  assertUnique(run.speakerSteps.map((step) => step.personaId), `${path}.speaker_steps.persona_id`);
  assertUnique(run.generatedMessageIds, `${path}.generated_message_ids`);
  return run;
}

export function normalizeTavernRoomDetail(
  raw: unknown,
  expectedRoomId?: string
): TavernRoomDetail {
  const path = "tavern.room_detail";
  const value = record(raw, path);
  const room = decodeRoom(field(value, "room", path), `${path}.room`);
  if (expectedRoomId !== undefined) {
    assertEqual(room.id, expectedRoomId, `${path}.room.id`);
  }
  const participants = array(field(value, "participants", path), `${path}.participants`, decodeParticipant);
  const messages = array(field(value, "messages", path), `${path}.messages`, decodeMessage);
  for (const [index, participant] of participants.entries()) {
    assertEqual(participant.roomId, room.id, `${path}.participants[${index}].room_id`);
    assertEqual(participant.personaSnapshot.id, participant.personaId, `${path}.participants[${index}].persona_snapshot.id`);
  }
  for (const [index, message] of messages.entries()) {
    assertEqual(message.roomId, room.id, `${path}.messages[${index}].room_id`);
  }
  assertUnique(participants.map((item) => item.personaId), `${path}.participants.persona_id`);
  assertUnique(participants.map((item) => item.displayOrder), `${path}.participants.display_order`);
  assertUnique(messages.map((item) => item.id), `${path}.messages.id`);
  assertUnique(messages.map((item) => item.sequence), `${path}.messages.sequence`);
  return {
    room,
    participants,
    messages,
    messageCount: integer(field(value, "message_count", path), `${path}.message_count`),
    nextAfterSequence: nullableField(value, "next_after_sequence", path, (item, itemPath) => integer(item, itemPath, 1)),
    nextBeforeSequence: nullableField(value, "next_before_sequence", path, (item, itemPath) => integer(item, itemPath, 1)),
  };
}

export function normalizeTavernTurnResult(
  raw: unknown,
  expectedRoomId?: string
): TavernTurnResult {
  const path = "tavern.turn_result";
  const value = record(raw, path);
  const run = decodeRun(field(value, "run", path), `${path}.run`);
  const inputMessage = nullableField(value, "input_message", path, decodeMessage);
  const generatedMessages = array(field(value, "generated_messages", path), `${path}.generated_messages`, decodeMessage);
  const roomState = decodeRoomState(field(value, "room_state", path), `${path}.room_state`);
  if (expectedRoomId !== undefined) {
    assertEqual(roomState.id, expectedRoomId, `${path}.room_state.id`);
  }
  assertEqual(run.roomId, roomState.id, `${path}.run.room_id`);
  if (run.triggerKind === "user_message") {
    if (!run.inputMessageId || !inputMessage) {
      throw new TavernDecodeError(
        `${path}.input_message`,
        "user_message_trigger_requires_input_message"
      );
    }
  } else if (inputMessage) {
    throw new TavernDecodeError(
      `${path}.input_message`,
      `${run.triggerKind}_trigger_forbids_input_message`
    );
  }
  if (run.triggerKind === "continue" && run.inputMessageId !== null) {
    throw new TavernDecodeError(
      `${path}.run.input_message_id`,
      "continue_trigger_forbids_input_message_id"
    );
  }
  if (inputMessage) {
    assertEqual(inputMessage.roomId, roomState.id, `${path}.input_message.room_id`);
    assertEqual(inputMessage.id, run.inputMessageId ?? "", `${path}.input_message.id`);
    assertEqual(inputMessage.runId ?? "", run.id, `${path}.input_message.run_id`);
    if (inputMessage.authorKind !== "user") {
      throw new TavernDecodeError(`${path}.input_message.author_kind`, "expected_user");
    }
  }
  const completedSteps = run.speakerSteps.filter((step) => step.status === "completed");
  const completedStepByMessageId = new Map(
    completedSteps.map((step) => [step.messageId as string, step])
  );
  for (const [index, message] of generatedMessages.entries()) {
    assertEqual(message.roomId, roomState.id, `${path}.generated_messages[${index}].room_id`);
    assertEqual(message.runId ?? "", run.id, `${path}.generated_messages[${index}].run_id`);
    if (message.authorKind !== "persona") {
      throw new TavernDecodeError(`${path}.run.speaker_steps[${index}].message_id`, "message_not_in_generated_messages");
    }
    const step = completedStepByMessageId.get(message.id);
    if (!step) {
      throw new TavernDecodeError(
        `${path}.generated_messages[${index}].id`,
        "message_not_owned_by_completed_step"
      );
    }
    assertEqual(
      message.personaId ?? "",
      step.personaId,
      `${path}.generated_messages[${index}].persona_id`
    );
  }
  assertUnique(generatedMessages.map((message) => message.id), `${path}.generated_messages.id`);
  assertUnique(generatedMessages.map((message) => message.sequence), `${path}.generated_messages.sequence`);
  const returnedMessageIds = generatedMessages.map((message) => message.id);
  const completedMessageIds = completedSteps.map((step) => step.messageId as string);
  if (
    JSON.stringify(run.generatedMessageIds) !== JSON.stringify(completedMessageIds) ||
    JSON.stringify(returnedMessageIds) !== JSON.stringify(completedMessageIds)
  ) {
    throw new TavernDecodeError(
      `${path}.generated_messages`,
      "generated_messages_do_not_match_completed_steps"
    );
  }
  if (roomState.lastSequence < run.terminalSequence) {
    throw new TavernDecodeError(`${path}.room_state.last_sequence`, "before_run_terminal_sequence");
  }
  return { run, inputMessage, generatedMessages, roomState };
}

export function normalizeTavernRoomList(raw: unknown): TavernRoomPage {
  const path = "tavern.room_list";
  const value = record(raw, path);
  const contractVersion = enumeration(
    field(value, "contract_version", path),
    ["tavern-room-list-v1"] as const,
    `${path}.contract_version`
  );
  const rooms = array(field(value, "items", path), `${path}.items`, (rawItem, itemPath) => {
    const item = record(rawItem, itemPath);
    return {
      id: string(field(item, "id", itemPath), `${itemPath}.id`),
      title: string(field(item, "title", itemPath), `${itemPath}.title`),
      participantPersonaIds: stringArray(field(item, "participant_persona_ids", itemPath), `${itemPath}.participant_persona_ids`),
      participantNames: stringArray(field(item, "participant_names", itemPath), `${itemPath}.participant_names`),
      messageCount: integer(field(item, "message_count", itemPath), `${itemPath}.message_count`),
      revision: integer(field(item, "revision", itemPath), `${itemPath}.revision`),
      status: enumeration(field(item, "status", itemPath), ["active", "archived"] as const, `${itemPath}.status`),
      createdAt: string(field(item, "created_at", itemPath), `${itemPath}.created_at`),
      updatedAt: string(field(item, "updated_at", itemPath), `${itemPath}.updated_at`),
    };
  });
  if (rooms.length > 50) {
    throw new TavernDecodeError(`${path}.items`, "room_page_exceeds_maximum");
  }
  assertUnique(rooms.map((room) => room.id), `${path}.items.id`);
  for (let index = 1; index < rooms.length; index += 1) {
    const previous = rooms[index - 1]!;
    const current = rooms[index]!;
    if (
      previous.updatedAt < current.updatedAt ||
      (previous.updatedAt === current.updatedAt && previous.id <= current.id)
    ) {
      throw new TavernDecodeError(
        `${path}.items[${index}]`,
        "room_page_not_monotonic_updated_at_id_desc"
      );
    }
  }
  const nextCursor = nullableField(
    value,
    "next_cursor",
    path,
    (cursor, cursorPath) => {
      const decoded = string(cursor, cursorPath);
      if (decoded.length > 512) {
        throw new TavernDecodeError(cursorPath, "cursor_exceeds_maximum_length");
      }
      return decoded;
    }
  );
  if (!rooms.length && nextCursor !== null) {
    throw new TavernDecodeError(`${path}.next_cursor`, "empty_page_has_next_cursor");
  }
  return { contractVersion, items: rooms, nextCursor };
}

export function normalizeTavernRunList(
  raw: unknown,
  expectedRoomId?: string
): TavernRun[] {
  const path = "tavern.run_list";
  const value = record(raw, path);
  const runs = array(field(value, "items", path), `${path}.items`, decodeRun);
  if (expectedRoomId !== undefined) {
    for (const [index, run] of runs.entries()) {
      assertEqual(run.roomId, expectedRoomId, `${path}.items[${index}].room_id`);
    }
  }
  assertUnique(runs.map((run) => run.id), `${path}.items.id`);
  return runs;
}

export function normalizeTavernRunRecovery(
  raw: unknown,
  expectedRoomId?: string
): TavernRunRecoveryChain[] {
  const path = "tavern.run_recovery";
  const value = record(raw, path);
  const chains = array(
    field(value, "items", path),
    `${path}.items`,
    (rawItem, itemPath) => {
      const item = record(rawItem, itemPath);
      const rootRunId = string(field(item, "root_run_id", itemPath), `${itemPath}.root_run_id`);
      const runIds = stringArray(field(item, "run_ids", itemPath), `${itemPath}.run_ids`);
      const leafRun = decodeRun(field(item, "leaf_run", itemPath), `${itemPath}.leaf_run`);
      if (!runIds.length || runIds[0] !== rootRunId || runIds[runIds.length - 1] !== leafRun.id) {
        throw new TavernDecodeError(`${itemPath}.run_ids`, "retry_chain_identity_mismatch");
      }
      assertUnique(runIds, `${itemPath}.run_ids`);
      if (expectedRoomId !== undefined) {
        assertEqual(leafRun.roomId, expectedRoomId, `${itemPath}.leaf_run.room_id`);
      }
      const chainStatus = enumeration(
        field(item, "chain_status", itemPath),
        ["active", "recoverable", "recovered", "completed", "canceled"] as const,
        `${itemPath}.chain_status`
      );
      const recoveryAction = enumeration(
        field(item, "recovery_action", itemPath),
        ["none", "replay_same_request", "reload_room", "wait_and_resume", "retry_leaf"] as const,
        `${itemPath}.recovery_action`
      );
      if ((chainStatus === "recoverable") !== (recoveryAction === "retry_leaf")) {
        throw new TavernDecodeError(`${itemPath}.recovery_action`, "chain_action_mismatch");
      }
      return {
        rootRunId,
        runIds,
        rootStatus: enumeration(
          field(item, "root_status", itemPath),
          ["pending", "completed", "partial", "failed", "canceled"] as const,
          `${itemPath}.root_status`
        ),
        leafRun,
        chainStatus,
        recoveryAction,
        completedParticipantIds: stringArray(
          field(item, "completed_participant_ids", itemPath),
          `${itemPath}.completed_participant_ids`
        ),
        unfinishedParticipantIds: stringArray(
          field(item, "unfinished_participant_ids", itemPath),
          `${itemPath}.unfinished_participant_ids`
        ),
      };
    }
  );
  assertUnique(chains.map((chain) => chain.rootRunId), `${path}.items.root_run_id`);
  return chains;
}

export function normalizeTavernErrorDetail(raw: unknown): TavernErrorDetail {
  const path = "tavern.error";
  const envelope = record(raw, path);
  const detailPath = `${path}.detail`;
  const value = record(field(envelope, "detail", path), detailPath);
  return {
    code: string(field(value, "code", detailPath), `${detailPath}.code`),
    runId: optionalStringField(value, "run_id", detailPath),
    childRunId: optionalStringField(value, "child_run_id", detailPath),
    currentRevision: nullableField(
      value,
      "current_revision",
      detailPath,
      (item, itemPath) => integer(item, itemPath, 0)
    ),
    recoveryAction: enumeration(
      field(value, "recovery_action", detailPath),
      ["none", "replay_same_request", "reload_room", "wait_and_resume", "retry_leaf"] as const,
      `${detailPath}.recovery_action`
    ),
  };
}

export function isTavernTerminalReplayDirective(
  status: number,
  detail: TavernErrorDetail | null
): boolean {
  return status === 502 &&
    detail?.recoveryAction === "replay_same_request" &&
    Boolean(detail.runId);
}
