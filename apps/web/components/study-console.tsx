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
      <div style={styles.row}>
        <label style={styles.selectLabel}>
          <span style={styles.selectCaption}>主线主题</span>
          <select
            style={styles.select}
            value={selectedTheme}
            onChange={(event) => onChangeTheme(event.target.value)}
            disabled={isPending || disabled}
            title={selectedTheme || "暂无主线主题"}
          >
            {weeklyFocus.length ? (
              weeklyFocus.map((theme) => (
                <option key={theme} value={theme}>
                  {theme}
                </option>
              ))
            ) : (
              <option value="">暂无主线主题</option>
            )}
          </select>
        </label>
        <button
          type="button"
          style={{
            ...styles.themeJumpButton,
            ...(isPending || disabled || !onJumpToThemeStart ? styles.buttonDisabled : {})
          }}
          disabled={isPending || disabled || !onJumpToThemeStart}
          onClick={() => {
            if (onJumpToThemeStart) {
              onJumpToThemeStart();
            }
          }}
        >
          跳转主题首页
        </button>
      </div>

      <div style={styles.inputRow}>
        <textarea
          style={styles.textarea}
          value={message}
          onChange={(event) => setMessage(event.target.value)}
          placeholder="继续输入问题，或直接追问上一轮内容…"
        />
        <button
          style={{
            ...styles.button,
            ...(isPending || disabled ? styles.buttonDisabled : {})
          }}
          disabled={isPending || disabled}
          onClick={() => onAsk(message)}
        >
          {isPending ? "发送中…" : "发送消息"}
        </button>
      </div>

      {chatErrorMessage ? (
        <div style={styles.errorBox}>
          <div style={styles.errorTitle}>对话请求失败</div>
          <div style={styles.errorText}>{chatErrorMessage}</div>
          <button
            type="button"
            style={{
              ...styles.retryButton,
              ...(isPending || disabled || !onRetryLastAsk ? styles.buttonDisabled : {})
            }}
            disabled={isPending || disabled || !onRetryLastAsk}
            onClick={() => {
              if (onRetryLastAsk) {
                void onRetryLastAsk();
              }
            }}
          >
            {isPending ? "重试中…" : "重试发送"}
          </button>
        </div>
      ) : null}

      {turns.length ? (
        <div style={styles.transcript}>
          <div style={styles.transcriptLabel}>对话记录</div>
          <div style={styles.turnList}>
            {sortedTurns.map((turn, index) => (
              <div
                key={buildTurnKey(turn.createdAt, index)}
                style={{
                  ...styles.turnCard,
                  ...(isAttemptTurn(turn.learnerMessage) ? styles.turnCardAttempt : {})
                }}
              >
                <div style={styles.turnMetaRow}>
                  <span style={styles.turnRole}>{isAttemptTurn(turn.learnerMessage) ? "答题记录" : "你"}</span>
                  <span style={styles.turnTime}>{formatTurnTime(turn.createdAt)}</span>
                </div>
                {isAttemptTurn(turn.learnerMessage) ? (
                  <span style={styles.attemptBadge}>已写回会话</span>
                ) : null}
                <p style={styles.turnText}>{formatLearnerMessage(turn.learnerMessage)}</p>
                <div style={{ ...styles.turnMetaRow, marginTop: 10 }}>
                  <span style={{ ...styles.turnRole, color: "var(--accent)" }}>AI</span>
                </div>
                <p style={styles.turnText}>{turn.assistantReply}</p>
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
                        onClick={() => {
                          if (onOpenPage) {
                            onOpenPage(citation.pageStart);
                          }
                        }}
                        title={`跳转到 p.${citation.pageStart}–${citation.pageEnd}`}
                        disabled={!onOpenPage}
                      >
                        {citation.title} · p.{citation.pageStart}–{citation.pageEnd}
                      </button>
                    ))}
                  </div>
                ) : null}
              </div>
            ))}
          </div>
        </div>
      ) : session?.reply ? (
        <div style={styles.reply}>
          <p style={styles.replyText}>{session.reply}</p>
          {session.citations.length ? (
            <div style={styles.citations}>
              {session.citations.map((citation, index) => (
                <button
                  key={`${citation.sectionId}:${citation.pageStart}:${citation.pageEnd}:${index}`}
                  type="button"
                  style={styles.citation}
                  onClick={() => {
                    if (onOpenPage) {
                      onOpenPage(citation.pageStart);
                    }
                  }}
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
    gap: 14
  },
  row: {
    display: "flex",
    alignItems: "center",
    gap: 8,
    flexWrap: "nowrap"
  },
  selectLabel: {
    display: "grid",
    gap: 4,
    width: "100%",
    minWidth: 0
  },
  selectCaption: {
    fontSize: 11,
    letterSpacing: "0.06em",
    textTransform: "uppercase",
    color: "var(--muted)"
  },
  select: {
    width: "100%",
    height: 32,
    border: "1px solid var(--border)",
    borderRadius: 3,
    padding: "0 8px",
    background: "var(--panel)",
    color: "var(--ink)",
    fontSize: 13,
    maxWidth: "100%",
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap"
  },
  themeJumpButton: {
    border: "1px solid var(--border)",
    borderRadius: 3,
    height: 32,
    padding: "0 10px",
    background: "transparent",
    color: "var(--ink)",
    fontSize: 12,
    fontWeight: 600,
    whiteSpace: "nowrap",
    flexShrink: 0,
    alignSelf: "flex-end",
    cursor: "pointer"
  },
  errorBox: {
    display: "grid",
    gap: 8,
    border: "1px solid #f0c2c2",
    background: "#fff7f7",
    borderRadius: 3,
    padding: "10px 12px"
  },
  errorTitle: {
    fontSize: 12,
    fontWeight: 700,
    color: "#9f1d1d"
  },
  errorText: {
    fontSize: 12,
    color: "#7f1d1d",
    wordBreak: "break-word"
  },
  retryButton: {
    border: "1px solid #f0c2c2",
    borderRadius: 3,
    background: "white",
    color: "#7f1d1d",
    height: 30,
    padding: "0 12px",
    fontSize: 12,
    fontWeight: 600,
    cursor: "pointer",
    width: "fit-content"
  },
  inputRow: {
    display: "flex",
    gap: 10,
    alignItems: "flex-start"
  },
  textarea: {
    flex: 1,
    minHeight: 72,
    border: "1px solid var(--border)",
    borderRadius: 3,
    padding: "8px 10px",
    background: "var(--panel)",
    resize: "vertical",
    fontSize: 14,
    lineHeight: 1.6,
    color: "var(--ink)"
  },
  button: {
    border: "none",
    borderRadius: 3,
    height: 34,
    padding: "0 18px",
    background: "var(--accent)",
    color: "white",
    fontWeight: 600,
    cursor: "pointer",
    fontSize: 13,
    whiteSpace: "nowrap",
    flexShrink: 0,
    alignSelf: "flex-end"
  },
  buttonDisabled: {
    opacity: 0.45,
    cursor: "not-allowed"
  },
  reply: {
    display: "grid",
    gap: 10
  },
  transcript: {
    display: "grid",
    gap: 10
  },
  transcriptLabel: {
    fontSize: 11,
    letterSpacing: "0.06em",
    textTransform: "uppercase",
    color: "var(--muted)"
  },
  turnList: {
    display: "grid",
    gap: 0
  },
  turnCard: {
    display: "grid",
    gap: 8,
    padding: "14px 0",
    borderBottom: "1px solid var(--border)"
  },
  turnCardAttempt: {
    paddingLeft: 12,
    borderLeft: "3px solid var(--teal)"
  },
  turnMetaRow: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 12
  },
  turnRole: {
    fontSize: 11,
    fontWeight: 700,
    letterSpacing: "0.06em",
    textTransform: "uppercase",
    color: "var(--muted)"
  },
  turnTime: {
    fontSize: 11,
    color: "var(--muted)"
  },
  attemptBadge: {
    display: "inline-flex",
    width: "fit-content",
    color: "var(--teal)",
    fontSize: 11,
    fontWeight: 600
  },
  turnText: {
    margin: 0,
    lineHeight: 1.75,
    fontSize: 14,
    whiteSpace: "pre-wrap"
  },
  questionWrap: {
    display: "grid",
    gap: 8,
    borderTop: "1px solid var(--border)",
    paddingTop: 10
  },
  questionTitle: {
    margin: 0,
    fontSize: 13,
    fontWeight: 700,
    color: "var(--ink)"
  },
  questionMeta: {
    fontSize: 12,
    color: "var(--muted)"
  },
  choiceList: {
    display: "grid",
    gap: 8
  },
  choiceButton: {
    textAlign: "left",
    border: "1px solid var(--border)",
    borderRadius: 3,
    padding: "8px 10px",
    background: "transparent",
    color: "var(--ink)",
    cursor: "pointer",
    fontSize: 13
  },
  choiceButtonActive: {
    borderColor: "var(--accent)",
    color: "var(--accent)"
  },
  blankInput: {
    width: "100%",
    border: "1px solid var(--border)",
    borderRadius: 3,
    minHeight: 34,
    padding: "0 10px",
    background: "var(--panel)",
    color: "var(--ink)",
    fontSize: 13
  },
  questionActions: {
    display: "flex",
    alignItems: "center",
    gap: 8,
    flexWrap: "wrap"
  },
  checkButton: {
    border: "1px solid var(--border)",
    borderRadius: 3,
    background: "var(--accent)",
    color: "white",
    height: 30,
    padding: "0 12px",
    fontSize: 12,
    cursor: "pointer"
  },
  feedbackOk: {
    fontSize: 12,
    color: "#0f766e"
  },
  feedbackBad: {
    fontSize: 12,
    color: "#b91c1c"
  },
  inlineGhostBtn: {
    border: "1px solid var(--border)",
    borderRadius: 3,
    background: "transparent",
    color: "var(--muted)",
    height: 30,
    padding: "0 10px",
    fontSize: 12,
    cursor: "pointer"
  },
  explanationBox: {
    marginTop: 4,
    padding: "8px 10px",
    borderRadius: 3,
    border: "1px solid var(--border)",
    background: "var(--panel)",
    fontSize: 12,
    color: "var(--muted)",
    lineHeight: 1.6
  },
  replyText: {
    margin: 0,
    lineHeight: 1.75,
    fontSize: 14
  },
  citations: {
    display: "flex",
    gap: 6,
    flexWrap: "wrap"
  },
  citation: {
    appearance: "none",
    padding: "2px 8px",
    border: "1px solid var(--border)",
    borderRadius: 3,
    fontSize: 12,
    color: "var(--teal)",
    background: "transparent",
    cursor: "pointer"
  }
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
        <p style={styles.turnText}>{question.prompt}</p>
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
              setQuestionFeedback((current) => ({
                ...current,
                [turnKey]: {
                  ok: correct,
                  text: feedbackText
                }
              }));
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
            onClick={() => {
              setExpandedExplanation((current) => ({ ...current, [turnKey]: !current[turnKey] }));
            }}
          >
            {explanationVisible ? "收起解析" : "查看解析"}
          </button>
          <button
            type="button"
            style={styles.inlineGhostBtn}
            disabled={disabled}
            onClick={() => {
              const topic = question.topic || "本章节核心概念";
              void onAsk(`请围绕${topic}再出一道同难度选择题。`);
            }}
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
      <p style={styles.turnText}>{question.prompt}</p>
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
            setQuestionFeedback((current) => ({
              ...current,
              [turnKey]: {
                ok: correct,
                text: feedbackText
              }
            }));
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
          onClick={() => {
            setExpandedExplanation((current) => ({ ...current, [turnKey]: !current[turnKey] }));
          }}
        >
          {explanationVisible ? "收起解析" : "查看解析"}
        </button>
        <button
          type="button"
          style={styles.inlineGhostBtn}
          disabled={disabled}
          onClick={() => {
            const topic = question.topic || "本章节核心概念";
            void onAsk(`请围绕${topic}再出一道同难度填空题。`);
          }}
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
  if (!isAttemptTurn(message)) {
    return message;
  }
  return message.replace("[练习作答]", "练习作答").trim();
}
