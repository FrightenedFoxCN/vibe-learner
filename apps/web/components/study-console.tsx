"use client";

import type { CSSProperties, Dispatch, SetStateAction } from "react";
import { useEffect, useRef, useState } from "react";
import type {
  CharacterStateEvent,
  Citation,
  InteractiveQuestion,
  PersonaProfile,
  SceneProfile,
  SessionAffinityState,
  SessionFollowUp,
  SessionPlanConfirmation,
  StudyChatResponse,
  StudySessionRecord
} from "@vibe-learner/shared";

import { CharacterShell } from "./character-shell";
import { MaterialIcon } from "./material-icon";
import { RichTextMessage } from "./rich-text-message";
import type { StudyConsolePageCache } from "../lib/learning-workspace-page-cache";

interface StudyConsoleProps {
  isPending: boolean;
  selectedPlanId: string;
  planOptions: Array<{ id: string; title: string }>;
  onSelectPlan: (planId: string) => void;
  onCreateSession?: () => void;
  showCreateSession?: boolean;
  onAsk: (message: string, attachments: File[]) => Promise<boolean> | boolean;
  onSubmitQuestionAttempt: (input: {
    questionType: "multiple_choice" | "fill_blank";
    prompt: string;
    topic: string;
    difficulty: "easy" | "medium" | "hard";
    options: Array<{ key: string; text: string }>;
    callBack?: boolean;
    answerKey?: string;
    acceptedAnswers: string[];
    submittedAnswer: string;
    isCorrect: boolean;
    explanation: string;
  }) => void | Promise<void>;
  onChangeSchedule: (scheduleId: string) => void;
  onOpenCitation?: (citation: Citation) => void;
  onJumpToScheduleStart?: () => void;
  canJumpToScheduleStart?: boolean;
  onCompleteCurrentSchedule?: () => void | Promise<void>;
  canCompleteCurrentSchedule?: boolean;
  chatErrorMessage?: string;
  onRetryLastAsk?: () => void | Promise<void>;
  selectedScheduleId: string;
  scheduleOptions: Array<{ id: string; title: string }>;
  turns: StudySessionRecord["turns"];
  session: StudyChatResponse | null;
  persona: PersonaProfile;
  sceneProfile?: SceneProfile | null;
  pendingFollowUps?: SessionFollowUp[];
  isDialogueInterrupted?: boolean;
  onInterruptDialogue?: () => void | Promise<void>;
  affinityState?: SessionAffinityState;
  planConfirmations?: SessionPlanConfirmation[];
  onResolvePlanConfirmation?: (input: {
    confirmationId: string;
    decision: "approve" | "reject";
    note?: string;
  }) => void | Promise<unknown>;
  chatImageUploadEnabled?: boolean;
  pendingComposerInsert?: {
    id: string;
    text: string;
  } | null;
  onConsumeComposerInsert?: () => void;
  disabled?: boolean;
  cachedState?: StudyConsolePageCache;
  onCachedStateChange?: (state: StudyConsolePageCache) => void;
}

export function StudyConsole({
  isPending,
  selectedPlanId,
  planOptions,
  onSelectPlan,
  onCreateSession,
  showCreateSession = false,
  onAsk,
  onSubmitQuestionAttempt,
  onChangeSchedule,
  onOpenCitation,
  onJumpToScheduleStart,
  canJumpToScheduleStart,
  onCompleteCurrentSchedule,
  canCompleteCurrentSchedule,
  chatErrorMessage,
  onRetryLastAsk,
  selectedScheduleId,
  scheduleOptions,
  turns,
  session,
  persona,
  sceneProfile,
  pendingFollowUps = [],
  isDialogueInterrupted = false,
  onInterruptDialogue,
  affinityState,
  planConfirmations = [],
  onResolvePlanConfirmation,
  chatImageUploadEnabled,
  pendingComposerInsert,
  onConsumeComposerInsert,
  disabled,
  cachedState,
  onCachedStateChange,
}: StudyConsoleProps) {
  const [message, setMessage] = useState(
    () => cachedState?.message ?? "请解释这一章的核心概念，并给我一个复述练习。"
  );
  const [attachments, setAttachments] = useState<File[]>(() => cachedState?.attachments ?? []);
  const [selectedChoices, setSelectedChoices] = useState<Record<string, string>>(
    () => cachedState?.selectedChoices ?? {}
  );
  const [blankAnswers, setBlankAnswers] = useState<Record<string, string>>(
    () => cachedState?.blankAnswers ?? {}
  );
  const [questionFeedback, setQuestionFeedback] = useState<Record<string, { ok: boolean; text: string }>>(
    () => cachedState?.questionFeedback ?? {}
  );
  const [expandedExplanation, setExpandedExplanation] = useState<Record<string, boolean>>(
    () => cachedState?.expandedExplanation ?? {}
  );
  const transcriptRef = useRef<HTMLDivElement | null>(null);
  const attachmentInputRef = useRef<HTMLInputElement | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const activeFollowUp = pendingFollowUps.find((item) => item.status === "pending") ?? null;

  const sortedTurns = [...turns].sort((a, b) => {
    const aTime = Date.parse(a.createdAt || "") || 0;
    const bTime = Date.parse(b.createdAt || "") || 0;
    return aTime - bTime;
  });

  useEffect(() => {
    const node = transcriptRef.current;
    if (!node) return;
    node.scrollTop = node.scrollHeight;
  }, [sortedTurns.length, session?.reply, chatErrorMessage]);

  useEffect(() => {
    if (!pendingComposerInsert?.id || !pendingComposerInsert.text) {
      return;
    }
    setMessage((current) => {
      const trimmed = current.trimEnd();
      const prefix = trimmed ? `${trimmed}\n\n` : "";
      return `${prefix}${pendingComposerInsert.text}`;
    });
    textareaRef.current?.focus();
    onConsumeComposerInsert?.();
  }, [onConsumeComposerInsert, pendingComposerInsert]);

  useEffect(() => {
    onCachedStateChange?.({
      message,
      attachments,
      selectedChoices,
      blankAnswers,
      questionFeedback,
      expandedExplanation,
    });
  }, [
    attachments,
    blankAnswers,
    expandedExplanation,
    message,
    onCachedStateChange,
    questionFeedback,
    selectedChoices,
  ]);

  useEffect(() => {
    const node = textareaRef.current;
    if (!node) return;
    node.style.height = "0px";
    node.style.height = `${Math.min(node.scrollHeight, 220)}px`;
  }, [message]);

  return (
    <div style={styles.wrap}>
      <div className="study-console-layout" style={styles.consoleCard}>
        <section style={styles.chatPanel}>
          <div style={styles.transcript}>
            {turns.length ? (
              <div ref={transcriptRef} style={styles.turnList}>
                {sortedTurns.map((turn, index) => (
                  <div
                    key={buildTurnKey(turn.createdAt, index)}
                    style={styles.turnCard}
                  >
                    {!isHiddenLearnerMessage(turn) ? (
                      <div style={styles.userSection}>
                        <div style={{ ...styles.turnMeta, ...styles.turnMetaRight }}>
                          <span style={styles.timeLabel}>{formatTurnTime(turn.createdAt)}</span>
                          <span style={styles.roleLabel}>你</span>
                        </div>
                        <p style={styles.userMessage}>{formatLearnerMessage(turn)}</p>
                        {turn.learnerAttachments?.length ? (
                          <div style={styles.attachmentChipRow}>
                            {turn.learnerAttachments.map((attachment) => (
                              <span key={attachment.attachmentId} style={styles.attachmentChip}>
                                {formatAttachmentLabel(attachment)}
                              </span>
                            ))}
                          </div>
                        ) : null}
                      </div>
                    ) : null}

                    <div style={styles.aiSection}>
                      <div style={styles.turnMeta}>
                        <span style={styles.aiLabel}>{persona.name}</span>
                        <span style={styles.timeLabel}>{formatTurnTime(turn.createdAt)}</span>
                      </div>
                      <div style={styles.aiBubble}>
                        <RichTextMessage
                          content={buildRenderableReply(turn.assistantReply, turn.richBlocks)}
                          style={styles.aiMessage}
                        />
                        <CharacterEventInline events={turn.characterEvents} />
                      {turn.interactiveQuestion ? (
                        <div style={styles.questionWrap}>
                            {renderInteractiveQuestion({
                              question: turn.interactiveQuestion,
                              turnKey: buildTurnKey(turn.createdAt, index),
                              selectedChoices,
                              blankAnswers,
                              questionFeedback,
                              setSelectedChoices,
                              setBlankAnswers,
                              setQuestionFeedback,
                              expandedExplanation,
                              setExpandedExplanation,
                              onAsk,
                              onSubmitQuestionAttempt,
                              disabled: Boolean(disabled || isPending)
                            })}
                          </div>
                        ) : null}
                        {turn.citations.length ? (
                          <div style={styles.citations}>
                            {turn.citations.map((citation, citationIndex) => (
                              <button
                                key={`${turn.createdAt}:${citation.sectionId}:${citation.pageStart}:${citation.pageEnd}:${citationIndex}`}
                                type="button"
                                style={styles.citation}
                                onClick={() => { if (onOpenCitation) onOpenCitation(citation); }}
                                title={`跳转到 p.${citation.pageStart}–${citation.pageEnd}`}
                                disabled={!onOpenCitation}
                              >
                                {citation.title} · p.{citation.pageStart}–{citation.pageEnd}
                              </button>
                            ))}
                          </div>
                        ) : null}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            ) : session?.reply ? (
              <div ref={transcriptRef} style={styles.turnList}>
                <div style={styles.turnCard}>
                  <div style={styles.aiSection}>
                    <div style={styles.turnMeta}>
                      <span style={styles.aiLabel}>{persona.name}</span>
                    </div>
                    <div style={styles.aiBubble}>
                      <RichTextMessage
                        content={buildRenderableReply(session.reply, session.richBlocks)}
                        style={styles.aiMessage}
                      />
                      <CharacterEventInline events={session.characterEvents} />
                      {session.citations.length ? (
                        <div style={styles.citations}>
                          {session.citations.map((citation, index) => (
                            <button
                              key={`${citation.sectionId}:${citation.pageStart}:${citation.pageEnd}:${index}`}
                              type="button"
                              style={styles.citation}
                              onClick={() => { if (onOpenCitation) onOpenCitation(citation); }}
                              title={`跳转到 p.${citation.pageStart}–${citation.pageEnd}`}
                              disabled={!onOpenCitation}
                            >
                              {citation.title} · p.{citation.pageStart}–{citation.pageEnd}
                            </button>
                          ))}
                        </div>
                      ) : null}
                    </div>
                  </div>
                </div>
              </div>
            ) : (
              <div style={styles.emptyTranscriptCard}>
                <p style={styles.emptyTranscriptText}>开始提问后会显示在这里。</p>
              </div>
            )}
          </div>

          {chatErrorMessage ? (
            <div style={styles.errorBox}>
              <span style={styles.errorTitle}>对话请求失败</span>
              <span style={styles.errorText}>{chatErrorMessage}</span>
              <button
                type="button"
                style={{
                  ...styles.retryBtn,
                  ...(isPending || disabled || !onRetryLastAsk ? styles.btnDisabled : {})
                }}
                disabled={isPending || disabled || !onRetryLastAsk}
                onClick={() => { if (onRetryLastAsk) void onRetryLastAsk(); }}
              >
                {isPending ? "重试中…" : "重试"}
              </button>
            </div>
          ) : null}

          {planConfirmations.filter((item) => item.status === "pending").length ? (
            <div style={styles.confirmationStack}>
              {planConfirmations
                .filter((item) => item.status === "pending")
                .map((item) => (
                  <div key={item.id} style={styles.confirmationCard}>
                    <div style={styles.confirmationHead}>
                      <span style={styles.confirmationTitle}>{item.title}</span>
                      <span style={styles.confirmationMeta}>{formatToolName(item.toolName)}</span>
                    </div>
                    <p style={styles.confirmationSummary}>{item.summary || "请确认这项调整。"}</p>
                    {item.previewLines.length ? (
                      <div style={styles.confirmationLines}>
                        {item.previewLines.map((line, index) => (
                          <span key={`${item.id}:${index}`} style={styles.confirmationLine}>{line}</span>
                        ))}
                      </div>
                    ) : null}
                    <div style={styles.confirmationActions}>
                      <button
                        type="button"
                        style={{
                          ...styles.confirmApproveBtn,
                          ...(disabled || isPending || !onResolvePlanConfirmation ? styles.btnDisabled : {})
                        }}
                        disabled={disabled || isPending || !onResolvePlanConfirmation}
                        onClick={() => { if (onResolvePlanConfirmation) void onResolvePlanConfirmation({ confirmationId: item.id, decision: "approve" }); }}
                      >
                        确认应用
                      </button>
                      <button
                        type="button"
                        style={{
                          ...styles.confirmRejectBtn,
                          ...(disabled || isPending || !onResolvePlanConfirmation ? styles.btnDisabled : {})
                        }}
                        disabled={disabled || isPending || !onResolvePlanConfirmation}
                        onClick={() => { if (onResolvePlanConfirmation) void onResolvePlanConfirmation({ confirmationId: item.id, decision: "reject" }); }}
                      >
                        暂不应用
                      </button>
                    </div>
                  </div>
                ))}
            </div>
          ) : null}

          <div style={styles.inputArea}>
            <div style={styles.inputStack}>
              <textarea
                ref={textareaRef}
                style={styles.textarea}
                value={message}
                onChange={(event) => setMessage(event.target.value)}
              />
              <div style={styles.attachmentToolbar}>
                <input
                  ref={attachmentInputRef}
                  type="file"
                  multiple
                  accept={chatImageUploadEnabled ? "image/*,.pdf,.txt,.md,.markdown,.json,.csv,.log,.yaml,.yml,.xml" : ".pdf,.txt,.md,.markdown,.json,.csv,.log,.yaml,.yml,.xml"}
                  style={styles.hiddenFileInput}
                  onChange={(event) => {
                    const nextFiles = Array.from(event.target.files ?? []);
                    if (!nextFiles.length) {
                      return;
                    }
                    setAttachments((current) => {
                      const deduped = [...current];
                      nextFiles.forEach((file) => {
                        if (deduped.some((item) => item.name === file.name && item.size === file.size && item.type === file.type)) {
                          return;
                        }
                        deduped.push(file);
                      });
                      return deduped.slice(0, 4);
                    });
                    event.currentTarget.value = "";
                  }}
                />
                <button
                  type="button"
                  style={{
                    ...styles.iconToolButton,
                    ...(disabled || isPending ? styles.btnDisabled : {})
                  }}
                  disabled={disabled || isPending}
                  onClick={() => attachmentInputRef.current?.click()}
                  aria-label="添加附件"
                  title="添加附件"
                >
                  <MaterialIcon name="attach_file" size={16} />
                </button>
                {onInterruptDialogue ? (
                  <button
                    type="button"
                    style={{
                      ...styles.iconToolButton,
                      ...(disabled || isPending || isDialogueInterrupted ? styles.btnDisabled : {})
                    }}
                    disabled={disabled || isPending || isDialogueInterrupted}
                  onClick={() => { void onInterruptDialogue(); }}
                  aria-label={isDialogueInterrupted ? "已举手打断" : "举手打断"}
                  title={isDialogueInterrupted ? "已举手打断" : "举手打断"}
                >
                    <MaterialIcon name="front_hand" size={16} />
                  </button>
                ) : null}
                <button
                  style={{
                    ...styles.iconSendButton,
                    ...(isPending || disabled ? styles.btnDisabled : {})
                  }}
                  disabled={isPending || disabled}
                  onClick={async () => {
                    const didSend = await onAsk(message, attachments);
                    if (!didSend) {
                      return;
                    }
                    setMessage("");
                    setAttachments([]);
                  }}
                  aria-label={isPending ? "发送中" : "发送"}
                  title={isPending ? "发送中" : "发送"}
                >
                  <MaterialIcon name="send" size={16} />
                </button>
              </div>
              {attachments.length ? (
                <div style={styles.attachmentDraftList}>
                  {attachments.map((file) => (
                    <div key={`${file.name}:${file.size}:${file.type}`} style={styles.attachmentDraftItem}>
                      <span style={styles.attachmentDraftText}>
                        {file.name} · {formatFileSize(file.size)}{file.type.startsWith("image/") ? " · 图片" : ""}
                      </span>
                      <button
                        type="button"
                        style={{
                          ...styles.attachmentRemoveBtn,
                          ...(disabled || isPending ? styles.btnDisabled : {})
                        }}
                        disabled={disabled || isPending}
                        onClick={() => {
                          setAttachments((current) =>
                            current.filter((item) => !(item.name === file.name && item.size === file.size && item.type === file.type))
                          );
                        }}
                      >
                        移除
                      </button>
                    </div>
                  ))}
                </div>
              ) : null}
            </div>
          </div>

        </section>

        <aside style={styles.sidebar}>
          <div style={styles.sidebarStack}>
            <div style={styles.controlCard}>
              <div style={styles.controlStack}>
                <div style={styles.themeRow}>
                  <label style={{ ...styles.themeLabel, ...styles.primarySelectLabel }}>
                    <span style={styles.caption}>学习计划</span>
                    <select
                      style={styles.select}
                      value={selectedPlanId}
                      onChange={(event) => onSelectPlan(event.target.value)}
                      disabled={!planOptions.length}
                      title={planOptions.find((item) => item.id === selectedPlanId)?.title || "暂无学习计划"}
                    >
                      {planOptions.length ? (
                        planOptions.map((item) => (
                          <option key={item.id} value={item.id}>{item.title}</option>
                        ))
                      ) : (
                        <option value="">暂无学习计划</option>
                      )}
                    </select>
                  </label>
                  {showCreateSession ? (
                    <button
                      type="button"
                      style={{
                        ...styles.primaryBtn,
                        ...(isPending || !onCreateSession ? styles.btnDisabled : {})
                      }}
                      disabled={isPending || !onCreateSession}
                      onClick={() => { if (onCreateSession) onCreateSession(); }}
                    >
                      {isPending ? "创建中…" : "创建会话"}
                    </button>
                  ) : null}
                </div>

                <div style={styles.themeRow}>
                  <label style={styles.themeLabel}>
                    <span style={styles.caption}>排期项</span>
                    <select
                      style={styles.select}
                      value={selectedScheduleId}
                      onChange={(event) => onChangeSchedule(event.target.value)}
                      disabled={isPending || disabled}
                      title={scheduleOptions.find((item) => item.id === selectedScheduleId)?.title || "暂无排期项"}
                    >
                      {scheduleOptions.length ? (
                        scheduleOptions.map((item) => (
                          <option key={item.id} value={item.id}>{item.title}</option>
                        ))
                      ) : (
                        <option value="">暂无排期项</option>
                      )}
                    </select>
                  </label>
                </div>

                <div style={styles.themeRow}>
                  <button
                    type="button"
                    style={{
                      ...styles.ghostBtn,
                      ...(isPending || disabled || !onJumpToScheduleStart || !canJumpToScheduleStart ? styles.btnDisabled : {})
                    }}
                    disabled={isPending || disabled || !onJumpToScheduleStart || !canJumpToScheduleStart}
                    onClick={() => { if (onJumpToScheduleStart) onJumpToScheduleStart(); }}
                  >
                    定位排期首页
                  </button>
                  <button
                    type="button"
                    style={{
                      ...styles.primaryBtn,
                      ...(isPending || disabled || !onCompleteCurrentSchedule || !canCompleteCurrentSchedule ? styles.btnDisabled : {})
                    }}
                    disabled={isPending || disabled || !onCompleteCurrentSchedule || !canCompleteCurrentSchedule}
                    onClick={() => { if (onCompleteCurrentSchedule) void onCompleteCurrentSchedule(); }}
                  >
                    完成当前排期
                  </button>
                </div>
              </div>
            </div>

            <div style={styles.companionCard}>
              <div style={styles.companionMeta}>
                <div style={styles.companionHeader}>
                  <span style={styles.caption}>教师人格</span>
                </div>
                <div style={styles.companionRow}>
                  <span style={styles.companionChip}>人格 · {persona.name}</span>
                  <span style={styles.companionChip}>场景 · {sceneProfile?.title || "未设置"}</span>
                </div>
                <p style={styles.companionSummary}>
                  {sceneProfile?.summary || persona.summary || "尚未配置场景摘要。"}
                </p>
              </div>
              <div style={styles.shellCard}>
                <CharacterShell
                  persona={persona}
                  response={session}
                  pending={isPending}
                  turnCount={turns.length}
                  affinityState={affinityState}
                  nextFollowUp={activeFollowUp}
                  variant="embedded"
                />
              </div>
            </div>
          </div>
        </aside>
      </div>
    </div>
  );
}

const styles: Record<string, CSSProperties> = {
  wrap: {
    display: "block",
    width: "100%",
  },
  consoleCard: {
    display: "grid",
    gridTemplateColumns: "minmax(0, 1fr) 280px",
    gap: 10,
    alignItems: "start",
    width: "100%",
  },
  chatPanel: {
    display: "grid",
    gridTemplateRows: "minmax(0, 1fr) auto auto",
    gap: 12,
    minWidth: 0,
    width: "100%",
    minHeight: "calc(100vh - 220px)",
    padding: 0,
    background: "transparent",
  },
  controlStack: {
    display: "grid",
    gap: 10,
    background: "transparent",
    minWidth: 0,
  },
  controlCard: {
    display: "grid",
    gap: 10,
    border: "1px solid var(--border)",
    background: "white",
    padding: "12px",
    minWidth: 0,
    overflow: "hidden",
  },
  sidebar: {
    minWidth: 0,
    width: 280,
    maxWidth: 280,
    position: "sticky",
    top: "calc(var(--study-heading-offset, 112px) + 18px)",
  },
  sidebarStack: {
    display: "grid",
    gap: 10,
    minWidth: 0,
  },
  companionCard: {
    display: "grid",
    gap: 10,
    border: "1px solid var(--border)",
    background: "white",
    padding: "12px",
    minWidth: 0,
    overflow: "hidden",
  },
  companionMeta: {
    display: "grid",
    gap: 6,
    alignContent: "start",
  },
  companionHeader: {
    display: "flex",
    gap: 8,
    alignItems: "center",
  },
  companionRow: {
    display: "flex",
    gap: 6,
    flexWrap: "wrap",
    minWidth: 0,
  },
  companionChip: {
    fontSize: 12,
    color: "var(--ink-2)",
    border: "1px solid var(--border)",
    background: "var(--panel)",
    padding: "2px 8px",
    minWidth: 0,
    maxWidth: "100%",
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap",
  },
  companionSummary: {
    margin: 0,
    fontSize: 12,
    color: "var(--muted)",
    lineHeight: 1.6,
    minWidth: 0,
    wordBreak: "break-word",
    overflowWrap: "anywhere",
  },
  shellCard: {
    minWidth: 0,
    padding: 0,
  },
  themeRow: {
    display: "flex",
    alignItems: "flex-end",
    gap: 8,
    flexWrap: "wrap",
    minWidth: 0,
    width: "100%",
  },
  themeLabel: {
    display: "grid",
    gap: 4,
    flex: 1,
    minWidth: 0,
  },
  primarySelectLabel: {
    flex: "1.4 1 320px",
  },
  caption: {
    fontSize: 11,
    fontWeight: 600,
    letterSpacing: "0.07em",
    textTransform: "uppercase",
    color: "var(--muted)",
  },
  select: {
    width: "100%",
    height: 36,
    border: "1px solid var(--border)",
    padding: "0 10px",
    background: "white",
    color: "var(--ink)",
    fontSize: 13,
    minWidth: 0,
    maxWidth: "100%",
  },
  subsectionHint: {
    minHeight: 34,
    display: "inline-flex",
    alignItems: "center",
    maxWidth: 420,
    fontSize: 12,
    color: "var(--muted)",
    lineHeight: 1.6,
  },
  ghostBtn: {
    border: "1px solid var(--border)",
    height: 36,
    padding: "0 12px",
    background: "white",
    color: "var(--ink-2)",
    fontSize: 12,
    fontWeight: 600,
    whiteSpace: "nowrap",
    flexShrink: 0,
    cursor: "pointer",
  },
  primaryBtn: {
    border: "1px solid var(--accent)",
    height: 36,
    padding: "0 14px",
    background: "var(--accent)",
    color: "white",
    fontWeight: 600,
    cursor: "pointer",
    fontSize: 13,
    whiteSpace: "nowrap",
    flexShrink: 0,
  },
  inputArea: {
    display: "grid",
    gap: 10,
    position: "sticky",
    bottom: 0,
    zIndex: 8,
    padding: "12px 0 18px",
    background: "rgba(255, 255, 255, 0.96)",
  },
  inputStack: {
    display: "grid",
    gap: 8,
    minWidth: 0,
  },
  textarea: {
    height: 40,
    border: "1px solid var(--border)",
    padding: "9px 10px",
    background: "white",
    resize: "none",
    overflow: "hidden",
    fontSize: 14,
    lineHeight: 1.6,
    color: "var(--ink)",
  },
  attachmentToolbar: {
    display: "flex",
    gap: 8,
    alignItems: "center",
    flexWrap: "wrap",
  },
  iconToolButton: {
    width: 36,
    height: 36,
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
    border: "1px solid var(--border)",
    background: "white",
    color: "var(--ink-2)",
    cursor: "pointer",
    flexShrink: 0,
  },
  hiddenFileInput: {
    display: "none",
  },
  attachmentHint: {
    fontSize: 11,
    color: "var(--muted)",
    lineHeight: 1.5,
  },
  attachmentDraftList: {
    display: "grid",
    gap: 6,
  },
  attachmentDraftItem: {
    display: "flex",
    justifyContent: "space-between",
    gap: 10,
    alignItems: "center",
    padding: "8px 10px",
    border: "1px solid var(--border)",
    background: "var(--panel)",
  },
  attachmentDraftText: {
    fontSize: 12,
    color: "var(--ink-2)",
    lineHeight: 1.6,
    wordBreak: "break-word",
  },
  attachmentRemoveBtn: {
    border: "1px solid var(--border)",
    background: "white",
    color: "var(--muted)",
    height: 28,
    padding: "0 10px",
    fontSize: 11,
    cursor: "pointer",
    flexShrink: 0,
  },
  iconSendButton: {
    border: "1px solid var(--accent)",
    width: 36,
    height: 36,
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
    marginLeft: "auto",
    background: "var(--accent)",
    color: "white",
    cursor: "pointer",
    flexShrink: 0,
  },
  btnDisabled: {
    opacity: 0.45,
    cursor: "not-allowed",
  },
  errorBox: {
    display: "grid",
    gap: 8,
    border: "1px solid #f0c2c2",
    background: "#fff7f7",
    padding: "10px 12px",
  },
  errorTitle: {
    fontSize: 12,
    fontWeight: 700,
    color: "#9f1d1d",
  },
  errorText: {
    fontSize: 12,
    color: "#7f1d1d",
    wordBreak: "break-word",
  },
  retryBtn: {
    border: "1px solid #f0c2c2",
    background: "white",
    color: "#7f1d1d",
    height: 30,
    padding: "0 12px",
    fontSize: 12,
    fontWeight: 600,
    cursor: "pointer",
    width: "fit-content",
  },
  confirmationStack: {
    display: "grid",
    gap: 10,
  },
  confirmationCard: {
    display: "grid",
    gap: 10,
    padding: "12px 14px",
    border: "1px solid #d7d9bf",
    background: "#fffef1",
  },
  confirmationHead: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    gap: 10,
    flexWrap: "wrap",
  },
  confirmationTitle: {
    fontSize: 13,
    fontWeight: 700,
    color: "#5d4b00",
  },
  confirmationMeta: {
    fontSize: 11,
    color: "#7a6806",
  },
  confirmationSummary: {
    margin: 0,
    fontSize: 12,
    color: "#6a5810",
    lineHeight: 1.6,
  },
  confirmationLines: {
    display: "grid",
    gap: 6,
  },
  confirmationLine: {
    fontSize: 12,
    color: "#4f4a2c",
    lineHeight: 1.6,
  },
  confirmationActions: {
    display: "flex",
    gap: 8,
    flexWrap: "wrap",
  },
  confirmApproveBtn: {
    border: "1px solid #b8d5c9",
    background: "#f3fbf7",
    color: "#0f6d46",
    height: 32,
    padding: "0 12px",
    fontSize: 12,
    fontWeight: 700,
    cursor: "pointer",
  },
  confirmRejectBtn: {
    border: "1px solid var(--border)",
    background: "white",
    color: "var(--ink-2)",
    height: 32,
    padding: "0 12px",
    fontSize: 12,
    fontWeight: 600,
    cursor: "pointer",
  },
  auditCard: {
    border: "1px solid var(--border)",
    background: "rgba(255, 255, 255, 0.84)",
    padding: "10px 12px",
  },
  auditSummary: {
    cursor: "pointer",
    fontSize: 12,
    fontWeight: 700,
    color: "var(--ink)",
  },
  auditGrid: {
    display: "grid",
    gap: 10,
    marginTop: 10,
  },
  auditSection: {
    display: "grid",
    gap: 6,
  },
  auditLabel: {
    fontSize: 11,
    fontWeight: 700,
    letterSpacing: "0.06em",
    textTransform: "uppercase",
    color: "var(--muted)",
  },
  auditItem: {
    fontSize: 12,
    color: "var(--ink-2)",
    lineHeight: 1.6,
  },
  auditEmpty: {
    fontSize: 12,
    color: "var(--muted)",
    lineHeight: 1.6,
  },
  affinityBadge: {
    display: "inline-flex",
    width: "fit-content",
    alignItems: "center",
    padding: "3px 8px",
    border: "1px solid rgba(29, 125, 117, 0.18)",
    background: "rgba(29, 125, 117, 0.1)",
    color: "var(--teal)",
    fontSize: 12,
    fontWeight: 700,
  },
  transcript: {
    display: "grid",
    gridTemplateRows: "auto minmax(0, 1fr)",
    gap: 12,
    padding: "8px 0 6px",
    background: "transparent",
    minHeight: 0,
    overflow: "hidden",
    width: "100%",
    minWidth: 0,
  },
  turnList: {
    display: "grid",
    gap: 16,
    overflowY: "auto",
    paddingRight: 0,
    alignContent: "start",
    width: "100%",
    minWidth: 0,
    overflowX: "hidden",
  },
  turnCard: {
    display: "grid",
    gap: 12,
  },
  userSection: {
    display: "grid",
    gap: 6,
    width: "100%",
    justifyItems: "end",
  },
  aiSection: {
    display: "grid",
    gap: 8,
    width: "100%",
    justifyItems: "start",
  },
  turnMeta: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 12,
  },
  turnMetaRight: {
    justifyContent: "flex-end",
  },
  roleLabel: {
    fontSize: 11,
    fontWeight: 700,
    letterSpacing: "0.07em",
    textTransform: "uppercase",
    color: "var(--muted)",
  },
  timeLabel: {
    fontSize: 11,
    color: "var(--muted)",
  },
  userMessage: {
    margin: 0,
    padding: "10px 12px",
    background: "color-mix(in srgb, white 60%, var(--accent-soft))",
    border: "1px solid color-mix(in srgb, var(--accent) 20%, var(--border))",
    maxWidth: "min(96%, 1200px)",
    fontSize: 14,
    lineHeight: 1.7,
    color: "var(--ink-2)",
    whiteSpace: "pre-wrap",
    wordBreak: "break-word",
    overflowWrap: "anywhere",
  },
  attachmentChipRow: {
    display: "flex",
    gap: 6,
    flexWrap: "wrap",
    justifyContent: "flex-end",
    maxWidth: "min(96%, 1200px)",
  },
  attachmentChip: {
    display: "inline-flex",
    alignItems: "center",
    padding: "3px 8px",
    border: "1px solid color-mix(in srgb, var(--accent) 20%, var(--border))",
    background: "color-mix(in srgb, white 74%, var(--accent-soft))",
    color: "var(--ink-2)",
    fontSize: 11,
    lineHeight: 1.4,
  },
  aiLabel: {
    fontSize: 11,
    fontWeight: 700,
    letterSpacing: "0.07em",
    textTransform: "uppercase",
    color: "var(--accent)",
  },
  aiMessage: {
    margin: 0,
    fontSize: 14,
    lineHeight: 1.75,
    color: "var(--ink)",
    whiteSpace: "pre-wrap",
    wordBreak: "break-word",
    overflowWrap: "anywhere",
  },
  aiBubble: {
    display: "grid",
    gap: 10,
    width: "min(100%, 1200px)",
    padding: "12px 14px",
    border: "1px solid var(--border)",
    background: "white",
  },
  eventInline: {
    display: "grid",
    gap: 4,
    minWidth: 0,
  },
  eventNotes: {
    display: "grid",
    gap: 4,
  },
  eventNoteText: {
    margin: 0,
    fontSize: 12,
    lineHeight: 1.6,
    color: "var(--muted)",
    wordBreak: "break-word",
  },
  questionWrap: {
    display: "grid",
    gap: 8,
    borderTop: "1px solid var(--border)",
    paddingTop: 12,
  },
  questionTitle: {
    margin: 0,
    fontSize: 13,
    fontWeight: 700,
    color: "var(--ink)",
  },
  questionMeta: {
    fontSize: 12,
    color: "var(--muted)",
  },
  choiceList: {
    display: "grid",
    gap: 6,
  },
  choiceButton: {
    textAlign: "left",
    borderWidth: 1,
    borderStyle: "solid",
    borderColor: "var(--border)",
    padding: "8px 10px",
    background: "transparent",
    color: "var(--ink)",
    cursor: "pointer",
    fontSize: 13,
  },
  choiceButtonText: {
    margin: 0,
    fontSize: 13,
    lineHeight: 1.65,
    color: "inherit",
    whiteSpace: "normal",
    wordBreak: "break-word",
  },
  choiceButtonActive: {
    borderColor: "var(--accent)",
    background: "var(--accent-soft)",
    color: "var(--accent)",
  },
  choiceButtonLocked: {
    cursor: "default",
  },
  blankInput: {
    width: "100%",
    border: "1px solid var(--border)",
    height: 36,
    padding: "0 10px",
    background: "var(--panel)",
    color: "var(--ink)",
    fontSize: 13,
  },
  blankInputLocked: {
    color: "var(--muted)",
    background: "#f8fbfc",
  },
  questionActions: {
    display: "flex",
    alignItems: "center",
    gap: 8,
    flexWrap: "wrap",
  },
  checkButton: {
    border: "none",
    background: "var(--accent)",
    color: "white",
    height: 30,
    padding: "0 12px",
    fontSize: 12,
    fontWeight: 600,
    cursor: "pointer",
  },
  feedbackOk: {
    fontSize: 12,
    color: "var(--positive)",
    fontWeight: 500,
  },
  feedbackBad: {
    fontSize: 12,
    color: "var(--negative)",
    fontWeight: 500,
  },
  answerInline: {
    margin: 0,
    fontSize: 12,
    lineHeight: 1.6,
    color: "var(--muted)",
  },
  inlineGhostBtn: {
    border: "1px solid var(--border)",
    background: "transparent",
    color: "var(--muted)",
    height: 30,
    padding: "0 10px",
    fontSize: 12,
    cursor: "pointer",
  },
  explanationBox: {
    marginTop: 4,
    padding: "8px 10px",
    border: "1px solid var(--border)",
    background: "var(--panel)",
    fontSize: 12,
    color: "var(--muted)",
    lineHeight: 1.6,
  },
  citations: {
    display: "flex",
    gap: 6,
    flexWrap: "wrap",
  },
  citation: {
    appearance: "none",
    padding: "2px 8px",
    border: "1px solid var(--border)",
    fontSize: 12,
    color: "var(--teal)",
    background: "transparent",
    cursor: "pointer",
  },
  emptyTranscriptCard: {
    display: "grid",
    gap: 8,
    minHeight: 220,
    alignContent: "center",
    justifyItems: "start",
  },
  emptyTranscriptText: {
    margin: 0,
    maxWidth: 560,
    fontSize: 14,
    lineHeight: 1.75,
    color: "var(--muted)",
  },
};

function formatTurnTime(value: string) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit"
  });
}

function buildTurnKey(createdAt: string, index: number) {
  return `${createdAt}:${index}`;
}

function renderInteractiveQuestion(input: {
  question: InteractiveQuestion;
  turnKey: string;
  selectedChoices: Record<string, string>;
  blankAnswers: Record<string, string>;
  questionFeedback: Record<string, { ok: boolean; text: string }>;
  setSelectedChoices: Dispatch<SetStateAction<Record<string, string>>>;
  setBlankAnswers: Dispatch<SetStateAction<Record<string, string>>>;
  setQuestionFeedback: Dispatch<SetStateAction<Record<string, { ok: boolean; text: string }>>>;
  expandedExplanation: Record<string, boolean>;
  setExpandedExplanation: Dispatch<SetStateAction<Record<string, boolean>>>;
  onAsk: (message: string, attachments: File[]) => Promise<boolean> | boolean;
  onSubmitQuestionAttempt: (input: {
    questionType: "multiple_choice" | "fill_blank";
    prompt: string;
    topic: string;
    difficulty: "easy" | "medium" | "hard";
    options: Array<{ key: string; text: string }>;
    callBack?: boolean;
    answerKey?: string;
    acceptedAnswers: string[];
    submittedAnswer: string;
    isCorrect: boolean;
    explanation: string;
  }) => void | Promise<void>;
  disabled: boolean;
}) {
  const {
    question,
    turnKey,
    selectedChoices,
    blankAnswers,
    questionFeedback,
    setSelectedChoices,
    setBlankAnswers,
    setQuestionFeedback,
    expandedExplanation,
    setExpandedExplanation,
    onAsk,
    onSubmitQuestionAttempt,
    disabled
  } = input;
  const feedback = questionFeedback[turnKey];
  const explanationVisible = Boolean(expandedExplanation[turnKey]);
  const persistedFeedback = question.feedbackText
    ? { ok: Boolean(question.isCorrect), text: question.feedbackText }
    : undefined;
  const effectiveFeedback = feedback ?? persistedFeedback;
  const isLocked = Boolean(question.submittedAnswer);

  if (question.questionType === "multiple_choice") {
    const selected = selectedChoices[turnKey] ?? question.submittedAnswer ?? "";
    return (
      <>
        <p style={styles.questionTitle}>选择题</p>
        <span style={styles.questionMeta}>{question.topic || "章节练习"} · {question.difficulty}</span>
        <RichTextMessage content={question.prompt} style={styles.aiMessage} />
        <div style={styles.choiceList}>
          {question.options.map((option) => (
            <button
              key={`${turnKey}:${option.key}`}
              type="button"
              style={{
                ...styles.choiceButton,
                ...(selected === option.key ? styles.choiceButtonActive : {}),
                ...(isLocked ? styles.choiceButtonLocked : {})
              }}
              disabled={isLocked}
              onClick={() => setSelectedChoices((current) => ({ ...current, [turnKey]: option.key }))}
            >
              <RichTextMessage
                content={`${option.key}. ${option.text}`}
                inline
                style={styles.choiceButtonText}
              />
            </button>
          ))}
        </div>
        <div style={styles.questionActions}>
          <button
            type="button"
            style={styles.checkButton}
            disabled={!selected || disabled || isLocked}
            onClick={() => {
              const correct = selected.trim().toUpperCase() === (question.answerKey ?? "").trim().toUpperCase();
              const feedbackText = correct ? "回答正确" : `回答不正确，正确答案是 ${question.answerKey ?? "未提供"}`;
              setQuestionFeedback((current) => ({ ...current, [turnKey]: { ok: correct, text: feedbackText } }));
              void onSubmitQuestionAttempt({
                questionType: question.questionType,
                prompt: question.prompt,
                topic: question.topic,
                difficulty: question.difficulty,
                options: question.options,
                callBack: question.callBack,
                answerKey: question.answerKey,
                acceptedAnswers: question.acceptedAnswers,
                submittedAnswer: selected,
                isCorrect: correct,
                explanation: question.explanation
              });
            }}
          >
            提交答案
          </button>
          {isLocked ? (
            <button
              type="button"
              style={styles.inlineGhostBtn}
              onClick={() => setExpandedExplanation((current) => ({ ...current, [turnKey]: !current[turnKey] }))}
            >
              {explanationVisible ? "收起解析" : "查看解析"}
            </button>
          ) : null}
          <button
            type="button"
            style={styles.inlineGhostBtn}
            disabled={disabled}
            onClick={() => { void onAsk(`请围绕${question.topic || "本章节核心概念"}再出一道同难度选择题。`, []); }}
          >
            再来一题
          </button>
          {effectiveFeedback ? (
            <span style={effectiveFeedback.ok ? styles.feedbackOk : styles.feedbackBad}>{effectiveFeedback.text}</span>
          ) : null}
        </div>
        {selected ? (
          <p style={styles.answerInline}>
            你的选择：{selected}
          </p>
        ) : null}
        {explanationVisible ? (
          <div style={styles.explanationBox}>
            <RichTextMessage content={question.explanation || "暂无解析"} />
          </div>
        ) : null}
      </>
    );
  }

  const value = blankAnswers[turnKey] ?? question.submittedAnswer ?? "";
  return (
    <>
      <p style={styles.questionTitle}>填空题</p>
      <span style={styles.questionMeta}>{question.topic || "章节练习"} · {question.difficulty}</span>
      <RichTextMessage content={question.prompt} style={styles.aiMessage} />
      <input
        type="text"
        value={value}
        style={{ ...styles.blankInput, ...(isLocked ? styles.blankInputLocked : {}) }}
        onChange={(event) => {
          const next = event.target.value;
          setBlankAnswers((current) => ({ ...current, [turnKey]: next }));
        }}
        readOnly={isLocked}
        placeholder="输入你的答案"
      />
      <div style={styles.questionActions}>
        <button
          type="button"
          style={styles.checkButton}
          disabled={!value.trim() || disabled || isLocked}
          onClick={() => {
            const normalized = normalizeAnswer(value);
            const accepted = question.acceptedAnswers.map(normalizeAnswer);
            const correct = accepted.includes(normalized);
            const feedbackText = correct
              ? "回答正确"
              : `回答不正确，参考答案：${question.acceptedAnswers.join(" / ") || "未提供"}`;
            setQuestionFeedback((current) => ({ ...current, [turnKey]: { ok: correct, text: feedbackText } }));
            void onSubmitQuestionAttempt({
              questionType: question.questionType,
              prompt: question.prompt,
              topic: question.topic,
              difficulty: question.difficulty,
              options: question.options,
              callBack: question.callBack,
              answerKey: question.answerKey,
              acceptedAnswers: question.acceptedAnswers,
              submittedAnswer: value,
              isCorrect: correct,
              explanation: question.explanation
            });
          }}
        >
          提交答案
        </button>
        {isLocked ? (
          <button
            type="button"
            style={styles.inlineGhostBtn}
            onClick={() => setExpandedExplanation((current) => ({ ...current, [turnKey]: !current[turnKey] }))}
          >
            {explanationVisible ? "收起解析" : "查看解析"}
          </button>
        ) : null}
        <button
          type="button"
          style={styles.inlineGhostBtn}
          disabled={disabled}
          onClick={() => { void onAsk(`请围绕${question.topic || "本章节核心概念"}再出一道同难度填空题。`, []); }}
          >
            再来一题
          </button>
        {effectiveFeedback ? (
          <span style={effectiveFeedback.ok ? styles.feedbackOk : styles.feedbackBad}>{effectiveFeedback.text}</span>
        ) : null}
      </div>
      {value.trim() ? (
        <p style={styles.answerInline}>
          你的答案：{value.trim()}
        </p>
      ) : null}
      {explanationVisible ? (
        <div style={styles.explanationBox}>
          <RichTextMessage content={question.explanation || "暂无解析"} />
        </div>
      ) : null}
    </>
  );
}

function normalizeAnswer(value: string) {
  return value.trim().toLowerCase().replace(/\s+/g, " ");
}

function buildRenderableReply(
  reply: string,
  richBlocks?: Array<{ kind: string; content: string }>
) {
  const normalizedReply = String(reply ?? "").trim();
  const blocks = Array.isArray(richBlocks) ? richBlocks : [];
  if (!blocks.length) {
    return normalizedReply;
  }
  const appendix = blocks
    .map((block) => {
      const kind = String(block.kind ?? "").trim().toLowerCase();
      const content = String(block.content ?? "").trim();
      if (!kind || !content) {
        return "";
      }
      if (kind === "mermaid") {
        return `\n\n\`\`\`mermaid\n${content}\n\`\`\``;
      }
      return `\n\n\`\`\`${kind}\n${content}\n\`\`\``;
    })
    .filter(Boolean)
    .join("");
  return `${normalizedReply}${appendix}`;
}

function CharacterEventInline({ events }: { events: CharacterStateEvent[] }) {
  if (!events.length) {
    return null;
  }

  const descriptionLines = collectEventDescriptions(events);
  if (!descriptionLines.length) {
    return null;
  }

  return (
    <div style={styles.eventInline}>
      <div style={styles.eventNotes}>
        {descriptionLines.map((line, index) => (
          <p key={`${line}:${index}`} style={styles.eventNoteText}>{line}</p>
        ))}
      </div>
    </div>
  );
}

function collectEventDescriptions(events: CharacterStateEvent[]) {
  const lines: string[] = [];
  const seen = new Set<string>();

  events.forEach((event) => {
    [
      formatActionDescription(event.action),
      event.deliveryCue,
      event.toolSummary
    ].forEach((item) => {
      const text = String(item ?? "").trim();
      if (!text || text.length < 6 || seen.has(text)) {
        return;
      }
      seen.add(text);
      lines.push(text);
    });
  });

  return lines.slice(0, 3);
}

function formatActionDescription(value: string) {
  const normalized = value.trim().toLowerCase();
  if (!normalized || normalized === "idle") return "";
  if (normalized === "nod") return "轻轻点头。";
  if (normalized === "point") return "指向当前重点。";
  if (normalized === "lean_in") return "微微前倾。";
  if (normalized === "smile") return "带着笑意。";
  if (normalized === "pause") return "短暂停顿。";
  if (normalized === "write") return "抬手书写比划。";
  return value.trim();
}

function formatSpeechStyleLabel(value: string) {
  const normalized = value.trim().toLowerCase();
  if (normalized === "steady") return "平稳";
  if (normalized === "warm") return "温和";
  if (normalized === "dramatic") return "戏剧化";
  if (normalized === "gentle") return "轻柔";
  if (normalized === "energetic") return "有活力";
  return value || "默认";
}

function formatToolName(value: string) {
  const normalized = value.trim().toLowerCase();
  if (normalized === "update_learning_plan") return "提出计划修改";
  if (normalized === "update_learning_plan_progress") return "提出进度修改";
  return value || "工具事件";
}

function isAttemptTurn(message: string) {
  return message.trim().startsWith("[练习作答]");
}

function isHiddenLearnerMessage(turn: Pick<StudySessionRecord["turns"][number], "learnerMessage" | "learnerMessageKind">) {
  const kind = String(turn.learnerMessageKind ?? "learner");
  if (kind !== "learner") {
    return true;
  }
  const normalized = turn.learnerMessage.trim();
  return normalized.startsWith("[练习作答]") || normalized.startsWith("[交互回调]");
}

function formatLearnerMessage(turn: Pick<StudySessionRecord["turns"][number], "learnerMessage" | "learnerMessageKind">) {
  const kind = String(turn.learnerMessageKind ?? "learner");
  if (kind === "interactive_callback") return "答题回调";
  if (kind === "session_prelude") return "章节预处理";
  if (kind === "scheduled_follow_up") return "自动续接";
  if (!isAttemptTurn(turn.learnerMessage)) return turn.learnerMessage;
  return turn.learnerMessage.replace("[练习作答]", "练习作答").trim();
}

function formatAttachmentLabel(attachment: NonNullable<StudySessionRecord["turns"][number]["learnerAttachments"]>[number]) {
  const typeLabel =
    attachment.kind === "image"
      ? "图片"
      : attachment.kind === "pdf"
        ? "PDF"
        : "附件";
  return `${typeLabel} · ${attachment.name}`;
}

function formatFileSize(size: number) {
  if (size >= 1024 * 1024) {
    return `${(size / (1024 * 1024)).toFixed(1)} MB`;
  }
  if (size >= 1024) {
    return `${Math.round(size / 1024)} KB`;
  }
  return `${size} B`;
}
