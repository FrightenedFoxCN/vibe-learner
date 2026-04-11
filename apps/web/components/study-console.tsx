"use client";

import Link from "next/link";
import type { CSSProperties, Dispatch, SetStateAction } from "react";
import { useEffect, useRef, useState } from "react";
import type {
  CharacterStateEvent,
  DocumentSection,
  InteractiveQuestion,
  PersonaProfile,
  SceneProfile,
  StudyChatResponse,
  StudySessionRecord
} from "@vibe-learner/shared";

import { CharacterShell } from "./character-shell";
import { RichTextMessage } from "./rich-text-message";

interface StudyConsoleProps {
  isPending: boolean;
  onAsk: (message: string) => void;
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
  onChangeChapter: (chapter: string) => void;
  onOpenPage?: (page: number) => void;
  onJumpToChapterStart?: () => void;
  chatErrorMessage?: string;
  onRetryLastAsk?: () => void | Promise<void>;
  selectedChapter: string;
  studyChapters: string[];
  selectedSubsectionId?: string;
  subsectionOptions?: DocumentSection[];
  onChangeSubsection?: (subsectionId: string) => void;
  turns: StudySessionRecord["turns"];
  session: StudyChatResponse | null;
  persona: PersonaProfile;
  sceneProfile?: SceneProfile | null;
  sceneSourceLabel?: string;
  sceneInstanceId?: string;
  onTogglePdfPreview?: () => void;
  isPdfPreviewOpen?: boolean;
  canOpenPdfPreview?: boolean;
  disabled?: boolean;
}

export function StudyConsole({
  isPending,
  onAsk,
  onSubmitQuestionAttempt,
  onChangeChapter,
  onOpenPage,
  onJumpToChapterStart,
  chatErrorMessage,
  onRetryLastAsk,
  selectedChapter,
  studyChapters,
  selectedSubsectionId,
  subsectionOptions = [],
  onChangeSubsection,
  turns,
  session,
  persona,
  sceneProfile,
  sceneSourceLabel,
  sceneInstanceId,
  onTogglePdfPreview,
  isPdfPreviewOpen,
  canOpenPdfPreview,
  disabled
}: StudyConsoleProps) {
  const [message, setMessage] = useState("请解释这一章的核心概念，并给我一个复述练习。");
  const [selectedChoices, setSelectedChoices] = useState<Record<string, string>>({});
  const [blankAnswers, setBlankAnswers] = useState<Record<string, string>>({});
  const [questionFeedback, setQuestionFeedback] = useState<Record<string, { ok: boolean; text: string }>>({});
  const [expandedExplanation, setExpandedExplanation] = useState<Record<string, boolean>>({});
  const transcriptRef = useRef<HTMLDivElement | null>(null);

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

  return (
    <div style={styles.wrap}>
      <div className="study-console-layout" style={styles.consoleCard}>
        <section style={styles.chatPanel}>
          <div style={styles.consoleHead}>
            <div style={styles.consoleMeta}>
              <span style={styles.caption}>章节对话主界面</span>
              <h2 style={styles.consoleTitle}>{selectedChapter || "选择章节后开始对话"}</h2>
              <p style={styles.consoleSummary}>
                左侧保持常规聊天窗口，历史消息会被新内容向上推走；右侧单列只保留人格与场景陪伴信息。
              </p>
            </div>
            <div style={styles.consoleActions}>
              <button
                type="button"
                style={{
                  ...styles.ghostBtn,
                  ...(disabled || !canOpenPdfPreview || !onTogglePdfPreview ? styles.btnDisabled : {})
                }}
                disabled={disabled || !canOpenPdfPreview || !onTogglePdfPreview}
                onClick={() => { if (onTogglePdfPreview) onTogglePdfPreview(); }}
              >
                {isPdfPreviewOpen ? "收拢教材浮窗" : "展开教材浮窗"}
              </button>
            </div>
          </div>

          <div style={styles.controlStack}>
            <div style={styles.themeRow}>
              <label style={styles.themeLabel}>
                <span style={styles.caption}>学习章节</span>
                <select
                  style={styles.select}
                  value={selectedChapter}
                  onChange={(event) => onChangeChapter(event.target.value)}
                  disabled={isPending || disabled}
                  title={selectedChapter || "暂无学习章节"}
                >
                  {studyChapters.length ? (
                    studyChapters.map((chapter) => (
                      <option key={chapter} value={chapter}>{chapter}</option>
                    ))
                  ) : (
                    <option value="">暂无学习章节</option>
                  )}
                </select>
              </label>
              <button
                type="button"
                style={{
                  ...styles.ghostBtn,
                  ...(isPending || disabled || !onJumpToChapterStart ? styles.btnDisabled : {})
                }}
                disabled={isPending || disabled || !onJumpToChapterStart}
                onClick={() => { if (onJumpToChapterStart) onJumpToChapterStart(); }}
              >
                定位章节首页
              </button>
            </div>

            <div style={styles.themeRow}>
              <label style={styles.themeLabel}>
                <span style={styles.caption}>子章节</span>
                <select
                  style={styles.select}
                  value={selectedSubsectionId ?? ""}
                  onChange={(event) => { if (onChangeSubsection) onChangeSubsection(event.target.value); }}
                  disabled={isPending || disabled || !subsectionOptions.length || !onChangeSubsection}
                  title={selectedSubsectionId || "当前按整章范围学习"}
                >
                  <option value="">整章范围</option>
                  {subsectionOptions.map((subsection) => (
                    <option key={subsection.id} value={subsection.id}>
                      {subsection.title} · p.{subsection.pageStart}-{subsection.pageEnd}
                    </option>
                  ))}
                </select>
              </label>
              <span style={styles.subsectionHint}>
                {subsectionOptions.length
                  ? "选择更细的子章节后，会话和教材预览会同步切到对应 section。"
                  : "当前章节没有可用的子章节，保持整章范围。"}
              </span>
            </div>
          </div>

          <div style={styles.transcript}>
            <div style={styles.transcriptHeader}>
              <span style={styles.caption}>对话记录</span>
              <span style={styles.transcriptMeta}>{turns.length} 轮内容</span>
            </div>
            {turns.length ? (
              <div ref={transcriptRef} style={styles.turnList}>
                {sortedTurns.map((turn, index) => (
                  <div
                    key={buildTurnKey(turn.createdAt, index)}
                    style={styles.turnCard}
                  >
                    {!isHiddenLearnerMessage(turn.learnerMessage) ? (
                      <div style={styles.userSection}>
                        <div style={{ ...styles.turnMeta, ...styles.turnMetaRight }}>
                          <span style={styles.timeLabel}>{formatTurnTime(turn.createdAt)}</span>
                          <span style={styles.roleLabel}>你</span>
                        </div>
                        <p style={styles.userMessage}>{formatLearnerMessage(turn.learnerMessage)}</p>
                      </div>
                    ) : null}

                    <div style={styles.aiSection}>
                      <div style={styles.turnMeta}>
                        <span style={styles.aiLabel}>AI</span>
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
                                onClick={() => { if (onOpenPage) onOpenPage(citation.pageStart); }}
                                title={`跳转到 p.${citation.pageStart}–${citation.pageEnd}`}
                                disabled={!onOpenPage}
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
                      <span style={styles.aiLabel}>AI</span>
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
                              onClick={() => { if (onOpenPage) onOpenPage(citation.pageStart); }}
                              title={`跳转到 p.${citation.pageStart}–${citation.pageEnd}`}
                              disabled={!onOpenPage}
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
                <span style={styles.caption}>对话记录</span>
                <p style={styles.emptyTranscriptText}>创建会话后，从当前章节开始提问，回答、练习题和引用页码都会集中显示在这里。</p>
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

          <div style={styles.inputArea}>
            <textarea
              style={styles.textarea}
              value={message}
              onChange={(event) => setMessage(event.target.value)}
              placeholder="继续输入问题，或追问上一轮内容…"
            />
            <button
              style={{
                ...styles.sendBtn,
                ...(isPending || disabled ? styles.btnDisabled : {})
              }}
              disabled={isPending || disabled}
              onClick={() => onAsk(message)}
            >
              {isPending ? "发送中…" : "发送"}
            </button>
          </div>
        </section>

        <aside style={styles.sidebar}>
          <div style={styles.companionCard}>
            <div style={styles.companionMeta}>
              <div style={styles.companionHeader}>
                <span style={styles.caption}>陪伴设定</span>
                <div style={styles.companionLinks}>
                  <Link href="/persona-spectrum" style={styles.companionLink}>人格库</Link>
                  <Link href="/scene-setup" style={styles.companionLink}>场景编辑</Link>
                </div>
              </div>
              <div style={styles.companionRow}>
                <span style={styles.companionChip}>人格 · {persona.name}</span>
                <span style={styles.companionChip}>场景 · {sceneProfile?.title || "未设置"}</span>
                {sceneSourceLabel ? <span style={styles.companionChip}>来源 · {sceneSourceLabel}</span> : null}
                {sceneInstanceId ? <span style={styles.companionChip}>副本 · {sceneInstanceId}</span> : null}
              </div>
              <p style={styles.companionSummary}>
                {sceneProfile?.summary || persona.summary || "尚未配置场景摘要。"}
              </p>
              {sceneProfile?.selectedPath.length ? (
                <p style={styles.companionPath}>{sceneProfile.selectedPath.join(" / ")}</p>
              ) : null}
            </div>
            <div style={styles.shellCard}>
              <CharacterShell
                persona={persona}
                response={session}
                pending={isPending}
                variant="embedded"
              />
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
  },
  consoleCard: {
    display: "grid",
    gridTemplateColumns: "minmax(0, 1.75fr) minmax(320px, 0.82fr)",
    gap: 20,
    alignItems: "start",
  },
  chatPanel: {
    display: "grid",
    gridTemplateRows: "auto auto minmax(0, 1fr) auto auto",
    gap: 14,
    minWidth: 0,
    minHeight: "calc(100vh - 220px)",
    padding: 20,
    border: "1px solid var(--border)",
    background: "linear-gradient(180deg, #fbfdfe 0%, #f3f7f8 100%)",
    boxShadow: "0 22px 60px rgba(13, 32, 40, 0.08)",
  },
  controlStack: {
    display: "grid",
    gap: 10,
    padding: "14px 16px",
    border: "1px solid var(--border)",
    background: "rgba(255, 255, 255, 0.78)",
  },
  sidebar: {
    minWidth: 0,
    position: "sticky",
    top: 96,
  },
  consoleHead: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "flex-start",
    gap: 16,
    flexWrap: "wrap",
  },
  consoleMeta: {
    display: "grid",
    gap: 6,
    minWidth: 0,
    flex: 1,
  },
  consoleTitle: {
    margin: 0,
    fontSize: 24,
    lineHeight: 1.15,
    color: "var(--ink)",
  },
  consoleSummary: {
    margin: 0,
    maxWidth: 720,
    fontSize: 13,
    lineHeight: 1.7,
    color: "var(--muted)",
  },
  consoleActions: {
    display: "flex",
    gap: 8,
    flexWrap: "wrap",
    justifyContent: "flex-end",
  },
  companionCard: {
    display: "grid",
    gap: 14,
    border: "1px solid var(--border)",
    background: "linear-gradient(180deg, #fbfdfe 0%, #f4f7f8 100%)",
    padding: "16px 16px 18px",
    boxShadow: "0 18px 48px rgba(13, 32, 40, 0.08)",
  },
  companionMeta: {
    display: "grid",
    gap: 10,
    alignContent: "start",
  },
  companionHeader: {
    display: "flex",
    justifyContent: "space-between",
    gap: 12,
    alignItems: "center",
    flexWrap: "wrap",
  },
  companionLinks: {
    display: "flex",
    gap: 10,
    flexWrap: "wrap",
  },
  companionLink: {
    fontSize: 12,
    color: "var(--accent)",
    fontWeight: 600,
  },
  companionRow: {
    display: "flex",
    gap: 8,
    flexWrap: "wrap",
  },
  companionChip: {
    fontSize: 12,
    color: "var(--ink-2)",
    border: "1px solid var(--border)",
    background: "white",
    padding: "2px 8px",
  },
  companionSummary: {
    margin: 0,
    fontSize: 12,
    color: "var(--muted)",
    lineHeight: 1.6,
  },
  companionPath: {
    margin: 0,
    fontSize: 12,
    color: "var(--ink-2)",
    lineHeight: 1.6,
  },
  shellCard: {
    minWidth: 0,
    padding: "12px 14px",
    border: "1px solid var(--border)",
    background: "var(--panel)",
  },
  themeRow: {
    display: "flex",
    alignItems: "flex-end",
    gap: 8,
    flexWrap: "wrap",
  },
  themeLabel: {
    display: "grid",
    gap: 4,
    flex: 1,
    minWidth: 0,
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
    height: 34,
    border: "1px solid var(--border)",
    padding: "0 8px",
    background: "var(--panel)",
    color: "var(--ink)",
    fontSize: 13,
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
    height: 34,
    padding: "0 12px",
    background: "transparent",
    color: "var(--ink-2)",
    fontSize: 12,
    fontWeight: 500,
    whiteSpace: "nowrap",
    flexShrink: 0,
    cursor: "pointer",
  },
  inputArea: {
    display: "grid",
    gridTemplateColumns: "minmax(0, 1fr) auto",
    gap: 8,
    alignItems: "end",
    position: "sticky",
    bottom: 0,
    zIndex: 8,
    padding: "14px 16px 16px",
    border: "1px solid var(--border)",
    background: "rgba(255, 255, 255, 0.92)",
    boxShadow: "0 -10px 26px rgba(13, 32, 40, 0.08)",
  },
  textarea: {
    minHeight: 84,
    border: "1px solid var(--border)",
    padding: "8px 10px",
    background: "white",
    resize: "vertical",
    fontSize: 14,
    lineHeight: 1.6,
    color: "var(--ink)",
  },
  sendBtn: {
    border: "none",
    height: 84,
    padding: "0 20px",
    background: "var(--accent)",
    color: "white",
    fontWeight: 600,
    cursor: "pointer",
    fontSize: 13,
    whiteSpace: "nowrap",
    alignSelf: "stretch",
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
  transcript: {
    display: "grid",
    gridTemplateRows: "auto minmax(0, 1fr)",
    gap: 12,
    padding: "16px 16px 10px",
    border: "1px solid var(--border)",
    background: "white",
    minHeight: 0,
    overflow: "hidden",
  },
  transcriptHeader: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    gap: 12,
    flexWrap: "wrap",
  },
  transcriptMeta: {
    fontSize: 12,
    color: "var(--muted)",
  },
  turnList: {
    display: "grid",
    gap: 16,
    overflowY: "auto",
    paddingRight: 6,
    alignContent: "start",
  },
  turnCard: {
    display: "grid",
    gap: 12,
  },
  userSection: {
    display: "grid",
    gap: 6,
    justifyItems: "end",
  },
  aiSection: {
    display: "grid",
    gap: 8,
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
    background: "linear-gradient(180deg, #e7f5f7 0%, #dff0f2 100%)",
    border: "1px solid #b8dde2",
    maxWidth: "min(82%, 720px)",
    fontSize: 14,
    lineHeight: 1.7,
    color: "var(--ink-2)",
    whiteSpace: "pre-wrap",
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
  },
  aiBubble: {
    display: "grid",
    gap: 10,
    width: "min(100%, 820px)",
    padding: "12px 14px",
    border: "1px solid var(--border)",
    background: "#fcfefe",
  },
  eventInline: {
    display: "grid",
    gap: 8,
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
  eventBadgeRow: {
    display: "flex",
    gap: 6,
    flexWrap: "wrap",
  },
  eventBadge: {
    display: "inline-flex",
    alignItems: "center",
    padding: "3px 8px",
    borderRadius: 999,
    border: "1px solid var(--border)",
    background: "var(--panel)",
    color: "var(--ink)",
    fontSize: 11,
    lineHeight: 1.4,
    maxWidth: "100%",
  },
  eventBadgeMuted: {
    background: "var(--bg)",
    color: "var(--muted)",
  },
  eventBadgeAccent: {
    background: "rgba(29, 125, 117, 0.14)",
    color: "var(--teal)",
    border: "1px solid rgba(29, 125, 117, 0.22)",
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
  onAsk: (message: string) => void;
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
          <button
            type="button"
            style={styles.inlineGhostBtn}
            onClick={() => setExpandedExplanation((current) => ({ ...current, [turnKey]: !current[turnKey] }))}
          >
            {explanationVisible ? "收起解析" : "查看解析"}
          </button>
          <button
            type="button"
            style={styles.inlineGhostBtn}
            disabled={disabled}
            onClick={() => { void onAsk(`请围绕${question.topic || "本章节核心概念"}再出一道同难度选择题。`); }}
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
        <button
          type="button"
          style={styles.inlineGhostBtn}
          onClick={() => setExpandedExplanation((current) => ({ ...current, [turnKey]: !current[turnKey] }))}
        >
          {explanationVisible ? "收起解析" : "查看解析"}
        </button>
        <button
          type="button"
          style={styles.inlineGhostBtn}
          disabled={disabled}
          onClick={() => { void onAsk(`请围绕${question.topic || "本章节核心概念"}再出一道同难度填空题。`); }}
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
  const badges = collectEventBadges(events);
  if (!descriptionLines.length && !badges.length) {
    return null;
  }

  return (
    <div style={styles.eventInline}>
      {descriptionLines.length ? (
        <div style={styles.eventNotes}>
          {descriptionLines.map((line, index) => (
            <p key={`${line}:${index}`} style={styles.eventNoteText}>{line}</p>
          ))}
        </div>
      ) : null}
      {badges.length ? (
        <div style={styles.eventBadgeRow}>
          {badges.map((badge, index) => (
            <span
              key={`${badge.label}:${badge.value}:${index}`}
              style={{
                ...styles.eventBadge,
                ...(badge.kind === "accent" ? styles.eventBadgeAccent : {}),
                ...(badge.kind === "muted" ? styles.eventBadgeMuted : {})
              }}
            >
              {badge.label}·{badge.value}
            </span>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function collectEventDescriptions(events: CharacterStateEvent[]) {
  const lines: string[] = [];
  const seen = new Set<string>();

  events.forEach((event) => {
    [
      formatActionDescription(event.action),
      event.commentary,
      event.deliveryCue,
      event.toolSummary
    ].forEach((item) => {
      const text = String(item ?? "").trim();
      if (!text || text.length < 12 || seen.has(text)) {
        return;
      }
      seen.add(text);
      lines.push(text);
    });
  });

  return lines.slice(0, 3);
}

function collectEventBadges(events: CharacterStateEvent[]) {
  const badges: Array<{ label: string; value: string; kind?: "default" | "muted" | "accent" }> = [];
  const seen = new Set<string>();

  const pushBadge = (
    label: string,
    value: string,
    kind: "default" | "muted" | "accent" = "default"
  ) => {
    const normalizedValue = value.trim();
    if (!normalizedValue) {
      return;
    }
    const key = `${label}:${normalizedValue}:${kind}`;
    if (seen.has(key)) {
      return;
    }
    seen.add(key);
    badges.push({ label, value: normalizedValue, kind });
  };

  events.forEach((event) => {
    pushBadge("情绪", formatEmotionLabel(event.emotion));
    pushBadge("语气", formatSpeechStyleLabel(event.speechStyle), "muted");
    pushBadge("场景", formatSceneHint(event.sceneHint), "muted");
    if (event.toolName) {
      pushBadge("工具", formatToolName(event.toolName), "accent");
    }
  });

  return badges.slice(0, 12);
}

function formatEmotionLabel(value: string) {
  const normalized = value.trim().toLowerCase();
  if (normalized === "calm") return "冷静";
  if (normalized === "encouraging") return "鼓励";
  if (normalized === "playful") return "轻快";
  if (normalized === "serious") return "认真";
  if (normalized === "excited") return "兴奋";
  if (normalized === "concerned") return "关注";
  return value || "未标注";
}

function formatActionDescription(value: string) {
  const normalized = value.trim().toLowerCase();
  if (!normalized || normalized === "idle") return "";
  if (normalized === "nod") return "动作：轻轻点头，示意可以继续。";
  if (normalized === "point") return "动作：抬手指向当前重点，提醒注意关键位置。";
  if (normalized === "lean_in") return "动作：身体微微前倾，像是在等你回应。";
  if (normalized === "smile") return "动作：嘴角带笑，把鼓励自然递出来。";
  if (normalized === "pause") return "动作：短暂停住，像是在给思路留白。";
  if (normalized === "write") return "动作：抬手书写比划，把结构关系描出来。";
  return `动作：${value.trim()}`;
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

function formatSceneHint(value: string) {
  if (!value) {
    return "学习场景";
  }
  if (value.startsWith("study_session:")) {
    const detail = value.replace("study_session:", "");
    return `学习场景:${detail}`;
  }
  if (value.startsWith("scene_tool:")) {
    return `场景工具:${formatToolName(value.replace("scene_tool:", ""))}`;
  }
  return value
    .replaceAll("study_session", "学习场景")
    .replaceAll("overview", "概览")
    .replaceAll("scene_tool", "场景工具");
}

function formatToolName(value: string) {
  const normalized = value.trim().toLowerCase();
  if (normalized === "read_scene_overview") return "读取场景";
  if (normalized === "add_scene") return "新增场景层";
  if (normalized === "move_to_scene") return "切换场景层";
  if (normalized === "add_object") return "新增物件";
  if (normalized === "update_object_description") return "更新物件描述";
  if (normalized === "delete_object") return "删除物件";
  if (normalized === "retrieve_memory_context") return "检索记忆";
  if (normalized === "read_page_range_content") return "读取教材正文";
  if (normalized === "read_page_range_images") return "读取教材图像";
  return value || "工具事件";
}

function isAttemptTurn(message: string) {
  return message.trim().startsWith("[练习作答]");
}

function isHiddenLearnerMessage(message: string) {
  const normalized = message.trim();
  return normalized.startsWith("[练习作答]") || normalized.startsWith("[交互回调]");
}

function formatLearnerMessage(message: string) {
  if (!isAttemptTurn(message)) return message;
  return message.replace("[练习作答]", "练习作答").trim();
}
