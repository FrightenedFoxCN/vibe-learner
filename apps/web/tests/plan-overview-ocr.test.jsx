import { dom } from "./support/dom.js";
import assert from "node:assert/strict";
import { after, afterEach, test } from "node:test";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { PlanOverview } from "../components/plan-overview.tsx";
import { mockPlan } from "../lib/mock-data.ts";

afterEach(cleanup);
after(() => dom.window.close());

const callbacks = {
  onRenamePlan: async () => true,
  onUpdatePlanProgress: async () => true,
  onAnswerPlanningQuestion: async () => true,
  onStartStudyFromPlan: () => {},
};

function documentWithOcrStatus(ocrStatus) {
  return {
    id: "doc-1",
    filename: "mechanics.pdf",
    title: "力学教材",
    status: "processed",
    pageCount: 18,
    usedOcr: ocrStatus !== "not_required",
    ocrStatus,
    sections: [],
    studyUnits: [],
    warnings: [],
    createdAt: "2026-09-13T00:00:00+00:00",
    updatedAt: "2026-09-13T00:00:00+00:00",
  };
}

test("Plan Workspace renders distinct OCR outcomes with the shared status vocabulary", () => {
  const props = {
    plan: mockPlan,
    document: documentWithOcrStatus("not_required"),
    documentTitle: "力学教材",
    personaName: "Aurora",
    planPositionLabel: "当前计划",
    isBusy: false,
    ...callbacks,
  };
  const view = render(<PlanOverview {...props} />);

  assert.ok(screen.getByText("OCR 不需要 OCR"));

  view.rerender(
    <PlanOverview {...props} document={documentWithOcrStatus("partial")} />
  );
  assert.ok(screen.getByText("OCR 部分页面 OCR 降级"));
  assert.equal(screen.queryByText("OCR 不需要 OCR"), null);
});

test("Plan Workspace exposes each course as an independently actionable and reviewable atom", async () => {
  const plan = structuredClone(mockPlan);
  plan.todayTasks = ["先完成定义回忆。", "再核对例题步骤。"];
  plan.schedule[0].durationMinutes = 45;
  plan.schedule.push({
    ...structuredClone(plan.schedule[0]),
    id: "schedule-2",
    title: "牛顿定律复习",
    activityType: "review",
    status: "completed",
    scheduleChapters: plan.schedule[0].scheduleChapters.map((chapter, index) => ({
      ...chapter,
      id: `schedule-2:chapter-${index + 1}`,
    })),
  });
  plan.progressSummary = {
    totalScheduleCount: 2,
    completedScheduleCount: 1,
    inProgressScheduleCount: 0,
    pendingScheduleCount: 1,
    blockedScheduleCount: 0,
    completionPercent: 50,
  };
  plan.progressEvents = [{
    id: "review-2",
    actor: "user",
    source: "ui",
    scheduleIds: ["schedule-2"],
    status: "completed",
    note: "第二课已能独立复述。",
    createdAt: "2026-09-13T10:00:00+08:00",
  }];
  const progressCalls = [];

  render(
    <PlanOverview
      plan={plan}
      document={documentWithOcrStatus("not_required")}
      documentTitle="力学教材"
      personaName="Aurora"
      planPositionLabel="当前计划"
      isBusy={false}
      {...callbacks}
      onUpdatePlanProgress={async (input) => {
        progressCalls.push(input);
        return true;
      }}
    />
  );

  assert.ok(screen.getByText("今日行动"));
  assert.ok(screen.getByText("先完成定义回忆。"));
  assert.ok(screen.getByText("再核对例题步骤。"));

  const first = document.querySelector('[data-plan-schedule="schedule-1"]');
  const second = document.querySelector('[data-plan-schedule="schedule-2"]');
  assert.ok(first);
  assert.ok(second);
  assert.ok(within(first).getByText("第 1 课"));
  assert.ok(within(first).getByText("时长 45 分钟"));
  assert.ok(within(first).getByText("范围 p.12–18"));
  assert.ok(within(first).getByText("本次任务"));
  assert.ok(within(second).getByText("第 2 课"));
  assert.ok(within(second).getByText("第二课已能独立复述。"));

  fireEvent.click(within(first).getByRole("button", { name: "完成第 1 课：力学导论 精读" }));
  fireEvent.change(within(first).getByLabelText("第 1 课复盘"), {
    target: { value: "第一课需要补做受力图。" },
  });
  fireEvent.click(within(first).getByRole("button", { name: "保存本课复盘" }));

  await waitFor(() => assert.equal(progressCalls.length, 2));
  assert.deepEqual(progressCalls[0], {
    planId: plan.id,
    scheduleIds: ["schedule-1"],
    status: "completed",
  });
  assert.deepEqual(progressCalls[1], {
    planId: plan.id,
    scheduleIds: ["schedule-1"],
    status: "planned",
    note: "第一课需要补做受力图。",
  });
});
