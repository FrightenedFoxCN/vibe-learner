import { dom } from "./support/dom.js";
import assert from "node:assert/strict";
import { after, afterEach, test } from "node:test";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { StudyConsole } from "../components/study-console.tsx";
import { mockPersonas } from "../lib/mock-data.ts";
import { attempt, commitAttempt, session as questionSession } from "./support/study-attempts.ts";

afterEach(cleanup);
after(() => dom.window.close());

function renderCommittedQuestion(onContinueAfterQuestion) {
  const session = questionSession();
  commitAttempt(session, attempt());
  return render(
    <StudyConsole
      isPending={false}
      selectedPlanId=""
      planOptions={[]}
      onSelectPlan={() => {}}
      onAsk={() => true}
      onSubmitQuestionAttempt={() => true}
      onContinueAfterQuestion={onContinueAfterQuestion}
      onChangeSchedule={() => {}}
      selectedScheduleId=""
      scheduleOptions={[]}
      turns={session.turns}
      session={null}
      persona={mockPersonas[0]}
      disabled={false}
    />
  );
}

test("committed grading requires an explicit cost warning before model continuation", () => {
  const continued = [];
  renderCommittedQuestion((turnId) => {
    continued.push(turnId);
    return true;
  });

  assert.ok(screen.getByText("回答正确 · 已记录"));
  assert.equal(continued.length, 0);

  fireEvent.click(screen.getByRole("button", { name: "生成答题讲解" }));
  assert.match(
    screen.getByText(/继续会调用学习模型/).textContent,
    /调用学习模型.*可能产生费用.*取消不会影响评分结果/
  );
  assert.equal(continued.length, 0);

  fireEvent.click(screen.getByRole("button", { name: "取消" }));
  assert.equal(screen.queryByText(/继续会调用学习模型/), null);
  assert.equal(continued.length, 0);

  fireEvent.click(screen.getByRole("button", { name: "生成答题讲解" }));
  fireEvent.click(screen.getByRole("button", { name: "继续生成（调用模型）" }));
  assert.deepEqual(continued, ["turn-1"]);
});
