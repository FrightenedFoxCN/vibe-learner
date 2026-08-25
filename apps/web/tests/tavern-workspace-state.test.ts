import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import type {
  TavernMessage,
  TavernParticipant,
  TavernRoomState,
  TavernRoomSummary,
  TavernRun,
} from "@vibe-learner/shared";

import {
  isTavernRoomStateAtLeast,
  authoritativeFacilitatedRecovery,
  latestFacilitatedRecovery,
  listRetryableRuns,
  mergeTavernMessages,
  mergeTavernRoomPages,
  projectParticipantStates,
  reconcileTavernCreationDraftPersonas,
  reconcileTavernRuns,
  tavernRoomSummaryButtons,
  TavernMessageConflictError,
  TavernRoomPageConflictError,
} from "../lib/tavern-workspace-state.ts";
import {
  normalizeTavernRoomDetail,
  normalizeTavernErrorDetail,
  normalizeTavernRoomList,
  normalizeTavernRunList,
  normalizeTavernRunRecovery,
  normalizeTavernTurnResult,
  isTavernTerminalReplayDirective,
  TavernDecodeError,
} from "../lib/tavern-decode.ts";

function roomSummary(
  id: string,
  updatedAt: string,
  title = id
): TavernRoomSummary {
  return {
    id,
    title,
    participantPersonaIds: ["persona-1"],
    participantNames: ["Aurora"],
    messageCount: 0,
    revision: 0,
    status: "active",
    createdAt: "2026-08-12T00:00:00Z",
    updatedAt,
  };
}

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

function participant(personaId: string, displayOrder: number): TavernParticipant {
  return {
    roomId: "room-1",
    personaId,
    displayOrder,
    displayName: personaId,
    personaSnapshot: {
      id: personaId,
      name: personaId,
      source: "user",
      summary: "summary",
      relationship: "peer",
      learnerAddress: "learner",
      systemPrompt: "prompt",
      referenceHints: [],
      slots: [],
      availableEmotions: ["calm"],
      availableActions: ["nod"],
      defaultSpeechStyle: "warm",
    },
    promptHash: `hash-${personaId}`,
    joinedAt: "2026-08-12T00:00:00Z",
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

test("Tavern Room pages append monotonically, deduplicate IDs, and retain at most 100 summaries", () => {
  const first = Array.from({ length: 80 }, (_, index) =>
    roomSummary(
      `room-${String(200 - index).padStart(3, "0")}`,
      `2026-08-12T00:${String(59 - Math.floor(index / 60)).padStart(2, "0")}:${String(59 - (index % 60)).padStart(2, "0")}Z`
    )
  );
  const incoming = [
    first[79]!,
    ...Array.from({ length: 30 }, (_, index) =>
      roomSummary(
        `room-${String(120 - index).padStart(3, "0")}`,
        `2026-08-11T23:59:${String(59 - index).padStart(2, "0")}Z`
      )
    ),
  ];
  const merged = mergeTavernRoomPages(first, incoming);
  assert.equal(merged.length, 100);
  assert.equal(new Set(merged.map((room) => room.id)).size, 100);
  assert.equal(merged[80]?.id, "room-120");

  assert.throws(
    () => mergeTavernRoomPages(
      [roomSummary("room-z", "2026-08-12T00:00:00Z")],
      [roomSummary("room-newer", "2026-08-13T00:00:00Z")]
    ),
    TavernRoomPageConflictError
  );
});

test("selected Tavern Room detail remains a visible authoritative button outside loaded summaries", () => {
  const loaded = Array.from({ length: 100 }, (_, index) =>
    roomSummary(
      `room-${String(200 - index).padStart(3, "0")}`,
      `2026-08-${String(24 - Math.floor(index / 10)).padStart(2, "0")}T00:00:${String(59 - (index % 10)).padStart(2, "0")}Z`
    )
  );
  const rawSelected = rawRoomDetail();
  rawSelected.room.id = "selected-outside-page";
  rawSelected.room.title = "权威详情标题";
  rawSelected.room.updated_at = "2026-07-01T00:00:00Z";
  rawSelected.participants[0]!.room_id = rawSelected.room.id;
  const selectedDetail = normalizeTavernRoomDetail(rawSelected);
  const buttons = tavernRoomSummaryButtons(loaded, selectedDetail);
  assert.equal(buttons.length, 100);
  assert.equal(buttons[0]?.id, "selected-outside-page");
  assert.equal(buttons[0]?.title, "权威详情标题");
  assert.equal(new Set(buttons.map((room) => room.id)).size, 100);

  rawSelected.room.id = loaded[5]!.id;
  rawSelected.room.title = "mutation 后的权威标题";
  rawSelected.participants[0]!.room_id = rawSelected.room.id;
  const refreshedButtons = tavernRoomSummaryButtons(
    loaded,
    normalizeTavernRoomDetail(rawSelected)
  );
  assert.equal(refreshedButtons[5]?.id, loaded[5]!.id);
  assert.equal(refreshedButtons[5]?.title, "mutation 后的权威标题");
});

test("Tavern creation drafts drop deleted personas and rotate request identity", () => {
  const draft = {
    key: "old-request-key",
    title: "夜航酒馆",
    personaIds: ["persona-1", "deleted-persona", "persona-1", "persona-2"],
    sceneId: "",
    openingPrompt: "",
  };
  assert.deepEqual(
    reconcileTavernCreationDraftPersonas(
      draft,
      ["persona-1", "persona-2", "persona-3"],
      "new-request-key",
    ),
    {
      ...draft,
      key: "new-request-key",
      personaIds: ["persona-1", "persona-2"],
    },
  );
  assert.equal(
    reconcileTavernCreationDraftPersonas(
      { ...draft, personaIds: ["persona-1", "persona-2"] },
      ["persona-1", "persona-2"],
      "unused-request-key",
    )?.key,
    "old-request-key",
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

test("latest facilitated recovery exposes only unfinished actors", () => {
  const recovery = latestFacilitatedRecovery([
    {
      ...run("facilitated", "partial"),
      mode: "facilitated",
      scheduledParticipantIds: ["persona-1", "persona-2", "persona-3"],
      speakerSteps: [
        speakerStep("facilitated", 0, "persona-1", "completed"),
        speakerStep("facilitated", 1, "persona-2", "failed"),
        speakerStep("facilitated", 2, "persona-3", "blocked"),
      ],
    },
  ]);
  assert.equal(recovery?.run.id, "facilitated");
  assert.equal(recovery?.completedCount, 1);
  assert.equal(recovery?.totalCount, 3);
  assert.deepEqual(recovery?.unfinishedPersonaIds, ["persona-2", "persona-3"]);
});

test("facilitated recovery hides ineligible and already retried runs", () => {
  const parent = {
    ...run("parent", "partial"),
    mode: "facilitated" as const,
    speakerSteps: [speakerStep("parent", 0, "persona-1", "failed")],
  };
  assert.equal(latestFacilitatedRecovery([run("direct", "failed")]), null);
  assert.equal(latestFacilitatedRecovery([{ ...parent, status: "completed" }]), null);
  assert.equal(latestFacilitatedRecovery([{ ...parent, status: "pending" }]), null);
  assert.equal(
    latestFacilitatedRecovery([parent, run("child", "completed", "parent")]),
    null
  );
});

test("authoritative recovery follows the chain leaf instead of a recent run window", () => {
  const parent = {
    ...run("parent", "partial"),
    mode: "facilitated" as const,
    scheduledParticipantIds: ["persona-1", "persona-2"],
    speakerSteps: [
      speakerStep("parent", 0, "persona-1", "completed"),
      speakerStep("parent", 1, "persona-2", "failed"),
    ],
  };
  const child = {
    ...run("child", "completed", "parent"),
    mode: "facilitated" as const,
    scheduledParticipantIds: ["persona-2"],
    speakerSteps: [speakerStep("child", 0, "persona-2", "completed")],
  };
  const recovery = authoritativeFacilitatedRecovery([{
    rootRunId: parent.id,
    runIds: [parent.id, child.id],
    rootStatus: "partial",
    leafRun: child,
    chainStatus: "recovered",
    recoveryAction: "none",
    completedParticipantIds: ["persona-1", "persona-2"],
    unfinishedParticipantIds: [],
  }]);
  assert.equal(recovery?.run.id, child.id);
  assert.equal(recovery?.chainStatus, "recovered");
  assert.equal(recovery?.completedCount, 2);
  assert.deepEqual(recovery?.unfinishedPersonaIds, []);
});

test("Tavern client recovery only accepts an explicit terminal replay directive", () => {
  const detail = normalizeTavernErrorDetail({
    detail: {
      code: "tavern_run_failed",
      run_id: "run-1",
      child_run_id: "",
      current_revision: 1,
      recovery_action: "replay_same_request",
    },
  });
  assert.equal(isTavernTerminalReplayDirective(502, detail), true);
  assert.equal(isTavernTerminalReplayDirective(409, detail), false);
  assert.equal(
    isTavernTerminalReplayDirective(502, { ...detail, runId: undefined }),
    false
  );
  assert.equal(
    isTavernTerminalReplayDirective(502, { ...detail, recoveryAction: "reload_room" }),
    false
  );
});

test("Tavern client strictly decodes the empty room update error envelope", () => {
  assert.deepEqual(
    normalizeTavernErrorDetail({
      detail: {
        code: "tavern_update_payload_empty",
        run_id: "",
        child_run_id: "",
        current_revision: 0,
        recovery_action: "none",
      },
    }),
    {
      code: "tavern_update_payload_empty",
      runId: undefined,
      childRunId: undefined,
      currentRevision: 0,
      recoveryAction: "none",
    }
  );
  assert.throws(
    () => normalizeTavernErrorDetail({ detail: "tavern_update_payload_empty" }),
    TavernDecodeError
  );
});

function speakerStep(
  runId: string,
  stepIndex: number,
  personaId: string,
  status: TavernRun["speakerSteps"][number]["status"]
): TavernRun["speakerSteps"][number] {
  return {
    runId,
    stepIndex,
    personaId,
    participantPromptHash: `hash-${personaId}`,
    status,
    claimCount: status === "blocked" ? 0 : 1,
  };
}

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

test("optimistic roster marks only the first eligible actor as generating", () => {
  const states = projectParticipantStates(
    [participant("persona-2", 1), participant("persona-1", 0), participant("persona-3", 2)],
    [],
    ["persona-2", "persona-1"]
  );
  assert.deepEqual(
    states.map((item) => [item.participant.personaId, item.state]),
    [
      ["persona-1", "generating"],
      ["persona-2", "pending"],
      ["persona-3", "idle"],
    ]
  );
});

test("server speaker steps override optimistic roster state", () => {
  const active = {
    ...run("active", "pending"),
    mode: "facilitated" as const,
    speakerSteps: [
      speakerStep("active", 0, "persona-1", "completed"),
      speakerStep("active", 1, "persona-2", "generating"),
      speakerStep("active", 2, "persona-3", "pending"),
    ],
  };
  const states = projectParticipantStates(
    [participant("persona-1", 0), participant("persona-2", 1), participant("persona-3", 2)],
    [active],
    ["persona-1", "persona-3"]
  );
  assert.deepEqual(
    states.map((item) => item.state),
    ["completed", "generating", "pending"]
  );
});

test("an admitted run without visible steps stays truthful while starting", () => {
  const active = {
    ...run("active-no-steps", "pending"),
    mode: "facilitated" as const,
    scheduledParticipantIds: ["persona-1", "persona-2"],
  };
  const states = projectParticipantStates(
    [participant("persona-1", 0), participant("persona-2", 1)],
    [active]
  );
  assert.deepEqual(states.map((item) => item.state), ["pending", "pending"]);
});

test("terminal roster states are explicitly scoped to the previous round", () => {
  const terminal = {
    ...run("terminal", "partial"),
    mode: "facilitated" as const,
    speakerSteps: [
      speakerStep("terminal", 0, "persona-1", "completed"),
      speakerStep("terminal", 1, "persona-2", "failed"),
      speakerStep("terminal", 2, "persona-3", "blocked"),
    ],
  };
  const states = projectParticipantStates(
    [participant("persona-1", 0), participant("persona-2", 1), participant("persona-3", 2)],
    [terminal]
  );
  assert.deepEqual(
    states.map((item) => item.state),
    ["previous_completed", "previous_failed", "previous_blocked"]
  );
});

test("mobile Tavern DOM order matches its primary visual flow", () => {
  const componentSource = readFileSync(
    new URL("../components/tavern-workspace.tsx", import.meta.url),
    "utf8"
  );
  const gridStart = componentSource.indexOf('<div className={`tavern-workspace-grid');
  const leftRail = componentSource.indexOf('className="tavern-left-rail"', gridStart);
  const rightRail = componentSource.indexOf('className="tavern-right-rail"', gridStart);
  const conversation = componentSource.indexOf("<TavernConversationPanel", gridStart);
  assert.ok(gridStart >= 0);
  assert.ok(leftRail > gridStart && rightRail > leftRail && conversation > rightRail);
  assert.ok(componentSource.includes('activeRoom ? "has-room" : "empty-room"'));
  assert.ok(componentSource.includes("先创建或打开一个酒馆，然后开始对话。"));
  assert.ok(!componentSource.includes("从左侧创建或打开一个酒馆。"));
});

test("Tavern Session pagination exposes pending, error, and duplicate-cursor fences", () => {
  const componentSource = readFileSync(
    new URL("../components/tavern-workspace.tsx", import.meta.url),
    "utf8"
  );
  assert.ok(componentSource.includes("loadingRoomCursorRef.current === cursor"));
  assert.ok(componentSource.includes('disabled={busy || loadingMore}'));
  assert.ok(componentSource.includes('{pageError ? <p role="alert">{pageError}</p> : null}'));
  assert.ok(componentSource.includes("已显示最近 100 个房间"));
});

test("mobile Tavern buttons keep a 44px minimum touch target", () => {
  const cssSource = readFileSync(
    new URL("../app/globals.css", import.meta.url),
    "utf8"
  );
  const mobileStart = cssSource.indexOf("@media (max-width: 480px)");
  const mobileCss = cssSource.slice(mobileStart);

  assert.ok(mobileStart >= 0);
  assert.match(mobileCss, /\.tavern-button\s*\{\s*min-height:\s*44px;/);
});

test("Interaction Composer restores focus only after a confirmed user turn settles", () => {
  const componentSource = readFileSync(
    new URL("../components/tavern-workspace.tsx", import.meta.url),
    "utf8"
  );
  const composerStart = componentSource.indexOf("function InteractionComposer");
  const composerEnd = componentSource.indexOf("function ReliabilityDetails", composerStart);
  const composer = componentSource.slice(composerStart, composerEnd);
  const turnStart = componentSource.indexOf("const handleTurn = useCallback");
  const turnEnd = componentSource.indexOf("const handleCancelRun", turnStart);
  const handleTurn = componentSource.slice(turnStart, turnEnd);
  const sendStart = composer.indexOf("const sendMessage = async () =>");
  const continueStart = composer.indexOf("const continueConversation = async () =>");
  const sendMessage = composer.slice(sendStart, continueStart);

  assert.ok(composerStart >= 0 && composerEnd > composerStart);
  assert.ok(turnStart >= 0 && turnEnd > turnStart);
  assert.ok(sendStart >= 0 && continueStart > sendStart);
  assert.ok(handleTurn.includes("return Boolean(recoveredRun);"));
  assert.match(
    sendMessage,
    /if \(completed\) \{\s*setMessage\(""\);\s*setGuidance\(""\);\s*setFocusRequestVersion/
  );
  assert.equal((composer.match(/setFocusRequestVersion/g) ?? []).length, 2);
  assert.ok(composer.includes("if (busy) return;"));
  assert.ok(composer.includes("if (!roomActive || message || guidance)"));
  assert.ok(composer.includes("mountedRoomIdRef.current !== expectedRoomId"));
  assert.ok(composer.includes("!input.isConnected || input.disabled"));
  assert.ok(composer.includes("window.requestAnimationFrame"));
  assert.ok(composer.includes("window.cancelAnimationFrame(frame)"));
  assert.ok(composer.includes("ref={messageInputRef}"));
});

test("Interaction Composer retains Enter, Shift+Enter, and IME composition fencing", () => {
  const componentSource = readFileSync(
    new URL("../components/tavern-workspace.tsx", import.meta.url),
    "utf8"
  );
  const composer = componentSource.slice(
    componentSource.indexOf("function InteractionComposer"),
    componentSource.indexOf("function ReliabilityDetails")
  );

  assert.ok(composer.includes('event.key !== "Enter" || event.shiftKey'));
  assert.ok(composer.includes("composingRef.current"));
  assert.ok(composer.includes("event.nativeEvent.isComposing"));
  assert.ok(composer.includes("event.nativeEvent.keyCode === 229"));
  assert.ok(composer.includes("suppressCompositionEnterRef.current"));
  assert.ok(composer.includes("event.preventDefault()"));
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
  assert.throws(() => normalizeTavernRoomList([]), TavernDecodeError);
  const rawSummary = {
    id: "room-a",
    title: "Room A",
    participant_persona_ids: ["persona-1"],
    participant_names: ["Aurora"],
    message_count: 1,
    revision: 0,
    status: "active",
    created_at: "2026-08-12T00:00:00Z",
    updated_at: "2026-08-12T00:00:00Z",
  };
  const validPage = {
    contract_version: "tavern-room-list-v1",
    items: [rawSummary],
    next_cursor: "opaque.cursor",
  };
  assert.equal(normalizeTavernRoomList(validPage).items[0]?.id, "room-a");
  assert.throws(
    () => normalizeTavernRoomList({ ...validPage, contract_version: "tavern-room-list-v2" }),
    TavernDecodeError
  );
  assert.throws(
    () => normalizeTavernRoomList({ ...validPage, next_cursor: 7 }),
    TavernDecodeError
  );
  assert.throws(
    () => normalizeTavernRoomList({
      ...validPage,
      items: [
        { ...rawSummary, id: "room-a" },
        { ...rawSummary, id: "room-b", updated_at: "2026-08-13T00:00:00Z" },
      ],
      next_cursor: null,
    }),
    TavernDecodeError
  );
  assert.throws(
    () => normalizeTavernRoomList({
      contract_version: "tavern-room-list-v1",
      items: [],
      next_cursor: "unexpected",
    }),
    TavernDecodeError
  );
  assert.throws(() => normalizeTavernRunList({ items: null }), TavernDecodeError);
  assert.throws(() => normalizeTavernRunRecovery({ items: null }), TavernDecodeError);
});

test("strict Tavern recovery and error decoders enforce identity and action", () => {
  const rawRun = rawTurnResult().run;
  const validChain = {
    root_run_id: rawRun.id,
    run_ids: [rawRun.id],
    root_status: rawRun.status,
    leaf_run: rawRun,
    chain_status: "completed",
    recovery_action: "none",
    completed_participant_ids: rawRun.scheduled_participant_ids,
    unfinished_participant_ids: [],
  };
  const decoded = normalizeTavernRunRecovery({ items: [validChain] }, "room-1");
  assert.equal(decoded[0]?.leafRun.id, rawRun.id);
  assert.deepEqual(
    normalizeTavernErrorDetail({
      detail: {
        code: "tavern_run_failed",
        run_id: rawRun.id,
        child_run_id: "",
        current_revision: 2,
        recovery_action: "replay_same_request",
      },
    }),
    {
      code: "tavern_run_failed",
      runId: rawRun.id,
      childRunId: undefined,
      currentRevision: 2,
      recoveryAction: "replay_same_request",
    }
  );
  assert.throws(
    () => normalizeTavernRunRecovery({
      items: [{ ...validChain, run_ids: ["wrong-root", rawRun.id] }],
    }),
    TavernDecodeError
  );
  assert.throws(
    () => normalizeTavernRunRecovery({
      items: [{ ...validChain, chain_status: "recoverable", recovery_action: "none" }],
    }),
    TavernDecodeError
  );
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
