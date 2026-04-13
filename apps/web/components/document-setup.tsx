"use client";

import Link from "next/link";
import type { CSSProperties } from "react";
import { useEffect, useState } from "react";
import type {
  DocumentRecord,
  LearningPlan,
  PersonaProfile,
  SceneProfile,
  StudySessionRecord
} from "@vibe-learner/shared";
import type { PlanSetupPageCache } from "../lib/learning-workspace-page-cache";
import type { SceneLibraryItemPayload } from "../lib/data/scenes";
import { MaterialIcon } from "./material-icon";
import { PersonaSelector } from "./persona-selector";

interface DocumentSetupProps {
  personas: PersonaProfile[];
  selectedPersonaId: string;
  onSelectPersonaId: (personaId: string) => void;
  onGenerate: (input: { mode: "document" | "goal_only"; file?: File | null; objective: string }) => void;
  onOpenStudyDialog: () => void;
  canOpenStudyDialog: boolean;
  hasStudySession: boolean;
  onRenameStudyUnitTitle: (
    documentId: string,
    studyUnitId: string,
    title: string
  ) => Promise<boolean>;
  isBusy: boolean;
  document: DocumentRecord | null;
  plan: LearningPlan | null;
  session: StudySessionRecord | null;
  sceneLibraryItems: SceneLibraryItemPayload[];
  selectedSceneLibraryId: string;
  onSelectSceneLibraryId: (sceneId: string) => void;
  sceneProfile?: SceneProfile | null;
  planStreamEvents: StreamEventItem[];
  planStreamStatus: string;
  cachedState?: PlanSetupPageCache;
  onCachedStateChange?: (state: PlanSetupPageCache) => void;
}

interface StreamEventItem {
  stage: string;
  payload: Record<string, unknown>;
}

export function DocumentSetup({
  personas,
  selectedPersonaId,
  onSelectPersonaId,
  onGenerate,
  onOpenStudyDialog,
  canOpenStudyDialog,
  hasStudySession,
  onRenameStudyUnitTitle,
  isBusy,
  document,
  plan,
  session,
  sceneLibraryItems,
  selectedSceneLibraryId,
  onSelectSceneLibraryId,
  sceneProfile,
  planStreamEvents,
  planStreamStatus,
  cachedState,
  onCachedStateChange,
}: DocumentSetupProps) {
  const [file, setFile] = useState<File | null>(() => cachedState?.file ?? null);
  const [generationMode, setGenerationMode] = useState<"document" | "goal_only">(
    () => cachedState?.generationMode ?? "document"
  );
  const [objective, setObjective] = useState(
    () => cachedState?.objective ?? "请基于教材结构生成首轮学习计划，先给出学习章节顺序，再拆分每章的细分学习要点。"
  );
  const [editingUnitId, setEditingUnitId] = useState("");
  const [unitTitleDraft, setUnitTitleDraft] = useState("");

  useEffect(() => {
    if (!editingUnitId || !document) {
      return;
    }
    const editingUnit = document.studyUnits.find((unit) => unit.id === editingUnitId);
    if (!editingUnit) {
      setEditingUnitId("");
      setUnitTitleDraft("");
    }
  }, [document, editingUnitId]);

  useEffect(() => {
    onCachedStateChange?.({
      generationMode,
      objective,
      file,
    });
  }, [file, generationMode, objective, onCachedStateChange]);

  const planRoundSummary = summarizePlanRounds(planStreamEvents);
  const shouldShowPlanRounds =
    planStreamStatus !== "idle" || planStreamEvents.length > 0 || planRoundSummary.rounds.length > 0;
  const displayedStudyUnits = document?.studyUnits.length
    ? document.studyUnits
    : (plan?.studyUnits ?? []);

  return (
    <div className="plan-setup-column" style={styles.wrap}>
      <div style={styles.sectionHead}>
        <span style={styles.sectionTitle}>计划设置</span>
        <span style={styles.sectionMeta}>先确定陪伴人格与场景，再上传教材开始分析。</span>
      </div>

      <section style={styles.card}>
        <div style={styles.cardHead}>
          <span style={styles.cardTitle}>上传前配置</span>
          <span style={styles.cardMeta}>人格、场景、章节入口</span>
        </div>

        <label style={styles.field}>
          <span style={styles.fieldLabel}>教师人格</span>
          <PersonaSelector
            personas={personas}
            selectedPersonaId={selectedPersonaId}
            onChange={onSelectPersonaId}
            compact
          />
        </label>

        <label style={styles.field}>
          <span style={styles.fieldLabel}>计划使用场景</span>
          <select
            value={selectedSceneLibraryId}
            onChange={(event) => onSelectSceneLibraryId(event.target.value)}
            style={styles.select}
          >
            <option value="">不使用场景库场景</option>
            {sceneLibraryItems.map((item) => (
              <option key={item.sceneId} value={item.sceneId}>
                {item.sceneName}
              </option>
            ))}
          </select>
          <span style={styles.fieldHint}>
            {sceneProfile
              ? `当前将使用：${formatSceneSummary(sceneProfile)}`
              : "未选择场景时会回退到本地场景草稿（若存在）。"}
          </span>
        </label>

        <div style={styles.actionRow}>
          <Link href="/scene-setup" style={styles.iconButton} aria-label="打开场景编辑" title="去场景编辑">
            <MaterialIcon name="landscape" size={18} />
          </Link>
          <button
            type="button"
            style={{
              ...styles.iconButton,
              ...((!canOpenStudyDialog || isBusy) ? styles.buttonDisabled : {})
            }}
            disabled={!canOpenStudyDialog || isBusy}
            onClick={onOpenStudyDialog}
            aria-label={hasStudySession ? "打开章节对话" : "创建并打开章节对话"}
            title={hasStudySession ? "打开章节对话" : "创建并打开章节对话"}
          >
            <MaterialIcon name="chat" size={18} />
          </button>
        </div>
      </section>

      <section style={styles.card}>
        <div style={styles.cardHead}>
          <span style={styles.cardTitle}>教材上传与分析</span>
          <span style={styles.cardMeta}>上传 PDF 生成计划，学习目标会参与标题、任务和章节取舍</span>
        </div>

        <div style={styles.form}>
          <label style={styles.field}>
            <span style={styles.fieldLabel}>创建方式</span>
            <select
              value={generationMode}
              onChange={(event) => setGenerationMode(event.target.value === "goal_only" ? "goal_only" : "document")}
              style={styles.select}
            >
              <option value="document">教材 + 目标</option>
              <option value="goal_only">仅学习目标</option>
            </select>
            <span style={styles.fieldHint}>
              {generationMode === "document"
                ? "标准模式：先解析教材，再结合目标生成学习计划。"
                : "轻量模式：不上传教材，直接围绕目标生成一版阶段性计划。"}
            </span>
          </label>
          <label style={styles.field}>
            <span style={styles.fieldLabel}>教材文件（PDF）</span>
            <input
              type="file"
              accept=".pdf"
              style={styles.fileInput}
              onChange={(event) => setFile(event.target.files?.[0] ?? null)}
              disabled={generationMode === "goal_only"}
            />
            {generationMode === "goal_only" ? (
              <span style={styles.fieldHint}>当前为仅目标模式，本轮不会上传教材。</span>
            ) : null}
          </label>
          <label style={styles.field}>
            <span style={styles.fieldLabel}>学习目标</span>
            <textarea
              value={objective}
              onChange={(event) => setObjective(event.target.value)}
              style={styles.textarea}
            />
          </label>
        </div>

        <button
          type="button"
          style={{
            ...styles.primaryButton,
            ...((isBusy || (generationMode === "document" && !file)) ? styles.buttonDisabled : {})
          }}
          disabled={isBusy || (generationMode === "document" && !file)}
          onClick={() => {
            if (generationMode === "document" && !file) return;
            console.info("[vibe-learner] ui:upload_click", {
              mode: generationMode,
              filename: file?.name ?? "",
              sizeBytes: file?.size ?? 0,
              selectedPersonaId
            });
            onGenerate({ mode: generationMode, file, objective });
          }}
        >
          <MaterialIcon name="upload" size={18} />
          {isBusy ? "处理中…" : generationMode === "document" ? "上传并生成计划" : "直接生成目标计划"}
        </button>

        {shouldShowPlanRounds ? (
          <div style={styles.progressSection}>
            <div style={styles.progressHeader}>
              <div style={styles.progressHeaderMeta}>
                <span style={styles.progressTitle}>计划生成轮次</span>
                <span style={styles.progressMeta}>直接显示模型轮次，不再只藏在 Debug 浮窗里。</span>
              </div>
              <span style={statusBadgeStyle(planStreamStatus)}>
                {formatPlanStreamStatus(planStreamStatus)}
              </span>
            </div>

            <div style={styles.progressStats}>
              <span style={styles.progressStat}>已见轮次 {planRoundSummary.rounds.length}</span>
              <span style={styles.progressStat}>工具调用 {planRoundSummary.totalToolCalls}</span>
              <span style={styles.progressStat}>规划提问 {planRoundSummary.planningQuestions.length}</span>
            </div>

            {planRoundSummary.latestMessage ? (
              <div style={styles.progressNotice}>{planRoundSummary.latestMessage}</div>
            ) : null}

            {planRoundSummary.planningQuestions.length ? (
              <div style={styles.questionNotice}>
                {planRoundSummary.planningQuestions.map((item) => (
                  <div key={item.id} style={styles.questionNoticeItem}>
                    <strong style={styles.questionNoticeLabel}>待确认</strong>
                    <span>{item.question}</span>
                    {item.reason ? <span style={styles.questionNoticeReason}>原因：{item.reason}</span> : null}
                  </div>
                ))}
              </div>
            ) : null}

            {planRoundSummary.rounds.length ? (
              <div style={styles.roundList}>
                {planRoundSummary.rounds.map((round) => (
                  <div key={round.roundIndex} style={styles.roundCard}>
                    <div style={styles.roundHeader}>
                      <strong style={styles.roundTitle}>Round {round.roundIndex + 1}</strong>
                      <span style={roundStatusBadgeStyle(round.status)}>
                        {formatRoundStatus(round.status)}
                      </span>
                    </div>
                    <span style={styles.roundMeta}>
                      工具 {round.toolCalls.length}
                      {round.finishReason ? ` · finish=${round.finishReason}` : ""}
                      {typeof round.elapsedMs === "number" ? ` · ${round.elapsedMs} ms` : ""}
                    </span>
                    {round.error ? <span style={styles.roundError}>失败原因：{round.error}</span> : null}
                    {round.toolCalls.length ? (
                      <div style={styles.roundToolList}>
                        {round.toolCalls.map((toolName, index) => (
                          <span key={`${round.roundIndex}:${toolName}:${index}`} style={styles.roundToolTag}>
                            {toolName}
                          </span>
                        ))}
                      </div>
                    ) : null}
                  </div>
                ))}
              </div>
            ) : (
              <span style={styles.fieldHint}>计划流已启动，等待首个模型轮次事件。</span>
            )}
          </div>
        ) : null}
      </section>

      <div style={styles.statusGrid}>
        <div style={styles.statusItem}>
          <span style={styles.statusLabel}>教材</span>
          <span style={styles.statusValue}>
            {document
              ? formatDocumentSummary(document)
              : plan?.creationMode === "goal_only"
                ? "仅目标模式"
                : "未上传"}
          </span>
        </div>
        <div style={styles.statusItem}>
          <span style={styles.statusLabel}>计划</span>
          <span style={styles.statusValue}>
            {plan ? `${plan.todayTasks.length} 条任务` : "未生成"}
          </span>
        </div>
        <div style={styles.statusItem}>
          <span style={styles.statusLabel}>会话</span>
          <span style={styles.statusValue}>
            {session ? formatSessionStatus(session.status) : "未创建"}
          </span>
        </div>
        <div style={styles.statusItem}>
          <span style={styles.statusLabel}>场景</span>
          <span style={styles.statusValue}>
            {sceneProfile ? formatSceneSummary(sceneProfile) : "未配置"}
          </span>
        </div>
      </div>

      {displayedStudyUnits.length ? (
        <div style={styles.unitSection}>
          <span style={styles.unitSectionLabel}>学习单元清单</span>
          <div style={styles.unitList}>
            {displayedStudyUnits.map((unit) => (
              <div key={unit.id} style={styles.unitItem}>
                {editingUnitId === unit.id ? (
                  <div style={styles.unitEditWrap}>
                    <input
                      value={unitTitleDraft}
                      onChange={(event) => setUnitTitleDraft(event.target.value)}
                      style={styles.unitTitleInput}
                      placeholder="输入学习单元标题"
                      disabled={isBusy}
                    />
                    <div style={styles.unitActionRow}>
                      <button
                        type="button"
                        style={{
                          ...styles.unitActionButtonPrimary,
                          ...((isBusy || !unitTitleDraft.trim() || unitTitleDraft.trim() === unit.title.trim())
                            ? styles.buttonDisabled
                            : {})
                        }}
                        disabled={isBusy || !unitTitleDraft.trim() || unitTitleDraft.trim() === unit.title.trim()}
                        onClick={() => {
                          if (!document) return;
                          void onRenameStudyUnitTitle(document.id, unit.id, unitTitleDraft).then((didSave) => {
                            if (didSave) {
                              setEditingUnitId("");
                              setUnitTitleDraft("");
                            }
                          });
                        }}
                      >
                        保存
                      </button>
                      <button
                        type="button"
                        style={styles.unitActionButton}
                        disabled={isBusy}
                        onClick={() => {
                          setEditingUnitId("");
                          setUnitTitleDraft("");
                        }}
                      >
                        取消
                      </button>
                    </div>
                  </div>
                ) : (
                  <div style={styles.unitTitleRow}>
                    <span style={styles.unitTitle}>{unit.title}</span>
                    <button
                      type="button"
                      style={styles.unitEditButton}
                      disabled={isBusy || !document}
                      onClick={() => {
                        setEditingUnitId(unit.id);
                        setUnitTitleDraft(unit.title);
                      }}
                    >
                      编辑标题
                    </button>
                  </div>
                )}
                <span style={styles.unitMeta}>
                  p.{unit.pageStart}–{unit.pageEnd} · {formatUnitKind(unit.unitKind)}
                  {unit.includeInPlan ? "" : " · 已跳过"}
                </span>
              </div>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}

const styles: Record<string, CSSProperties> = {
  wrap: {
    display: "grid",
    gap: 18
  },
  sectionHead: {
    display: "grid",
    gap: 4,
    paddingBottom: 4
  },
  sectionTitle: {
    fontSize: 15,
    fontWeight: 700,
    color: "var(--ink)"
  },
  sectionMeta: {
    fontSize: 12,
    color: "var(--muted)",
    lineHeight: 1.6
  },
  card: {
    display: "grid",
    gap: 14,
    padding: 16,
    border: "1px solid var(--border)",
    background: "var(--panel)"
  },
  cardHead: {
    display: "grid",
    gap: 2
  },
  cardTitle: {
    fontSize: 13,
    fontWeight: 700,
    color: "var(--ink)"
  },
  cardMeta: {
    fontSize: 12,
    color: "var(--muted)"
  },
  form: {
    display: "grid",
    gap: 14
  },
  field: {
    display: "grid",
    gap: 6
  },
  fieldLabel: {
    fontSize: 11,
    fontWeight: 600,
    textTransform: "uppercase",
    letterSpacing: "0.07em",
    color: "var(--muted)"
  },
  textarea: {
    width: "100%",
    minHeight: 88,
    border: "1px solid var(--border)",
    padding: "8px 10px",
    background: "white",
    resize: "vertical",
    fontSize: 13,
    lineHeight: 1.6,
    color: "var(--ink)"
  },
  fileInput: {
    width: "100%",
    border: "1px solid var(--border)",
    padding: "6px 8px",
    background: "white",
    color: "var(--ink)",
    fontSize: 13
  },
  select: {
    width: "100%",
    height: 36,
    border: "1px solid var(--border)",
    padding: "0 10px",
    background: "white",
    color: "var(--ink)",
    fontSize: 13
  },
  fieldHint: {
    fontSize: 12,
    color: "var(--muted)",
    lineHeight: 1.5
  },
  actionRow: {
    display: "flex",
    flexWrap: "wrap",
    gap: 10
  },
  iconButton: {
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
    width: 34,
    height: 34,
    border: "1px solid var(--border)",
    background: "white",
    color: "var(--accent)",
    fontSize: 13,
    cursor: "pointer",
    flexShrink: 0
  },
  primaryButton: {
    border: "none",
    minHeight: 36,
    padding: "0 14px",
    background: "var(--accent)",
    color: "white",
    fontWeight: 600,
    cursor: "pointer",
    fontSize: 13,
    justifySelf: "start",
    display: "inline-flex",
    alignItems: "center",
    gap: 8
  },
  buttonDisabled: {
    opacity: 0.45,
    cursor: "not-allowed"
  },
  progressSection: {
    display: "grid",
    gap: 10,
    paddingTop: 14,
    borderTop: "1px solid var(--border)"
  },
  progressHeader: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "flex-start",
    gap: 10,
    flexWrap: "wrap"
  },
  progressHeaderMeta: {
    display: "grid",
    gap: 2
  },
  progressTitle: {
    fontSize: 12,
    fontWeight: 700,
    color: "var(--ink)",
    textTransform: "uppercase",
    letterSpacing: "0.06em"
  },
  progressMeta: {
    fontSize: 12,
    color: "var(--muted)",
    lineHeight: 1.5
  },
  progressStats: {
    display: "flex",
    flexWrap: "wrap",
    gap: 8
  },
  progressStat: {
    padding: "5px 8px",
    borderWidth: 1,
    borderStyle: "solid",
    borderColor: "var(--border)",
    background: "white",
    fontSize: 12,
    color: "var(--muted)"
  },
  progressNotice: {
    padding: "10px 12px",
    border: "1px solid color-mix(in srgb, var(--accent) 16%, var(--border))",
    background: "color-mix(in srgb, white 84%, var(--accent-soft))",
    color: "var(--ink)",
    fontSize: 12,
    lineHeight: 1.6
  },
  questionNotice: {
    display: "grid",
    gap: 8
  },
  questionNoticeItem: {
    display: "grid",
    gap: 4,
    padding: "10px 12px",
    border: "1px solid color-mix(in srgb, var(--accent) 16%, var(--border))",
    background: "white",
    fontSize: 12,
    color: "var(--ink)",
    lineHeight: 1.6
  },
  questionNoticeLabel: {
    fontSize: 11,
    color: "var(--accent)",
    textTransform: "uppercase",
    letterSpacing: "0.06em"
  },
  questionNoticeReason: {
    color: "var(--muted)"
  },
  roundList: {
    display: "grid",
    gap: 8
  },
  roundCard: {
    display: "grid",
    gap: 6,
    padding: "10px 12px",
    border: "1px solid var(--border)",
    background: "white"
  },
  roundHeader: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 8,
    flexWrap: "wrap"
  },
  roundTitle: {
    fontSize: 13,
    color: "var(--ink)"
  },
  roundMeta: {
    fontSize: 12,
    color: "var(--muted)"
  },
  roundError: {
    fontSize: 12,
    color: "var(--danger, #b42318)"
  },
  roundRecovery: {
    fontSize: 12,
    color: "var(--muted)"
  },
  roundToolList: {
    display: "flex",
    flexWrap: "wrap",
    gap: 6
  },
  roundToolTag: {
    padding: "4px 8px",
    border: "1px solid color-mix(in srgb, var(--accent) 18%, var(--border))",
    background: "color-mix(in srgb, white 88%, var(--accent-soft))",
    color: "var(--accent)",
    fontSize: 12
  },
  statusGrid: {
    display: "flex",
    flexWrap: "wrap",
    gap: "8px 20px",
    padding: "14px 0 0",
    borderTop: "1px solid var(--border)"
  },
  statusItem: {
    display: "flex",
    gap: 6,
    alignItems: "baseline"
  },
  statusLabel: {
    fontSize: 11,
    textTransform: "uppercase",
    letterSpacing: "0.06em",
    color: "var(--muted)",
    fontWeight: 600
  },
  statusValue: {
    fontSize: 13,
    color: "var(--ink)"
  },
  unitSection: {
    display: "grid",
    gap: 10,
    paddingTop: 18,
    borderTop: "1px solid var(--border)"
  },
  unitSectionLabel: {
    fontSize: 11,
    fontWeight: 700,
    textTransform: "uppercase",
    letterSpacing: "0.07em",
    color: "var(--muted)"
  },
  unitList: {
    display: "grid",
    gap: 8
  },
  unitItem: {
    display: "grid",
    gap: 2,
    padding: "10px 12px",
    background: "var(--panel)",
    border: "1px solid var(--border)"
  },
  unitTitleRow: {
    display: "flex",
    alignItems: "flex-start",
    justifyContent: "space-between",
    gap: 10
  },
  unitTitle: {
    fontSize: 13,
    fontWeight: 600,
    color: "var(--ink)"
  },
  unitEditWrap: {
    display: "grid",
    gap: 8
  },
  unitTitleInput: {
    width: "100%",
    minHeight: 36,
    border: "1px solid var(--border-strong)",
    padding: "6px 10px",
    background: "white",
    color: "var(--ink)",
    fontSize: 13,
    fontWeight: 600
  },
  unitActionRow: {
    display: "flex",
    flexWrap: "wrap",
    gap: 8
  },
  unitActionButton: {
    minHeight: 30,
    border: "1px solid var(--border)",
    padding: "0 10px",
    background: "white",
    color: "var(--muted)",
    fontSize: 12,
    cursor: "pointer"
  },
  unitActionButtonPrimary: {
    minHeight: 30,
    border: "none",
    padding: "0 10px",
    background: "var(--accent)",
    color: "white",
    fontSize: 12,
    fontWeight: 600,
    cursor: "pointer"
  },
  unitEditButton: {
    minHeight: 28,
    border: "1px solid var(--border)",
    padding: "0 8px",
    background: "white",
    color: "var(--muted)",
    fontSize: 12,
    cursor: "pointer",
    whiteSpace: "nowrap"
  },
  unitMeta: {
    fontSize: 12,
    color: "var(--muted)"
  }
};

function formatDocumentSummary(document: DocumentRecord) {
  return `${document.title} · ${document.studyUnitCount || document.sections.length} 个单元`;
}

function formatSceneSummary(sceneProfile: SceneProfile) {
  const path = sceneProfile.selectedPath.join(" / ");
  return path ? `${sceneProfile.title} · ${path}` : sceneProfile.title || sceneProfile.sceneName || "未命名场景";
}

function formatSessionStatus(status: string) {
  switch (status) {
    case "active":
      return "进行中";
    case "completed":
      return "已完成";
    default:
      return status || "未知";
  }
}

function formatUnitKind(unitKind: string) {
  switch (unitKind) {
    case "chapter":
      return "章节";
    case "section":
      return "小节";
    default:
      return unitKind || "单元";
  }
}

type PlanRoundStatus = "running" | "completed" | "failed";

interface PlanRoundSummaryItem {
  roundIndex: number;
  status: PlanRoundStatus;
  toolCalls: string[];
  finishReason: string;
  elapsedMs?: number;
  error?: string;
}

interface PlanningQuestionSummaryItem {
  id: string;
  question: string;
  reason: string;
}

function summarizePlanRounds(events: StreamEventItem[]) {
  const rounds = new Map<number, PlanRoundSummaryItem>();
  const planningQuestions = new Map<string, PlanningQuestionSummaryItem>();
  let totalToolCalls = 0;
  let latestMessage = "";

  for (const event of events) {
    const roundIndex = toNumber(event.payload.round_index);
    const ensureRound = () => {
      if (roundIndex === null) {
        return null;
      }
      const current =
        rounds.get(roundIndex) ??
        {
          roundIndex,
          status: "running" as const,
          toolCalls: [],
          finishReason: "",
        };
      rounds.set(roundIndex, current);
      return current;
    };

    if (event.stage === "model_round_started") {
      const round = ensureRound();
      if (round) {
        round.status = "running";
        latestMessage = `Round ${round.roundIndex + 1} 已启动。`;
      }
      continue;
    }

    if (event.stage === "model_tool_call") {
      const round = ensureRound();
      const toolName = String(event.payload.tool_name ?? "").trim();
      if (round && toolName) {
        round.toolCalls.push(toolName);
        totalToolCalls += 1;
        latestMessage = `Round ${round.roundIndex + 1} 调用了工具 ${toolName}。`;
      }
      continue;
    }

    if (event.stage === "planning_question_asked") {
      const questionId = String(event.payload.question_id ?? "").trim();
      const question = String(event.payload.question ?? "").trim();
      if (questionId && question) {
        planningQuestions.set(questionId, {
          id: questionId,
          question,
          reason: String(event.payload.reason ?? "").trim()
        });
        latestMessage = "计划器提出了一个待确认问题。";
      }
      continue;
    }

    if (event.stage === "model_round_completed") {
      const round = ensureRound();
      if (round) {
        round.status = "completed";
        round.finishReason = String(event.payload.finish_reason ?? "").trim();
        round.elapsedMs = toNumber(event.payload.elapsed_ms) ?? undefined;
        latestMessage = `Round ${round.roundIndex + 1} 已完成。`;
      }
      continue;
    }

    if (event.stage === "model_round_failed") {
      const round = ensureRound();
      if (round) {
        round.status = "failed";
        round.finishReason = String(event.payload.finish_reason ?? "").trim();
        round.elapsedMs = toNumber(event.payload.elapsed_ms) ?? undefined;
        round.error = String(event.payload.error ?? "").trim();
        latestMessage = `Round ${round.roundIndex + 1} 失败。`;
      }
      continue;
    }

    if (event.stage === "learning_plan_completed") {
      latestMessage = "学习计划已生成完成。";
      continue;
    }

    if (event.stage === "stream_error") {
      latestMessage = `计划流出错：${String(event.payload.error ?? "未知错误")}`;
      continue;
    }

    if (event.stage === "stream_completed" && !latestMessage) {
      latestMessage = "计划流已完成。";
    }
  }

  return {
    rounds: [...rounds.values()].sort((a, b) => a.roundIndex - b.roundIndex),
    planningQuestions: [...planningQuestions.values()],
    totalToolCalls,
    latestMessage,
  };
}

function toNumber(value: unknown): number | null {
  const next = Number(value);
  return Number.isFinite(next) ? next : null;
}

function formatPlanStreamStatus(status: string) {
  switch (status) {
    case "running":
      return "生成中";
    case "completed":
      return "已完成";
    case "error":
      return "出错";
    default:
      return "未开始";
  }
}

function formatRoundStatus(status: PlanRoundStatus) {
  switch (status) {
    case "completed":
      return "完成";
    case "failed":
      return "失败";
    default:
      return "进行中";
  }
}

function statusBadgeStyle(status: string): CSSProperties {
  if (status === "completed") {
    return {
      ...styles.progressStat,
      color: "var(--accent)",
      borderColor: "color-mix(in srgb, var(--accent) 28%, var(--border))",
      background: "color-mix(in srgb, white 88%, var(--accent-soft))",
    };
  }
  if (status === "error") {
    return {
      ...styles.progressStat,
      color: "var(--danger, #b42318)",
      borderColor: "rgba(180, 35, 24, 0.24)",
      background: "rgba(180, 35, 24, 0.06)",
    };
  }
  if (status === "running") {
    return {
      ...styles.progressStat,
      color: "var(--accent)",
      borderColor: "color-mix(in srgb, var(--accent) 28%, var(--border))",
    };
  }
  return styles.progressStat;
}

function roundStatusBadgeStyle(status: PlanRoundStatus): CSSProperties {
  if (status === "completed") {
    return {
      ...styles.progressStat,
      padding: "3px 8px",
      color: "var(--accent)",
      borderColor: "color-mix(in srgb, var(--accent) 28%, var(--border))",
      background: "color-mix(in srgb, white 88%, var(--accent-soft))",
    };
  }
  if (status === "failed") {
    return {
      ...styles.progressStat,
      padding: "3px 8px",
      color: "var(--danger, #b42318)",
      borderColor: "rgba(180, 35, 24, 0.24)",
      background: "rgba(180, 35, 24, 0.06)",
    };
  }
  return {
    ...styles.progressStat,
    padding: "3px 8px",
    color: "var(--accent)",
  };
}
