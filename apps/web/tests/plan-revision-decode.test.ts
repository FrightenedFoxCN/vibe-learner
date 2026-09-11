import assert from "node:assert/strict";
import test from "node:test";
import { decodePlanRevision } from "../lib/plan-revision-decode.ts";
import { wireGoalOnlyPlan } from "./support/learning-wire.ts";
function fixture() {
  const base = { ...wireGoalOnlyPlan(), revision: 0 };
  return { operation_id: `plan-revision-${"a".repeat(32)}`, client_request_id: "request-1", plan_id: base.id,
    base_revision: 0, status: "ready", instruction: "Review", rollback_revision: null as number | null,
    base_plan: base, result: null as typeof base | null, error_code: "",
    proposal: { schema_name: "PlanRevisionProposal", schema_version: "plan-revision-proposal-v1", explanation: "Review first",
      course_title: "Revised", overview: "Overview", today_tasks: ["Review"],
      schedule: base.schedule.map(s => ({ schedule_ref: s.id, title: s.title, focus: s.focus })) } };
}
function decode(v: ReturnType<typeof fixture>) { return decodePlanRevision(v, v.plan_id, "request-1"); }
test("revision admission binds base revision, instruction and rollback action", () => {
  const v = fixture();
  assert.equal(decodePlanRevision(v, v.plan_id, v.client_request_id, { baseRevision: 0, instruction: "Review" }).status, "ready");
  for (const input of [{ baseRevision: 1, instruction: "Review" }, { baseRevision: 0, instruction: "Other" }, { baseRevision: 0, rollbackRevision: 0 }])
    assert.throws(() => decodePlanRevision(v, v.plan_id, v.client_request_id, input), /admission_mismatch/);
});
test("revision proposal preserves backend string and task bounds", () => {
  const unicode = fixture(); unicode.proposal.course_title = "😀".repeat(500); assert.equal(decode(unicode).proposal?.courseTitle, unicode.proposal.course_title);
  const mutations: ((v: ReturnType<typeof fixture>) => void)[] = [
    v => { v.proposal.course_title = "x".repeat(501); }, v => { v.proposal.overview = "x".repeat(8001); },
    v => { v.proposal.explanation = "x".repeat(4001); }, v => { v.proposal.schedule[0].focus = "x".repeat(4001); },
    v => { v.proposal.schedule[0].title = "x".repeat(501); }, v => { v.proposal.today_tasks = [" "]; },
    v => { v.proposal.today_tasks = ["x".repeat(4001)]; }, v => { v.instruction = "x".repeat(8001); },
    v => { v.instruction = ""; }, v => { v.rollback_revision = 0; },
  ];
  for (const mutate of mutations) { const v = fixture(); mutate(v); assert.throws(() => decode(v)); }
});
test("revision decoder rejects identity, unknown targets and state effect tampering", () => {
  const v = fixture(); assert.equal(decode(v).status, "ready");
  assert.throws(() => decodePlanRevision(v, "another-plan", v.client_request_id), /identity_mismatch/);
  const target = fixture(); target.proposal.schedule[0].schedule_ref = "alien"; assert.throws(() => decode(target), /schedule_target_mismatch/);
  const accepted = fixture(); accepted.status = "accepted";
  accepted.result = { ...structuredClone(accepted.base_plan), revision: 1, course_title: accepted.proposal.course_title,
    overview: accepted.proposal.overview, today_tasks: accepted.proposal.today_tasks };
  accepted.result.study_unit_progress[0].objective_fragment = accepted.proposal.schedule[0].focus;
  assert.equal(decode(accepted).status, "accepted");
  accepted.result.objective = "Tampered objective";
  assert.throws(() => decode(accepted), /committed_projection_mismatch/);
});

test("accepted revision binds derived focus while rejecting stale or invented progress labels", () => {
  const v = fixture(); v.status = "accepted"; v.proposal.schedule[0].focus = "New learning objective";
  v.result = { ...structuredClone(v.base_plan), revision: 1, course_title: v.proposal.course_title,
    overview: v.proposal.overview, today_tasks: v.proposal.today_tasks };
  v.result.schedule[0].focus = v.proposal.schedule[0].focus;
  v.result.study_unit_progress[0].objective_fragment = v.proposal.schedule[0].focus;
  assert.equal(decode(v).result?.studyUnitProgress[0].objectiveFragment, "New learning objective");
  v.result.study_unit_progress[0].objective_fragment = "Old or invented objective";
  assert.throws(() => decode(v), /committed_projection_mismatch/);
});
