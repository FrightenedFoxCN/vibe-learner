import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import type {
  TavernMessage,
  TavernRoomState,
  TavernRun,
} from "@vibe-learner/shared";

import {
  isTavernRoomStateAtLeast,
  listRetryableRuns,
  mergeTavernMessages,
  reconcileTavernRuns,
  TavernMessageConflictError,
} from "../lib/tavern-workspace-state.ts";
import {
  normalizeTavernRoomDetail,
  normalizeTavernRoomList,
  normalizeTavernRunList,
  normalizeTavernTurnResult,
  TavernDecodeError,
} from "../lib/tavern-decode.ts";

function message(id: string, sequence: number): TavernMessage {
  return {
    id,
    roomId: "room-1",
    sequence,
    authorKind: "user",
    content: id,
    emotion: "calm",
    addressedParticipantIds: [],
    createdAt: "2026-08-12T00:00:00Z",
  };
}

function run(id: string, status: TavernRun["status"], parentRunId?: string): TavernRun {
  return {
    id,
    roomId: "room-1",
    idempotencyKey: `key-${id}`,
    mode: "direct",
    triggerKind: parentRunId ? "retry" : "user_message",
    parentRunId,
    inputMessageId: null,
    scheduledParticipantIds: [],
    speakerSteps: [],
    guidance: "",
    status,
    expectedRoomRevision: 0,
    generatedMessageIds: [],
    harnessTrace: [],
    terminalSequence: 0,
    createdAt: `2026-08-12T00:00:0${id.length}Z`,
  };
}

function roomState(revision: number, lastSequence: number): TavernRoomState {
  return {
    id: "room-1",
    status: "active",
    revision,
    lastSequence,
    updatedAt: "2026-08-12T00:00:00Z",
  };
}

test("mergeTavernMessages orders and deduplicates tail/prepend pages", () => {
  assert.deepEqual(
    mergeTavernMessages(
      [message("m3", 3), message("m4", 4)],
      [message("m1", 1), message("m2", 2), message("m3", 3)]
    ).map((item) => item.id),
    ["m1", "m2", "m3", "m4"]
  );
});

test("mergeTavernMessages fails closed on message identity conflicts", () => {
  assert.throws(
    () => mergeTavernMessages([message("m1", 1)], [message("m2", 1)]),
    TavernMessageConflictError
  );
  assert.throws(
    () => mergeTavernMessages([message("m1", 1)], [message("m1", 2)]),
    TavernMessageConflictError
  );
  assert.throws(
    () => mergeTavernMessages(
      [message("m1", 1)],
      [{ ...message("m1", 1), content: "changed" }]
    ),
    TavernMessageConflictError
  );
  assert.throws(
    () => mergeTavernMessages(
      [message("m1", 1)],
      [{ ...message("m2", 2), roomId: "room-2" }]
    ),
    TavernMessageConflictError
  );
});

test("a child retry suppresses retry on its parent", () => {
  assert.deepEqual(
    listRetryableRuns([
      run("parent", "partial"),
      run("child", "failed", "parent"),
    ]).map((item) => item.id),
    ["child"]
  );
});

test("stale room results cannot move revision or sequence backwards", () => {
  const current = roomState(4, 12);
  assert.equal(isTavernRoomStateAtLeast(roomState(4, 12), current), true);
  assert.equal(isTavernRoomStateAtLeast(roomState(3, 12), current), false);
  assert.equal(isTavernRoomStateAtLeast(roomState(5, 11), current), false);
  assert.equal(
    isTavernRoomStateAtLeast({ ...roomState(5, 13), id: "room-2" }, current),
    false
  );
});

test("late run polling cannot resurrect a terminal run", () => {
  const completed = run("foreground", "completed");
  const reconciled = reconcileTavernRuns(
    [completed, run("older", "failed")],
    [run("foreground", "pending")]
  );
  assert.equal(reconciled.find((item) => item.id === "foreground")?.status, "completed");
  assert.equal(reconciled.find((item) => item.id === "older")?.status, "failed");

  const advanced = reconcileTavernRuns(
    [run("foreground", "pending")],
    [completed]
  );
  assert.equal(advanced[0]?.status, "completed");
});

test("mobile Tavern DOM order matches its primary visual flow", () => {
  const componentSource = readFileSync(
    new URL("../components/tavern-workspace.tsx", import.meta.url),
    "utf8"
  );
  const gridStart = componentSource.indexOf('<div className="tavern-workspace-grid">');
  const conversation = componentSource.indexOf("<TavernConversationPanel", gridStart);
  const rightRail = componentSource.indexOf('className="tavern-right-rail"', gridStart);
  const leftRail = componentSource.indexOf('className="tavern-left-rail"', gridStart);
  assert.ok(gridStart >= 0);
  assert.ok(conversation > gridStart && rightRail > conversation && leftRail > rightRail);
});

function rawPersona() {
  return {
    id: "persona-1",
    name: "Aurora",
    source: "user",
    summary: "A reliable persona",
    relationship: "teacher",
    learner_address: "learner",
    system_prompt: "Be helpful",
    reference_hints: [],
    slots: [],
    available_emotions: ["calm"],
    available_actions: ["nod"],
    default_speech_style: "warm",
  };
}

function rawTrace() {
  return {
    version: "tavern-harness-v1",
    workflow: "tavern",
    stage: "actor_reply",
    status: "passed",
    schema_name: "TavernActorReply",
    input_digest: "",
    context_digest: "",
    checks: [],
    attempts: 1,
    recovery_strategy: "none",
    duration_ms: 3,
  };
}

function rawRoomDetail() {
  return {
    room: {
      id: "room-1",
      creation_key: "",
      creation_input_digest: "",
      title: "Tavern",
      scene_profile: null,
      harness_policy: {
        version: "tavern-harness-v1",
        max_character_messages: 4,
        max_reply_characters: 1200,
        context_message_limit: 18,
        prevent_speaker_impersonation: true,
      },
      status: "active",
      revision: 0,
      last_sequence: 0,
      created_at: "2026-08-12T00:00:00Z",
      updated_at: "2026-08-12T00:00:00Z",
    },
    participants: [{
      room_id: "room-1",
      persona_id: "persona-1",
      display_order: 0,
      display_name: "Aurora",
      persona_snapshot: rawPersona(),
      prompt_hash: "digest",
      joined_at: "2026-08-12T00:00:00Z",
    }],
    messages: [],
    message_count: 0,
    next_after_sequence: null,
    next_before_sequence: null,
  };
}

function rawTurnResult() {
  return {
    run: {
      id: "run-1",
      room_id: "room-1",
      idempotency_key: "turn-key-1",
      request_digest: "request-digest",
      context_digest: "context-digest",
      mode: "direct",
      trigger_kind: "user_message",
      parent_run_id: "",
      root_run_id: "run-1",
      input_message_id: "message-1",
      anchor_message_id: "",
      scheduled_participant_ids: ["persona-1"],
      speaker_steps: [{
        run_id: "run-1",
        step_index: 0,
        persona_id: "persona-1",
        participant_prompt_hash: "digest",
        status: "completed",
        message_id: "message-2",
        reply_to_message_id: "message-1",
        error_code: "",
        harness_trace: rawTrace(),
        claim_count: 1,
        started_at: "2026-08-12T00:00:00Z",
        completed_at: "2026-08-12T00:00:01Z",
      }],
      guidance: "",
      status: "completed",
      expected_room_revision: 0,
      generated_message_ids: ["message-2"],
      harness_trace: [rawTrace()],
      error_code: "",
      terminal_sequence: 2,
      created_at: "2026-08-12T00:00:00Z",
      completed_at: "2026-08-12T00:00:01Z",
    },
    input_message: {
      id: "message-1",
      room_id: "room-1",
      sequence: 1,
      run_id: "run-1",
      author_kind: "user",
      persona_id: "",
      persona_name: "",
      content: "Hi",
      emotion: "calm",
      action: "",
      speech_style: "",
      addressed_participant_ids: ["persona-1"],
      reply_to_message_id: "",
      client_request_id: "turn-key-1",
      created_at: "2026-08-12T00:00:00Z",
      harness_trace: null,
    },
    generated_messages: [{
      id: "message-2",
      room_id: "room-1",
      sequence: 2,
      run_id: "run-1",
      author_kind: "persona",
      persona_id: "persona-1",
      persona_name: "Aurora",
      content: "Hello",
      emotion: "calm",
      action: "nod",
      speech_style: "warm",
      addressed_participant_ids: [],
      reply_to_message_id: "message-1",
      client_request_id: "",
      created_at: "2026-08-12T00:00:01Z",
      harness_trace: rawTrace(),
    }],
    room_state: {
      id: "room-1",
      status: "active",
      revision: 1,
      last_sequence: 2,
      updated_at: "2026-08-12T00:00:01Z",
    },
  };
}

test("strict Tavern decoders accept the current backend wire format", () => {
  const detail = normalizeTavernRoomDetail(rawRoomDetail());
  const result = normalizeTavernTurnResult(rawTurnResult());
  assert.equal(detail.room.id, "room-1");
  assert.equal(detail.room.creationKey, undefined);
  assert.equal(result.generatedMessages[0]?.sequence, 2);
  assert.equal(result.run.speakerSteps[0]?.harnessTrace?.status, "passed");
});

test("strict Tavern decoder accepts retry responses without replaying the user message", () => {
  const retry = rawTurnResult() as Record<string, any>;
  retry.run.trigger_kind = "retry";
  retry.run.parent_run_id = "run-parent";
  retry.input_message = null;
  assert.equal(normalizeTavernTurnResult(retry).run.triggerKind, "retry");
});

test("strict Tavern decoder enforces trigger and input-message semantics", () => {
  const missingUserInput = rawTurnResult() as Record<string, any>;
  missingUserInput.run.input_message_id = null;
  missingUserInput.input_message = null;
  assert.throws(() => normalizeTavernTurnResult(missingUserInput), TavernDecodeError);

  const continueWithInput = rawTurnResult() as Record<string, any>;
  continueWithInput.run.trigger_kind = "continue";
  continueWithInput.run.input_message_id = null;
  assert.throws(() => normalizeTavernTurnResult(continueWithInput), TavernDecodeError);

  const retryWithInput = rawTurnResult() as Record<string, any>;
  retryWithInput.run.trigger_kind = "retry";
  assert.throws(() => normalizeTavernTurnResult(retryWithInput), TavernDecodeError);
});

test("strict Tavern decoder accepts a legacy persona with an empty system prompt", () => {
  const detail = rawRoomDetail() as Record<string, any>;
  detail.participants[0].persona_snapshot.system_prompt = "";
  assert.equal(
    normalizeTavernRoomDetail(detail).participants[0]?.personaSnapshot.systemPrompt,
    ""
  );
});

test("strict Tavern decoder mirrors backend-compatible empty persona and scene strings", () => {
  const detail = rawRoomDetail() as Record<string, any>;
  detail.participants[0].display_name = "";
  detail.participants[0].persona_snapshot.name = "";
  detail.participants[0].persona_snapshot.default_speech_style = "";
  detail.room.scene_profile = {
    scene_name: "",
    scene_id: "",
    title: "",
    summary: "",
    tags: [],
    selected_path: [],
    focus_object_names: [],
    scene_tree: [{
      id: "",
      title: "",
      scope_label: "",
      summary: "",
      atmosphere: "",
      rules: "",
      entrance: "",
      tags: "",
      reuse_id: "",
      reuse_hint: "",
      objects: [{
        id: "",
        name: "",
        description: "",
        interaction: "",
        tags: "",
        reuse_id: "",
        reuse_hint: "",
      }],
      children: [],
    }],
  };
  const decoded = normalizeTavernRoomDetail(detail);
  assert.equal(decoded.participants[0]?.displayName, "");
  assert.equal(decoded.room.sceneProfile?.sceneTree[0]?.id, "");
});

test("strict Tavern decoders fail closed on invalid identity, enums, and counters", () => {
  const invalidCases: Array<() => unknown> = [
    () => normalizeTavernRoomDetail({
      ...rawRoomDetail(),
      room: { ...rawRoomDetail().room, id: "" },
    }),
    () => normalizeTavernRoomDetail({
      ...rawRoomDetail(),
      room: { ...rawRoomDetail().room, status: "deleted" },
    }),
    () => normalizeTavernRoomDetail({
      ...rawRoomDetail(),
      room: { ...rawRoomDetail().room, revision: -1 },
    }),
    () => normalizeTavernTurnResult({
      ...rawTurnResult(),
      generated_messages: [{
        ...rawTurnResult().generated_messages[0],
        sequence: 0,
      }],
    }),
  ];
  for (const decode of invalidCases) {
    assert.throws(decode, TavernDecodeError);
  }
});

test("Tavern v1 Harness trace status is not coerced from an unknown enum", () => {
  const payload = rawTurnResult();
  payload.run.harness_trace[0]!.status = "mystery";
  assert.throws(() => normalizeTavernTurnResult(payload));
});

test("strict Tavern decoder distinguishes a missing nullable field from null", () => {
  const missingInputMessage = rawTurnResult() as Record<string, any>;
  delete missingInputMessage.input_message;
  const missingRunInput = rawTurnResult() as Record<string, any>;
  delete missingRunInput.run.input_message_id;
  const missingCursor = rawRoomDetail() as Record<string, any>;
  delete missingCursor.next_before_sequence;
  assert.throws(() => normalizeTavernTurnResult(missingInputMessage), TavernDecodeError);
  assert.throws(() => normalizeTavernTurnResult(missingRunInput), TavernDecodeError);
  assert.throws(() => normalizeTavernRoomDetail(missingCursor), TavernDecodeError);
});

test("strict Tavern decoder rejects malformed nested persona and scene snapshots", () => {
  const missingPersonaId = rawRoomDetail() as Record<string, any>;
  delete missingPersonaId.participants[0].persona_snapshot.id;
  assert.throws(() => normalizeTavernRoomDetail(missingPersonaId), TavernDecodeError);

  const invalidScene = rawRoomDetail() as Record<string, any>;
  invalidScene.room.scene_profile = {
    scene_name: "Scene",
    scene_id: "scene-1",
    title: "Scene",
    summary: "",
    tags: [],
    selected_path: [],
    focus_object_names: [],
    scene_tree: [{ id: "node-1" }],
  };
  assert.throws(() => normalizeTavernRoomDetail(invalidScene), TavernDecodeError);
});

test("strict Tavern list decoders reject a malformed envelope", () => {
  assert.throws(() => normalizeTavernRoomList(null), TavernDecodeError);
  assert.throws(() => normalizeTavernRoomList({}), TavernDecodeError);
  assert.throws(() => normalizeTavernRunList({ items: null }), TavernDecodeError);
});

test("strict Tavern decoders bind responses to the requested room", () => {
  assert.throws(
    () => normalizeTavernRoomDetail(rawRoomDetail(), "room-2"),
    TavernDecodeError
  );
  assert.throws(
    () => normalizeTavernTurnResult(rawTurnResult(), "room-2"),
    TavernDecodeError
  );
  assert.throws(
    () => normalizeTavernRunList({ items: [rawTurnResult().run] }, "room-2"),
    TavernDecodeError
  );
});

test("strict Tavern decoders reject aggregate ownership mismatches", () => {
  const wrongParticipantRoom = rawRoomDetail() as Record<string, any>;
  wrongParticipantRoom.participants[0].room_id = "room-2";
  assert.throws(() => normalizeTavernRoomDetail(wrongParticipantRoom), TavernDecodeError);

  const wrongRunRoom = rawTurnResult() as Record<string, any>;
  wrongRunRoom.run.room_id = "room-2";
  assert.throws(() => normalizeTavernTurnResult(wrongRunRoom), TavernDecodeError);

  const wrongStepRun = rawTurnResult() as Record<string, any>;
  wrongStepRun.run.speaker_steps[0].run_id = "run-2";
  assert.throws(() => normalizeTavernTurnResult(wrongStepRun), TavernDecodeError);

  const duplicateSequence = rawRoomDetail() as Record<string, any>;
  duplicateSequence.messages = [
    { ...rawTurnResult().generated_messages[0], id: "message-2" },
    { ...rawTurnResult().generated_messages[0], id: "message-3" },
  ];
  assert.throws(() => normalizeTavernRoomDetail(duplicateSequence), TavernDecodeError);
});

test("strict Tavern decoder binds the run schedule to ordered speaker steps", () => {
  const missingStep = rawTurnResult() as Record<string, any>;
  missingStep.run.speaker_steps = [];
  assert.throws(() => normalizeTavernTurnResult(missingStep), TavernDecodeError);

  const wrongIndex = rawTurnResult() as Record<string, any>;
  wrongIndex.run.speaker_steps[0].step_index = 1;
  assert.throws(() => normalizeTavernTurnResult(wrongIndex), TavernDecodeError);

  const wrongPersona = rawTurnResult() as Record<string, any>;
  wrongPersona.run.speaker_steps[0].persona_id = "persona-2";
  assert.throws(() => normalizeTavernTurnResult(wrongPersona), TavernDecodeError);
});

test("strict Tavern decoder requires exact completed-step message projections", () => {
  const extraMessage = rawTurnResult() as Record<string, any>;
  extraMessage.generated_messages.push({
    ...extraMessage.generated_messages[0],
    id: "message-extra",
    sequence: 3,
  });
  assert.throws(() => normalizeTavernTurnResult(extraMessage), TavernDecodeError);

  const wrongAuthor = rawTurnResult() as Record<string, any>;
  wrongAuthor.generated_messages[0].author_kind = "director";
  assert.throws(() => normalizeTavernTurnResult(wrongAuthor), TavernDecodeError);

  const wrongPersona = rawTurnResult() as Record<string, any>;
  wrongPersona.generated_messages[0].persona_id = "persona-2";
  assert.throws(() => normalizeTavernTurnResult(wrongPersona), TavernDecodeError);
});

test("strict Tavern decoder rejects non-finite and out-of-range evidence", () => {
  const nonFiniteSlot = rawRoomDetail() as Record<string, any>;
  nonFiniteSlot.participants[0].persona_snapshot.slots = [{
    kind: "custom",
    label: "Custom",
    content: "Content",
    weight: Number.NaN,
    locked: false,
    sort_order: 0,
  }];
  assert.throws(() => normalizeTavernRoomDetail(nonFiniteSlot), TavernDecodeError);

  const excessiveAttempts = rawTurnResult() as Record<string, any>;
  excessiveAttempts.run.harness_trace[0].attempts = 4;
  assert.throws(() => normalizeTavernTurnResult(excessiveAttempts), TavernDecodeError);

  const v3WithoutAdoption = rawTurnResult() as Record<string, any>;
  v3WithoutAdoption.run.harness_trace[0].trace_schema_version = "harness-trace-v3";
  assert.throws(() => normalizeTavernTurnResult(v3WithoutAdoption), TavernDecodeError);

  const disguisedV3 = rawTurnResult() as Record<string, any>;
  disguisedV3.run.harness_trace[0].version = "harness-trace-v3";
  assert.throws(() => normalizeTavernTurnResult(disguisedV3), TavernDecodeError);
});
