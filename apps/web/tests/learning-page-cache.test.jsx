import { dom } from "./support/dom.js";
import assert from "node:assert/strict";
import { after, afterEach, test } from "node:test";
import { useState } from "react";
import { cleanup, fireEvent, render } from "@testing-library/react";
import { LearningPageCacheProvider, useLearningPageCache } from "../components/learning-page-cache-provider.tsx";
import { createInitialLearningWorkspaceState } from "../lib/learning-workspace-reducer.ts";

afterEach(() => { cleanup(); window.sessionStorage.clear(); });
after(() => dom.window.close());

function DraftEditor() {
  const { getPageCache, setPageCache } = useLearningPageCache();
  const [draft, setDraft] = useState(() => getPageCache("planSetup") ?? { generationMode: "document", objective: "", file: null });
  const change = (patch) => {
    const next = { ...draft, ...patch };
    setDraft(next);
    setPageCache("planSetup", next);
    setPageCache("selection", { planId: "older-plan", personaId: "chosen-persona", sceneLibraryId: "chosen-scene" });
  };
  return <>
    <input aria-label="Objective" value={draft.objective} onChange={event => change({ objective: event.target.value })} />
    <input aria-label="Textbook" type="file" onChange={event => change({ file: event.target.files[0] })} />
    <output role="status" aria-label="File">{draft.file?.name ?? "no-file"}</output>
    <output aria-label="Selection">{getPageCache("selection")?.planId ?? "none"}</output>
  </>;
}

test("file and text drafts survive leaving and re-entering the learning routes", () => {
  const tree = active => <LearningPageCacheProvider>{active ? <DraftEditor /> : <p>Settings</p>}</LearningPageCacheProvider>;
  const view = render(tree(true));
  fireEvent.change(view.getByLabelText("Objective"), { target: { value: "Keep my objective" } });
  fireEvent.change(view.getByLabelText("Textbook"), { target: { files: [new window.File(["pdf"], "lesson.pdf")] } });
  view.rerender(tree(false));
  view.rerender(tree(true));
  assert.equal(view.getByLabelText("Objective").value, "Keep my objective");
  assert.equal(view.getByRole("status", { name: "File" }).textContent, "lesson.pdf");
  assert.equal(view.getByLabelText("Selection").textContent, "older-plan");
  view.unmount();
  const restored = render(tree(true));
  assert.equal(restored.getByLabelText("Objective").value, "Keep my objective");
  assert.equal(restored.getByRole("status", { name: "File" }).textContent, "no-file");
  assert.equal(restored.getByLabelText("Selection").textContent, "older-plan");
});

test("selected identities seed the reducer before authoritative data is refreshed", () => {
  const state = createInitialLearningWorkspaceState({ initialPersonas: [], initialSelection: { planId: "older-plan", personaId: "chosen-persona" } });
  assert.equal(state.selectedPlanId, "older-plan");
  assert.equal(state.selectedPersonaId, "chosen-persona");
  assert.deepEqual(state.planHistory, []);
  assert.equal(state.studySession, null);
});
