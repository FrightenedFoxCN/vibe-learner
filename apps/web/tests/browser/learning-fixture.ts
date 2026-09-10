import type { Page } from "@playwright/test";
import { observeRequests } from "./api-fixture";
import { wireGoalOnlyPlan, fullWireSession, fullWireTurn } from "../support/learning-wire";

export async function populatedLearning(page: Page) {
  await observeRequests(page);
  const plan = { ...wireGoalOnlyPlan(), persona_id: "fixture-mentor", course_title: "Historical Course" };
  const unitId = plan.study_units[0].id;
  const session: ReturnType<typeof fullWireSession> = { ...fullWireSession(), document_id: "", plan_id: plan.id, persona_id: "fixture-mentor",
    study_unit_id: unitId, study_unit_title: "Historical Unit", prepared_study_unit_ids: [unitId] };
  session.turns[0].assistant_reply = "Historical answer";
  session.turns[0].citations = [];
  session.turns[0].character_events = [];
  const requests: { method: string; path: string }[] = [];
  page.on("request", request => {
    if (request.url().startsWith("http://127.0.0.1:18999/")) requests.push({ method: request.method(), path: new URL(request.url()).pathname });
  });
  await page.route("http://127.0.0.1:18999/learning-plans", route => route.fulfill({ json: { items: [plan] } }));
  await page.route(/http:\/\/127\.0\.0\.1:18999\/study-sessions(?:\?.*)?$/, route => route.fulfill({ json: { items: [session] } }));
  function commitAnswer() {
    const turn = { ...fullWireTurn(), id: "turn-2", sequence: 2, learner_message: "Recover my question", assistant_reply: "Recovered answer", citations: [], character_events: [] };
    session.turns = [session.turns[0], turn];
    session.revision = 2; session.last_turn_sequence = 2;
  }
  function operation(status: string, requestId = "pending-learner") {
    const committed = status === "committed";
    const terminal = committed || status === "uncertain" || status === "not_committed";
    const turn = session.turns.at(-1);
    return {
      operation_id: "study-chat-op-fixture", session_id: session.id, client_request_id: requestId,
      status, safe_to_retry: status === "not_committed", admitted_session_revision: 1,
      committed_session_revision: committed ? 2 : null,
      committed_turn_id: committed ? "turn-2" : null, committed_turn_sequence: committed ? 2 : null,
      result: committed ? {
        reply: turn.assistant_reply, citations: turn.citations, character_events: turn.character_events,
        rich_blocks: turn.rich_blocks, interactive_question: turn.interactive_question,
        persona_slot_trace: turn.persona_slot_trace, memory_trace: turn.memory_trace,
        tool_calls: turn.tool_calls, scene_profile: null, model_recoveries: [], session,
      } : null,
      error_code: status === "uncertain" ? "study_chat_execution_uncertain" : "",
      created_at: "2026-08-24T10:00:01+08:00", updated_at: "2026-08-24T10:00:02+08:00",
      completed_at: terminal ? "2026-08-24T10:00:02+08:00" : null,
    };
  }
  return { plan, session, requests, commitAnswer, operation, unitId };
}
