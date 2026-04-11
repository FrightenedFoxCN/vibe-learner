"use client";

import type { CSSProperties, Dispatch, SetStateAction } from "react";
import { useState } from "react";
import type { InteractiveQuestion, StudyChatResponse, StudySessionRecord } from "@vibe-learner/shared";

interface StudyConsoleProps {
  isPending: boolean;
  onAsk: (message: string) => void;
  onSubmitQuestionAttempt: (input: {
    questionType: "multiple_choice" | "fill_blank";
    prompt: string;
    topic: string;
    difficulty: "easy" | "medium" | "hard";
    options: Array<{ key: string; text: string }>;
    answerKey?: string;
    acceptedAnswers: string[];
    submittedAnswer: string;
    isCorrect: boolean;
    explanation: string;
  }) => void | Promise<void>;
  onChangeTheme: (theme: string) => void;
  onOpenPage?: (page: number) => void;
  onJumpToThemeStart?: () => void;
  chatErrorMessage?: string;
  onRetryLastAsk?: () => void | Promise<void>;
  selectedTheme: string;
  weeklyFocus: string[];
  turns: StudySessionRecord["turns"];
  session: StudyChatResponse | null;
  disabled?: boolean;
}

export function StudyConsole({
  isPending,
  onAsk,
  onSubmitQuestionAttempt,
  onChangeTheme,
  onOpenPage,
  onJumpToThemeStart,
  chatErrorMessage,
  onRetryLastAsk,
  selectedTheme,
  weeklyFocus,
  turns,
  session,
  disabled
}: StudyConsoleProps) {
  const [message, setMessage] = useState("请解释这一章的核心概念，并给我一个复述练习。");
  const [selectedChoices, setSelectedChoices] = useState<Record<string, string>>({});
  const [blankAnswers, setBlankAnswers] = useState<Record<string, string>>({});
  const [questionFeedback, setQuestionFeedback] = useState<Record<string, { ok: boolean; text: string }>>({});
  const [expandedExplanation, setExpandedExplanation] = useState<Record<string, boolean>>({});

  const sortedTurns = [...turns].sort((a, b) => {
    const aTime = Date.parse(a.createdAt || "") || 0;
    const bTime = Date.parse(b.createdAt || "") || 0;
    return bTime - aTime;
  });

  return (
    <div style={styles.wrap}>
      {/* Theme selector */}
      <div style={styles.themeRow}>
        <label style={styles.themeLabel}>
          <span style={styles.caption}>主线主题</span>
          <select
            style={styles.select}
            value={selectedTheme}
            onChange={(event) => onChangeTheme(event.target.value)}
            disabled={isPending || disabled}
            title={selectedTheme || "暂无主线主题"}
          >
            {weeklyFocus.length ? (
              weeklyFocus.map((theme) => (
                <option key={theme} value={theme}>{theme}</option>
              ))
            ) : (
              <option value="">暂无主线主题</option>
            )}
          </select>
        </label>
        <button
          type="button"
          style={{
            ...styles.ghostBtn,
            ...(isPending || disabled || !onJumpToThemeStart ? styles.btnDisabled : {})
          }}
          disabled={isPending || disabled || !onJumpToThemeStart}
          onClick={() => { if (onJumpToThemeStart) onJumpToThemeStart(); }}
        >
          跳转首页
        </button>
      </div>

      {/* Input */}
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

      {/* Error */}
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

      {/* Conversation turns */}
      {turns.length ? (
        <div style={styles.transcript}>
          <span style={styles.caption}>对话记录</span>
          <div style={styles.turnList}>
            {sortedTurns.map((turn, index) => (
              <div
                key={buildTurnKey(turn.createdAt, index)}
                style={styles.turnCard}
              >
                {/* User message */}
                <div style={styles.userSection}>
                  <div style={styles.turnMeta}>
                    <span style={styles.roleLabel}>
                      {isAttemptTurn(turn.learnerMessage) ? "答题记录" : "你"}
                    </span>
                    <span style={styles.timeLabel}>{formatTurnTime(turn.createdAt)}</span>
                  </div>
                  <p style={styles.userMessage}>{formatLearnerMessage(turn.learnerMessage)}</p>
                </div>

                {/* AI reply */}
                <div style={styles.aiSection}>
                  <span style={styles.aiLabel}>AI</span>
                  <p style={styles.aiMessage}>{turn.assistantReply}</p>
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
                  {turn.personaSlotTrace?.length ? (
                    <div style={styles.traceWrap}>
                      <span style={styles.traceTitle}>本轮参考人格插槽</span>
                      <div style={styles.traceList}>
                        {turn.personaSlotTrace.map((item, idx) => (
                          <div key={`${turn.createdAt}:${item.kind}:${idx}`} style={styles.traceItem}>
                            <strong>{item.label}</strong>
                            <span style={styles.traceReason}>{item.reason}</span>
                            <span>{item.contentExcerpt}</span>
                          </div>
                        ))}
                      </div>
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
            ))}
          </div>
        </div>
      ) : session?.reply ? (
        <div style={styles.aiSection}>
          <span style={styles.aiLabel}>AI</span>
          <p style={styles.aiMessage}>{session.reply}</p>
          {session.personaSlotTrace?.length ? (
            <div style={styles.traceWrap}>
              <span style={styles.traceTitle}>本轮参考人格插槽</span>
              <div style={styles.traceList}>
                {session.personaSlotTrace.map((item, idx) => (
                  <div key={`${item.kind}:${idx}`} style={styles.traceItem}>
                    <strong>{item.label}</strong>
                    <span style={styles.traceReason}>{item.reason}</span>
                    <span>{item.contentExcerpt}</span>
                  </div>
                ))}
              </div>
            </div>
          ) : null}
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
      ) : null}
    </div>
  );
}

const styles: Record<string, CSSProperties> = {
  wrap: {
    display: "grid",
    gap: 14,
  },
  themeRow: {
    display: "flex",
    alignItems: "flex-end",
    gap: 8,
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
  },
  textarea: {
    minHeight: 76,
    border: "1px solid var(--border)",
    padding: "8px 10px",
    background: "var(--panel)",
    resize: "vertical",
    fontSize: 14,
    lineHeight: 1.6,
    color: "var(--ink)",
  },
  sendBtn: {
    border: "none",
    height: 76,
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
    gap: 10,
  },
  turnList: {
    display: "grid",
    gap: 0,
  },
  turnCard: {
    display: "grid",
    gap: 0,
    borderBottom: "1px solid var(--border)",
    paddingBottom: 16,
    marginBottom: 16,
  },
  userSection: {
    display: "grid",
    gap: 6,
    marginBottom: 12,
  },
  aiSection: {
    display: "grid",
    gap: 8,
  },
  turnMeta: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 12,
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
    padding: "8px 12px",
    background: "var(--panel)",
    borderLeft: "2px solid var(--border-strong)",
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
  questionWrap: {
    display: "grid",
    gap: 8,
    borderTop: "1px solid var(--border)",
    paddingTop: 10,
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
    border: "1px solid var(--border)",
    padding: "8px 10px",
    background: "transparent",
    color: "var(--ink)",
    cursor: "pointer",
    fontSize: 13,
  },
  choiceButtonActive: {
    borderColor: "var(--accent)",
    background: "var(--accent-soft)",
    color: "var(--accent)",
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
  traceWrap: {
    marginTop: 8,
    border: "1px solid var(--border)",
    background: "var(--panel)",
    padding: "8px 10px",
    display: "grid",
    gap: 8,
  },
  traceTitle: {
    fontSize: 12,
    fontWeight: 700,
    color: "var(--ink)",
  },
  traceList: {
    display: "grid",
    gap: 6,
  },
  traceItem: {
    display: "grid",
    gap: 2,
    fontSize: 12,
    lineHeight: 1.6,
    color: "var(--muted)",
  },
  traceReason: {
    color: "var(--teal)",
    fontSize: 11,
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

  if (question.questionType === "multiple_choice") {
    const selected = selectedChoices[turnKey] ?? "";
    return (
      <>
        <p style={styles.questionTitle}>选择题</p>
        <span style={styles.questionMeta}>{question.topic || "章节练习"} · {question.difficulty}</span>
        <p style={styles.aiMessage}>{question.prompt}</p>
        <div style={styles.choiceList}>
          {question.options.map((option) => (
            <button
              key={`${turnKey}:${option.key}`}
              type="button"
              style={{ ...styles.choiceButton, ...(selected === option.key ? styles.choiceButtonActive : {}) }}
              onClick={() => setSelectedChoices((current) => ({ ...current, [turnKey]: option.key }))}
            >
              {option.key}. {option.text}
            </button>
          ))}
        </div>
        <div style={styles.questionActions}>
          <button
            type="button"
            style={styles.checkButton}
            disabled={!selected || disabled}
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
          {feedback ? <span style={feedback.ok ? styles.feedbackOk : styles.feedbackBad}>{feedback.text}</span> : null}
        </div>
        {explanationVisible ? (
          <div style={styles.explanationBox}>{question.explanation || "暂无解析"}</div>
        ) : null}
      </>
    );
  }

  const value = blankAnswers[turnKey] ?? "";
  return (
    <>
      <p style={styles.questionTitle}>填空题</p>
      <span style={styles.questionMeta}>{question.topic || "章节练习"} · {question.difficulty}</span>
      <p style={styles.aiMessage}>{question.prompt}</p>
      <input
        type="text"
        value={value}
        style={styles.blankInput}
        onChange={(event) => {
          const next = event.target.value;
          setBlankAnswers((current) => ({ ...current, [turnKey]: next }));
        }}
        placeholder="输入你的答案"
      />
      <div style={styles.questionActions}>
        <button
          type="button"
          style={styles.checkButton}
          disabled={!value.trim() || disabled}
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
        {feedback ? <span style={feedback.ok ? styles.feedbackOk : styles.feedbackBad}>{feedback.text}</span> : null}
      </div>
      {explanationVisible ? (
        <div style={styles.explanationBox}>{question.explanation || "暂无解析"}</div>
      ) : null}
    </>
  );
}

function normalizeAnswer(value: string) {
  return value.trim().toLowerCase().replace(/\s+/g, " ");
}

function isAttemptTurn(message: string) {
  return message.trim().startsWith("[练习作答]");
}

function formatLearnerMessage(message: string) {
  if (!isAttemptTurn(message)) return message;
  return message.replace("[练习作答]", "练习作答").trim();
}
