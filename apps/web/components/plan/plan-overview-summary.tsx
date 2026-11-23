import type { LearningPlan } from "@vibe-learner/shared";
import type { PlanOverviewProps } from "./plan-overview";
import styles from "./plan-overview.module.css";

interface PlanSummaryProps {
  plan: LearningPlan;
  activeCourseTitle: string;
  isBusy: boolean;
  isEditingTitle: boolean;
  titleDraft: string;
  setIsEditingTitle: (value: boolean) => void;
  setTitleDraft: (value: string) => void;
  handleSaveTitle: () => Promise<void>;
  metaItems: string[];
}

export function PlanSummary({
  plan,
  activeCourseTitle,
  isBusy,
  isEditingTitle,
  titleDraft,
  setIsEditingTitle,
  setTitleDraft,
  handleSaveTitle,
  metaItems,
}: PlanSummaryProps) {
  return (
    <>
      <div className={styles.titleBlock}>
        {isEditingTitle ? (
          <>
            <input
              value={titleDraft}
              onChange={(event) => setTitleDraft(event.target.value)}
              className={styles.titleInput}
              placeholder="输入计划题目"
              disabled={isBusy}
            />
            <div className={styles.titleActions}>
              <button
                type="button"
                className={styles.primaryButton}
                disabled={
                  isBusy ||
                  !titleDraft.trim() ||
                  titleDraft.trim() === plan.courseTitle.trim()
                }
                onClick={() => {
                  void handleSaveTitle();
                }}
              >
                保存题目
              </button>
              <button
                type="button"
                className={styles.ghostButton}
                disabled={isBusy}
                onClick={() => {
                  setTitleDraft(plan.courseTitle);
                  setIsEditingTitle(false);
                }}
              >
                取消
              </button>
            </div>
          </>
        ) : (
          <div className={styles.titleRow}>
            <h2 className={styles.title}>{activeCourseTitle}</h2>
            <button
              type="button"
              className={styles.ghostButton}
              disabled={isBusy}
              onClick={() => setIsEditingTitle(true)}
            >
              编辑题目
            </button>
          </div>
        )}
      </div>

      <p className={styles.overview}>{plan.overview}</p>

      <div className={styles.metaStrip}>
        {metaItems.map((item) => (
          <span key={item} className={styles.metaChip}>
            {item}
          </span>
        ))}
      </div>
    </>
  );
}

export function PlanTodayTasks({ tasks }: { tasks: LearningPlan["todayTasks"] }) {
  return (
    <div className={styles.todayTaskCard}>
      <div className={styles.sectionHeadMeta}>
        <span className={styles.sectionLabel}>今日行动</span>
        <span className={styles.count}>{tasks.length} 项</span>
      </div>
      <ol className={styles.todayTaskList}>
        {tasks.map((task, index) => (
          <li key={`${index}:${task}`} className={styles.todayTask}>
            {task}
          </li>
        ))}
      </ol>
    </div>
  );
}

interface PlanQuestionsProps {
  plan: LearningPlan;
  isBusy: boolean;
  planningAnswerDrafts: Record<string, string>;
  onChangeAnswer: (questionId: string, answer: string) => void;
  onAnswerPlanningQuestion: PlanOverviewProps["onAnswerPlanningQuestion"];
}

export function PlanQuestions({
  plan,
  isBusy,
  planningAnswerDrafts,
  onChangeAnswer,
  onAnswerPlanningQuestion,
}: PlanQuestionsProps) {
  if (!plan.planningQuestions.length) return null;
  const pendingCount = plan.planningQuestions.filter(
    (item) => item.status !== "answered",
  ).length;
  return (
    <div className={styles.questionCard}>
      <div className={styles.sectionHead}>
        <div className={styles.sectionHeadMeta}>
          <span className={styles.sectionLabel}>补充信息</span>
          <span className={styles.count}>{pendingCount} 条待答</span>
        </div>
      </div>
      <div className={styles.questionList}>
        {plan.planningQuestions.map((item) => (
          <div key={item.id} className={styles.questionItem}>
            <div className={styles.questionHeader}>
              <strong className={styles.questionTitle}>{item.question}</strong>
              <span
                className={styles.statusBadge}
                data-status={item.status === "answered" ? "completed" : "planned"}
              >
                {item.status === "answered" ? "已回答" : "待回答"}
              </span>
            </div>
            {item.reason ? (
              <span className={styles.questionReason}>备注：{item.reason}</span>
            ) : null}
            <textarea
              value={planningAnswerDrafts[item.id] ?? ""}
              onChange={(event) => onChangeAnswer(item.id, event.target.value)}
              className={styles.focusTextarea}
              placeholder="输入回答"
              disabled={isBusy}
            />
            <div className={styles.titleActions}>
              <button
                type="button"
                className={styles.primaryButton}
                disabled={isBusy || !(planningAnswerDrafts[item.id] ?? "").trim()}
                onClick={() => {
                  void onAnswerPlanningQuestion({
                    planId: plan.id,
                    questionId: item.id,
                    answer: planningAnswerDrafts[item.id] ?? "",
                  });
                }}
              >
                保存回答
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
