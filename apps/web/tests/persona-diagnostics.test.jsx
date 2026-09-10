import { dom } from "./support/dom.js";
import assert from "node:assert/strict";
import { after, afterEach, test } from "node:test";
import { act, cleanup, renderHook } from "@testing-library/react";
import { usePersonaDraft } from "../hooks/use-persona-draft.ts";
import { usePersonaLibrary } from "../hooks/use-persona-library.ts";
import { usePersonaPersistence } from "../hooks/use-persona-persistence.ts";
import { usePersonaCardGeneration } from "../hooks/use-persona-card-generation.ts";
import { EMPTY_PERSONA_DRAFT } from "../lib/persona-draft.ts";
import { registerDiagnosticPage } from "../lib/diagnostics.ts";

afterEach(cleanup);
after(() => dom.window.close());

test("Persona generation/save/reload share flow; save refresh preserves action across page replacement", async () => {
  const page = registerDiagnosticPage();
  const calls = [];
  let records = [], finishSave;
  const port = {
    listPersonas: async context => { calls.push({ name: "reload", context }); return records; },
    createPersona: (input, context) => { calls.push({ name: "save", context }); return new Promise(resolve => {
      finishSave = () => { const result = { ...input, id: "saved", revision: 1, source: "user" }; records = [result]; resolve(result); };
    }); },
    updatePersona: async () => { throw new Error("unexpected update"); },
    deletePersona: async () => {}, listPersonaCards: async () => [], deletePersonaCard: async () => {}, broadcast() {},
  };
  const view = renderHook(() => {
    const library = usePersonaLibrary(port);
    const editor = usePersonaDraft({ personas: library.personas, onSelectionChange() {}, onPromptDismiss() {} }, () => true);
    const persistence = usePersonaPersistence({ editor, library, onStarted() {}, onPromptDismiss() {} });
    const generation = usePersonaCardGeneration({ draft: editor.draft, updatePersonaDraft: editor.updatePersonaDraft,
      currentPersonaAsyncScope: editor.currentPersonaAsyncScope, beginDiagnosticAction: editor.beginDiagnosticAction },
    async (_input, context) => { calls.push({ name: "generate", context }); return {
      items: [], summary: "Generated", relationship: "Teacher", learnerAddress: "Student", usedModel: "mock", usedWebSearch: false,
    }; });
    return { editor, persistence, generation };
  });
  act(() => {
    view.result.current.editor.replacePersonaDraft({ ...EMPTY_PERSONA_DRAFT, name: "Persona" }, true);
    view.result.current.generation.setCardKeywordInput("teacher");
  });
  await act(async () => { await view.result.current.generation.handleGenerateCards("keywords"); });
  act(() => view.result.current.generation.applyGeneratedCardsToDraft());
  let saving;
  act(() => { saving = view.result.current.persistence.handleCreatePersona(); });
  const replacement = registerDiagnosticPage();
  page.dispose();
  await act(async () => { finishSave(); await saving; });
  await act(async () => { await view.result.current.persistence.handleReloadSelectedPersona(); });
  assert.deepEqual(calls.map(call => call.name), ["generate", "save", "reload", "reload"]);
  assert.equal(new Set(calls.map(call => call.context.flow_id)).size, 1);
  assert.notEqual(calls[0].context.action_id, calls[1].context.action_id);
  assert.deepEqual(calls[1].context, calls[2].context);
  assert.notEqual(calls[2].context.action_id, calls[3].context.action_id);
  assert.equal(calls[2].context.page_view_id, page.id);
  assert.equal(calls[3].context.page_view_id, replacement.id);
  act(() => view.result.current.editor.activatePersonaDraft(""));
  assert.notEqual(view.result.current.editor.beginDiagnosticAction().flow_id, calls[0].context.flow_id);
  replacement.dispose();
});
