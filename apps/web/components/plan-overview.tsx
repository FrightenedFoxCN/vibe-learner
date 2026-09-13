"use client";

import type { CSSProperties } from "react";
import { useEffect, useState } from "react";
import type {
  DocumentRecord,
  LearningPlan,
  SceneProfile,
  StudyScheduleItem,
  StudyUnit,
} from "@vibe-learner/shared";
import { formatOcrStatus } from "../lib/ocr-status";

interface PlanOverviewProps {
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
  const [planningAnswerDrafts, setPlanningAnswerDrafts] = useState<Record<string, string>>({});
  const [reviewDrafts, setReviewDrafts] = useState<Record<string, string>>({});
  const [showScheduleDetails, setShowScheduleDetails] = useState(false);
  const [expandedScheduleItems, setExpandedScheduleItems] = useState<Record<string, boolean>>({});

  useEffect(() => {
    setTitleDraft(plan?.courseTitle ?? "");
    setIsEditingTitle(false);
    setShowScheduleDetails(false);
    setExpandedScheduleItems({});
    setReviewDrafts({});
  }, [plan?.courseTitle, plan?.id]);

  useEffect(() => {
    const nextDrafts = Object.fromEntries(
      (plan?.planningQuestions ?? []).map((item) => [item.id, item.answer ?? ""])
    );
    setPlanningAnswerDrafts(nextDrafts);
  }, [plan?.id, plan?.planningQuestions]);

  const activeCourseTitle = plan
    ? resolveCourseTitle(
        plan.courseTitle,
        plan.creationMode === "goal_only" ? "目标导向学习计划" : documentTitle
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

  const pendingPlanningQuestions = (plan?.planningQuestions ?? []).filter(
    (item) => item.status !== "answered"
  );
  const visibleScheduleItems = showScheduleDetails
    ? (plan?.schedule ?? [])
    : (plan?.schedule ?? []).slice(0, 4);
  const hasCollapsedScheduleItems = (plan?.schedule.length ?? 0) > visibleScheduleItems.length;
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
        `创建于 ${formatDate(plan.createdAt)}`,
      ].filter(Boolean)
    : [];

  return (
    <section style={styles.wrap}>
      <div style={styles.headerRow}>
        <div style={styles.headerMeta}>
          <span style={styles.sectionLabel}>计划</span>
        </div>
        {plan ? <span style={styles.badge}>{planPositionLabel}</span> : null}
      </div>

      {plan ? (
        <>
          <div style={styles.titleBlock}>
            {isEditingTitle ? (
              <>
                <input
                  value={titleDraft}
                  onChange={(event) => setTitleDraft(event.target.value)}
                  style={styles.titleInput}
                  placeholder="输入计划题目"
                  disabled={isBusy}
                />
                <div style={styles.titleActions}>
                  <button
                    type="button"
                    style={{
                      ...styles.primaryButton,
                      ...((isBusy || !titleDraft.trim() || titleDraft.trim() === plan.courseTitle.trim())
                        ? styles.buttonDisabled
                        : {}),
                    }}
                    disabled={isBusy || !titleDraft.trim() || titleDraft.trim() === plan.courseTitle.trim()}
                    onClick={() => { void handleSaveTitle(); }}
                  >
                    保存题目
                  </button>
                  <button
                    type="button"
                    style={styles.ghostButton}
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
              <div style={styles.titleRow}>
                <h2 style={styles.title}>{activeCourseTitle}</h2>
                <button
                  type="button"
                  style={styles.ghostButton}
                  disabled={isBusy}
                  onClick={() => setIsEditingTitle(true)}
                >
                  编辑题目
                </button>
              </div>
            )}
          </div>

          <p style={styles.overview}>{plan.overview}</p>

          <div style={styles.metaStrip}>
            {metaItems.map((item) => (
              <span key={item} style={styles.metaChip}>{item}</span>
            ))}
          </div>

          <div style={styles.todayTaskCard}>
            <div style={styles.sectionHeadMeta}>
              <span style={styles.sectionLabel}>今日行动</span>
              <span style={styles.count}>{plan.todayTasks.length} 项</span>
            </div>
            <ol style={styles.todayTaskList}>
              {plan.todayTasks.map((task, index) => (
                <li key={`${index}:${task}`} style={styles.todayTask}>{task}</li>
              ))}
            </ol>
          </div>

          {plan.planningQuestions.length ? (
            <div style={styles.questionCard}>
              <div style={styles.sectionHead}>
                <div style={styles.sectionHeadMeta}>
                  <span style={styles.sectionLabel}>补充信息</span>
                  <span style={styles.count}>{pendingPlanningQuestions.length} 条待答</span>
                </div>
              </div>
              <div style={styles.questionList}>
                {plan.planningQuestions.map((item) => (
                  <div key={item.id} style={styles.questionItem}>
                    <div style={styles.questionHeader}>
                      <strong style={styles.questionTitle}>{item.question}</strong>
                      <span style={scheduleStatusStyle(item.status === "answered" ? "completed" : "planned")}>
                        {item.status === "answered" ? "已回答" : "待回答"}
                      </span>
                    </div>
                    {item.reason ? <span style={styles.questionReason}>备注：{item.reason}</span> : null}
                    <textarea
                      value={planningAnswerDrafts[item.id] ?? ""}
                      onChange={(event) =>
                        setPlanningAnswerDrafts((current) => ({
                          ...current,
                          [item.id]: event.target.value,
                        }))
                      }
                      style={styles.focusTextarea}
                      placeholder="输入回答"
                      disabled={isBusy}
                    />
                    <div style={styles.titleActions}>
                      <button
                        type="button"
                        style={{
                          ...styles.primaryButton,
                          ...((isBusy || !(planningAnswerDrafts[item.id] ?? "").trim()) ? styles.buttonDisabled : {}),
                        }}
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
          ) : null}

          <div style={styles.progressCard}>
            <div style={styles.progressHead}>
              <div style={styles.sectionHeadMeta}>
                <span style={styles.sectionLabel}>推进</span>
                <span style={styles.count}>
                  {plan.progressSummary.completedScheduleCount}/{plan.progressSummary.totalScheduleCount}
                </span>
              </div>
              <span style={styles.progressPercent}>{plan.progressSummary.completionPercent}%</span>
            </div>
            <div style={styles.progressBarTrack}>
              <div
                style={{
                  ...styles.progressBarFill,
                  width: `${Math.max(0, Math.min(100, plan.progressSummary.completionPercent))}%`,
                }}
              />
            </div>
            <div style={styles.progressStats}>
              <span style={styles.progressStat}>进行中 {plan.progressSummary.inProgressScheduleCount}</span>
              <span style={styles.progressStat}>待处理 {plan.progressSummary.pendingScheduleCount}</span>
              <span style={styles.progressStat}>阻塞 {plan.progressSummary.blockedScheduleCount}</span>
            </div>

            {plan.schedule.length ? (
              <div style={styles.scheduleList}>
                <p style={styles.startNotice}>
                  点击“开始”会创建或打开对应学习会话，并调用模型准备该 Study Unit；这会产生模型用量。
                </p>
                {visibleScheduleItems.map((item, index) => (
                  <div key={item.id} style={styles.scheduleItem} data-plan-schedule={item.id}>
                    <div style={styles.scheduleHeader}>
                      <div style={styles.scheduleTitleBlock}>
                        <span style={styles.scheduleIndex}>第 {index + 1} 课</span>
                        <span style={styles.scheduleTitle}>{item.title}</span>
                      </div>
                      <div style={styles.scheduleHeaderActions}>
                        <span style={scheduleStatusStyle(item.status)}>{formatScheduleStatus(item.status)}</span>
                        {item.scheduleChapters.length ? (
                          <button
                            type="button"
                            style={styles.inlineButton}
                            disabled={isBusy}
                            aria-expanded={expandedScheduleItems[item.id] ? "true" : "false"}
                            aria-label={`${expandedScheduleItems[item.id] ? "收起" : "展开"}第 ${index + 1} 课章节`}
                            onClick={() =>
                              setExpandedScheduleItems((current) => ({
                                ...current,
                                [item.id]: !current[item.id],
                              }))
                            }
                          >
                            {expandedScheduleItems[item.id]
                              ? `收起章节 · ${item.scheduleChapters.length}`
                              : `展开章节 · ${item.scheduleChapters.length}`}
                          </button>
                        ) : null}
                        <button
                          type="button"
                          style={styles.ghostButton}
                          disabled={isBusy || item.status === "in_progress"}
                          aria-label={`开始第 ${index + 1} 课：${item.title}`}
                          onClick={() => {
                            const studyUnit = resolveStudyUnitById(plan, item.unitId);
                            if (!studyUnit) {
                              return;
                            }
                            const firstScheduleChapter = item.scheduleChapters[0];
                            void onStartStudyFromPlan({
                              studyUnitId: item.unitId,
                              scheduleId: item.id,
                              scheduleChapterId: firstScheduleChapter?.id,
                              chapter: firstScheduleChapter?.title || item.title,
                              page: firstScheduleChapter?.anchorPageStart || studyUnit.pageStart,
                              scheduleIds: [item.id],
                            });
                          }}
                        >
                          开始
                        </button>
                        <button
                          type="button"
                          style={styles.primaryButton}
                          disabled={isBusy || item.status === "completed"}
                          aria-label={`完成第 ${index + 1} 课：${item.title}`}
                          onClick={() => {
                            void onUpdatePlanProgress({
                              planId: plan.id,
                              scheduleIds: [item.id],
                              status: "completed",
                            });
                          }}
                        >
                          完成
                        </button>
                        <button
                          type="button"
                          style={styles.ghostButton}
                          disabled={isBusy || item.status === "planned"}
                          aria-label={`重置第 ${index + 1} 课：${item.title}`}
                          onClick={() => {
                            void onUpdatePlanProgress({
                              planId: plan.id,
                              scheduleIds: [item.id],
                              status: "planned",
                            });
                          }}
                        >
                          重置
                        </button>
                      </div>
                    </div>
                    <div style={styles.scheduleMeta}>
                      <span style={styles.scheduleMetaItem}>
                        时长 {item.durationMinutes ? `${item.durationMinutes} 分钟` : "未记录"}
                      </span>
                      <span style={styles.scheduleMetaItem}>范围 {formatScheduleScope(item)}</span>
                      <span style={styles.scheduleMetaItem}>方式 {formatActivityType(item.activityType)}</span>
                    </div>
                    <div style={styles.scheduleTaskBlock}>
                      <span style={styles.scheduleTaskLabel}>本次任务</span>
                      <p style={styles.scheduleFocus}>{item.focus}</p>
                    </div>
                    {item.coverageMode && item.coverageMode !== "complete" && item.workloadRationale ? (
                      <p style={styles.scheduleFocus}>
                        {item.coverageMode === "overview" ? "导览说明" : "选读说明"}：
                        {item.workloadRationale}
                      </p>
                    ) : null}
                    {item.scheduleChapters.length && expandedScheduleItems[item.id] ? (
                      <div style={styles.subsectionList}>
                        {item.scheduleChapters.map((chapter) => (
                          <div key={chapter.id} style={styles.subsectionTag}>
                            <span style={styles.subsectionName}>{chapter.title}</span>
                            <span style={styles.subsectionPage}>
                              p.{chapter.anchorPageStart}-{chapter.anchorPageEnd}
                            </span>
                          </div>
                        ))}
                      </div>
                    ) : null}
                    <details style={styles.reviewDetails}>
                      <summary style={styles.reviewSummary}>
                        复盘与进度记录 · {reviewEventsForSchedule(plan, item.id).length}
                      </summary>
                      <div style={styles.reviewBody}>
                        <label style={styles.reviewLabel}>
                          <span>第 {index + 1} 课复盘</span>
                          <textarea
                            value={reviewDrafts[item.id] ?? ""}
                            onChange={(event) =>
                              setReviewDrafts((current) => ({
                                ...current,
                                [item.id]: event.target.value,
                              }))
                            }
                            style={styles.reviewTextarea}
                            placeholder="记录掌握情况、疑问或下次要补回的内容"
                            disabled={isBusy}
                          />
                        </label>
                        <button
                          type="button"
                          style={styles.ghostButton}
                          disabled={isBusy || !(reviewDrafts[item.id] ?? "").trim()}
                          onClick={async () => {
                            const didSave = await onUpdatePlanProgress({
                              planId: plan.id,
                              scheduleIds: [item.id],
                              status: item.status,
                              note: reviewDrafts[item.id] ?? "",
                            });
                            if (didSave) {
                              setReviewDrafts((current) => ({ ...current, [item.id]: "" }));
                            }
                          }}
                        >
                          保存本课复盘
                        </button>
                        {reviewEventsForSchedule(plan, item.id).length ? (
                          <ol style={styles.reviewList}>
                            {reviewEventsForSchedule(plan, item.id).map((event) => (
                              <li key={event.id} style={styles.reviewEntry}>
                                <span>{event.note}</span>
                                <span style={styles.reviewMeta}>
                                  {formatDate(event.createdAt)} · {formatScheduleStatus(event.status)}
                                </span>
                              </li>
                            ))}
                          </ol>
                        ) : (
                          <p style={styles.reviewEmpty}>尚无复盘记录。</p>
                        )}
                      </div>
                    </details>
                  </div>
                ))}
                {hasCollapsedScheduleItems ? (
                  <button
                    type="button"
                    style={styles.scheduleToggle}
                    onClick={() => setShowScheduleDetails((current) => !current)}
                  >
                    {showScheduleDetails
                      ? "收起额外排期"
                      : `展开后面 ${plan.schedule.length - visibleScheduleItems.length} 项`}
                  </button>
                ) : null}
              </div>
            ) : null}
          </div>
        </>
      ) : (
        <div style={styles.emptyState}>
          <h2 style={styles.title}>暂无学习计划</h2>
          <p style={styles.overview}>生成计划后会显示在这里。</p>
        </div>
      )}
    </section>
  );
}

const styles: Record<string, CSSProperties> = {
  wrap: {
    display: "grid",
    gap: 14,
  },
  headerRow: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 10,
    paddingBottom: 10,
    borderBottom: "1px solid color-mix(in srgb, var(--border) 76%, white)",
  },
  headerMeta: {
    display: "flex",
    alignItems: "center",
  },
  titleBlock: {
    paddingTop: 4,
    display: "grid",
    gap: 8,
  },
  titleRow: {
    display: "flex",
    alignItems: "flex-start",
    justifyContent: "space-between",
    gap: 12,
  },
  titleActions: {
    display: "flex",
    flexWrap: "wrap",
    gap: 8,
  },
  title: {
    margin: 0,
    fontSize: "clamp(1.32rem, 1.95vw, 1.72rem)",
    lineHeight: 1.18,
    fontWeight: 700,
    color: "var(--ink)",
    letterSpacing: "-0.02em",
  },
  titleInput: {
    width: "100%",
    minHeight: 42,
    border: "1px solid color-mix(in srgb, var(--border-strong) 82%, white)",
    padding: "8px 10px",
    background: "color-mix(in srgb, white 74%, var(--surface))",
    color: "var(--ink)",
    fontSize: 15,
    fontWeight: 600,
  },
  badge: {
    minHeight: 20,
    padding: "0 6px",
    border: "none",
    background: "color-mix(in srgb, white 70%, var(--surface))",
    fontSize: 10,
    color: "var(--ink-2)",
    whiteSpace: "nowrap",
    display: "inline-flex",
    alignItems: "center",
  },
  overview: {
    margin: 0,
    color: "var(--ink-2)",
    fontSize: 15,
    lineHeight: 1.6,
    maxWidth: "72ch",
  },
  metaStrip: {
    display: "flex",
    flexWrap: "wrap",
    alignItems: "center",
    gap: 14,
  },
  metaChip: {
    minHeight: "auto",
    padding: 0,
    border: "none",
    background: "transparent",
    color: "var(--muted)",
    fontSize: 11,
    display: "inline-flex",
    alignItems: "center",
  },
  todayTaskCard: {
    display: "grid",
    gap: 8,
    padding: "12px 14px",
    border: "1px solid color-mix(in srgb, var(--border) 72%, white)",
    background: "color-mix(in srgb, white 84%, var(--surface))",
  },
  todayTaskList: {
    display: "grid",
    gap: 6,
    margin: 0,
    paddingLeft: 22,
  },
  todayTask: {
    color: "var(--ink-2)",
    fontSize: 13,
    lineHeight: 1.6,
  },
  primaryButton: {
    border: "none",
    minHeight: 34,
    padding: "0 16px",
    background: "var(--accent)",
    color: "white",
    fontWeight: 600,
    cursor: "pointer",
    fontSize: 12,
  },
  ghostButton: {
    minHeight: 34,
    border: "none",
    padding: "0 12px",
    background: "color-mix(in srgb, white 70%, var(--surface))",
    color: "var(--ink-2)",
    fontSize: 12,
    cursor: "pointer",
  },
  inlineButton: {
    minHeight: 30,
    width: "fit-content",
    border: "none",
    padding: "0 10px",
    background: "color-mix(in srgb, white 70%, var(--surface))",
    color: "var(--ink-2)",
    fontSize: 11,
    cursor: "pointer",
  },
  buttonDisabled: {
    opacity: 0.45,
    cursor: "not-allowed",
  },
  progressCard: {
    display: "grid",
    gap: 12,
    padding: 18,
    border: "1px solid color-mix(in srgb, var(--border) 72%, white)",
    background: "color-mix(in srgb, white 84%, var(--surface))",
  },
  progressHead: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 12,
  },
  sectionHead: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 8,
  },
  sectionHeadMeta: {
    display: "flex",
    alignItems: "center",
    gap: 8,
  },
  sectionLabel: {
    fontSize: 10,
    fontWeight: 700,
    textTransform: "uppercase",
    letterSpacing: "0.12em",
    color: "var(--muted)",
  },
  count: {
    fontSize: 10,
    color: "var(--muted)",
  },
  progressPercent: {
    fontSize: 22,
    fontWeight: 700,
    color: "var(--accent)",
  },
  progressBarTrack: {
    height: 8,
    background: "color-mix(in srgb, var(--accent-soft) 35%, white)",
    overflow: "hidden",
  },
  progressBarFill: {
    height: "100%",
    background: "var(--accent)",
  },
  progressStats: {
    display: "flex",
    flexWrap: "wrap",
    gap: 6,
  },
  progressStat: {
    padding: "4px 8px",
    border: "none",
    background: "color-mix(in srgb, white 70%, var(--surface))",
    fontSize: 11,
    color: "var(--muted)",
  },
  scheduleList: {
    display: "grid",
    gap: 0,
    borderTop: "1px solid color-mix(in srgb, var(--border) 72%, white)",
  },
  startNotice: {
    margin: 0,
    paddingTop: 12,
    color: "var(--muted)",
    fontSize: 13,
    lineHeight: 1.55,
  },
  scheduleItem: {
    display: "grid",
    gap: 6,
    padding: "12px 0",
    borderBottom: "1px solid color-mix(in srgb, var(--border) 72%, white)",
  },
  scheduleHeader: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 10,
    flexWrap: "wrap",
  },
  scheduleHeaderActions: {
    display: "flex",
    alignItems: "center",
    justifyContent: "flex-end",
    gap: 6,
    flexWrap: "wrap",
  },
  scheduleTitleBlock: {
    display: "flex",
    alignItems: "baseline",
    gap: 8,
    minWidth: 0,
  },
  scheduleIndex: {
    color: "var(--accent)",
    fontSize: 11,
    fontWeight: 700,
    whiteSpace: "nowrap",
  },
  scheduleToggle: {
    minHeight: 42,
    border: "none",
    borderBottom: "1px solid color-mix(in srgb, var(--border) 72%, white)",
    padding: "0",
    background: "transparent",
    color: "var(--muted)",
    fontSize: 12,
    textAlign: "left",
    cursor: "pointer",
  },
  scheduleTitle: {
    fontSize: 14,
    fontWeight: 600,
    color: "var(--ink)",
  },
  scheduleMeta: {
    display: "flex",
    flexWrap: "wrap",
    gap: 6,
  },
  scheduleMetaItem: {
    padding: "3px 7px",
    background: "color-mix(in srgb, white 70%, var(--surface))",
    color: "var(--muted)",
    fontSize: 11,
  },
  scheduleTaskBlock: {
    display: "grid",
    gridTemplateColumns: "64px minmax(0, 1fr)",
    gap: 8,
    alignItems: "start",
  },
  scheduleTaskLabel: {
    paddingTop: 2,
    color: "var(--muted)",
    fontSize: 11,
    fontWeight: 600,
  },
  scheduleFocus: {
    margin: 0,
    fontSize: 13,
    lineHeight: 1.6,
    color: "var(--ink-2)",
    whiteSpace: "pre-wrap",
    overflowWrap: "anywhere",
    userSelect: "text",
  },
  questionCard: {
    display: "grid",
    gap: 10,
    padding: 18,
    border: "1px solid color-mix(in srgb, var(--border) 72%, white)",
    background: "color-mix(in srgb, white 84%, var(--surface))",
  },
  questionList: {
    display: "grid",
    gap: 0,
  },
  questionItem: {
    display: "grid",
    gap: 8,
    padding: "12px 0",
    borderBottom: "1px solid color-mix(in srgb, var(--border) 68%, white)",
    background: "transparent",
  },
  questionHeader: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 8,
    flexWrap: "wrap",
  },
  questionTitle: {
    fontSize: 14,
    color: "var(--ink)",
  },
  questionReason: {
    fontSize: 13,
    lineHeight: 1.6,
    color: "var(--muted)",
  },
  section: {
    paddingTop: 18,
    borderTop: "1px solid var(--border)",
    display: "grid",
    gap: 12,
  },
  sectionActions: {
    display: "flex",
    flexWrap: "wrap",
    gap: 8,
  },
  focusEditor: {
    display: "grid",
    gap: 10,
  },
  focusTextarea: {
    width: "100%",
    minHeight: 112,
    border: "1px solid color-mix(in srgb, var(--border-strong) 82%, white)",
    padding: "10px 12px",
    background: "color-mix(in srgb, white 74%, var(--surface))",
    color: "var(--ink)",
    fontSize: 14,
    lineHeight: 1.6,
    resize: "vertical",
  },
  subsectionList: {
    display: "grid",
    gap: 6,
    paddingTop: 2,
    paddingLeft: 14,
    borderLeft: "1px solid color-mix(in srgb, var(--border) 62%, white)",
  },
  subsectionTag: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 12,
    minHeight: 32,
    padding: "0 10px",
    border: "none",
    background: "color-mix(in srgb, white 72%, var(--surface))",
    color: "var(--ink-2)",
    textDecoration: "none",
  },
  subsectionName: {
    minWidth: 0,
    fontSize: 13,
    lineHeight: 1.5,
    color: "var(--ink)",
  },
  subsectionPage: {
    fontSize: 10,
    color: "var(--muted)",
    whiteSpace: "nowrap",
    flexShrink: 0,
  },
  reviewDetails: {
    marginTop: 4,
    borderTop: "1px dashed color-mix(in srgb, var(--border) 72%, white)",
    paddingTop: 8,
  },
  reviewSummary: {
    width: "fit-content",
    cursor: "pointer",
    color: "var(--muted)",
    fontSize: 12,
    fontWeight: 600,
  },
  reviewBody: {
    display: "grid",
    justifyItems: "start",
    gap: 8,
    marginTop: 10,
  },
  reviewLabel: {
    display: "grid",
    gap: 5,
    width: "100%",
    color: "var(--ink-2)",
    fontSize: 12,
    fontWeight: 600,
  },
  reviewTextarea: {
    width: "100%",
    minHeight: 72,
    boxSizing: "border-box",
    border: "1px solid var(--border)",
    padding: "8px 10px",
    background: "white",
    color: "var(--ink)",
    fontSize: 13,
    lineHeight: 1.6,
    resize: "vertical",
  },
  reviewList: {
    display: "grid",
    gap: 8,
    width: "100%",
    margin: 0,
    paddingLeft: 20,
  },
  reviewEntry: {
    display: "grid",
    gap: 2,
    color: "var(--ink-2)",
    fontSize: 12,
    lineHeight: 1.55,
  },
  reviewMeta: {
    color: "var(--muted)",
    fontSize: 10,
  },
  reviewEmpty: {
    margin: 0,
    color: "var(--muted)",
    fontSize: 12,
  },
  emptyState: {
    paddingTop: 4,
  },
};

function resolveCourseTitle(courseTitle: string, documentTitle: string) {
  const trimmed = courseTitle?.trim();
  if (trimmed) {
    return trimmed;
  }
  return documentTitle || "未命名计划";
}

function formatDate(value: string) {
  if (!value) return "未知时间";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatScheduleStatus(status: string) {
  switch (status) {
    case "completed":
      return "已完成";
    case "in_progress":
      return "进行中";
    case "blocked":
      return "阻塞";
    case "skipped":
      return "已跳过";
    default:
      return "待开始";
  }
}

function formatActivityType(activityType: string) {
  if (activityType === "review") return "复习";
  if (activityType === "learn") return "学习";
  return activityType || "未记录";
}

function formatScheduleScope(item: StudyScheduleItem) {
  const ranges = item.scheduleChapters.flatMap((chapter) =>
    chapter.contentSlices.length
      ? chapter.contentSlices.map((slice) => [slice.pageStart, slice.pageEnd] as const)
      : [[chapter.anchorPageStart, chapter.anchorPageEnd] as const]
  );
  if (!ranges.length) return "未记录";
  const ordered = ranges
    .filter(([start, end]) => start > 0 && end >= start)
    .sort(([left], [right]) => left - right);
  const merged: Array<[number, number]> = [];
  ordered.forEach(([start, end]) => {
    const previous = merged.at(-1);
    if (previous && start <= previous[1] + 1) {
      previous[1] = Math.max(previous[1], end);
    } else {
      merged.push([start, end]);
    }
  });
  return merged.length
    ? merged.map(([start, end]) => start === end ? `p.${start}` : `p.${start}–${end}`).join("、")
    : "未记录";
}

function reviewEventsForSchedule(plan: LearningPlan, scheduleId: string) {
  return plan.progressEvents
    .filter((event) => event.scheduleIds.includes(scheduleId) && event.note.trim())
    .slice(-3)
    .reverse();
}

function scheduleStatusStyle(status: string): CSSProperties {
  if (status === "completed") {
    return {
      padding: "3px 8px",
      border: "none",
      background: "color-mix(in srgb, var(--accent-soft) 72%, white)",
      color: "var(--accent)",
      fontSize: 10,
    };
  }
  if (status === "in_progress") {
    return {
      padding: "3px 8px",
      border: "none",
      background: "rgba(201, 122, 0, 0.10)",
      color: "#8a5700",
      fontSize: 10,
    };
  }
  if (status === "blocked") {
    return {
      padding: "3px 8px",
      border: "none",
      background: "rgba(180, 35, 24, 0.10)",
      color: "var(--danger, #b42318)",
      fontSize: 10,
    };
  }
  return {
    padding: "3px 8px",
    border: "none",
    background: "color-mix(in srgb, white 72%, var(--surface))",
    color: "var(--muted)",
    fontSize: 10,
  };
}

function resolveStudyUnitById(plan: LearningPlan, unitId: string): StudyUnit | null {
  return plan.studyUnits.find((unit) => unit.id === unitId) ?? null;
}
