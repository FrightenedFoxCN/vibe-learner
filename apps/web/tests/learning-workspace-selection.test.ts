import assert from "node:assert/strict";
import test from "node:test";
import type {
  LearningPlan,
  StudyChatResponse,
  StudySessionRecord,
} from "@vibe-learner/shared";
import { StudyAsyncViewFence } from "../lib/async-result-fence.ts";
import {
  createInitialLearningWorkspaceState,
  learningWorkspaceReducer,
} from "../lib/learning-workspace-reducer.ts";
import {
  resolvePlanSelection,
  type PlanSelectionIntent,
} from "../lib/learning-workspace-state.ts";

const plan = (id: string, createdAt: string) => ({ id, createdAt }) as LearningPlan;
const first = plan("first", "2026-01-01");
const second = plan("second", "2026-02-01");
const third = plan("third", "2026-03-01");
const session = {
  id: "session-first",
  studyUnitId: "unit-first",
  planId: first.id,
} as StudySessionRecord;
const response = {} as StudyChatResponse;

function fixture() {
  let visible = {
    ...createInitialLearningWorkspaceState({ initialPlan: first, initialPersonas: [] }),
    planHistory: [second, first],
    studySession: session,
    response,
  };
  let selection = {
    selectedPlanId: visible.selectedPlanId,
    planHistory: visible.planHistory,
  };
  const fence = new StudyAsyncViewFence({ initialPlanId: first.id, session });
  const ticket = fence.begin(session.id, "old-response");
  const actions: Parameters<typeof learningWorkspaceReducer>[1][] = [];
  function publish(intent: PlanSelectionIntent) {
    const transition = resolvePlanSelection(selection, intent);
    if (!transition) return;
    selection = transition.selection;
    if (transition.studyTarget) fence.transition(transition.studyTarget, true);
    actions.push({ type: "plan_transition", transition });
  }
  function render() {
    while (actions.length) {
      visible = learningWorkspaceReducer(visible, actions.shift()!) as typeof visible;
    }
    return visible;
  }
  return { publish, render, fence, ticket, selectedId: () => selection.selectedPlanId };
}

test("same-plan refresh, invalid selection and deleting an unselected plan retain the Study ticket", () => {
  const { publish, render, fence, ticket, selectedId } = fixture();
  publish({ type: "snapshot", plans: [first, second], preferredPlanId: second.id });
  publish({ type: "select", planId: "missing" });
  publish({ type: "select", planId: first.id });
  publish({ type: "delete", planId: second.id });
  assert.equal(fence.viewRevision, 0);
  assert.equal(fence.decide(ticket, selectedId()), "apply");
  assert.equal(render().studySession, session);
  assert.equal(render().response, response);
  assert.deepEqual(render().planHistory, [first]);
});

test("deleting the selected plan after an unrendered refresh uses the new fallback and rejects old replies synchronously", () => {
  const { publish, render, fence, ticket, selectedId } = fixture();
  publish({
    type: "snapshot",
    plans: [first, third, second],
    preferredPlanId: first.id,
  });
  publish({ type: "delete", planId: first.id });
  assert.equal(selectedId(), third.id);
  assert.equal(fence.session, null);
  assert.equal(fence.currentScope(selectedId()).fieldTarget, "study-plan:third");
  assert.equal(fence.decide(ticket, selectedId()), "operation_superseded");
  assert.equal(render().selectedPlanId, third.id);
  assert.equal(render().studySession, null);
  assert.equal(render().response, null);
});

test("selecting a different plan rejects an old reply before React has rendered", () => {
  const { publish, render, fence, ticket, selectedId } = fixture();
  publish({ type: "select", planId: second.id });
  assert.equal(fence.decide(ticket, selectedId()), "operation_superseded");
  assert.equal(render().selectedPlanId, second.id);
  assert.equal(render().studySession, null);
  assert.equal(render().response, null);
});

test("generation and recovery deliberately reset Study even if the selected plan ID matches", () => {
  const { publish, render, fence, selectedId } = fixture();
  publish({ type: "generated", plan: first });
  assert.equal(fence.viewRevision, 1);
  assert.equal(render().response, null);
  publish({ type: "generate" });
  assert.equal(fence.currentScope(selectedId()).fieldTarget, "study-plan:generating");
  assert.equal(render().selectedPlanId, "");
});
