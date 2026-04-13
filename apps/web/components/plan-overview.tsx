"use client";

import Link from "next/link";
import type { CSSProperties } from "react";
import { useEffect, useState } from "react";
import type { DocumentRecord, DocumentSection, LearningPlan, SceneProfile, StudyUnit } from "@vibe-learner/shared";

interface PlanOverviewProps {
  plan: LearningPlan | null;
  document: DocumentRecord | null;
  documentTitle: string;
  personaName: string;
  planPositionLabel: string;
  sceneProfile?: SceneProfile | null;
  hasSession: boolean;
  isBusy: boolean;
  onCreateSession: () => void;
  onRenamePlan: (planId: string, courseTitle: string) => Promise<boolean>;
  onUpdateStudyChapters: (planId: string, studyChapters: string[]) => Promise<boolean>;
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
}

export function PlanOverview({
  plan,
  document,
  documentTitle,
  personaName,
  planPositionLabel,
  sceneProfile,
  hasSession,
  isBusy,
  onCreateSession,
  onRenamePlan,
  onUpdateStudyChapters,
  onUpdatePlanProgress,
  onAnswerPlanningQuestion,
}: PlanOverviewProps) {
  const [isEditingTitle, setIsEditingTitle] = useState(false);
  const [isEditingStudyChapters, setIsEditingStudyChapters] = useState(false);
  const [titleDraft, setTitleDraft] = useState("");
  const [studyChaptersDraft, setStudyChaptersDraft] = useState("");
  const [planningAnswerDrafts, setPlanningAnswerDrafts] = useState<Record<string, string>>({});

  useEffect(() => {
    setTitleDraft(plan?.courseTitle ?? "");
    setIsEditingTitle(false);
    setStudyChaptersDraft((plan?.studyChapters ?? []).join("\n"));
    setIsEditingStudyChapters(false);
  }, [plan?.courseTitle, plan?.id, plan?.studyChapters]);

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

  const handleSaveStudyChapters = async () => {
    if (!plan) {
      return;
    }
    const nextStudyChapters = studyChaptersDraft
      .split("\n")
      .map((item) => item.trim())
      .filter(Boolean);
    const didSave = await onUpdateStudyChapters(plan.id, nextStudyChapters);
    if (didSave) {
      setIsEditingStudyChapters(false);
    }
  };

  const pendingPlanningQuestions = (plan?.planningQuestions ?? []).filter(
    (item) => item.status !== "answered"
  );

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
                        : {})
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

          <dl style={styles.meta}>
            <div style={styles.metaItem}>
              <dt style={styles.metaKey}>学习目标</dt>
              <dd style={styles.metaVal}>{plan.objective || "未填写"}</dd>
            </div>
            <div style={styles.metaItem}>
              <dt style={styles.metaKey}>教材</dt>
              <dd style={styles.metaVal}>
                {plan.creationMode === "goal_only" ? "仅学习目标" : documentTitle}
              </dd>
            </div>
            <div style={styles.metaItem}>
              <dt style={styles.metaKey}>教师人格</dt>
              <dd style={styles.metaVal}>{personaName}</dd>
            </div>
            <div style={styles.metaItem}>
              <dt style={styles.metaKey}>场景</dt>
              <dd style={styles.metaVal}>
                {sceneProfile ? formatSceneProfile(sceneProfile) : plan.sceneProfileSummary || "未配置"}
              </dd>
            </div>
            <div style={styles.metaItem}>
              <dt style={styles.metaKey}>生成时间</dt>
              <dd style={styles.metaVal}>{formatDate(plan.createdAt)}</dd>
            </div>
          </dl>

          {sceneProfile ? (
            <div style={styles.sceneCard}>
              <div style={styles.sceneCardHead}>
                <span style={styles.sectionLabel}>学习场景</span>
                <span style={styles.count}>{countSceneNodes(sceneProfile.sceneTree)} 节点</span>
              </div>
              <p style={styles.sceneName}>场景名：{sceneProfile.sceneName || "未命名"}</p>
              <div style={styles.sceneTitleRow}>
                <strong style={styles.sceneTitle}>{sceneProfile.title}</strong>
                <span style={styles.scenePath}>{sceneProfile.selectedPath.join(" / ")}</span>
              </div>
              <p style={styles.sceneSummary}>{sceneProfile.summary}</p>
              <div style={styles.sceneTags}>
                {sceneProfile.tags.slice(0, 4).map((tag) => (
                  <span key={tag} style={styles.sceneTag}>{tag}</span>
                ))}
                {sceneProfile.focusObjectNames.slice(0, 3).map((name) => (
                  <span key={name} style={styles.sceneTag}>{name}</span>
                ))}
              </div>
            </div>
          ) : null}

          <div style={styles.progressCard}>
            <div style={styles.progressHead}>
              <div style={styles.sectionHeadMeta}>
                <span style={styles.sectionLabel}>完成度</span>
                <span style={styles.count}>
                  {plan.progressSummary.completedScheduleCount}/{plan.progressSummary.totalScheduleCount}
                </span>
              </div>
              <span style={styles.progressPercent}>
                {plan.progressSummary.completionPercent}%
              </span>
            </div>
            <div style={styles.progressBarTrack}>
              <div
                style={{
                  ...styles.progressBarFill,
                  width: `${Math.max(0, Math.min(100, plan.progressSummary.completionPercent))}%`
                }}
              />
            </div>
            <div style={styles.progressStats}>
              <span style={styles.progressStat}>进行中 {plan.progressSummary.inProgressScheduleCount}</span>
              <span style={styles.progressStat}>待处理 {plan.progressSummary.pendingScheduleCount}</span>
              <span style={styles.progressStat}>阻塞 {plan.progressSummary.blockedScheduleCount}</span>
            </div>
            {plan.chapterProgress.length ? (
              <div style={styles.chapterProgressList}>
                {plan.chapterProgress.map((item) => (
                  <div key={item.unitId} style={styles.chapterProgressItem}>
                    <div style={styles.scheduleMeta}>
                      <span style={styles.scheduleTitle}>{item.title}</span>
                      <span style={scheduleStatusStyle(item.status)}>{formatScheduleStatus(item.status)}</span>
                    </div>
                    <span style={styles.scheduleFocus}>
                      {item.objectiveFragment || "暂无补充说明。"}
                    </span>
                    <div style={styles.chapterProgressTrack}>
                      <div
                        style={{
                          ...styles.chapterProgressFill,
                          width: `${Math.max(0, Math.min(100, item.completionPercent))}%`
                        }}
                      />
                    </div>
                    <div style={styles.progressStats}>
                      <span style={styles.progressStat}>
                        排期 {item.completedScheduleCount}/{item.totalScheduleCount}
                      </span>
                      <span style={styles.progressStat}>进行中 {item.inProgressScheduleCount}</span>
                      <span style={styles.progressStat}>待处理 {item.pendingScheduleCount}</span>
                    </div>
                    <div style={styles.scheduleActions}>
                      <button
                        type="button"
                        style={styles.ghostButton}
                        disabled={isBusy || !item.scheduleIds.length || item.status === "in_progress"}
                        onClick={() => {
                          void onUpdatePlanProgress({
                            planId: plan.id,
                            scheduleIds: item.scheduleIds,
                            status: "in_progress"
                          });
                        }}
                      >
                        本章开始
                      </button>
                      <button
                        type="button"
                        style={styles.primaryButton}
                        disabled={isBusy || !item.scheduleIds.length || item.status === "completed"}
                        onClick={() => {
                          void onUpdatePlanProgress({
                            planId: plan.id,
                            scheduleIds: item.scheduleIds,
                            status: "completed"
                          });
                        }}
                      >
                        本章完成
                      </button>
                      <button
                        type="button"
                        style={styles.ghostButton}
                        disabled={isBusy || !item.scheduleIds.length || item.status === "planned"}
                        onClick={() => {
                          void onUpdatePlanProgress({
                            planId: plan.id,
                            scheduleIds: item.scheduleIds,
                            status: "planned"
                          });
                        }}
                      >
                        本章重置
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            ) : null}
            <div style={styles.scheduleList}>
              {plan.schedule.map((item) => (
                <div key={item.id} style={styles.scheduleItem}>
                  <div style={styles.scheduleMeta}>
                    <span style={styles.scheduleTitle}>{item.title}</span>
                    <span style={scheduleStatusStyle(item.status)}>{formatScheduleStatus(item.status)}</span>
                  </div>
                  <span style={styles.scheduleFocus}>{item.focus}</span>
                  <div style={styles.scheduleActions}>
                    <button
                      type="button"
                      style={styles.ghostButton}
                      disabled={isBusy || item.status === "in_progress"}
                      onClick={() => {
                        void onUpdatePlanProgress({
                          planId: plan.id,
                          scheduleIds: [item.id],
                          status: "in_progress"
                        });
                      }}
                    >
                      开始
                    </button>
                    <button
                      type="button"
                      style={styles.primaryButton}
                      disabled={isBusy || item.status === "completed"}
                      onClick={() => {
                        void onUpdatePlanProgress({
                          planId: plan.id,
                          scheduleIds: [item.id],
                          status: "completed"
                        });
                      }}
                    >
                      完成
                    </button>
                    <button
                      type="button"
                      style={styles.ghostButton}
                      disabled={isBusy || item.status === "planned"}
                      onClick={() => {
                        void onUpdatePlanProgress({
                          planId: plan.id,
                          scheduleIds: [item.id],
                          status: "planned"
                        });
                      }}
                    >
                      重置
                    </button>
                  </div>
                </div>
              ))}
            </div>
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
                          [item.id]: event.target.value
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
                          ...((isBusy || !(planningAnswerDrafts[item.id] ?? "").trim()) ? styles.buttonDisabled : {})
                        }}
                        disabled={isBusy || !(planningAnswerDrafts[item.id] ?? "").trim()}
                        onClick={() => {
                          void onAnswerPlanningQuestion({
                            planId: plan.id,
                            questionId: item.id,
                            answer: planningAnswerDrafts[item.id] ?? ""
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

          <div style={styles.actionRow}>
            {hasSession ? (
              <span style={styles.sessionConnected}>会话已创建</span>
            ) : (
              <button
                type="button"
                style={{
                  ...styles.primaryButton,
                  ...(isBusy ? styles.buttonDisabled : {})
                }}
                onClick={onCreateSession}
                disabled={isBusy}
              >
                {isBusy ? "创建中…" : "创建章节会话"}
              </button>
            )}
          </div>
        </>
      ) : (
        <div style={styles.emptyState}>
          <h2 style={styles.title}>暂无学习计划</h2>
          <p style={styles.overview}>生成计划后会显示在这里。</p>
        </div>
      )}

      <div style={styles.section}>
        <div style={styles.sectionHead}>
          <div style={styles.sectionHeadMeta}>
            <span style={styles.sectionLabel}>学习章节</span>
            <span style={styles.count}>{plan?.studyChapters.length ?? 0}</span>
          </div>
          {plan ? (
            <button
              type="button"
              style={styles.ghostButton}
              disabled={isBusy}
              onClick={() => setIsEditingStudyChapters((current) => !current)}
            >
              {isEditingStudyChapters ? "收起编辑" : "编辑章节"}
            </button>
          ) : null}
        </div>
        {isEditingStudyChapters && plan ? (
          <div style={styles.focusEditor}>
            <textarea
              value={studyChaptersDraft}
              onChange={(event) => setStudyChaptersDraft(event.target.value)}
              style={styles.focusTextarea}
              placeholder={"每行一个学习章节"}
              disabled={isBusy}
            />
            <div style={styles.titleActions}>
              <button
                type="button"
                style={{
                  ...styles.primaryButton,
                  ...((isBusy || !studyChaptersDraft.trim()) ? styles.buttonDisabled : {})
                }}
                disabled={isBusy || !studyChaptersDraft.trim()}
                onClick={() => { void handleSaveStudyChapters(); }}
              >
                保存学习章节
              </button>
              <button
                type="button"
                style={styles.ghostButton}
                disabled={isBusy}
                onClick={() => {
                  setStudyChaptersDraft((plan.studyChapters ?? []).join("\n"));
                  setIsEditingStudyChapters(false);
                }}
              >
                取消
              </button>
            </div>
          </div>
        ) : null}
        <ol style={styles.list}>
          {(plan?.studyChapters.length
            ? plan.studyChapters
            : ["还没有学习章节。"]
          ).map((focus, index) => (
            <li key={`${focus}-${index}`} style={styles.listItem}>
              <span style={styles.idx}>{index + 1}</span>
              <div style={styles.chapterItem}>
                <span style={styles.chapterTitle}>{focus}</span>
                {plan && document ? (
                  (() => {
                    const studyUnit = resolveStudyUnitForChapter(plan, focus, index);
                    if (!studyUnit) return null;
                    const subsections = resolveSubsectionsForStudyUnit(document, studyUnit);
                    return (
                      <>
                        <Link
                          href={{
                            pathname: "/study",
                            query: {
                              plan: plan.id,
                              chapter: focus,
                              page: String(studyUnit.pageStart),
                            }
                          }}
                          style={styles.pageTag}
                          title={`跳转到第 ${studyUnit.pageStart} 页并打开章节对话`}
                        >
                          跳转到第 {studyUnit.pageStart} 页
                          {studyUnit.pageEnd > studyUnit.pageStart ? ` · p.${studyUnit.pageStart}-${studyUnit.pageEnd}` : ""}
                        </Link>
                        {subsections.length ? (
                          <div style={styles.subsectionList}>
                            {subsections.map((subsection) => (
                              <Link
                                key={subsection.id}
                                href={{
                                  pathname: "/study",
                                  query: {
                                    plan: plan.id,
                                    chapter: focus,
                                    subsection: subsection.id,
                                    page: String(subsection.pageStart),
                                  }
                                }}
                                style={styles.subsectionTag}
                                title={`跳转到子章节 ${subsection.title}`}
                              >
                                <span style={styles.subsectionName}>{subsection.title}</span>
                                <span style={styles.subsectionPage}>p.{subsection.pageStart}-{subsection.pageEnd}</span>
                              </Link>
                            ))}
                          </div>
                        ) : null}
                      </>
                    );
                  })()
                ) : null}
              </div>
            </li>
          ))}
        </ol>
      </div>

    </section>
  );
}

const styles: Record<string, CSSProperties> = {
  wrap: {
    display: "grid",
    gap: 0
  },
  headerRow: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 12,
    paddingBottom: 14,
    borderBottom: "1px solid var(--border)"
  },
  headerMeta: {
    display: "grid",
    gap: 2
  },
  sectionHint: {
    fontSize: 12,
    color: "var(--muted)"
  },
  titleBlock: {
    paddingTop: 16,
    paddingBottom: 8,
    display: "grid",
    gap: 10
  },
  titleRow: {
    display: "flex",
    alignItems: "flex-start",
    justifyContent: "space-between",
    gap: 12
  },
  titleActions: {
    display: "flex",
    flexWrap: "wrap",
    gap: 8
  },
  title: {
    margin: 0,
    fontSize: "clamp(1.1rem, 1.6vw, 1.35rem)",
    lineHeight: 1.3,
    fontWeight: 700,
    color: "var(--ink)"
  },
  titleInput: {
    width: "100%",
    minHeight: 40,
    border: "1px solid var(--border-strong)",
    padding: "8px 10px",
    background: "white",
    color: "var(--ink)",
    fontSize: 15,
    fontWeight: 600
  },
  badge: {
    fontSize: 12,
    color: "var(--muted)",
    whiteSpace: "nowrap"
  },
  overview: {
    margin: "0 0 16px",
    color: "var(--muted)",
    fontSize: 13,
    lineHeight: 1.7
  },
  meta: {
    margin: 0,
    padding: "0 0 14px",
    display: "flex",
    flexWrap: "wrap",
    gap: "6px 20px"
  },
  metaItem: {
    display: "flex",
    gap: 6,
    alignItems: "baseline"
  },
  metaKey: {
    fontSize: 11,
    fontWeight: 600,
    color: "var(--muted)",
    textTransform: "uppercase",
    letterSpacing: "0.07em",
    flexShrink: 0
  },
  metaVal: {
    margin: 0,
    fontSize: 13,
    color: "var(--ink)"
  },
  actionRow: {
    paddingBottom: 16
  },
  primaryButton: {
    border: "none",
    minHeight: 34,
    padding: "0 16px",
    background: "var(--accent)",
    color: "white",
    fontWeight: 600,
    cursor: "pointer",
    fontSize: 13
  },
  ghostButton: {
    minHeight: 34,
    border: "1px solid var(--border)",
    padding: "0 12px",
    background: "transparent",
    color: "var(--muted)",
    fontSize: 13,
    cursor: "pointer"
  },
  buttonDisabled: {
    opacity: 0.45,
    cursor: "not-allowed"
  },
  sessionConnected: {
    fontSize: 13,
    color: "var(--positive)",
    fontWeight: 500
  },
  sceneCard: {
    display: "grid",
    gap: 8,
    padding: 12,
    border: "1px solid var(--border)",
    background: "var(--panel)",
    marginBottom: 14
  },
  sceneCardHead: {
    display: "flex",
    justifyContent: "space-between",
    gap: 12,
    alignItems: "center"
  },
  sceneTitleRow: {
    display: "grid",
    gap: 2
  },
  sceneName: {
    margin: 0,
    fontSize: 12,
    color: "var(--accent)",
    fontWeight: 600
  },
  sceneTitle: {
    fontSize: 13,
    color: "var(--ink)"
  },
  scenePath: {
    margin: 0,
    fontSize: 12,
    color: "var(--muted)",
    lineHeight: 1.5
  },
  sceneSummary: {
    margin: 0,
    fontSize: 12,
    lineHeight: 1.6,
    color: "var(--muted)"
  },
  sceneTags: {
    display: "flex",
    flexWrap: "wrap",
    gap: 6
  },
  sceneTag: {
    padding: "3px 8px",
    border: "1px solid var(--border)",
    background: "white",
    color: "var(--muted)",
    fontSize: 11
  },
  progressCard: {
    display: "grid",
    gap: 10,
    padding: 12,
    border: "1px solid var(--border)",
    background: "white",
    marginBottom: 14
  },
  progressHead: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 12
  },
  progressPercent: {
    fontSize: 18,
    fontWeight: 700,
    color: "var(--accent)"
  },
  progressBarTrack: {
    height: 8,
    background: "color-mix(in srgb, var(--accent-soft) 35%, white)",
    overflow: "hidden"
  },
  progressBarFill: {
    height: "100%",
    background: "var(--accent)"
  },
  progressStats: {
    display: "flex",
    flexWrap: "wrap",
    gap: 8
  },
  progressStat: {
    padding: "4px 8px",
    border: "1px solid var(--border)",
    background: "var(--panel)",
    fontSize: 12,
    color: "var(--muted)"
  },
  chapterProgressList: {
    display: "grid",
    gap: 10
  },
  chapterProgressItem: {
    display: "grid",
    gap: 8,
    padding: "10px 12px",
    border: "1px solid var(--border)",
    background: "color-mix(in srgb, var(--panel) 72%, white)"
  },
  chapterProgressTrack: {
    height: 6,
    background: "color-mix(in srgb, var(--accent-soft) 30%, white)",
    overflow: "hidden"
  },
  chapterProgressFill: {
    height: "100%",
    background: "var(--accent)"
  },
  scheduleList: {
    display: "grid",
    gap: 8
  },
  scheduleItem: {
    display: "grid",
    gap: 6,
    padding: "10px 12px",
    border: "1px solid var(--border)",
    background: "var(--panel)"
  },
  scheduleMeta: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 8,
    flexWrap: "wrap"
  },
  scheduleTitle: {
    fontSize: 13,
    fontWeight: 600,
    color: "var(--ink)"
  },
  scheduleFocus: {
    fontSize: 12,
    lineHeight: 1.6,
    color: "var(--muted)"
  },
  scheduleActions: {
    display: "flex",
    flexWrap: "wrap",
    gap: 8
  },
  questionCard: {
    display: "grid",
    gap: 10,
    padding: 12,
    border: "1px solid var(--border)",
    background: "var(--panel)",
    marginBottom: 14
  },
  questionList: {
    display: "grid",
    gap: 10
  },
  questionItem: {
    display: "grid",
    gap: 8,
    padding: "10px 12px",
    border: "1px solid var(--border)",
    background: "white"
  },
  questionHeader: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 8,
    flexWrap: "wrap"
  },
  questionTitle: {
    fontSize: 13,
    color: "var(--ink)"
  },
  questionReason: {
    fontSize: 12,
    lineHeight: 1.6,
    color: "var(--muted)"
  },
  section: {
    paddingTop: 16,
    paddingBottom: 4,
    borderTop: "1px solid var(--border)",
    display: "grid",
    gap: 10
  },
  sectionHead: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 8
  },
  sectionHeadMeta: {
    display: "flex",
    alignItems: "center",
    gap: 8
  },
  sectionLabel: {
    fontSize: 11,
    fontWeight: 700,
    textTransform: "uppercase",
    letterSpacing: "0.07em",
    color: "var(--muted)"
  },
  count: {
    fontSize: 11,
    color: "var(--muted)"
  },
  focusEditor: {
    display: "grid",
    gap: 10
  },
  focusTextarea: {
    width: "100%",
    minHeight: 112,
    border: "1px solid var(--border-strong)",
    padding: "10px 12px",
    background: "white",
    color: "var(--ink)",
    fontSize: 13,
    lineHeight: 1.6,
    resize: "vertical"
  },
  list: {
    margin: 0,
    padding: 0,
    listStyle: "none",
    display: "grid",
    gap: 8
  },
  listItem: {
    display: "grid",
    gridTemplateColumns: "28px minmax(0, 1fr)",
    gap: 10,
    alignItems: "start",
    padding: "10px 0",
    borderBottom: "1px solid color-mix(in srgb, var(--border) 72%, white)"
  },
  chapterItem: {
    display: "grid",
    gap: 6,
    minWidth: 0,
  },
  chapterTitle: {
    fontSize: 13,
    color: "var(--ink)",
    lineHeight: 1.6,
  },
  pageTag: {
    display: "inline-flex",
    width: "fit-content",
    alignItems: "center",
    minHeight: 28,
    padding: "0 10px",
    border: "1px solid color-mix(in srgb, var(--accent) 20%, var(--border))",
    background: "color-mix(in srgb, var(--accent-soft) 68%, white)",
    color: "var(--accent)",
    fontSize: 12,
    fontWeight: 600,
    lineHeight: 1,
    textDecoration: "none",
  },
  subsectionList: {
    display: "grid",
    gap: 6,
    paddingTop: 4,
    paddingLeft: 14,
    borderLeft: "1px solid color-mix(in srgb, var(--border) 75%, white)",
  },
  subsectionTag: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 12,
    minHeight: 32,
    padding: "0 10px",
    border: "1px solid var(--border)",
    background: "white",
    color: "var(--ink-2)",
    textDecoration: "none",
  },
  subsectionName: {
    minWidth: 0,
    fontSize: 12,
    lineHeight: 1.5,
    color: "var(--ink)",
  },
  subsectionPage: {
    fontSize: 11,
    color: "var(--muted)",
    whiteSpace: "nowrap",
    flexShrink: 0,
  },
  idx: {
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
    width: 22,
    height: 22,
    borderRadius: "50%",
    background: "var(--accent-soft)",
    color: "var(--accent)",
    fontSize: 12,
    fontWeight: 700
  },
  emptyState: {
    paddingTop: 16
  }
};

function resolveCourseTitle(courseTitle: string, documentTitle: string) {
  const trimmed = courseTitle?.trim();
  if (trimmed) {
    return trimmed;
  }
  return documentTitle || "未命名计划";
}

function formatSceneProfile(sceneProfile: SceneProfile) {
  const path = sceneProfile.selectedPath.join(" / ");
  return path ? `${sceneProfile.title} · ${path}` : sceneProfile.title || sceneProfile.sceneName || "未命名";
}

function formatDate(value: string) {
  if (!value) return "未知时间";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit"
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

function scheduleStatusStyle(status: string): CSSProperties {
  if (status === "completed") {
    return {
      padding: "3px 8px",
      border: "1px solid color-mix(in srgb, var(--accent) 20%, var(--border))",
      background: "color-mix(in srgb, var(--accent-soft) 65%, white)",
      color: "var(--accent)",
      fontSize: 11
    };
  }
  if (status === "in_progress") {
    return {
      padding: "3px 8px",
      border: "1px solid color-mix(in srgb, #c97a00 24%, var(--border))",
      background: "rgba(201, 122, 0, 0.08)",
      color: "#8a5700",
      fontSize: 11
    };
  }
  if (status === "blocked") {
    return {
      padding: "3px 8px",
      border: "1px solid rgba(180, 35, 24, 0.24)",
      background: "rgba(180, 35, 24, 0.06)",
      color: "var(--danger, #b42318)",
      fontSize: 11
    };
  }
  return {
    padding: "3px 8px",
    border: "1px solid var(--border)",
    background: "white",
    color: "var(--muted)",
    fontSize: 11
  };
}

function countSceneNodes(nodes: import("@vibe-learner/shared").SceneTreeNode[]): number {
  return nodes.reduce((count, node) => count + 1 + countSceneNodes(node.children), 0);
}

function resolveStudyUnitForChapter(plan: LearningPlan, chapter: string, chapterIndex: number): StudyUnit | null {
  const exactFocusMatch = plan.schedule.find((item) => {
    const focus = item.focus?.trim() ?? "";
    return focus === chapter || focus.includes(chapter) || chapter.includes(focus);
  });
  if (exactFocusMatch?.unitId) {
    const matchedUnit = plan.studyUnits.find((unit) => unit.id === exactFocusMatch.unitId);
    if (matchedUnit) return matchedUnit;
  }

  const chapterScopedUnits = plan.studyUnits.filter((unit) => unit.includeInPlan);
  if (chapterScopedUnits[chapterIndex]) {
    return chapterScopedUnits[chapterIndex];
  }

  const uniqueUnitIds = Array.from(new Set(plan.schedule.map((item) => item.unitId).filter(Boolean)));
  const fallbackUnitId = uniqueUnitIds[chapterIndex];
  if (fallbackUnitId) {
    return plan.studyUnits.find((unit) => unit.id === fallbackUnitId) ?? null;
  }

  return null;
}

function resolveSubsectionsForStudyUnit(
  document: DocumentRecord | null,
  studyUnit: StudyUnit | null
): DocumentSection[] {
  if (!document || !studyUnit) {
    return [];
  }

  const sectionMap = new Map(document.sections.map((section) => [section.id, section]));
  const directMatches = studyUnit.sourceSectionIds
    .map((sectionId) => sectionMap.get(sectionId))
    .filter((section): section is DocumentSection => Boolean(section));
  const scopeSections = directMatches.length ? directMatches : [studyUnit];
  const candidates = document.sections
    .filter((section) =>
      scopeSections.some((scope) =>
        Math.max(scope.pageStart, section.pageStart) <= Math.min(scope.pageEnd, section.pageEnd)
      )
    )
    .filter((section) => section.level >= 2)
    .sort((left, right) =>
      left.pageStart - right.pageStart ||
      left.level - right.level ||
      left.pageEnd - right.pageEnd ||
      left.id.localeCompare(right.id)
    );

  return candidates.filter(
    (section, index) => candidates.findIndex((candidate) => candidate.id === section.id) === index
  );
}
