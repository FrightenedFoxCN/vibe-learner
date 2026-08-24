import assert from "node:assert/strict";
import test from "node:test";

import {
  applyAsyncResult,
  AsyncResultFence,
  decideAsyncResult,
  StudyAsyncViewFence,
  type AsyncResultScope,
} from "../lib/async-result-fence.ts";

const BASE_SCOPE: AsyncResultScope = {
  subjectId: "persona-1",
  draftRevision: 4,
  fieldTarget: "slot:2",
};

test("an async result applies only to its exact operation and captured scope", () => {
  const fence = new AsyncResultFence();
  const ticket = fence.begin(BASE_SCOPE, "operation-1");

  assert.equal(fence.decide(ticket, BASE_SCOPE, "operation-1"), "apply");
  assert.equal(fence.settle(ticket), true);
  assert.equal(fence.currentOperationId(), null);
});

test("cross-operation and superseded results fail closed", () => {
  const fence = new AsyncResultFence();
  const first = fence.begin(BASE_SCOPE, "operation-1");
  const second = fence.begin(BASE_SCOPE, "operation-2");

  assert.equal(fence.decide(first, BASE_SCOPE, "operation-1"), "operation_superseded");
  assert.equal(fence.decide(second, BASE_SCOPE, "operation-forged"), "operation_mismatch");
  assert.equal(fence.settle(first), false);
  assert.equal(fence.currentOperationId(), "operation-2");
});

test("a newer attempt for the same server operation supersedes the older request", () => {
  const fence = new AsyncResultFence();
  const originalPost = fence.begin(BASE_SCOPE, "study-chat-operation-1");
  const recoveryQuery = fence.begin(BASE_SCOPE, "study-chat-operation-1");

  assert.equal(
    fence.decide(originalPost, BASE_SCOPE, "study-chat-operation-1"),
    "operation_superseded",
  );
  assert.equal(
    fence.decide(recoveryQuery, BASE_SCOPE, "study-chat-operation-1"),
    "apply",
  );
  assert.equal(fence.settle(originalPost), false);
  assert.equal(fence.settle(recoveryQuery), true);
});

test("subject, draft revision, and field target changes reject a late result", () => {
  const fence = new AsyncResultFence();
  const ticket = fence.begin(BASE_SCOPE, "operation-1");

  assert.equal(
    fence.decide(ticket, { ...BASE_SCOPE, subjectId: "persona-2" }),
    "subject_changed",
  );
  assert.equal(
    fence.decide(ticket, { ...BASE_SCOPE, draftRevision: 5 }),
    "draft_changed",
  );
  assert.equal(
    fence.decide(ticket, { ...BASE_SCOPE, fieldTarget: "slot:3" }),
    "field_target_changed",
  );
});

test("invalid scopes and inactive tickets cannot be treated as current", () => {
  assert.throws(
    () => decideAsyncResult(
      { ...BASE_SCOPE, operationId: "operation-1", attemptSequence: 1 },
      { ...BASE_SCOPE, draftRevision: Number.NaN },
      { operationId: "operation-1", attemptSequence: 1 },
    ),
    /async_result_draft_revision_invalid/,
  );

  assert.throws(
    () => new AsyncResultFence().begin(BASE_SCOPE, "   "),
    /async_result_operation_required/,
  );

  const fence = new AsyncResultFence();
  const ticket = fence.begin(BASE_SCOPE, "operation-1");
  fence.invalidate();
  assert.equal(fence.decide(ticket, BASE_SCOPE), "operation_superseded");
});

test("Study rejects a response after the active Session or Plan changes", () => {
  const fence = new AsyncResultFence();
  const scope: AsyncResultScope = {
    subjectId: "study-session-1",
    draftRevision: 8,
    fieldTarget: "study-session:study-session-1:unit:unit-1",
  };
  const ticket = fence.begin(scope, "study-chat-operation-1");

  assert.equal(
    fence.decide(ticket, {
      subjectId: "study-session-2",
      draftRevision: 9,
      fieldTarget: "study-session:study-session-2:unit:unit-2",
    }),
    "subject_changed",
  );
});

test("Persona rejects an assist result after the user edits the draft", () => {
  const fence = new AsyncResultFence();
  const scope: AsyncResultScope = {
    subjectId: "persona-1",
    draftRevision: 12,
    fieldTarget: "persona-slot:2",
  };
  const ticket = fence.begin(scope);

  assert.equal(
    fence.decide(ticket, { ...scope, draftRevision: 13 }),
    "draft_changed",
  );
});

test("Scene rejects a rewrite result after switching layer, object, or field", () => {
  const fence = new AsyncResultFence();
  const scope: AsyncResultScope = {
    subjectId: "scene-library:scene-1",
    draftRevision: 3,
    fieldTarget: "layer-1:summary",
  };
  const ticket = fence.begin(scope);

  assert.equal(
    fence.decide(ticket, { ...scope, fieldTarget: "object-4:description" }),
    "field_target_changed",
  );
});

test("Study view keeps a newer projection for the same Session and Unit", () => {
  const view = new StudyAsyncViewFence({
    initialPlanId: "plan-1",
    session: { id: "session-1", studyUnitId: "unit-1", revision: 5 },
  });
  const ticket = view.begin("session-1", "study-operation-1");

  assert.equal(
    view.activateSession({ id: "session-1", studyUnitId: "unit-1", revision: 6 }),
    false,
  );
  assert.equal(view.session?.revision, 6);
  assert.equal(view.decide(ticket, "plan-1"), "apply");

  const nextRequest = {
    sessionId: view.session?.id,
    expectedSessionRevision: view.session?.revision,
  };
  assert.deepEqual(nextRequest, {
    sessionId: "session-1",
    expectedSessionRevision: 6,
  });
});

test("a deferred Study refresh cannot restore a Session after switching Plan", async () => {
  const view = new StudyAsyncViewFence({
    initialPlanId: "plan-1",
    session: { id: "session-1", studyUnitId: "unit-1", revision: 5 },
  });
  const ticket = view.begin("session-1", "refresh-operation-1");
  const deferred = createDeferred<{ id: string; studyUnitId: string; revision: number }>();
  let appliedSessionId = "";
  const refresh = deferred.promise.then((session) => {
    if (view.decide(ticket, "plan-2") !== "apply") return;
    view.activateSession(session);
    appliedSessionId = session.id;
  });

  view.transition("study-plan:plan-2", true);
  deferred.resolve({ id: "session-1", studyUnitId: "unit-1", revision: 6 });
  await refresh;

  assert.equal(appliedSessionId, "");
  assert.equal(view.session, null);
});

test("deferred Persona and Scene imports do not apply after edit or subject switch", async () => {
  const personaFence = new AsyncResultFence();
  let personaScope: AsyncResultScope = {
    subjectId: "persona-1",
    draftRevision: 1,
    fieldTarget: "persona-config-import",
  };
  const personaTicket = personaFence.begin(personaScope, "persona-import-1");
  const personaFile = createDeferred<string>();
  let personaDraft = "edited persona";
  const personaImport = personaFile.promise.then((value) => applyAsyncResult({
    fence: personaFence,
    ticket: personaTicket,
    currentScope: personaScope,
    value,
    apply: (next) => { personaDraft = next; },
  }));
  personaScope = { ...personaScope, draftRevision: 2 };
  personaFile.resolve("stale imported persona");
  assert.equal(await personaImport, "draft_changed");
  assert.equal(personaDraft, "edited persona");

  const sceneFence = new AsyncResultFence();
  let sceneScope: AsyncResultScope = {
    subjectId: "scene-1",
    draftRevision: 3,
    fieldTarget: "scene-file-import",
  };
  const sceneTicket = sceneFence.begin(sceneScope, "scene-import-1");
  const sceneFile = createDeferred<string>();
  let sceneDraft = "current scene";
  const sceneImport = sceneFile.promise.then((value) => applyAsyncResult({
    fence: sceneFence,
    ticket: sceneTicket,
    currentScope: sceneScope,
    value,
    apply: (next) => { sceneDraft = next; },
  }));
  sceneScope = { ...sceneScope, subjectId: "scene-2", draftRevision: 4 };
  sceneFile.resolve("stale imported scene");
  assert.equal(await sceneImport, "subject_changed");
  assert.equal(sceneDraft, "current scene");
});

function createDeferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((resolver) => {
    resolve = resolver;
  });
  return { promise, resolve };
}
