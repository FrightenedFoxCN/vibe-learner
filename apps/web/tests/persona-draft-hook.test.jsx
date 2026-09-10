import { dom } from "./support/dom.js";
import assert from "node:assert/strict";
import { after, afterEach, test } from "node:test";
import { act, cleanup, renderHook } from "@testing-library/react";
import { usePersonaDraft } from "../hooks/use-persona-draft.ts";
import { EMPTY_PERSONA_DRAFT, draftToCreatePersonaInput, personaToDraft } from "../lib/persona-draft.ts";

afterEach(cleanup);
after(() => dom.window.close());
const profile = id => ({ ...draftToCreatePersonaInput(EMPTY_PERSONA_DRAFT), id, name: id, revision: 1, source: "user" });
function fixture() {
  const personas = [profile("first"), profile("second")], messages = [], changes = [];
  let allow = false;
  const view = renderHook(() => usePersonaDraft({ personas, onSelectionChange: () => changes.push("selection"), onPromptDismiss: () => changes.push("prompt") }, message => { messages.push(message); return allow; }));
  return { ...view, personas, messages, changes, allow: () => { allow = true; } };
}

test("late initial library does not overwrite an edited or explicitly created draft", () => {
  for (const action of ["edit", "new"]) {
    const h = fixture();
    act(() => {
      if (action === "edit") h.result.current.updatePersonaDraft(draft => ({ ...draft, name: "user draft" }));
      else h.result.current.replacePersonaDraft({ ...EMPTY_PERSONA_DRAFT }, true);
      h.result.current.initializePersonaFromLibrary(h.personas[0]);
    });
    assert.equal(h.result.current.selectedPersonaId, "");
    assert.equal(h.result.current.draft.name, action === "edit" ? "user draft" : EMPTY_PERSONA_DRAFT.name);
    h.unmount();
  }
});

test("untouched draft initializes from authoritative library once", () => {
  const h = fixture();
  act(() => h.result.current.initializePersonaFromLibrary(h.personas[0]));
  assert.equal(h.result.current.draft.name, "first");
  assert.equal(h.result.current.isDraftDirty, false);
  act(() => h.result.current.initializePersonaFromLibrary(h.personas[1]));
  assert.equal(h.result.current.selectedPersonaId, "first");
});

test("switching a dirty persona requires confirmation and rejected switch preserves its scope", () => {
  const h = fixture();
  act(() => h.result.current.initializePersonaFromLibrary(h.personas[0]));
  act(() => h.result.current.updatePersonaDraft(draft => ({ ...draft, name: "edited" })));
  const scope = h.result.current.currentPersonaAsyncScope("field");
  act(() => assert.equal(h.result.current.activatePersonaDraft("second"), false));
  assert.deepEqual(h.result.current.currentPersonaAsyncScope("field"), scope);
  assert.equal(h.result.current.draft.name, "edited");
  h.allow();
  act(() => assert.equal(h.result.current.activatePersonaDraft("second"), true));
  assert.equal(h.result.current.draft.name, "second");
  assert.equal(h.result.current.isDraftDirty, false);
  assert.equal(h.result.current.currentPersonaAsyncScope("field").subjectId, "second");
});

test("a saved older snapshot advances the baseline without replacing later edits", () => {
  const h = fixture();
  act(() => h.result.current.initializePersonaFromLibrary(h.personas[0]));
  act(() => h.result.current.updatePersonaDraft(draft => ({ ...draft, name: "later" })));
  act(() => h.result.current.markPersonaDraftSaved(personaToDraft(h.personas[0])));
  assert.equal(h.result.current.draft.name, "later");
  assert.equal(h.result.current.isDraftDirty, true);
  act(() => h.result.current.markPersonaDraftSaved(h.result.current.draft));
  assert.equal(h.result.current.isDraftDirty, false);
});

test("dirty draft guards normal links and beforeunload, and removes listeners on unmount", () => {
  const h = fixture();
  act(() => h.result.current.updatePersonaDraft(draft => ({ ...draft, name: "dirty" })));
  const anchor = document.createElement("a"); anchor.href = "#another-page";
  document.body.append(anchor);
  let prevented = false;
  anchor.addEventListener("click", event => { prevented = event.defaultPrevented; event.preventDefault(); });
  anchor.dispatchEvent(new window.MouseEvent("click", { bubbles: true, cancelable: true, button: 0 }));
  assert.equal(prevented, true);
  assert.equal(h.messages.length, 1);
  anchor.dispatchEvent(new window.MouseEvent("click", { bubbles: true, cancelable: true, button: 0, ctrlKey: true }));
  assert.equal(h.messages.length, 1);
  const before = new window.Event("beforeunload", { cancelable: true }); window.dispatchEvent(before);
  assert.equal(before.defaultPrevented, true);
  h.unmount();
  const after = new window.Event("beforeunload", { cancelable: true }); window.dispatchEvent(after);
  assert.equal(after.defaultPrevented, false);
  anchor.remove();
});
