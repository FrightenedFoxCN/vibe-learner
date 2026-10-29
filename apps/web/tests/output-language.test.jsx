import { dom } from "./support/dom.js";
import React from "react";
import assert from "node:assert/strict";
import { after, afterEach, test } from "node:test";
import { act, cleanup, fireEvent, render } from "@testing-library/react";
import { AppRouterContext } from "next/dist/shared/lib/app-router-context.shared-runtime.js";
import { DocumentSetup } from "../components/document-setup.tsx";
import { StudyConsole } from "../components/study-console.tsx";
import { mockPersonas } from "../lib/mock-data.ts";
import { withOutputLanguage } from "../lib/output-language.ts";
import {
  parsePhysicalPdfRanges,
  physicalPageIntent,
} from "../lib/planning-page-scope.ts";
import {
  loadLearningWorkspacePageCache,
  persistLearningWorkspacePageCache,
} from "../lib/learning-workspace-page-cache.ts";
import { sendStudyMessage } from "../lib/api.ts";
import { decodeStudySession } from "../lib/study-session-decode.ts";
import { fullWireSession } from "./support/learning-wire.ts";

afterEach(() => {
  cleanup();
  window.sessionStorage.clear();
});
after(() => dom.window.close());

test("Session read-back accepts legacy absence and valid language while rejecting malformed preferences", () => {
  const wire = fullWireSession();
  assert.equal(decodeStudySession(wire).outputLanguage, undefined);
  assert.equal(
    decodeStudySession({ ...wire, output_language: "fr-CA" }).outputLanguage,
    "fr-CA",
  );
  for (const value of [null, "unknown", "fr\nignore", 42, "fr_XX"]) {
    assert.throws(() => decodeStudySession({ ...wire, output_language: value }));
  }
});

test("explicit language composes with physical page scope; auto keeps unknown intent", () => {
  const scope = physicalPageIntent(parsePhysicalPdfRanges("100–103"));
  const intent = withOutputLanguage(scope, "fr");
  assert.deepEqual(intent.pdfPageRanges, scope.pdfPageRanges);
  assert.deepEqual(intent.outputLanguage, { status: "user_explicit", value: "fr" });
  assert.equal(withOutputLanguage(undefined, "auto"), undefined);
  assert.throws(() => withOutputLanguage(scope, "fr\nignore"));
});

test("Plan Workspace persists the selected language and submits it as its own field", () => {
  const generated = [],
    drafts = [];
  const view = render(
    <AppRouterContext.Provider value={{ push() {}, replace() {}, prefetch() {} }}>
      <DocumentSetup
        personas={[]}
        selectedPersonaId=""
        onSelectPersonaId={() => {}}
        onGenerate={(input) => generated.push(input)}
        onInterruptGeneration={() => {}}
        isBusy={false}
        sceneLibraryItems={[]}
        selectedSceneLibraryId=""
        onSelectSceneLibraryId={() => {}}
        planStreamEvents={[]}
        planStreamStatus="idle"
        processStreamEvents={[]}
        processStreamStatus="idle"
        canInterruptGeneration={false}
        isInterruptingGeneration={false}
        cachedState={{ generationMode: "goal_only", objective: "Read", file: null }}
        onCachedStateChange={(draft) => drafts.push(draft)}
      />
    </AppRouterContext.Provider>,
  );
  fireEvent.change(view.getByRole("combobox", { name: "输出语言", exact: true }), {
    target: { value: "fr" },
  });
  fireEvent.click(view.getByRole("button", { name: "按目标生成", exact: true }));
  assert.equal(generated[0].outputLanguage, "fr");
  assert.equal(generated[0].objective, "Read");
  persistLearningWorkspacePageCache({ planSetup: drafts.at(-1) });
  assert.equal(loadLearningWorkspacePageCache().planSetup.outputLanguage, "fr");
  fireEvent.change(view.getByRole("combobox", { name: "输出语言", exact: true }), {
    target: { value: "custom" },
  });
  assert.ok(view.getByRole("alert"));
  assert.equal(
    view.getByRole("button", { name: "按目标生成", exact: true }).disabled,
    true,
  );
  fireEvent.change(view.getByRole("textbox", { name: "输出语言标签" }), {
    target: { value: "fr-CA" },
  });
  assert.equal(view.queryByRole("alert"), null);
});

test("Study Dialog inherits committed language, sends its override and resets it on Session change", async () => {
  const sent = [];
  const props = {
    isPending: false,
    selectedPlanId: "plan",
    planOptions: [],
    onSelectPlan() {},
    onAsk: (...args) => {
      sent.push(args);
      return true;
    },
    onSubmitQuestionAttempt: () => true,
    onChangeSchedule() {},
    selectedScheduleId: "",
    scheduleOptions: [],
    turns: [],
    session: null,
    persona: mockPersonas[0],
    outputLanguage: "fr",
    outputLanguageScope: "session-1",
  };
  const view = render(<StudyConsole {...props} />);
  const field = view.getByRole("combobox", { name: "输出语言", exact: true });
  assert.equal(field.value, "fr");
  fireEvent.change(field, { target: { value: "de" } });
  await act(async () =>
    fireEvent.click(view.getByRole("button", { name: "发送", exact: true })),
  );
  assert.equal(sent[0][2], "de");
  view.rerender(<StudyConsole {...props} outputLanguageScope="session-2" />);
  assert.equal(field.value, "fr");
});

test("both Study JSON and attachment transports bind language without rewriting the message", async () => {
  const original = globalThis.fetch;
  const requests = [];
  globalThis.fetch = async (_url, init) => {
    requests.push(init);
    return Response.json({ detail: "probe" }, { status: 503 });
  };
  try {
    for (const attachments of [[], [new File(["note"], "note.txt")]]) {
      await assert.rejects(
        sendStudyMessage({
          sessionId: "session",
          clientRequestId: "language-transport",
          expectedSessionRevision: 1,
          message: "引文 remains verbatim",
          outputLanguage: "fr",
          attachments,
        }),
      );
    }
  } finally {
    globalThis.fetch = original;
  }
  const json = JSON.parse(requests[0].body);
  assert.equal(json.output_language, "fr");
  assert.equal(json.message, "引文 remains verbatim");
  assert.equal(requests[1].body.get("output_language"), "fr");
  assert.equal(requests[1].body.get("message"), json.message);
});
