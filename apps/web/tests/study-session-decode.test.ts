import assert from "node:assert/strict";
import test from "node:test";

import type { DialogueTurnRecord, LearningPlan } from "@vibe-learner/shared";

import {
  decodeStudyChatExchange,
  decodeStudyPlanConfirmationDecisionResponse,
  decodeStudySceneProfile,
  decodeStudySession,
  decodeStudySessionCommittedIdentity,
  decodeStudySessionList,
  isStudySessionDecodeError,
  orderStudySessionTurns,
  resolveStudyChatFailurePresentation,
  resolveStudySessionErrorNotice,
  StudySessionDecodeError,
} from "../lib/study-session-decode.ts";

const createdAt = "2026-08-24T10:00:00+08:00";
const committedAt = "2026-08-24T10:00:01+08:00";

function fullWireTurn(): Record<string, any> {
  return {
    id: "turn-1",
    sequence: 1,
    learner_message: "Explain the chapter",
    learner_message_kind: "learner",
    learner_attachments: [],
    assistant_reply: "Start with the invariant.",
    citations: [{
      section_id: "unit-1",
      title: "Unit 1",
      page_start: 1,
      page_end: 2,
      source_kind: "document",
      source_id: "",
    }],
    character_events: [{
      emotion: "calm",
      action: "points to the diagram",
      speech_style: "steady",
      scene_hint: "Unit 1, pages 1-2",
      line_segment_id: "session-1:chat:0",
      timing_hint: "instant",
      tool_name: "",
      tool_summary: "",
      delivery_cue: "slowly",
      commentary: "",
    }],
    rich_blocks: [],
    interactive_question: null,
    persona_slot_trace: [],
    memory_trace: [],
    tool_calls: [],
    scene_profile: null,
    model_recoveries: [],
    created_at: committedAt,
  };
}

function fullWireSession(): Record<string, any> {
  return {
    id: "session-1",
    document_id: "document-1",
    persona_id: "persona-1",
    plan_id: null,
    scene_instance_id: "",
    scene_profile: null,
    study_unit_id: "unit-1",
    study_unit_title: "Unit 1",
    theme_hint: "invariants",
    session_system_prompt: "Teach from the cited pages.",
    status: "active",
    revision: 1,
    last_turn_sequence: 1,
    turns: [fullWireTurn()],
    prepared_study_unit_ids: [],
    pending_follow_ups: [],
    session_memory: [],
    affinity_state: {
      score: 0,
      level: "neutral",
      summary: "",
      updated_at: "",
      events: [],
    },
    plan_confirmations: [],
    projected_pdf: null,
    created_at: createdAt,
    updated_at: committedAt,
  };
}

function fullChatExchange(): Record<string, any> {
  const session = fullWireSession();
  const turn = session.turns[0]!;
  return {
    reply: turn.assistant_reply,
    citations: turn.citations,
    character_events: turn.character_events,
    rich_blocks: turn.rich_blocks,
    interactive_question: turn.interactive_question,
    persona_slot_trace: turn.persona_slot_trace,
    memory_trace: turn.memory_trace,
    tool_calls: turn.tool_calls,
    scene_profile: turn.scene_profile,
    model_recoveries: turn.model_recoveries,
    session,
  };
}

function emptyStudySceneProfile(): Record<string, any> {
  return {
    scene_name: "",
    scene_id: "scene-empty",
    title: "未命名场景",
    summary: "场景路径：未命名场景",
    tags: [],
    selected_path: ["未命名场景"],
    focus_object_names: [],
    scene_tree: [],
  };
}

function wireTurn(id: string, sequence: number) {
  return { id, sequence };
}

function wireSession(turns = [wireTurn("turn-1", 1), wireTurn("turn-2", 2)]) {
  return {
    revision: 4,
    last_turn_sequence: turns.length,
    turns,
  };
}

test("Study Session committed identity decoder accepts contiguous unique turns", () => {
  assert.deepEqual(decodeStudySessionCommittedIdentity(wireSession()), {
    revision: 4,
    lastTurnSequence: 2,
    turns: [wireTurn("turn-1", 1), wireTurn("turn-2", 2)],
  });
});

test("Study Session committed identity decoder fails closed on missing watermarks", () => {
  const missingRevision = { ...wireSession() } as Record<string, unknown>;
  delete missingRevision.revision;
  assert.throws(
    () => decodeStudySessionCommittedIdentity(missingRevision),
    (error: unknown) =>
      error instanceof StudySessionDecodeError && error.path === "study_session.revision",
  );

  const missingTurnWatermark = { ...wireSession() } as Record<string, unknown>;
  delete missingTurnWatermark.last_turn_sequence;
  assert.throws(
    () => decodeStudySessionCommittedIdentity(missingTurnWatermark),
    (error: unknown) =>
      error instanceof StudySessionDecodeError &&
      error.path === "study_session.last_turn_sequence",
  );
});

test("Study Session committed identity decoder rejects invalid numeric projections", () => {
  for (const revision of [Number.NaN, 1.5, -1, "4"]) {
    assert.throws(
      () => decodeStudySessionCommittedIdentity({ ...wireSession(), revision }),
      StudySessionDecodeError,
    );
  }
  assert.throws(
    () => decodeStudySessionCommittedIdentity({ ...wireSession(), last_turn_sequence: 1 }),
    (error: unknown) =>
      error instanceof StudySessionDecodeError &&
      error.path === "study_session.last_turn_sequence",
  );
});

test("Study Session committed identity decoder rejects duplicate, empty, or gapped turns", () => {
  for (const turns of [
    [wireTurn("turn-1", 1), wireTurn("turn-1", 2)],
    [wireTurn("", 1)],
    [wireTurn("turn-2", 2)],
    [wireTurn("turn-1", 1), wireTurn("turn-3", 3)],
  ]) {
    assert.throws(
      () => decodeStudySessionCommittedIdentity(wireSession(turns)),
      StudySessionDecodeError,
    );
  }
});

test("full Study Session decoder accepts the complete modern public projection", () => {
  const decoded = decodeStudySession(fullWireSession(), {
    expectedSessionId: "session-1",
    expectedDocumentId: "document-1",
    expectedPersonaId: "persona-1",
    expectedPlanId: null,
    expectedStudyUnitId: "unit-1",
  });
  assert.equal(decoded.revision, 1);
  assert.equal(decoded.turns[0]?.citations[0]?.sourceKind, "document");
  assert.equal(decoded.affinityState?.level, "neutral");
});

test("full Study Session decoder rejects missing, coerced, and fabricated aggregate state", () => {
  const missing = structuredClone(fullWireSession()) as Record<string, unknown>;
  delete missing.pending_follow_ups;
  assert.throws(
    () => decodeStudySession(missing),
    (error: unknown) => error instanceof StudySessionDecodeError &&
      error.path === "study_session.pending_follow_ups",
  );

  for (const mutation of [
    (session: ReturnType<typeof fullWireSession>) => { session.revision = "1" as never; },
    (session: ReturnType<typeof fullWireSession>) => { session.status = "completed"; },
    (session: ReturnType<typeof fullWireSession>) => { session.document_id = "document-forged"; },
  ]) {
    const session = structuredClone(fullWireSession());
    mutation(session);
    assert.throws(
      () => decodeStudySession(session, { expectedDocumentId: "document-1" }),
      StudySessionDecodeError,
    );
  }
});

test("attachment projection rejects private paths and broken citation references", () => {
  const withAttachment = structuredClone(fullWireSession());
  withAttachment.turns[0]!.learner_attachments = [{
    attachment_id: "attachment-pdf-1",
    name: "reference.pdf",
    mime_type: "application/pdf",
    kind: "pdf",
    size_bytes: 2048,
    image_url: "",
    text_excerpt: "A bounded public excerpt.",
    source: "learner_upload",
    page_count: 4,
    previewable: true,
  }];
  withAttachment.turns[0]!.citations = [{
    section_id: "attachment-pdf-1",
    title: "reference.pdf",
    page_start: 2,
    page_end: 2,
    source_kind: "attachment_pdf",
    source_id: "attachment-pdf-1",
  }];
  assert.equal(
    decodeStudySession(withAttachment).turns[0]?.learnerAttachments?.[0]?.attachmentId,
    "attachment-pdf-1",
  );

  const leaked = structuredClone(withAttachment);
  (leaked.turns[0]!.learner_attachments[0] as Record<string, unknown>).stored_path = "/private/staging/reference.pdf";
  assert.throws(
    () => decodeStudySession(leaked),
    (error: unknown) => error instanceof StudySessionDecodeError && error.path.endsWith(".stored_path"),
  );

  const forgedReference = structuredClone(withAttachment);
  forgedReference.turns[0]!.citations[0]!.source_id = "attachment-missing";
  forgedReference.turns[0]!.citations[0]!.section_id = "attachment-missing";
  assert.throws(() => decodeStudySession(forgedReference), StudySessionDecodeError);

  const outOfRange = structuredClone(withAttachment);
  outOfRange.turns[0]!.citations[0]!.page_end = 5;
  assert.throws(() => decodeStudySession(outOfRange), StudySessionDecodeError);
});

test("Character Events and tool traces are closed and cross-referenced", () => {
  const invalidTiming = structuredClone(fullWireSession());
  invalidTiming.turns[0]!.character_events[0]!.timing_hint = "eventually";
  assert.throws(() => decodeStudySession(invalidTiming), StudySessionDecodeError);

  const orphanToolEvent = structuredClone(fullWireSession());
  orphanToolEvent.turns[0]!.character_events[0]!.tool_name = "read_system_time";
  orphanToolEvent.turns[0]!.character_events[0]!.tool_summary = "Read the time";
  assert.throws(() => decodeStudySession(orphanToolEvent), StudySessionDecodeError);

  const malformedToolJson = structuredClone(fullWireSession());
  malformedToolJson.turns[0]!.tool_calls = [{
    tool_call_id: "call-1",
    tool_name: "read_system_time",
    arguments_json: "[]",
    result_summary: "Read the time",
    result_json: '{"ok":true}',
  }];
  assert.throws(() => decodeStudySession(malformedToolJson), StudySessionDecodeError);
});

test("interactive question decoder rejects grading leaks and partial result evidence", () => {
  const withQuestion = structuredClone(fullWireSession());
  withQuestion.revision = 2;
  withQuestion.turns[0]!.interactive_question = {
    schema_version: "study-interactive-question-v2",
    question_type: "multiple_choice",
    prompt: "Choose the invariant",
    difficulty: "medium",
    topic: "invariants",
    options: [{ key: "A", text: "Stable" }, { key: "B", text: "Mutable" }],
    call_back: true,
    result: null,
  };
  assert.equal(decodeStudySession(withQuestion).turns[0]?.interactiveQuestion?.result, null);

  const leaked = structuredClone(withQuestion);
  (leaked.turns[0]!.interactive_question as Record<string, unknown>).grading_spec = { correct: "A" };
  assert.throws(() => decodeStudySession(leaked), StudySessionDecodeError);

  const partial = structuredClone(withQuestion);
  partial.turns[0]!.interactive_question!.result = {
    schema_version: "study-question-result-v1",
    attempt_id: "attempt-1",
    client_attempt_id: null,
    submitted_answer: "A",
    is_correct: true,
    feedback_text: "Correct",
    explanation: "",
    before_revision: 1,
    committed_revision: 2,
    committed_at: committedAt,
  };
  assert.throws(() => decodeStudySession(partial), StudySessionDecodeError);
});

test("follow-up, affinity, and projected-state terminal invariants fail closed", () => {
  const invalidFollowUp = structuredClone(fullWireSession());
  invalidFollowUp.pending_follow_ups = [{
    id: "follow-up-1",
    trigger_kind: "scheduled_reply",
    status: "completed",
    delay_seconds: 10,
    due_at: committedAt,
    hidden_message: "Continue",
    reason: "",
    created_at: createdAt,
    completed_at: "",
    canceled_at: "",
  }];
  assert.throws(() => decodeStudySession(invalidFollowUp), StudySessionDecodeError);

  const invalidAffinity = structuredClone(fullWireSession());
  invalidAffinity.affinity_state.score = Number.NaN;
  assert.throws(() => decodeStudySession(invalidAffinity), StudySessionDecodeError);

  const invalidProjection = structuredClone(fullWireSession());
  invalidProjection.projected_pdf = {
    source_kind: "generated_image",
    source_id: "generated-image-1",
    title: "Diagram",
    page_number: 1,
    page_count: 1,
    image_url: "",
    overlays: [],
    updated_at: committedAt,
  };
  assert.throws(() => decodeStudySession(invalidProjection), StudySessionDecodeError);
});

test("Study Scene decoder preserves empty-tree and empty-reuse compatibility", () => {
  assert.equal(decodeStudySceneProfile(emptyStudySceneProfile()).sceneId, "scene-empty");

  const treeProfile = {
    scene_name: "Lab",
    scene_id: "layer-1",
    title: "Bench",
    summary: "A mutable Study scene",
    tags: ["metal", "movable"],
    selected_path: ["Bench"],
    focus_object_names: ["Block"],
    scene_tree: [{
      id: "layer-1",
      title: "Bench",
      scope_label: "room",
      summary: "",
      atmosphere: "",
      rules: "",
      entrance: "",
      tags: "layer-only-tag",
      reuse_id: "",
      reuse_hint: "",
      objects: [{
        id: "object-1",
        name: "Block",
        description: "",
        interaction: "",
        tags: "metal,movable",
        reuse_id: "",
        reuse_hint: "",
      }],
      children: [],
    }],
  };
  assert.deepEqual(decodeStudySceneProfile(treeProfile).tags, ["metal", "movable"]);

  const forged = structuredClone(treeProfile);
  forged.selected_path = ["Forged"];
  assert.throws(() => decodeStudySceneProfile(forged), StudySessionDecodeError);
});

test("committed Study Chat exchange must equal the exact committed last Turn", () => {
  const exchange = fullChatExchange();
  const decoded = decodeStudyChatExchange(exchange, {
    expectedSessionId: "session-1",
    evidence: {
      sessionId: "session-1",
      admittedSessionRevision: 0,
      committedSessionRevision: 1,
      committedTurnId: "turn-1",
      committedTurnSequence: 1,
    },
  });
  assert.equal(decoded.reply, "Start with the invariant.");

  const forgedReply = structuredClone(exchange);
  forgedReply.reply = "A different answer";
  assert.throws(() => decodeStudyChatExchange(forgedReply, {
    expectedSessionId: "session-1",
  }), StudySessionDecodeError);

  assert.throws(() => decodeStudyChatExchange(exchange, {
    expectedSessionId: "session-1",
    evidence: {
      sessionId: "session-1",
      admittedSessionRevision: 0,
      committedSessionRevision: 1,
      committedTurnId: "turn-forged",
      committedTurnSequence: 1,
    },
  }), StudySessionDecodeError);
});

test("Study Session list and plan-confirmation read-back fence identities and terminal state", () => {
  assert.equal(decodeStudySessionList({ items: [fullWireSession()] }, {
    expectedDocumentId: "document-1",
  }).length, 1);
  assert.throws(() => decodeStudySessionList({ items: [fullWireSession(), fullWireSession()] }), StudySessionDecodeError);

  const resolved = structuredClone(fullWireSession());
  resolved.plan_id = "plan-1";
  resolved.revision = 2;
  resolved.plan_confirmations = [{
    id: "confirmation-1",
    tool_name: "update_learning_plan",
    action_type: "update_plan",
    plan_id: "plan-1",
    title: "Update title",
    summary: "",
    preview_lines: ["New title"],
    payload: { course_title: "New title", note: "" },
    status: "approved",
    created_at: createdAt,
    resolved_at: committedAt,
    resolution_note: "",
  }];
  const callbackCalls: unknown[][] = [];
  const response = decodeStudyPlanConfirmationDecisionResponse(
    { session: resolved, plan: { id: "plan-1" } },
    {
      expectedSessionId: "session-1",
      expectedConfirmationId: "confirmation-1",
      expectedDecision: "approve",
      decodePlan: (...args) => {
        callbackCalls.push(args);
        return { id: "plan-1" } as LearningPlan;
      },
    },
  );
  assert.equal(response.plan?.id, "plan-1");
  assert.deepEqual(callbackCalls[0]?.slice(1), [
    "study_plan_confirmation_decision.plan", "plan-1", "document-1",
  ]);

  assert.throws(() => decodeStudyPlanConfirmationDecisionResponse(
    { session: resolved, plan: { id: "plan-1" } },
    {
      expectedSessionId: "session-1",
      expectedConfirmationId: "confirmation-1",
      expectedDecision: "reject",
      decodePlan: () => ({ id: "plan-1" }) as LearningPlan,
    },
  ), StudySessionDecodeError);
});

test("Study Session display ordering follows sequence rather than timestamps", () => {
  const base = {
    learnerMessage: "question",
    assistantReply: "answer",
    citations: [],
    characterEvents: [],
  };
  const laterCommit: DialogueTurnRecord = {
    ...base,
    id: "turn-2",
    sequence: 2,
    createdAt: "2026-08-12T00:00:00Z",
  };
  const earlierCommit: DialogueTurnRecord = {
    ...base,
    id: "turn-1",
    sequence: 1,
    createdAt: "2026-08-12T00:00:01Z",
  };
  assert.deepEqual(
    orderStudySessionTurns([laterCommit, earlierCommit]).map((turn) => turn.id),
    ["turn-1", "turn-2"],
  );
});

test("Study Session decode failures use safe user notices and retain generic fallbacks", () => {
  const decodeError = new StudySessionDecodeError("study_session.revision", "expected_integer");
  assert.equal(isStudySessionDecodeError(decodeError), true);
  const historyNotice = resolveStudySessionErrorNotice(
    decodeError,
    `载入失败：${String(decodeError)}`,
    "history",
  );
  assert.match(historyNotice, /历史学习会话格式异常/);
  assert.doesNotMatch(historyNotice, /StudySessionDecodeError|study_session\.revision/);

  const responseNotice = resolveStudySessionErrorNotice(decodeError, "发送失败", "response");
  assert.match(responseNotice, /不要重复发送本次消息/);
  assert.doesNotMatch(responseNotice, /StudySessionDecodeError|study_session\.revision/);

  assert.equal(
    resolveStudySessionErrorNotice(new Error("offline"), "网络连接失败", "update"),
    "网络连接失败",
  );
});

test("Study Session decode failures never expose a retryable chat failure", () => {
  const decodeError = new StudySessionDecodeError(
    "study_session.turns[0].sequence",
    "expected_contiguous_sequence_1",
  );
  assert.equal(resolveStudyChatFailurePresentation(decodeError), null);

  const ordinaryFailure = resolveStudyChatFailurePresentation(new Error("network_offline"));
  assert.deepEqual(ordinaryFailure, {
    detail: "Error: network_offline",
    retryAllowed: true,
  });
});
