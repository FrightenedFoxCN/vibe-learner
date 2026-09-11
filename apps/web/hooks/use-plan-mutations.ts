"use client";

import { useEffect, useRef, useState } from "react";
import type { DocumentRecord, LearningPlan } from "@vibe-learner/shared";
import { updateDocumentStudyUnitTitle } from "../lib/data/documents";
import {
  answerLearningPlanQuestion, deleteLearningPlan, updateLearningPlanProgress,
  updateLearningPlanTitle,
} from "../lib/data/learning-plans";
import { logWorkspaceError } from "../lib/learning-workspace-telemetry";

export interface PlanMutationPort {
  updateLearningPlanTitle: typeof updateLearningPlanTitle;
  deleteLearningPlan: typeof deleteLearningPlan;
  updateDocumentStudyUnitTitle: typeof updateDocumentStudyUnitTitle;
  updateLearningPlanProgress: typeof updateLearningPlanProgress;
  answerLearningPlanQuestion: typeof answerLearningPlanQuestion;
}
const defaultPort: PlanMutationPort = {
  updateLearningPlanTitle, deleteLearningPlan, updateDocumentStudyUnitTitle,
  updateLearningPlanProgress, answerLearningPlanQuestion,
};
interface PlanMutationOptions {
  plans?: LearningPlan[];
  onPlan: (plan: LearningPlan) => void;
  onDeleted: (id: string) => void;
  onDocumentAndPlans: (payload: { document: DocumentRecord; plans: LearningPlan[] }) => void;
  onNotice: (notice: string) => void;
}

/** Writes retain resource identity; navigation decisions use the latest workspace. */
export function usePlanMutations(options: PlanMutationOptions, port: PlanMutationPort = defaultPort) {
  const current = useRef(options);
  current.current = options;
  const mounted = useRef(false);
  const pending = useRef(new Set<string>());
  const [pendingCount, setPendingCount] = useState(0);
  const feedbackOwner = useRef<object | null>(null);
  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; feedbackOwner.current = null; };
  }, []);

  async function mutate<T>(key: string, request: () => Promise<T>, apply: (result: T) => void,
    success: string, failure: string, event: string): Promise<boolean> {
    if (!mounted.current || pending.current.has(key)) return false;
    const owner = {};
    feedbackOwner.current = owner;
    pending.current.add(key);
    setPendingCount(pending.current.size);
    try {
      const result = await request();
      if (!mounted.current) return false;
      apply(result);
      if (feedbackOwner.current === owner) current.current.onNotice(success);
      return true;
    } catch (error) {
      if (mounted.current && feedbackOwner.current === owner) current.current.onNotice(`${failure}：${String(error)}`);
      logWorkspaceError(event, error);
      return false;
    } finally {
      pending.current.delete(key);
      if (mounted.current) setPendingCount(pending.current.size);
    }
  }

  return {
    isMutating: pendingCount > 0,
    renamePlanTitle: (id: string, title: string) => !id || !title.trim() ? Promise.resolve(false) :
      mutate(`plan:${id}`, () => port.updateLearningPlanTitle(id, title.trim(), current.current.plans?.find(plan => plan.id === id)?.revision),
        plan => current.current.onPlan(plan), "题目已更新。", "更新题目失败", "workflow:plan_title_update:error"),
    removePlan: (id: string) => !id ? Promise.resolve(false) :
      mutate(`plan:${id}`, () => port.deleteLearningPlan(id, current.current.plans?.find(plan => plan.id === id)?.revision), () => current.current.onDeleted(id),
        "计划已删除。", "删除计划失败", "workflow:plan_delete:error"),
    renameStudyUnitTitle: (documentId: string, studyUnitId: string, title: string) =>
      !documentId || !studyUnitId || !title.trim() ? Promise.resolve(false) :
        mutate(`document:${documentId}`, () => port.updateDocumentStudyUnitTitle(documentId, studyUnitId, title.trim()),
          payload => current.current.onDocumentAndPlans(payload), "学习单元已更新。", "更新学习单元失败", "workflow:study_unit_title_update:error"),
    updatePlanProgress: (input: Parameters<PlanMutationPort["updateLearningPlanProgress"]>[0]) =>
      !input.planId || !input.scheduleIds.length || !input.status.trim() ? Promise.resolve(false) :
        mutate(`plan:${input.planId}`, () => port.updateLearningPlanProgress({ ...input, expectedRevision: current.current.plans?.find(plan => plan.id === input.planId)?.revision }),
          plan => current.current.onPlan(plan), "完成度已更新。", "更新完成度失败", "workflow:plan_progress_update:error"),
    answerPlanQuestion: (input: Parameters<PlanMutationPort["answerLearningPlanQuestion"]>[0]) =>
      !input.planId || !input.questionId || !input.answer.trim() ? Promise.resolve(false) :
        mutate(`plan:${input.planId}`, () => port.answerLearningPlanQuestion({ ...input, expectedRevision: current.current.plans?.find(plan => plan.id === input.planId)?.revision }),
          plan => current.current.onPlan(plan), "回答已保存；可生成修订预览后再决定是否应用。", "保存回答失败", "workflow:plan_question_answer:error"),
  };
}
