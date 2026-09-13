"use client";

import type { CSSProperties } from "react";
import { useEffect, useRef, useState } from "react";
import type {
  PersonaProfile,
} from "@vibe-learner/shared";
import type { PlanSetupPageCache } from "../lib/learning-workspace-page-cache";
import type { SceneLibraryItemPayload } from "../lib/data/scenes";
import { MaterialIcon } from "./material-icon";
import { PersonaSelector } from "./persona-selector";
import { AppLink } from "../lib/app-navigation";

interface DocumentSetupProps {
  personas: PersonaProfile[];
  selectedPersonaId: string;
  onSelectPersonaId: (personaId: string) => void;
  onGenerate: (input: { mode: "document" | "goal_only"; file?: File | null; objective: string }) => void;
  onInterruptGeneration: () => void;
  isBusy: boolean;
  sceneLibraryItems: SceneLibraryItemPayload[];
  selectedSceneLibraryId: string;
  onSelectSceneLibraryId: (sceneId: string) => void;
  planStreamEvents: StreamEventItem[];
  planStreamStatus: string;
  processStreamEvents: StreamEventItem[];
  processStreamStatus: string;
  canInterruptGeneration: boolean;
  isInterruptingGeneration: boolean;
  generationBlockedReason?: string;
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
  onInterruptGeneration,
  isBusy,
  sceneLibraryItems,
  selectedSceneLibraryId,
  onSelectSceneLibraryId,
  planStreamEvents,
  planStreamStatus,
  processStreamEvents,
  processStreamStatus,
  canInterruptGeneration,
  isInterruptingGeneration,
  generationBlockedReason,
  cachedState,
  onCachedStateChange,
}: DocumentSetupProps) {
  const [file, setFile] = useState<File | null>(() => cachedState?.file ?? null);
  const [generationMode, setGenerationMode] = useState<"document" | "goal_only">(
    () => cachedState?.generationMode ?? "document"
  );
  const [objective, setObjective] = useState(
    () => cachedState?.objective ?? "请基于教材结构生成首轮学习计划，先排出清晰、可执行的学习排期。"
  );
  const [showRoundDetails, setShowRoundDetails] = useState(false);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    onCachedStateChange?.({
      generationMode,
      objective,
      file,
    });
  }, [file, generationMode, objective, onCachedStateChange]);

  const planRoundSummary = summarizePlanRounds(planStreamEvents);
  const processProgress = summarizeProcessProgress(processStreamEvents);
  const shouldShowPlanRounds =
    planStreamStatus !== "idle" || planStreamEvents.length > 0 || planRoundSummary.rounds.length > 0;
  const isGenerateDisabled = isBusy || (generationMode === "document" && !file) || Boolean(generationBlockedReason);
  const generateButtonLabel = isBusy ? "处理中…" : generationMode === "document" ? "生成计划" : "按目标生成";
  const shouldShowProcessProgress = generationMode === "document" &&
    (processStreamStatus !== "idle" || processStreamEvents.length > 0);

  const handleGenerate = () => {
    if (generationMode === "document" && !file) {
      return;
    }
    console.info("[vibe-learner] ui:upload_click", {
      mode: generationMode,
      filename: file?.name ?? "",
      sizeBytes: file?.size ?? 0,
      selectedPersonaId
    });
    onGenerate({ mode: generationMode, file, objective });
  };

  return (
    <div className="plan-setup-column" style={styles.wrap}>
      <div style={styles.sectionHead}>
        <span style={styles.sectionTitle}>创建计划</span>
        <div style={styles.sectionActions}>
          <button
            type="button"
            style={{
              ...styles.primaryButton,
              ...(isGenerateDisabled ? styles.buttonDisabled : {})
            }}
            disabled={isGenerateDisabled}
            onClick={handleGenerate}
          >
            <MaterialIcon name="auto_awesome" size={18} />
            {generateButtonLabel}
          </button>
        </div>
      </div>

      <section style={styles.card}>
        <div style={styles.formSection}>
          <div style={styles.field}>
            <label htmlFor="plan-persona" style={styles.fieldLabel}>教师人格</label>
            <PersonaSelector
              personas={personas}
              selectedPersonaId={selectedPersonaId}
              onChange={onSelectPersonaId}
              compact
              selectId="plan-persona"
            />
          </div>

          <div style={styles.field}>
            <label htmlFor="plan-scene" style={styles.fieldLabel}>计划场景</label>
            <select
              id="plan-scene"
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
          </div>
        </div>

        <div style={{ ...styles.formSection, ...styles.formSectionSeparated }}>
          <div style={styles.form}>
            <div style={styles.field}>
              <label htmlFor="plan-generation-mode" style={styles.fieldLabel}>创建方式</label>
              <select
                id="plan-generation-mode"
                value={generationMode}
                onChange={(event) => setGenerationMode(event.target.value === "goal_only" ? "goal_only" : "document")}
                style={styles.select}
              >
                <option value="document">教材 + 目标</option>
                <option value="goal_only">仅学习目标</option>
              </select>
            </div>
            <div style={styles.field}>
              <label htmlFor="plan-document-file" style={styles.fieldLabel}>教材文件（PDF）</label>
              <input
                ref={fileInputRef}
                id="plan-document-file"
                type="file"
                accept=".pdf"
                className="plan-file-input"
                onChange={(event) => setFile(event.target.files?.[0] ?? null)}
                disabled={generationMode === "goal_only"}
              />
              <div className="plan-file-selection" aria-live="polite">
                <button
                  type="button"
                  style={{ ...styles.fileButton, ...(generationMode === "goal_only" ? styles.buttonDisabled : {}) }}
                  disabled={generationMode === "goal_only"}
                  onClick={() => fileInputRef.current?.click()}
                >
                  {file ? "更换教材" : "选择教材"}
                </button>
                <span
                  className="plan-file-name"
                  title={file?.name}
                >
                  {file?.name ?? (generationMode === "goal_only" ? "仅学习目标，无需教材" : "尚未选择文件")}
                </span>
              </div>
            </div>
            <div style={styles.field}>
              <label htmlFor="plan-objective" style={styles.fieldLabel}>学习目标</label>
              <textarea
                id="plan-objective"
                value={objective}
                onChange={(event) => setObjective(event.target.value)}
                style={styles.textarea}
              />
            </div>
          </div>
        </div>

        {generationBlockedReason ? (
          <div style={styles.warningCard}>
            <span style={styles.warningTitle}>开始前需要先修正运行设置</span>
            <span style={styles.warningText}>{generationBlockedReason}</span>
            <AppLink path="/settings" style={styles.warningLink}>
              前往统一设置
            </AppLink>
          </div>
        ) : null}

        {canInterruptGeneration ? (
          <button
            type="button"
            style={{
              ...styles.secondaryButton,
              ...(isInterruptingGeneration ? styles.buttonDisabled : {})
            }}
            disabled={isInterruptingGeneration}
            onClick={onInterruptGeneration}
          >
            <MaterialIcon name="close" size={18} />
            {isInterruptingGeneration ? "中断中…" : "中断当前任务"}
          </button>
        ) : null}

        {shouldShowProcessProgress ? (
          <div style={styles.progressSection} aria-live="polite">
            <div style={styles.progressHeader}>
              <div style={styles.progressHeaderMeta}><span style={styles.progressTitle}>教材解析 / OCR</span></div>
              <span style={statusBadgeStyle(processStreamStatus)}>{formatProcessStreamStatus(processStreamStatus)}</span>
            </div>
            <div style={styles.progressStats}>
              <span style={styles.progressStat}>页面 {processProgress.completedPages}{processProgress.totalPages ? ` / ${processProgress.totalPages}` : ""}</span>
              <span style={styles.progressStat}>阶段 {processProgress.phase}</span>
              {processProgress.rate ? <span style={styles.progressStat}>速率 {processProgress.rate} 页/分钟</span> : null}
              {processProgress.eta ? <span style={styles.progressStat}>预计还需 {processProgress.eta}</span> : null}
            </div>
            {processProgress.warning ? <div style={styles.warningText}>{processProgress.warning}</div> : null}
            {processProgress.error ? <div style={styles.roundError}>{formatProcessError(processProgress.error, processProgress.checkpointSaved)}</div> : null}
          </div>
        ) : null}

        {shouldShowPlanRounds ? (
          <div style={styles.progressSection}>
            <div style={styles.progressHeader}>
              <div style={styles.progressHeaderMeta}>
                <span style={styles.progressTitle}>生成进度</span>
              </div>
              <span style={statusBadgeStyle(planStreamStatus)}>
                {formatPlanStreamStatus(planStreamStatus)}
              </span>
            </div>

            <div style={styles.progressStats}>
              <span style={styles.progressStat}>轮次 {planRoundSummary.rounds.length}</span>
              <span style={styles.progressStat}>调用 {planRoundSummary.totalToolCalls}</span>
              <span style={styles.progressStat}>问题 {planRoundSummary.planningQuestions.length}</span>
              <span style={styles.progressStat}>Token {planRoundSummary.totalTokens || "—"}</span>
              <span style={styles.progressStat}>耗时 {formatElapsed(planRoundSummary.totalElapsedMs)}</span>
              {planRoundSummary.repairCount ? <span style={styles.progressStat}>修复 {planRoundSummary.repairCount} 次</span> : null}
            </div>

            {planRoundSummary.latestMessage ? (
              <div style={styles.progressNotice}>{planRoundSummary.latestMessage}</div>
            ) : null}

            {planRoundSummary.planningQuestions.length ? (
              <div style={styles.questionNotice}>
                {planRoundSummary.planningQuestions.map((item) => (
                  <div key={item.id} style={styles.questionNoticeItem}>
                    <strong style={styles.questionNoticeLabel}>待回答</strong>
                    <span>{item.question}</span>
                    {item.reason ? <span style={styles.questionNoticeReason}>备注：{item.reason}</span> : null}
                  </div>
                ))}
              </div>
            ) : null}

            {planRoundSummary.rounds.length ? (
              <div style={styles.foldSection}>
                <button
                  type="button"
                  style={styles.foldButton}
                  onClick={() => setShowRoundDetails((current) => !current)}
                >
                  {showRoundDetails ? "收起调用细节" : `查看调用细节 · ${planRoundSummary.rounds.length} 轮`}
                </button>

                {showRoundDetails ? (
                  <div style={styles.roundList}>
                    {planRoundSummary.rounds.map((round) => (
                      <div key={round.roundIndex} style={styles.roundCard}>
                        <div style={styles.roundHeader}>
                          <strong style={styles.roundTitle}>第 {round.roundIndex + 1} 轮</strong>
                          <span style={roundStatusBadgeStyle(round.status)}>
                            {formatRoundStatus(round.status)}
                          </span>
                        </div>
                        <span style={styles.roundMeta}>
                          工具 {round.toolCalls.length}
                          {round.finishReason ? ` · finish=${round.finishReason}` : ""}
                          {typeof round.elapsedMs === "number" ? ` · ${round.elapsedMs} ms` : ""}
                        </span>
                        {round.error ? <span style={styles.roundError}>出错：{round.error}</span> : null}
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
                ) : null}
              </div>
            ) : null}
          </div>
        ) : null}
      </section>
    </div>
  );
}

const styles: Record<string, CSSProperties> = {
  wrap: {
    display: "grid",
    gap: 16,
    paddingTop: 14,
    paddingRight: 4,
  },
  sectionHead: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 12,
    flexWrap: "wrap",
    minHeight: 24,
    paddingBottom: 10,
    borderBottom: "1px solid color-mix(in srgb, var(--border) 76%, white)"
  },
  sectionTitle: {
    fontSize: 10,
    fontWeight: 700,
    letterSpacing: "0.12em",
    textTransform: "uppercase",
    color: "var(--muted)"
  },
  sectionActions: {
    display: "flex",
    flexWrap: "wrap",
    gap: 8
  },
  card: {
    display: "grid",
    gap: 14,
    padding: 0,
    border: "none",
    background: "transparent"
  },
  formSection: {
    display: "grid",
    gap: 12,
  },
  formSectionSeparated: {
    paddingTop: 14,
    borderTop: "1px solid color-mix(in srgb, var(--border) 68%, white)",
  },
  form: {
    display: "grid",
    gap: 12
  },
  field: {
    display: "grid",
    gap: 7
  },
  fieldLabel: {
    fontSize: 11,
    fontWeight: 600,
    letterSpacing: "0.04em",
    textTransform: "uppercase",
    color: "var(--muted)"
  },
  textarea: {
    width: "100%",
    minHeight: 96,
    border: "1px solid color-mix(in srgb, var(--border) 76%, white)",
    padding: "10px 12px",
    background: "color-mix(in srgb, white 72%, var(--surface))",
    resize: "vertical",
    fontSize: 14,
    lineHeight: 1.65,
    color: "var(--ink)"
  },
  fileButton: {
    minHeight: 38,
    border: "1px solid color-mix(in srgb, var(--border) 76%, white)",
    padding: "0 12px",
    background: "color-mix(in srgb, white 72%, var(--surface))",
    color: "var(--ink)",
    fontSize: 13,
    fontWeight: 600,
    cursor: "pointer",
    flexShrink: 0,
  },
  select: {
    width: "100%",
    height: 38,
    border: "1px solid color-mix(in srgb, var(--border) 76%, white)",
    padding: "0 10px",
    background: "color-mix(in srgb, white 72%, var(--surface))",
    color: "var(--ink)",
    fontSize: 14
  },
  primaryButton: {
    border: "none",
    minHeight: 32,
    padding: "0 12px",
    background: "var(--accent)",
    color: "white",
    fontWeight: 600,
    cursor: "pointer",
    fontSize: 11,
    justifySelf: "start",
    display: "inline-flex",
    alignItems: "center",
    gap: 8
  },
  secondaryButton: {
    border: "none",
    minHeight: 36,
    padding: "0 14px",
    background: "color-mix(in srgb, white 84%, var(--negative) 16%)",
    color: "var(--danger, #b42318)",
    fontWeight: 600,
    cursor: "pointer",
    fontSize: 12,
    justifySelf: "start",
    display: "inline-flex",
    alignItems: "center",
    gap: 8
  },
  buttonDisabled: {
    opacity: 0.45,
    cursor: "not-allowed"
  },
  warningCard: {
    display: "grid",
    gap: 6,
    padding: "12px 14px",
    border: "none",
    background: "color-mix(in srgb, white 84%, var(--negative) 16%)",
  },
  warningTitle: {
    fontSize: 11,
    fontWeight: 700,
    letterSpacing: "0.08em",
    textTransform: "uppercase",
    color: "var(--danger, #b42318)",
  },
  warningText: {
    fontSize: 13,
    lineHeight: 1.6,
    color: "var(--ink-2)",
  },
  warningLink: {
    width: "fit-content",
    fontSize: 13,
    fontWeight: 600,
    color: "var(--accent)",
  },
  progressSection: {
    display: "grid",
    gap: 10,
    paddingTop: 16,
    borderTop: "1px solid color-mix(in srgb, var(--border) 68%, white)"
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
    fontSize: 10,
    fontWeight: 700,
    color: "var(--ink)",
    textTransform: "uppercase",
    letterSpacing: "0.12em"
  },
  progressMeta: {
    fontSize: 11,
    color: "var(--muted)",
    lineHeight: 1.5
  },
  progressStats: {
    display: "flex",
    flexWrap: "wrap",
    gap: 6
  },
  progressStat: {
    padding: "5px 8px",
    border: "none",
    background: "color-mix(in srgb, white 68%, var(--surface))",
    fontSize: 11,
    color: "var(--muted)"
  },
  progressNotice: {
    padding: "8px 10px",
    border: "none",
    background: "color-mix(in srgb, white 68%, var(--surface))",
    color: "var(--ink)",
    fontSize: 13,
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
    border: "none",
    background: "color-mix(in srgb, white 68%, var(--surface))",
    fontSize: 13,
    color: "var(--ink)",
    lineHeight: 1.6
  },
  questionNoticeLabel: {
    fontSize: 10,
    color: "var(--muted)",
    textTransform: "uppercase",
    letterSpacing: "0.12em"
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
    border: "none",
    background: "color-mix(in srgb, white 68%, var(--surface))"
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
    border: "1px solid var(--border)",
    background: "white",
    color: "var(--muted)",
    fontSize: 12
  },
  foldSection: {
    display: "grid",
    gap: 10
  },
  foldButton: {
    minHeight: 30,
    width: "fit-content",
    border: "1px solid color-mix(in srgb, var(--accent) 18%, var(--border))",
    padding: "0 10px",
    background: "white",
    color: "var(--accent)",
    fontSize: 12,
    fontWeight: 600,
    cursor: "pointer"
  }
};

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
  let totalTokens = 0;
  let totalElapsedMs = 0;
  let repairCount = 0;

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
        latestMessage = `第 ${round.roundIndex + 1} 轮开始。`;
      }
      continue;
    }

    if (event.stage === "model_tool_call") {
      const round = ensureRound();
      const toolName = String(event.payload.tool_name ?? "").trim();
      if (round && toolName) {
        round.toolCalls.push(toolName);
        totalToolCalls += 1;
        latestMessage = `第 ${round.roundIndex + 1} 轮调用了 ${toolName}。`;
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
        latestMessage = "有待回答问题。";
      }
      continue;
    }

    if (event.stage === "model_round_completed") {
      const round = ensureRound();
      if (round) {
        round.status = "completed";
        round.finishReason = String(event.payload.finish_reason ?? "").trim();
        round.elapsedMs = toNumber(event.payload.elapsed_ms) ?? undefined;
        totalElapsedMs += round.elapsedMs ?? 0;
        totalTokens += toNumber(event.payload.total_tokens) ?? toNumber(event.payload.completion_tokens) ?? 0;
        latestMessage = `第 ${round.roundIndex + 1} 轮完成。`;
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
        totalTokens += toNumber(event.payload.total_tokens) ?? toNumber(event.payload.completion_tokens) ?? 0;
        latestMessage = `第 ${round.roundIndex + 1} 轮失败。`;
      }
      continue;
    }

    if (event.stage.includes("repair") || event.stage === "schema_repair") {
      repairCount += 1;
    }

    if (event.stage === "learning_plan_completed") {
      latestMessage = "计划已生成。";
      continue;
    }

    if (event.stage === "stream_error") {
      latestMessage = `生成出错：${String(event.payload.error ?? "未知错误")}`;
      continue;
    }

    if (event.stage === "stream_cancelled") {
      latestMessage = "生成已中断。";
      continue;
    }

    if (event.stage === "stream_completed" && !latestMessage) {
      latestMessage = "生成完成。";
    }
  }

  return {
    rounds: [...rounds.values()].sort((a, b) => a.roundIndex - b.roundIndex),
    planningQuestions: [...planningQuestions.values()],
    totalToolCalls,
    totalTokens,
    totalElapsedMs,
    repairCount,
    latestMessage,
  };
}

function summarizeProcessProgress(events: StreamEventItem[]) {
  let totalPages = 0;
  let completedPages = 0;
  let phase = "等待开始";
  let warning = "";
  let error = "";
  let checkpointSaved: boolean | null = null;
  for (const event of events) {
    totalPages = Math.max(totalPages, toNumber(event.payload.page_count) ?? 0);
    completedPages = Math.max(completedPages, toNumber(event.payload.processed_pages) ?? toNumber(event.payload.page_number) ?? 0);
    if (event.stage === "parser_started") phase = "读取目录与页面";
    if (event.stage === "page_parsed") phase = event.payload.used_ocr ? "OCR 回退识别" : "提取页面文本";
    if (event.stage === "margin_patterns_detected") phase = "清理页眉页脚";
    if (event.stage === "study_units_built") phase = "整理学习单元";
    if (event.stage === "ocr_failed" || event.payload.extraction_source === "ocr_failed") warning = "部分页面 OCR 失败，结果可能缺少文字。";
    if (event.stage === "stream_error") error = String(event.payload.error ?? "未知错误");
    if (typeof event.payload.checkpoint_saved === "boolean") checkpointSaved = event.payload.checkpoint_saved;
  }
  const last = events.at(-1);
  const elapsedMs = toNumber(last?.payload.elapsed_ms) ?? 0;
  const rate = completedPages && elapsedMs > 0 ? Math.round(completedPages / (elapsedMs / 60000)) : 0;
  const remaining = totalPages > completedPages && rate ? Math.ceil((totalPages - completedPages) / rate) : 0;
  return { totalPages, completedPages, phase, warning, error, checkpointSaved, rate: rate || 0, eta: remaining ? `${remaining} 分钟` : "" };
}

function formatElapsed(value: number) {
  if (!value) return "进行中";
  return value < 1000 ? `${value} ms` : `${(value / 1000).toFixed(1)} s`;
}

function formatProcessStreamStatus(status: string) {
  if (status === "running") return "解析中";
  if (status === "completed") return "已完成";
  if (status === "cancelled") return "已中断";
  if (status === "error") return "失败";
  return "未开始";
}

function formatProcessError(error: string, checkpointSaved: boolean | null) {
  const checkpoint = checkpointSaved === true ? "已保存 checkpoint" : checkpointSaved === false ? "未保存 checkpoint" : "checkpoint 状态未返回";
  if (error.includes("ocr_unavailable")) return `OCR 引擎暂不可用（${checkpoint}）；请检查运行设置或拆分 PDF 后重试。`;
  if (error.includes("ocr_partial") || error.includes("ocr_failed")) return `部分页面 OCR 失败（${checkpoint}）；可拆分 PDF、调整 OCR 设置后重试。`;
  if (error.includes("timeout")) return `教材解析超时（${checkpoint}）；可拆分 PDF 或调整运行上限后重试。`;
  return `教材解析失败（${checkpoint}）；请检查 OCR 引擎、拆分 PDF 后重试。`;
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
    case "cancelled":
      return "已中断";
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
  if (status === "cancelled") {
    return {
      ...styles.progressStat,
      color: "#8a5a00",
      borderColor: "rgba(138, 90, 0, 0.24)",
      background: "rgba(138, 90, 0, 0.06)",
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
