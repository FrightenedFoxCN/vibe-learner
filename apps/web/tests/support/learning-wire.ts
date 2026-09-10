// Contract-valid wire records shared by decoder and browser tests.

export function wireUnit() {
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

export function wireChapter() {
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

export function wirePlan() {
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

export function wireGoalOnlyPlan() {
  const syntheticDocumentId = "goal-only:f9ebca2c";
  const unitId = `${syntheticDocumentId}:study-unit:goal:1`;
  const scheduleId = "schedule-goal-1";
  return {
    ...wirePlan(),
    id: "plan-goal-1",
    document_id: "",
    creation_mode: "goal_only",
    study_units: [
      {
        ...wireUnit(),
        id: unitId,
        document_id: syntheticDocumentId,
        source_section_ids: [],
      },
    ],
    schedule: [
      {
        ...wirePlan().schedule[0],
        id: scheduleId,
        unit_id: unitId,
        schedule_chapters: [
          {
            ...wireChapter(),
            id: `${unitId}:schedule-chapter:1`,
            source_section_ids: [],
            content_slices: [
              { page_start: 1, page_end: 2, source_section_ids: [] },
            ],
          },
        ],
      },
    ],
    study_unit_progress: [
      {
        ...wirePlan().study_unit_progress[0],
        unit_id: unitId,
        schedule_ids: [scheduleId],
      },
    ],
  };
}

export const createdAt = "2026-08-24T10:00:00+08:00";

export const committedAt = "2026-08-24T10:00:01+08:00";

export function fullWireTurn(): Record<string, any> {
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

export function fullWireSession(): Record<string, any> {
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

export function fullChatExchange(): Record<string, any> {
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
