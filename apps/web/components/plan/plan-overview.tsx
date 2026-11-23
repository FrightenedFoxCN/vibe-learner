"use client";

import { useEffect, useState } from "react";
import type { DocumentRecord, LearningPlan, SceneProfile } from "@vibe-learner/shared";
import { formatTimestamp } from "../../lib/format";
import { formatOcrStatus } from "../../lib/ocr-status";

import { PlanQuestions, PlanSummary, PlanTodayTasks } from "./plan-overview-summary";
import { PlanSchedule } from "./plan-overview-schedule";
import styles from "./plan-overview.module.css";

export interface PlanOverviewProps {
  plan: LearningPlan | null;
  document: DocumentRecord | null;
  documentTitle: string;
  personaName: string;
  planPositionLabel: string;
  sceneProfile?: SceneProfile | null;
  isBusy: boolean;
  onRenamePlan: (planId: string, courseTitle: string) => Promise<boolean>;
  onUpdatePlanProgress: (input: {
    planId: string;
    scheduleIds: string[];
    status: string;
    note?: string;
  }) => Promise<boolean>;
  onAnswerPlanningQuestion: (input: {
    planId: string;
    questionId: string;
    answer: string;
  }) => Promise<boolean>;
  onStartStudyFromPlan: (input: {
    studyUnitId: string;
    scheduleId: string;
    scheduleChapterId?: string;
    chapter: string;
    page: number;
    scheduleIds: string[];
  }) => void | Promise<void>;
}

export function PlanOverview({
  plan,
  document,
  documentTitle,
  personaName,
  planPositionLabel,
  sceneProfile,
  isBusy,
  onRenamePlan,
  onUpdatePlanProgress,
  onAnswerPlanningQuestion,
  onStartStudyFromPlan,
}: PlanOverviewProps) {
  const [isEditingTitle, setIsEditingTitle] = useState(false);
  const [titleDraft, setTitleDraft] = useState("");
  const [planningAnswerDrafts, setPlanningAnswerDrafts] = useState<
    Record<string, string>
  >({});
  const [reviewDrafts, setReviewDrafts] = useState<Record<string, string>>({});
  const [showScheduleDetails, setShowScheduleDetails] = useState(false);
  const [expandedScheduleItems, setExpandedScheduleItems] = useState<
    Record<string, boolean>
  >({});

  useEffect(() => {
    setTitleDraft(plan?.courseTitle ?? "");
    setIsEditingTitle(false);
    setShowScheduleDetails(false);
    setExpandedScheduleItems({});
    setReviewDrafts({});
  }, [plan?.courseTitle, plan?.id]);

  useEffect(() => {
    const nextDrafts = Object.fromEntries(
      (plan?.planningQuestions ?? []).map((item) => [item.id, item.answer ?? ""]),
    );
    setPlanningAnswerDrafts(nextDrafts);
  }, [plan?.id, plan?.planningQuestions]);

  const activeCourseTitle = plan
    ? resolveCourseTitle(
        plan.courseTitle,
        plan.creationMode === "goal_only" ? "目标导向学习计划" : documentTitle,
      )
    : "这里会显示当前计划。";

  const handleSaveTitle = async () => {
    if (!plan) {
      return;
    }
    const didSave = await onRenamePlan(plan.id, titleDraft);
    if (didSave) {
      setIsEditingTitle(false);
    }
  };

  const metaItems = plan
    ? [
        `教材 ${plan.creationMode === "goal_only" ? "仅学习目标" : documentTitle}`,
        plan.creationMode === "document" && document
          ? `OCR ${formatOcrStatus(document.ocrStatus)}`
          : "",
        `人格 ${personaName}`,
        sceneProfile || plan.sceneProfileSummary
          ? `场景 ${sceneProfile?.title || sceneProfile?.sceneName || plan.sceneProfileSummary}`
          : "",
        `创建于 ${formatTimestamp(plan.createdAt, { style: "short" })}`,
      ].filter(Boolean)
    : [];

  return (
    <section className={styles.wrap}>
      <div className={styles.headerRow}>
        <div className={styles.headerMeta}>
          <span className={styles.sectionLabel}>计划</span>
        </div>
        {plan ? <span className={styles.badge}>{planPositionLabel}</span> : null}
      </div>

      {plan ? (
        <>
          <PlanSummary
            plan={plan}
            activeCourseTitle={activeCourseTitle}
            isBusy={isBusy}
            isEditingTitle={isEditingTitle}
            titleDraft={titleDraft}
            setIsEditingTitle={setIsEditingTitle}
            setTitleDraft={setTitleDraft}
            handleSaveTitle={handleSaveTitle}
            metaItems={metaItems}
          />
          <PlanTodayTasks tasks={plan.todayTasks} />
          <PlanQuestions
            plan={plan}
            isBusy={isBusy}
            planningAnswerDrafts={planningAnswerDrafts}
            onChangeAnswer={(questionId, answer) =>
              setPlanningAnswerDrafts((current) => ({
                ...current,
                [questionId]: answer,
              }))
            }
            onAnswerPlanningQuestion={onAnswerPlanningQuestion}
          />
          <PlanSchedule
            plan={plan}
            isBusy={isBusy}
            showScheduleDetails={showScheduleDetails}
            onToggleScheduleDetails={() =>
              setShowScheduleDetails((current) => !current)
            }
            expandedScheduleItems={expandedScheduleItems}
            onToggleScheduleItem={(id) =>
              setExpandedScheduleItems((current) => ({
                ...current,
                [id]: !current[id],
              }))
            }
            reviewDrafts={reviewDrafts}
            onChangeReview={(id, note) =>
              setReviewDrafts((current) => ({ ...current, [id]: note }))
            }
            onUpdatePlanProgress={onUpdatePlanProgress}
            onStartStudyFromPlan={onStartStudyFromPlan}
          />
        </>
      ) : (
        <div className={styles.emptyState}>
          <h2 className={styles.title}>暂无学习计划</h2>
          <p className={styles.overview}>生成计划后会显示在这里。</p>
        </div>
      )}
    </section>
  );
}

function resolveCourseTitle(courseTitle: string, documentTitle: string) {
  const trimmed = courseTitle?.trim();
  if (trimmed) {
    return trimmed;
  }
  return documentTitle || "未命名计划";
}
