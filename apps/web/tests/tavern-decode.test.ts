import assert from "node:assert/strict";
import test from "node:test";

import v3Traces from "./fixtures/tavern-trace-v3.json" with { type: "json" };

import {
  decodeHarnessTrace,
  normalizeTavernErrorDetail,
  normalizeTavernRoomDetail,
  normalizeTavernRoomList,
  normalizeTavernRunRecovery,
  TavernDecodeError,
} from "../lib/tavern-decode.ts";

function rejects(decode: () => unknown, path: string, reason: string) {
  assert.throws(decode, (error) => {
    assert.ok(error instanceof TavernDecodeError);
    assert.equal(error.code, "tavern_response_decode_error");
    assert.equal(error.path, path);
    assert.equal(error.message, `${reason} at ${path}`);
    return true;
  });
}

const timestamp = "2024-01-01T00:00:00Z";
const roomId = "room-1";
const personaId = "persona-1";

const roomItem = {
  id: roomId,
  title: "Tavern",
  participant_persona_ids: [personaId],
  participant_names: ["Guide"],
  message_count: 0,
  revision: 1,
  status: "active",
  created_at: timestamp,
  updated_at: timestamp,
};
const roomPage = {
  contract_version: "tavern-room-list-v1",
  items: [roomItem],
  next_cursor: null,
};

const roomDetail = {
  room: {
    id: roomId,
    creation_key: "",
    creation_input_digest: "",
    title: "Tavern",
    scene_profile: null,
    harness_policy: {
      version: "v1",
      max_character_messages: 1,
      max_reply_characters: 4000,
      context_message_limit: 4,
      prevent_speaker_impersonation: true,
    },
    status: "active",
    revision: 0,
    last_sequence: 0,
    created_at: timestamp,
    updated_at: timestamp,
  },
  participants: [
    {
      room_id: roomId,
      persona_id: personaId,
      display_order: 0,
      display_name: "",
      prompt_hash: "prompt-1",
      joined_at: timestamp,
      persona_snapshot: {
        id: personaId,
        name: "",
        source: "builtin",
        summary: "",
        relationship: "",
        learner_address: "",
        system_prompt: "",
        reference_hints: [],
        slots: [
          {
            kind: "identity",
            label: "",
            content: "",
            weight: -Number.MAX_VALUE,
            locked: false,
            sort_order: 0,
          },
        ],
        available_emotions: [],
        available_actions: [],
        default_speech_style: "",
      },
    },
  ],
  messages: [],
  message_count: 0,
  next_after_sequence: null,
  next_before_sequence: 1,
};

const runId = "run-1";
const run = {
  id: runId,
  room_id: roomId,
  idempotency_key: "request-1",
  request_digest: "",
  context_digest: "",
  mode: "facilitated",
  trigger_kind: "continue",
  parent_run_id: "",
  root_run_id: "",
  input_message_id: null,
  anchor_message_id: "",
  scheduled_participant_ids: [personaId],
  speaker_steps: [
    {
      run_id: runId,
      step_index: 0,
      persona_id: personaId,
      participant_prompt_hash: "",
      status: "failed",
      message_id: "",
      reply_to_message_id: "",
      error_code: "",
      harness_trace: null,
      claim_count: 0,
      started_at: "",
      completed_at: "",
    },
  ],
  guidance: "",
  status: "failed",
  expected_room_revision: 0,
  generated_message_ids: [],
  harness_trace: [],
  error_code: "",
  terminal_sequence: 0,
  created_at: timestamp,
  completed_at: "",
};
const chain = {
  root_run_id: runId,
  run_ids: [runId],
  root_status: "failed",
  leaf_run: run,
  chain_status: "recoverable",
  recovery_action: "retry_leaf",
  completed_participant_ids: [],
  unfinished_participant_ids: [personaId],
};

test("room pages retain shape, indexed field errors, identity uniqueness and order", () => {
  const prefix = "tavern.room_list";
  assert.equal(normalizeTavernRoomList(roomPage).items[0]?.id, roomId);
  rejects(() => normalizeTavernRoomList([]), prefix, "expected_object");
  rejects(
    () => normalizeTavernRoomList({ ...roomPage, items: {} }),
    `${prefix}.items`,
    "expected_array",
  );
  rejects(
    () =>
      normalizeTavernRoomList({
        ...roomPage,
        items: [{ ...roomItem, status: "deleted" }],
      }),
    `${prefix}.items[0].status`,
    "unexpected_enum_deleted",
  );
  rejects(
    () =>
      normalizeTavernRoomList({
        ...roomPage,
        items: [{ ...roomItem, participant_names: [""] }],
      }),
    `${prefix}.items[0].participant_names[0]`,
    "expected_non_empty_string",
  );
  rejects(
    () => normalizeTavernRoomList({ ...roomPage, items: [roomItem, roomItem] }),
    `${prefix}.items.id`,
    "expected_unique_values",
  );
  rejects(
    () =>
      normalizeTavernRoomList({
        ...roomPage,
        items: [roomItem, { ...roomItem, id: "room-2" }],
      }),
    `${prefix}.items[1]`,
    "room_page_not_monotonic_updated_at_id_desc",
  );
});

test("nullable and blank string projections still require own wire fields", () => {
  const detail = {
    code: "retry",
    run_id: "",
    child_run_id: "",
    current_revision: null,
    recovery_action: "none",
  };
  assert.deepEqual(normalizeTavernErrorDetail({ detail }), {
    code: "retry",
    runId: undefined,
    childRunId: undefined,
    currentRevision: null,
    recoveryAction: "none",
  });
  rejects(
    () =>
      normalizeTavernErrorDetail({
        detail: Object.assign(Object.create({ run_id: "" }), { code: "retry" }),
      }),
    "tavern.error.detail.run_id",
    "missing_required_field",
  );
  rejects(
    () => normalizeTavernErrorDetail({ detail: { ...detail, run_id: null } }),
    "tavern.error.detail.run_id",
    "expected_string",
  );
  rejects(
    () => normalizeTavernRoomList({ ...roomPage, next_cursor: undefined }),
    "tavern.room_list.next_cursor",
    "expected_non_empty_string",
  );
  rejects(
    () =>
      normalizeTavernRoomList({
        contract_version: roomPage.contract_version,
        items: [],
      }),
    "tavern.room_list.next_cursor",
    "missing_required_field",
  );
});

test("integer bounds and finite numbers keep their Tavern-specific reasons", () => {
  const detail = normalizeTavernRoomDetail(roomDetail, roomId);
  assert.equal(detail.room.creationKey, undefined);
  assert.equal(detail.room.sceneProfile, undefined);
  assert.equal(detail.participants[0]?.personaSnapshot.revision, 0);
  assert.equal(
    detail.participants[0]?.personaSnapshot.slots[0]?.weight,
    -Number.MAX_VALUE,
  );
  assert.equal(detail.nextBeforeSequence, 1);
  const badPolicy = structuredClone(roomDetail);
  badPolicy.room.harness_policy.max_reply_characters = 4001;
  rejects(
    () => normalizeTavernRoomDetail(badPolicy),
    "tavern.room_detail.room.harness_policy.max_reply_characters",
    "expected_integer_120_to_4000",
  );
  assert.equal(
    normalizeTavernRoomDetail({
      ...roomDetail,
      next_before_sequence: Number.MAX_SAFE_INTEGER,
    }).nextBeforeSequence,
    Number.MAX_SAFE_INTEGER,
  );
  rejects(
    () =>
      normalizeTavernRoomDetail({
        ...roomDetail,
        next_before_sequence: Number.MAX_SAFE_INTEGER + 1,
      }),
    "tavern.room_detail.next_before_sequence",
    "expected_integer_1_to_9007199254740991",
  );
  const badWeight = structuredClone(roomDetail);
  badWeight.participants[0]!.persona_snapshot.slots[0]!.weight = Infinity;
  rejects(
    () => normalizeTavernRoomDetail(badWeight),
    "tavern.room_detail.participants[0].persona_snapshot.slots[0].weight",
    "expected_finite_number",
  );
});

test("room and participant snapshot identities are checked", () => {
  rejects(
    () => normalizeTavernRoomDetail(roomDetail, "other-room"),
    "tavern.room_detail.room.id",
    "identity_mismatch_expected_other-room",
  );
  const wrongPersona = structuredClone(roomDetail);
  wrongPersona.participants[0]!.persona_snapshot.id = "other-persona";
  rejects(
    () => normalizeTavernRoomDetail(wrongPersona),
    "tavern.room_detail.participants[0].persona_snapshot.id",
    "identity_mismatch_expected_persona-1",
  );
});

test("retry chains preserve run and schedule identity constraints", () => {
  const prefix = "tavern.run_recovery.items[0]";
  assert.equal(
    normalizeTavernRunRecovery({ items: [chain] }, roomId)[0]?.leafRun.inputMessageId,
    null,
  );
  rejects(
    () => normalizeTavernRunRecovery({ items: [{ ...chain, run_ids: ["other-run"] }] }),
    `${prefix}.run_ids`,
    "retry_chain_identity_mismatch",
  );
  rejects(
    () =>
      normalizeTavernRunRecovery({ items: [{ ...chain, recovery_action: "none" }] }),
    `${prefix}.recovery_action`,
    "chain_action_mismatch",
  );
  const wrongStepRun = structuredClone(chain);
  wrongStepRun.leaf_run.speaker_steps[0]!.run_id = "other-run";
  rejects(
    () => normalizeTavernRunRecovery({ items: [wrongStepRun] }),
    `${prefix}.leaf_run.speaker_steps[0].run_id`,
    "identity_mismatch_expected_run-1",
  );
  const wrongSchedule = structuredClone(chain);
  wrongSchedule.leaf_run.speaker_steps[0]!.step_index = 1;
  rejects(
    () => normalizeTavernRunRecovery({ items: [wrongSchedule] }),
    `${prefix}.leaf_run.speaker_steps[0].step_index`,
    "schedule_index_mismatch_expected_0",
  );
});

test("historical v2 trace keeps its attempt order and decoding behavior", () => {
  const operationId = `harness-operation-${"a".repeat(32)}`;
  const trace = {
    trace_schema_version: "harness-trace-v2",
    trace_id: `harness-trace-${"b".repeat(32)}`,
    operation_id: operationId,
    workflow: "tavern",
    stage: "speaker",
    context: { operation_id: operationId, workflow: "tavern", stage: "speaker" },
    commit_evidence: { status: "not_applicable" },
    checks: [],
    attempt_records: [
      { attempt_index: 1, attempt_id: `harness-attempt-${"c".repeat(32)}` },
    ],
    parent_trace_id: null,
    status: "passed",
    recovery_strategy: "none",
    error_code: "",
    duration_ms: 0,
    started_at: timestamp,
    completed_at: timestamp,
  };
  const parsed = decodeHarnessTrace(trace, "trace");
  assert.equal("operationId" in parsed && parsed.operationId, operationId);
  rejects(
    () =>
      decodeHarnessTrace(
        {
          ...trace,
          attempt_records: [{ ...trace.attempt_records[0], attempt_index: 2 }],
        },
        "trace",
      ),
    "trace.attempt_records[0]",
    "invalid_attempt_ordering",
  );
});

test("legacy unversioned traces still use their read-only contract", () => {
  const trace = decodeHarnessTrace(
    {
      version: "tavern-actor-reply-v1",
      workflow: "tavern",
      stage: "actor_reply",
      status: "passed",
      schema_name: "TavernReply",
      input_digest: "",
      context_digest: "",
      checks: [],
      attempts: 1,
      recovery_strategy: "none",
      duration_ms: 0,
    },
    "legacy",
  );
  assert.ok("version" in trace);
  assert.equal(trace.attempts, 1);
});

test("persisted v3 fixtures from the first released v3 and current mock backend decode strictly", () => {
  // Unmodified run trace objects captured using a SQLite TestClient and SequencedTavernProvider.
  for (const [wire, state, evidence] of [
    [v3Traces.legacyTagPassed, "passed", "committed"],
    [v3Traces.currentRepaired, "repaired", "committed"],
    [v3Traces.currentFailed, "failed", "not_committed"],
  ] as const) {
    const trace = decodeHarnessTrace(wire, "trace");
    assert.ok(
      "traceSchemaVersion" in trace && trace.traceSchemaVersion === "harness-trace-v3",
    );
    assert.equal(trace.status, state);
    assert.equal(trace.workflow, "tavern");
    assert.equal(trace.stage, "actor_reply");
    assert.equal(trace.context.operationId, trace.operationId);
    assert.equal(trace.commitEvidence.status, evidence);
    assert.equal(trace.contract.name, wire.contract.name);
    assert.equal(trace.attemptRecords[0]?.attemptIndex, 1);
  }
});

test("missing or inconsistent v3 evidence does not fall back to legacy", () => {
  const fixture = v3Traces.legacyTagPassed;
  const { contract, ...withoutContract } = fixture;
  assert.ok(contract.version);
  rejects(
    () => decodeHarnessTrace(withoutContract, "trace"),
    "trace.contract",
    "missing_required_field",
  );
  const mismatchedContext = structuredClone(fixture);
  mismatchedContext.context.operation_id = "harness-operation-" + "0".repeat(32);
  rejects(
    () => decodeHarnessTrace(mismatchedContext, "trace"),
    "trace.context.operation_id",
    "identity_mismatch_expected_" + fixture.operation_id,
  );
  const misorderedAttempts = structuredClone(fixture);
  misorderedAttempts.attempt_records[0]!.attempt_index = 2;
  rejects(
    () => decodeHarnessTrace(misorderedAttempts, "trace"),
    "trace",
    "invalid_attempt_order_or_duration",
  );
});
