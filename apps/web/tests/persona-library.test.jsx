import { dom } from "./support/dom.js";
import assert from "node:assert/strict";
import { after, afterEach, test } from "node:test";
import { act, cleanup, renderHook } from "@testing-library/react";
import { usePersonaLibrary } from "../hooks/use-persona-library.ts";

afterEach(cleanup);
after(() => dom.window.close());
function deferred() {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}
const persona = (id, revision = 1) => ({ id, name: id, revision });
function fixture(overrides = {}) {
  const reads = [], broadcasts = [], writes = [];
  const port = {
    listPersonas: () => { const pending = deferred(); reads.push(pending); return pending.promise; },
    listPersonaCards: async () => [], createPersona: async () => persona("created"),
    updatePersona: async (id, input) => { writes.push(input); return persona(id, input.expectedRevision + 1); },
    deletePersona: async (id, revision) => { writes.push({ id, revision }); }, deletePersonaCard: async () => {},
    broadcast: () => broadcasts.push("changed"), ...overrides,
  };
  return { ...renderHook(() => usePersonaLibrary(port)), reads, broadcasts, writes };
}

test("late list reconciles mutations committed after the read started", async () => {
  const h = fixture(); let read;
  act(() => { read = h.result.current.listPersonas(); });
  await act(async () => { await h.result.current.updatePersona("updated", { expectedRevision: 2 }); await h.result.current.deletePersona("deleted", 1); });
  await act(async () => { h.reads[0].resolve([persona("updated", 2), persona("deleted"), persona("other")]); await read; });
  assert.deepEqual(h.result.current.personas.map(item => [item.id, item.revision]), [["updated", 3], ["other", 1]]);
  assert.equal(h.writes[0].expectedRevision, 2);
  assert.deepEqual(h.writes[1], { id: "deleted", revision: 1 });
  assert.equal(h.broadcasts.length, 2);
});

test("newer authoritative refresh can supersede old local projections", async () => {
  const h = fixture();
  await act(async () => { await h.result.current.updatePersona("changed", { expectedRevision: 1 }); });
  let read;
  act(() => { read = h.result.current.listPersonas(); });
  await act(async () => { h.reads[0].resolve([persona("changed", 5)]); await read; });
  assert.equal(h.result.current.personas[0].revision, 5);
});

test("superseded list response returns the current snapshot rather than an obsolete replacement", async () => {
  const h = fixture(); let old, current;
  act(() => { old = h.result.current.listPersonas(); current = h.result.current.listPersonas(); });
  await act(async () => { h.reads[1].resolve([persona("current")]); await current; });
  let returned;
  await act(async () => { h.reads[0].resolve([persona("old")]); returned = await old; });
  assert.deepEqual(returned.map(item => item.id), ["current"]);
  assert.deepEqual(h.result.current.personas.map(item => item.id), ["current"]);
});

test("failed mutation does not broadcast or change records; duplicate pending writes never reach API", async () => {
  const pending = deferred(); let calls = 0;
  const h = fixture({ updatePersona: () => { calls++; return pending.promise; } }); let run;
  act(() => { run = h.result.current.updatePersona("same", { expectedRevision: 1 }); });
  await assert.rejects(h.result.current.updatePersona("same", { expectedRevision: 1 }), /write_in_progress/);
  const rejected = assert.rejects(run, /offline/);
  await act(async () => { pending.reject(new Error("offline")); await rejected; });
  assert.equal(calls, 1);
  assert.deepEqual(h.result.current.personas, []);
  assert.equal(h.broadcasts.length, 0);
});

test("committed create after unmount still broadcasts but does not update the abandoned view", async () => {
  const created = deferred(), h = fixture({ createPersona: () => created.promise }); let run;
  act(() => { run = h.result.current.createPersona({}); });
  h.unmount();
  await act(async () => { created.resolve(persona("created")); await run; });
  assert.deepEqual(h.result.current.personas, []);
  assert.equal(h.broadcasts.length, 1);
});
