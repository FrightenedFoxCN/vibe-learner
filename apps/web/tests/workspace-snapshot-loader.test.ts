import assert from "node:assert/strict";
import test from "node:test";
import { WorkspaceSnapshotLoader } from "../lib/workspace-snapshot-loader.ts";
import type { WorkspaceSnapshotObserver } from "../lib/workspace-snapshot-loader.ts";

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: Error) => void;
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}

function observer() {
  const events: unknown[] = [];
  const callbacks: WorkspaceSnapshotObserver = {
    started: () => { events.push("started"); },
    loaded: value => { events.push(value); },
    failed: error => { events.push(error); },
    finished: () => { events.push("finished"); },
  };
  return { events, callbacks };
}

function fixture() {
  const documents: ReturnType<typeof deferred<[]>>[] = [];
  const plans: ReturnType<typeof deferred<[]>>[] = [];
  const personas: ReturnType<typeof deferred<[]>>[] = [];
  const loader = new WorkspaceSnapshotLoader({
    listDocuments: () => { const item = deferred<[]>(); documents.push(item); return item.promise; },
    listLearningPlans: () => { const item = deferred<[]>(); plans.push(item); return item.promise; },
    listPersonas: () => { const item = deferred<[]>(); personas.push(item); return item.promise; },
  });
  return { loader, documents, plans, personas };
}

test("refresh supersedes delayed initial load and still initializes Personas", async () => {
  const { loader, documents, plans, personas } = fixture();
  const initial = observer(), refresh = observer();
  const old = loader.load(true, initial.callbacks);
  const latest = loader.load(false, refresh.callbacks);
  assert.equal(personas.length, 2);
  documents[1]!.resolve([]); plans[1]!.resolve([]); personas[1]!.resolve([]);
  await latest;
  assert.deepEqual(refresh.events, ["started", { documents: [], plans: [], personas: [] }, "finished"]);
  documents[0]!.resolve([]); plans[0]!.resolve([]); personas[0]!.resolve([]);
  await old;
  assert.deepEqual(initial.events, ["started"]);
  const subsequent = loader.load(false, observer().callbacks);
  assert.equal(personas.length, 2);
  documents[2]!.resolve([]); plans[2]!.resolve([]);
  await subsequent;
});

test("superseded failures do not replace the latest loading state", async () => {
  const { loader, documents, plans, personas } = fixture();
  const initial = observer(), latest = observer();
  const first = loader.load(true, initial.callbacks);
  const second = loader.load(true, latest.callbacks);
  documents[0]!.reject(new Error("old failure"));
  await first;
  assert.deepEqual(initial.events, ["started"]);
  assert.deepEqual(latest.events, ["started"]);
  documents[1]!.resolve([]); plans[1]!.resolve([]); personas[1]!.resolve([]);
  await second;
  assert.equal(latest.events.at(-1), "finished");
});

test("unmount blocks new queries and old responses after reactivation", async () => {
  const { loader, documents, plans, personas } = fixture();
  const old = observer(), inactive = observer(), next = observer();
  const pending = loader.load(true, old.callbacks);
  loader.deactivate();
  await loader.load(true, inactive.callbacks);
  assert.equal(documents.length, 1);
  assert.deepEqual(inactive.events, []);
  loader.activate();
  const restored = loader.load(true, next.callbacks);
  documents[0]!.resolve([]); plans[0]!.resolve([]); personas[0]!.resolve([]);
  await pending;
  assert.deepEqual(old.events, ["started"]);
  documents[1]!.resolve([]); plans[1]!.resolve([]); personas[1]!.resolve([]);
  await restored;
  assert.equal(next.events.at(-1), "finished");
});

test("failed initialization retries Persona loading and balances current notifications", async () => {
  const { loader, documents, plans, personas } = fixture();
  const failed = observer();
  const error = new Error("unavailable");
  const first = loader.load(true, failed.callbacks);
  documents[0]!.reject(error);
  await first;
  assert.deepEqual(failed.events, ["started", error, "finished"]);
  const retried = loader.load(false, observer().callbacks);
  assert.equal(personas.length, 2);
  documents[1]!.resolve([]); plans[1]!.resolve([]); personas[1]!.resolve([]);
  await retried;
});
