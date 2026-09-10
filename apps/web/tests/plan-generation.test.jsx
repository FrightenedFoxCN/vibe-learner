import { dom } from "./support/dom.js";
import assert from "node:assert/strict";
import { after, afterEach, test } from "node:test";
import { act, cleanup, renderHook } from "@testing-library/react";
import { registerDiagnosticPage } from "../lib/diagnostics.ts";
import { usePlanGeneration } from "../hooks/use-plan-generation.ts";

afterEach(cleanup);
after(() => dom.window.close());
const deferred = () => {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
};
const plan = id => ({ id, creationMode: "goal_only", todayTasks: [], studyUnits: [], studyUnitProgress: [], schedule: [], objective: "learn" });
const input = { mode: "goal_only", objective: "learn" };
function fixture(overrides = {}, optionOverrides = {}) {
  const calls = { finished: 0, plans: [], sessions: [], documents: [], notices: [], cancelled: [] };
  const options = {
    personaId: "teacher", blockedReason: "", resolveSceneProfile: () => undefined,
    onStarted() {}, onFinished() { calls.finished++; },
    onNotice(value) { calls.notices.push(value); },
    onDocument(value) { calls.documents.push(value); },
    onPlan(value) { calls.plans.push(value); return () => true; },
    onSession(value) { calls.sessions.push(value); }, ...optionOverrides,
  };
  const port = {
    uploadDocument: async () => { throw new Error("unexpected upload"); },
    processDocumentStream: async () => { throw new Error("unexpected parse"); },
    createLearningPlanStream: async () => plan("plan"),
    createStudySession: async () => ({ id: "session" }),
    cancelStreamRun: async id => { calls.cancelled.push(id); }, ...overrides,
  };
  return { ...renderHook(() => usePlanGeneration(options, port)), calls };
}

test("cancelled upload cannot start parsing or apply a document", async () => {
  const upload = deferred();
  const view = fixture({ uploadDocument: () => upload.promise });
  let run;
  act(() => { run = view.result.current.generatePlanWorkflow({ mode: "document", file: new File(["pdf"], "book.pdf"), objective: "learn" }); });
  await act(async () => { await view.result.current.cancelPlanGeneration(); upload.resolve({ id: "document" }); await run; });
  assert.deepEqual(view.calls.documents, []);
  assert.deepEqual(view.calls.plans, []);
  assert.equal(view.result.current.processStreamStatus, "cancelled");
  assert.equal(view.result.current.isGeneratingPlan, false);
});

test("superseded stream events and finally cannot overwrite the active generation", async () => {
  const requests = [];
  const view = fixture({ createLearningPlanStream: (_input, event) => {
    const pending = deferred(); requests.push({ ...pending, event }); return pending.promise;
  } });
  let first, second;
  act(() => { first = view.result.current.generatePlanWorkflow(input); });
  act(() => { requests[0].event({ stage: "working", operationId: "old", payload: {} }); });
  act(() => { second = view.result.current.generatePlanWorkflow(input); });
  await act(async () => {
    requests[0].event({ stage: "stream_error", operationId: "late", payload: {} });
    requests[0].resolve(plan("old")); await first;
  });
  assert.equal(view.result.current.isGeneratingPlan, true);
  assert.equal(view.result.current.planStreamStatus, "running");
  assert.deepEqual(view.result.current.planStreamEvents, []);
  assert.equal(view.calls.finished, 0);
  assert.deepEqual(view.calls.cancelled, ["old"]);
  await act(async () => { requests[1].resolve(plan("new")); await second; });
  assert.deepEqual(view.calls.plans.map(item => item.id), ["new"]);
  assert.equal(view.calls.finished, 1);
});

test("unmount cancels the known operation and suppresses late committed session projection", async () => {
  const session = deferred();
  const view = fixture({
    createLearningPlanStream: async (_input, event) => { event({ stage: "working", operationId: "operation", payload: {} }); return plan("plan"); },
    createStudySession: () => session.promise,
  });
  let run;
  await act(async () => { run = view.result.current.generatePlanWorkflow(input); });
  view.unmount();
  await act(async () => { session.resolve({ id: "late" }); await run; });
  assert.deepEqual(view.calls.cancelled, ["operation"]);
  assert.deepEqual(view.calls.sessions, []);
  assert.equal(view.calls.finished, 0);
});

test("changing the selected view fences session success and failure", async () => {
  for (const fails of [false, true]) {
    const session = deferred(); let current = true;
    const view = fixture({ createStudySession: () => session.promise }, { onPlan: () => () => current });
    let run;
    await act(async () => { run = view.result.current.generatePlanWorkflow(input); });
    current = false;
    const notices = [...view.calls.notices];
    await act(async () => { fails ? session.reject(new Error("late")) : session.resolve({ id: "late" }); await run; });
    assert.deepEqual(view.calls.sessions, []);
    assert.deepEqual(view.calls.notices, notices);
    assert.equal(view.calls.finished, 1);
    view.unmount();
  }
});

test("plan and initial session share the scene captured before generation", async () => {
  const scene = { summary: "original", nested: { name: "room" } };
  const pending = deferred(); let planInput, sessionInput;
  const view = fixture({
    createLearningPlanStream: data => { planInput = data; return pending.promise; },
    createStudySession: async data => { sessionInput = data; return { id: "session" }; },
  }, { resolveSceneProfile: () => scene });
  let run;
  act(() => { run = view.result.current.generatePlanWorkflow(input); });
  scene.summary = "edited"; scene.nested.name = "changed";
  await act(async () => { pending.resolve(plan("new")); await run; });
  assert.deepEqual(planInput.sceneProfile, { summary: "original", nested: { name: "room" } });
  assert.deepEqual(sessionInput.sceneProfile, planInput.sceneProfile);
  assert.equal(sessionInput.planId, "new");
  assert.equal(view.calls.sessions.length, 1);
});

test("document generation carries the parsed revision and bounds stream history", async () => {
  const document = { id: "book", updatedAt: "revision", studyUnits: [{ id: "unit" }] };
  let planInput, sessionInput;
  const view = fixture({
    uploadDocument: async () => ({ id: "book" }),
    processDocumentStream: async (_id, _options, event) => {
      for (let index = 0; index < 90; index++) event({ stage: "page_parsed", payload: { index } });
      event({ stage: "stream_completed", payload: {} });
      return document;
    },
    createLearningPlanStream: async (data, event) => {
      planInput = data;
      for (let index = 0; index < 130; index++) event({ stage: "working", payload: { index } });
      event({ stage: "stream_completed", payload: {} });
      return { ...plan("document-plan"), creationMode: "document" };
    },
    createStudySession: async data => { sessionInput = data; return { id: "session" }; },
  });
  await act(async () => { await view.result.current.generatePlanWorkflow({ mode: "document", file: new File(["pdf"], "book.pdf"), objective: "learn" }); });
  assert.deepEqual(view.calls.documents, [document]);
  assert.equal(planInput.expectedDocumentUpdatedAt, "revision");
  assert.equal(sessionInput.documentId, "book");
  assert.equal(sessionInput.studyUnitId, "unit");
  assert.equal(view.result.current.processStreamEvents.length, 80);
  assert.equal(view.result.current.planStreamEvents.length, 120);
  assert.equal(view.result.current.processStreamStatus, "completed");
  assert.equal(view.result.current.planStreamStatus, "completed");
});


test("upload, parse, plan and session keep one action captured before page replacement", async () => {
  const owner = registerDiagnosticPage("/plan"), parsing = deferred(), contexts = [];
  const document = { id: "doc", studyUnits: [], updatedAt: "2026-09-10T00:00:00Z" };
  const view = fixture({
    uploadDocument: async (_file, options) => { contexts.push(options.diagnostic); return document; },
    processDocumentStream: (_id, options) => { contexts.push(options.diagnostic); return parsing.promise; },
    createLearningPlanStream: async (_goal, _event, options) => { contexts.push(options.diagnostic); return plan("planned"); },
    createStudySession: async (_input, context) => { contexts.push(context); return { id: "session" }; },
  });
  let running;
  await act(async () => { running = view.result.current.generatePlanWorkflow({ mode: "document", file: new File(["private"], "private.pdf"), objective: "private objective" }); });
  assert.equal(contexts.length, 2);
  const replacement = registerDiagnosticPage("/study"); owner.dispose();
  await act(async () => { parsing.resolve(document); await running; });
  assert.equal(contexts.length, 4);
  assert.ok(contexts[0].flow_id);
  assert.ok(contexts.every(context => context === contexts[0]));
  assert.equal(contexts[3].page_view_id, owner.id);
  assert.ok(!JSON.stringify(contexts).includes("private"));
  replacement.dispose();
});

test("supersession cancellation retains old flow and page while the new run gets its own flow", async () => {
  const page = registerDiagnosticPage("/plan"), requests = [], cancellations = [];
  const view = fixture({
    createLearningPlanStream: (_goal, event, options) => {
      const pending = deferred(); requests.push({ ...pending, event, context: options.diagnostic }); return pending.promise;
    },
    cancelStreamRun: async (id, context) => { cancellations.push({ id, context }); },
  });
  let first, second;
  act(() => { first = view.result.current.generatePlanWorkflow(input); });
  act(() => requests[0].event({ stage: "working", operationId: "first-stream", payload: {} }));
  const replacement = registerDiagnosticPage("/study"); page.dispose();
  act(() => { second = view.result.current.generatePlanWorkflow(input); });
  assert.equal(cancellations[0].id, "first-stream");
  assert.equal(cancellations[0].context.flow_id, requests[0].context.flow_id);
  assert.equal(cancellations[0].context.page_view_id, page.id);
  assert.notEqual(cancellations[0].context.action_id, requests[0].context.action_id);
  assert.notEqual(requests[1].context.flow_id, requests[0].context.flow_id);
  assert.equal(requests[1].context.page_view_id, replacement.id);
  await act(async () => { requests[0].resolve(plan("old")); requests[1].resolve(plan("new")); await first; await second; });
  replacement.dispose();
});
