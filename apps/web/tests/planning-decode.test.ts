import assert from "node:assert/strict";
import test from "node:test";

import {
  decodeDocumentPlanningContext,
  decodeDocumentPlanningTraceResponse,
  decodeLearningPlan,
  decodeLearningPlanList,
  PlanningDecodeError,
} from "../lib/planning-decode.ts";

function wireUnit() {
  return {
    id: "unit-1",
    document_id: "document-1",
    title: "Unit 1",
    page_start: 1,
    page_end: 2,
    unit_kind: "chapter",
    include_in_plan: true,
    source_section_ids: ["section-1"],
    summary: "Summary",
    confidence: 0.9,
  };
}

function wireChapter() {
  return {
    id: "unit-1:schedule-chapter:1",
    title: "Chapter 1",
    anchor_page_start: 1,
    anchor_page_end: 2,
    source_section_ids: ["section-1"],
    content_slices: [
      { page_start: 1, page_end: 2, source_section_ids: ["section-1"] },
    ],
  };
}

function wirePlan() {
  return {
    id: "plan-1",
    document_id: "document-1",
    persona_id: "persona-1",
    creation_mode: "document",
    course_title: "Course",
    objective: "Learn",
    scene_profile_summary: "",
    scene_profile: null,
    overview: "Overview",
    today_tasks: ["Read"],
    study_units: [wireUnit()],
    schedule: [
      {
        id: "schedule-1",
        unit_id: "unit-1",
        title: "Learn unit",
        focus: "Concepts",
        activity_type: "learn",
        status: "planned",
        schedule_chapters: [wireChapter()],
      },
    ],
    progress_summary: {
      total_schedule_count: 1,
      completed_schedule_count: 0,
      in_progress_schedule_count: 0,
      pending_schedule_count: 1,
      blocked_schedule_count: 0,
      completion_percent: 0,
    },
    study_unit_progress: [
      {
        unit_id: "unit-1",
        title: "Unit 1",
        objective_fragment: "Concepts",
        schedule_ids: ["schedule-1"],
        total_schedule_count: 1,
        completed_schedule_count: 0,
        in_progress_schedule_count: 0,
        pending_schedule_count: 1,
        blocked_schedule_count: 0,
        completion_percent: 0,
        status: "planned",
      },
    ],
    progress_events: [],
    planning_questions: [],
    created_at: "2026-08-24T00:00:00Z",
  };
}

function wirePlanningContext() {
  const section = {
    section_id: "section-1",
    title: "Section 1",
    level: 1,
    page_start: 1,
    page_end: 2,
  };
  const unit = {
    unit_id: "unit-1",
    title: "Unit 1",
    page_start: 1,
    page_end: 2,
    summary: "Summary",
    unit_kind: "chapter",
    include_in_plan: true,
    subsection_titles: [],
    related_section_ids: ["section-1"],
    detail_tool_target_id: "unit-1",
  };
  return {
    document_id: "document-1",
    course_outline: [{ ...section, children: [] }],
    study_units: [unit],
    detail_map: {
      "unit-1": {
        ...unit,
        related_sections: [section],
        chunk_count: 1,
        chunk_excerpts: [
          {
            chunk_id: "chunk-1",
            section_id: "section-1",
            page_start: 1,
            page_end: 2,
            char_count: 20,
            content: "Content",
          },
        ],
      },
    },
    available_tools: [
      { name: "get_study_unit_detail", description: "Read unit detail" },
      { name: "read_page_range_content", description: "Read page content" },
    ],
  };
}

function wirePlanningTrace() {
  return {
    document_id: "document-1",
    has_trace: true,
    summary: {
      round_count: 1,
      tool_call_count: 1,
      latest_finish_reason: "stop",
    },
    trace: {
      document_id: "document-1",
      plan_id: "plan-1",
      model: "gpt-test",
      created_at: "2026-08-24T00:00:00Z",
      rounds: [
        {
          round_index: 0,
          finish_reason: "stop",
          assistant_content: "{}",
          thinking: "",
          elapsed_ms: 10,
          timeout_seconds: 30,
          tool_calls: [
            {
              tool_call_id: "call-1",
              tool_name: "get_study_unit_detail",
              arguments_json: "{}",
              argument_contract_version: "planning-tool-arguments-v1",
              result_contract_version: "planning-tool-result-v1",
              result_summary: "ok",
              result_json: "{}",
            },
          ],
          recoveries: [
            {
              schema_version: "model-recovery-v1",
              recovery_id: "recovery-1",
              category: "schema",
              reason: "malformed",
              strategy: "repair",
              attempts: 1,
              note: "",
              created_at: "2026-08-24T00:00:00Z",
            },
          ],
        },
      ],
    },
  };
}

test("Planning decoder accepts a coherent plan and list envelope", () => {
  const plan = decodeLearningPlan(wirePlan(), {
    expectedPlanId: "plan-1",
    expectedDocumentId: "document-1",
  });
  assert.equal(plan.schedule[0]?.scheduleChapters[0]?.anchorPageEnd, 2);
  assert.deepEqual(decodeLearningPlanList({ items: [wirePlan()] }), [plan]);
});

test("Planning decoder rejects plan/document identity and illegal enums", () => {
  assert.throws(
    () => decodeLearningPlan(wirePlan(), { expectedPlanId: "plan-other" }),
    (error: unknown) =>
      error instanceof PlanningDecodeError && error.path === "learning_plan.id",
  );
  assert.throws(
    () => decodeLearningPlan({ ...wirePlan(), document_id: "document-other" }),
    PlanningDecodeError,
  );
  for (const attack of [
    { ...wirePlan(), creation_mode: "legacy" },
    {
      ...wirePlan(),
      schedule: [{ ...wirePlan().schedule[0], status: "done" }],
    },
    {
      ...wirePlan(),
      schedule: [{ ...wirePlan().schedule[0], activity_type: "watch" }],
    },
  ]) {
    assert.throws(() => decodeLearningPlan(attack), PlanningDecodeError);
  }
});

test("Planning decoder rejects broken Study Unit, chapter, and slice references", () => {
  assert.throws(
    () => decodeLearningPlan({
      ...wirePlan(),
      schedule: [{ ...wirePlan().schedule[0], unit_id: "missing" }],
    }),
    (error: unknown) =>
      error instanceof PlanningDecodeError && error.reason === "unknown_study_unit_reference",
  );
  assert.throws(
    () => decodeLearningPlan({
      ...wirePlan(),
      schedule: [
        {
          ...wirePlan().schedule[0],
          schedule_chapters: [{ ...wireChapter(), source_section_ids: ["missing"] }],
        },
      ],
    }),
    PlanningDecodeError,
  );
  assert.throws(
    () => decodeLearningPlan({
      ...wirePlan(),
      schedule: [
        {
          ...wirePlan().schedule[0],
          schedule_chapters: [
            {
              ...wireChapter(),
              content_slices: [
                { page_start: 1, page_end: 3, source_section_ids: ["section-1"] },
              ],
            },
          ],
        },
      ],
    }),
    PlanningDecodeError,
  );
});

test("Planning decoder rejects duplicate IDs, invalid numbers, and forged progress", () => {
  assert.throws(
    () => decodeLearningPlanList({ items: [wirePlan(), wirePlan()] }),
    PlanningDecodeError,
  );
  assert.throws(
    () => decodeLearningPlan({
      ...wirePlan(),
      study_units: [{ ...wireUnit(), confidence: Number.POSITIVE_INFINITY }],
    }),
    PlanningDecodeError,
  );
  assert.throws(
    () => decodeLearningPlan({
      ...wirePlan(),
      progress_summary: { ...wirePlan().progress_summary, completed_schedule_count: 1 },
    }),
    (error: unknown) =>
      error instanceof PlanningDecodeError &&
      error.reason === "schedule_count_projection_mismatch",
  );
  assert.throws(
    () => decodeLearningPlan({
      ...wirePlan(),
      study_unit_progress: [
        { ...wirePlan().study_unit_progress[0], schedule_ids: ["missing"] },
      ],
    }),
    PlanningDecodeError,
  );
});

test("Planning Context decoder validates identity, ordering, detail set, and references", () => {
  const context = decodeDocumentPlanningContext(wirePlanningContext(), "document-1");
  assert.equal(context.detailMap["unit-1"]?.chunkExcerpts[0]?.chunkId, "chunk-1");

  assert.throws(
    () => decodeDocumentPlanningContext(wirePlanningContext(), "document-other"),
    PlanningDecodeError,
  );
  assert.throws(
    () => decodeDocumentPlanningContext({
      ...wirePlanningContext(),
      study_units: [
        { ...wirePlanningContext().study_units[0], detail_tool_target_id: "unit-other" },
      ],
    }),
    PlanningDecodeError,
  );
  const detail = wirePlanningContext().detail_map["unit-1"];
  assert.throws(
    () => decodeDocumentPlanningContext({
      ...wirePlanningContext(),
      detail_map: {
        "unit-1": {
          ...detail,
          chunk_excerpts: [{ ...detail.chunk_excerpts[0], section_id: "missing" }],
        },
      },
    }),
    PlanningDecodeError,
  );
  assert.throws(
    () => decodeDocumentPlanningContext({
      ...wirePlanningContext(),
      available_tools: [
        { name: "get_study_unit_detail", description: "one" },
        { name: "get_study_unit_detail", description: "two" },
      ],
    }),
    PlanningDecodeError,
  );
});

test("Planning Trace decoder validates recovery versions, contracts, identity, and summary", () => {
  const trace = decodeDocumentPlanningTraceResponse(wirePlanningTrace(), "document-1");
  assert.equal(trace.trace?.rounds[0]?.recoveries[0]?.schemaVersion, "model-recovery-v1");
  assert.equal(
    trace.trace?.rounds[0]?.toolCalls[0]?.argumentContractVersion,
    "planning-tool-arguments-v1",
  );

  const rawTrace = wirePlanningTrace().trace;
  const rawRound = rawTrace.rounds[0];
  const rawRecovery = rawRound.recoveries[0];
  const rawToolCall = rawRound.tool_calls[0];
  for (const attack of [
    { ...wirePlanningTrace(), document_id: "document-other" },
    { ...wirePlanningTrace(), summary: { ...wirePlanningTrace().summary, round_count: 2 } },
    {
      ...wirePlanningTrace(),
      trace: {
        ...rawTrace,
        rounds: [
          {
            ...rawRound,
            recoveries: [{ ...rawRecovery, schema_version: "model-recovery-v999" }],
          },
        ],
      },
    },
    {
      ...wirePlanningTrace(),
      trace: {
        ...rawTrace,
        rounds: [
          {
            ...rawRound,
            tool_calls: [
              { ...rawToolCall, argument_contract_version: "planning-tool-arguments-v999" },
            ],
          },
        ],
      },
    },
  ]) {
    assert.throws(
      () => decodeDocumentPlanningTraceResponse(attack, "document-1"),
      PlanningDecodeError,
    );
  }
});

test("Planning Trace decoder accepts a truthful no-trace projection only", () => {
  assert.deepEqual(
    decodeDocumentPlanningTraceResponse({
      document_id: "document-1",
      has_trace: false,
      summary: { round_count: 0, tool_call_count: 0, latest_finish_reason: "" },
      trace: null,
    }),
    {
      documentId: "document-1",
      hasTrace: false,
      summary: { roundCount: 0, toolCallCount: 0, latestFinishReason: "" },
      trace: null,
    },
  );
  assert.throws(
    () => decodeDocumentPlanningTraceResponse({
      ...wirePlanningTrace(),
      has_trace: false,
    }),
    PlanningDecodeError,
  );
});
