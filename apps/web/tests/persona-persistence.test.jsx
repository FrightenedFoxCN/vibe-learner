import { dom } from "./support/dom.js";
import assert from "node:assert/strict";
import { after, afterEach, test } from "node:test";
import { act, cleanup, renderHook } from "@testing-library/react";
import { usePersonaDraft } from "../hooks/use-persona-draft.ts";
import { usePersonaLibrary } from "../hooks/use-persona-library.ts";
import { usePersonaPersistence } from "../hooks/use-persona-persistence.ts";
import { EMPTY_PERSONA_DRAFT, draftToCreatePersonaInput } from "../lib/persona-draft.ts";

afterEach(cleanup);
after(() => dom.window.close());
const profile = (id, name = id, revision = 1) => ({ ...draftToCreatePersonaInput(EMPTY_PERSONA_DRAFT), id, name, revision, source: "user" });
async function fixture(isNew = false) {
  let records = [profile("existing")], nextRead;
  const requests = [];
  const mutate = (kind, id, input) => new Promise((resolve, reject) => requests.push({ kind, id, input, reject, resolve: result => {
    if (kind === "delete") records = records.filter(item => item.id !== id);
    else records = [result, ...records.filter(item => item.id !== result.id)];
    resolve(result);
  } }));
  const port = { listPersonas: () => nextRead ? nextRead() : Promise.resolve(records), listPersonaCards: async () => [],
    createPersona: input => mutate("create", "", input), updatePersona: (id, input) => mutate("update", id, input),
    deletePersona: (id, revision) => mutate("delete", id, revision), deletePersonaCard: async () => {}, broadcast() {} };
  const view = renderHook(() => {
    const library = usePersonaLibrary(port);
    const editor = usePersonaDraft({ personas: library.personas, onSelectionChange() {}, onPromptDismiss() {} }, () => true);
    const persistence = usePersonaPersistence({ editor, library, onStarted() {}, onPromptDismiss() {} }, () => true);
    return { editor, library, persistence };
  });
  await act(async () => { await view.result.current.library.listPersonas(); });
  act(() => {
    if (isNew) view.result.current.editor.replacePersonaDraft({ ...EMPTY_PERSONA_DRAFT, name: "new" }, true);
    else view.result.current.editor.initializePersonaFromLibrary(records[0]);
  });
  return { ...view, requests, setRead: value => { nextRead = value; } };
}

test("create binds only continuing edits to the same new draft", async () => {
  const h = await fixture(true); let run;
  act(() => { run = h.result.current.persistence.handleCreatePersona(); });
  act(() => h.result.current.editor.updatePersonaDraft(draft => ({ ...draft, name: "later edit" })));
  await act(async () => { h.requests[0].resolve(profile("created", "new")); await run; });
  assert.equal(h.result.current.editor.selectedPersonaId, "created");
  assert.equal(h.result.current.editor.draft.name, "later edit");
  assert.equal(h.result.current.editor.isDraftDirty, true);
});

test("late create cannot bind another new draft with an empty selected id", async () => {
  const h = await fixture(true); let run;
  act(() => { run = h.result.current.persistence.handleCreatePersona(); });
  act(() => h.result.current.editor.replacePersonaDraft({ ...EMPTY_PERSONA_DRAFT, name: "different new draft" }, true));
  await act(async () => { h.requests[0].resolve(profile("created", "new")); await run; });
  assert.equal(h.result.current.editor.selectedPersonaId, "");
  assert.equal(h.result.current.editor.draft.name, "different new draft");
  assert.equal(h.result.current.editor.isDraftDirty, false);
  assert.ok(h.result.current.library.personas.some(item => item.id === "created"));
});

test("update preserves in-flight edits and sends the selected committed revision", async () => {
  const h = await fixture(); let run;
  act(() => { run = h.result.current.persistence.handleUpdatePersona(); });
  assert.equal(h.requests[0].input.expectedRevision, 1);
  act(() => h.result.current.editor.updatePersonaDraft(draft => ({ ...draft, name: "later" })));
  await act(async () => { h.requests[0].resolve(profile("existing", "existing", 2)); await run; });
  assert.equal(h.result.current.editor.draft.name, "later");
  assert.equal(h.result.current.editor.isDraftDirty, true);
  assert.equal(h.result.current.library.personas[0].revision, 2);
});

test("repeated save while pending never starts a second write", async () => {
  const h = await fixture(); let run;
  act(() => { run = h.result.current.persistence.handleUpdatePersona(); });
  await act(async () => { await h.result.current.persistence.handleUpdatePersona(); });
  assert.equal(h.requests.length, 1);
  assert.equal(h.result.current.persistence.savingPersona, true);
  await act(async () => { h.requests[0].reject(new Error("offline")); await run; });
  assert.equal(h.result.current.persistence.savingPersona, false);
  assert.ok(h.result.current.persistence.saveError);
});

test("reload cannot overwrite edits made while its read was pending", async () => {
  const h = await fixture(); let resolveRead, run;
  h.setRead(() => new Promise(resolve => { resolveRead = resolve; }));
  act(() => { run = h.result.current.persistence.handleReloadSelectedPersona(); });
  act(() => h.result.current.editor.updatePersonaDraft(draft => ({ ...draft, name: "keep edit" })));
  await act(async () => { resolveRead([profile("existing", "server", 3)]); await run; });
  assert.equal(h.result.current.editor.draft.name, "keep edit");
  assert.match(h.result.current.persistence.personaLibraryMessage, /编辑已保留/);
});

test("delete preserves a later selected draft and keeps edits to the removed persona as a new draft", async () => {
  for (const change of ["switch", "edit"]) {
    const h = await fixture(); let run;
    act(() => { run = h.result.current.persistence.handleDeletePersona(h.result.current.library.personas[0]); });
    act(() => {
      if (change === "switch") { h.result.current.editor.selectPersonaDraft(""); h.result.current.editor.replacePersonaDraft({ ...EMPTY_PERSONA_DRAFT, name: "other" }, true); }
      else h.result.current.editor.updatePersonaDraft(draft => ({ ...draft, name: "keep changed" }));
    });
    assert.equal(h.requests[0].input, 1);
    await act(async () => { h.requests[0].resolve(); await run; });
    assert.equal(h.result.current.editor.selectedPersonaId, "");
    assert.equal(h.result.current.editor.draft.name, change === "switch" ? "other" : "keep changed");
    assert.equal(h.result.current.editor.isDraftDirty, change === "edit");
    h.unmount();
  }
});

test("unmounted create does not bind or project into the abandoned draft", async () => {
  const h = await fixture(true); let run;
  act(() => { run = h.result.current.persistence.handleCreatePersona(); });
  h.unmount();
  await act(async () => { h.requests[0].resolve(profile("created")); await run; });
  assert.equal(h.result.current.editor.selectedPersonaId, "");
  assert.equal(h.result.current.editor.draft.name, "new");
});
