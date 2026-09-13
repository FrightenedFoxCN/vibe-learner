import { dom } from "./support/dom.js";
import assert from "node:assert/strict";
import { after, afterEach, test } from "node:test";
import { cleanup, render, screen } from "@testing-library/react";
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
