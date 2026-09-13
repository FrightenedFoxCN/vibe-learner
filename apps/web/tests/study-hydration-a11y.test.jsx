import assert from "node:assert/strict";
import { test } from "node:test";
import { renderToString } from "react-dom/server";
import { JSDOM } from "jsdom";
import { StudyConsole } from "../components/study-console.tsx";
import { mockPersonas } from "../lib/mock-data.ts";
import { attempt, commitAttempt, session as questionSession } from "./support/study-attempts.ts";

test("server render exposes every persisted Assistant Turn and committed option label", () => {
  const session = questionSession();
  session.turns[0].assistantReply = "First persisted explanation";
  session.turns.push(
    {
      ...structuredClone(session.turns[0]),
      id: "turn-2",
      sequence: 2,
      assistantReply: "Second persisted explanation",
      interactiveQuestion: null,
      createdAt: "2026-08-13T00:01:00Z",
    },
    {
      ...structuredClone(session.turns[0]),
      id: "turn-3",
      sequence: 3,
      assistantReply: "Third persisted explanation",
      interactiveQuestion: null,
      createdAt: "2026-08-13T00:02:00Z",
    }
  );
  commitAttempt(session, attempt());

  const html = renderToString(
    <StudyConsole
      isPending={false}
      selectedPlanId=""
      planOptions={[]}
      onSelectPlan={() => {}}
      onAsk={() => true}
      onSubmitQuestionAttempt={() => true}
      onChangeSchedule={() => {}}
      selectedScheduleId=""
      scheduleOptions={[]}
      turns={session.turns}
      session={null}
      persona={mockPersonas[0]}
      disabled={false}
    />
  );
  const document = new JSDOM(html).window.document;

  for (const text of [
    "First persisted explanation",
    "Second persisted explanation",
    "Third persisted explanation",
  ]) {
    assert.match(document.body.textContent ?? "", new RegExp(text));
  }
  const radioLabels = [...document.querySelectorAll('input[type="radio"]')]
    .map((input) => input.closest("label")?.textContent?.trim());
  assert.deepEqual(radioLabels, ["A. A", "B. B"]);
  assert.match(document.body.textContent ?? "", /回答正确 · 已记录/);
});
