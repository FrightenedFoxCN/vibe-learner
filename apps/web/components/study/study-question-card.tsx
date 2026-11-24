import type { Dispatch, SetStateAction } from "react";
import { useEffect, useId, useRef, useState } from "react";
import type { InteractiveQuestion } from "@vibe-learner/shared";
import { RichTextMessage } from "../ui/rich-text-message";
import {
  studyQuestionAttemptDisplayAnswer,
  type StudyQuestionAttemptCardState,
} from "../../lib/study-question-attempt";

export interface StudyQuestionCardProps {
  question: InteractiveQuestion;
  turnKey: string;
  selectedChoices: Record<string, string>;
  blankAnswers: Record<string, string>;
  setSelectedChoices: Dispatch<SetStateAction<Record<string, string>>>;
  setBlankAnswers: Dispatch<SetStateAction<Record<string, string>>>;
  attemptState?: StudyQuestionAttemptCardState;
  expandedExplanation: Record<string, boolean>;
  setExpandedExplanation: Dispatch<SetStateAction<Record<string, boolean>>>;
  onAsk: (message: string, attachments: File[]) => Promise<boolean> | boolean;
  onSubmitQuestionAttempt: (input: {
    turnId: string;
    submittedAnswer: string;
  }) => void | Promise<void>;
  onContinueAfterQuestion?: (turnId: string) => boolean | Promise<boolean>;
  disabled: boolean;
}

export function StudyQuestionCard({
  question,
  turnKey,
  selectedChoices,
  blankAnswers,
  setSelectedChoices,
  setBlankAnswers,
  attemptState,
  expandedExplanation,
  setExpandedExplanation,
  onAsk,
  onSubmitQuestionAttempt,
  onContinueAfterQuestion,
  disabled,
}: StudyQuestionCardProps) {
  const id = useId();
  const root = useRef<HTMLDivElement>(null);
  const feedback = useRef<HTMLParagraphElement>(null);
  const restoreFocus = useRef(false);
  const [showContinuationConfirm, setShowContinuationConfirm] = useState(false);
  const isLocked = question.result !== null;
  const phase = isLocked ? undefined : attemptState?.phase;
  const isSubmitting = phase === "submitting" || phase === "reading_back";
  const isAwaitingRead = phase === "retry_read";
  const isAwaitingConfirmation = phase === "retry_submit";
  const isAnswerLocked =
    isLocked || isSubmitting || isAwaitingRead || isAwaitingConfirmation;
  const isChoice = question.questionType === "multiple_choice";
  const draft = (isChoice ? selectedChoices[turnKey] : blankAnswers[turnKey]) ?? "";
  const value = studyQuestionAttemptDisplayAnswer(question, attemptState, draft);
  const explanationVisible = isLocked && Boolean(expandedExplanation[turnKey]);
  const feedbackText = question.result
    ? `${question.result.feedbackText} · 已记录`
    : phase === "failed"
      ? "答案未记录，请检查后重新提交。"
      : phase === "submitting"
        ? "正在保存到学习记录…"
        : phase === "reading_back"
          ? "答案已记录，正在读取结果…"
          : isAwaitingRead
            ? "答案已记录，但暂时无法读取结果。无需重新提交。"
            : isAwaitingConfirmation
              ? "暂时无法确认答案是否已记录。请重试确认原答案。"
              : "";
  const submitLabel =
    phase === "submitting"
      ? "正在记录答案…"
      : phase === "reading_back"
        ? "正在读取结果…"
        : isAwaitingRead
          ? "重试读取结果"
          : isAwaitingConfirmation
            ? "重试确认原答案"
            : phase === "failed"
              ? "重新提交答案"
              : "提交答案";

  useEffect(() => {
    if (
      !restoreFocus.current ||
      (!isLocked && phase !== "failed" && !isAwaitingRead && !isAwaitingConfirmation)
    )
      return;
    restoreFocus.current = false;
    // Only return focus for this submission while the learner remains here.
    // A late result from another page or after moving to another control cannot steal it.
    if (
      root.current &&
      (root.current.contains(document.activeElement) ||
        document.activeElement === document.body)
    ) {
      feedback.current?.focus({ preventScroll: true });
    }
  }, [isLocked, phase, isAwaitingRead, isAwaitingConfirmation]);

  const submitAttempt = () => {
    if (disabled || isLocked || isSubmitting || !value.trim()) return;
    restoreFocus.current = true;
    void onSubmitQuestionAttempt({ turnId: turnKey, submittedAnswer: value });
  };

  return (
    <div ref={root} className="study-console-question-card">
      <fieldset
        aria-busy={isSubmitting}
        aria-describedby={`${id}-prompt ${id}-meta`}
        className="study-console-question-fieldset"
      >
        <legend className="study-console-question-title">
          {isChoice ? "选择题（单选）" : "填空题"}
        </legend>
        <span id={`${id}-meta`} className="study-console-question-meta">
          {question.topic || "章节练习"} · {question.difficulty}
        </span>
        <div id={`${id}-prompt`}>
          <RichTextMessage
            content={question.prompt}
            className="study-console-ai-message"
          />
        </div>
        {isChoice ? (
          <div
            className="study-console-choice-list"
            role="radiogroup"
            aria-label="选择一个答案"
            aria-describedby={`${id}-prompt`}
          >
            {question.options.map((option) => (
              <label
                key={option.key}
                className="study-console-choice-button"
                data-selected={value === option.key || undefined}
                data-locked={isAnswerLocked || undefined}
              >
                <input
                  type="radio"
                  name={`${id}-choice`}
                  value={option.key}
                  checked={value === option.key}
                  disabled={disabled || isAnswerLocked}
                  onChange={() =>
                    setSelectedChoices((current) => ({
                      ...current,
                      [turnKey]: option.key,
                    }))
                  }
                />
                <RichTextMessage
                  content={`${option.key}. ${option.text}`}
                  inline
                  className="study-console-choice-button-text"
                />
              </label>
            ))}
          </div>
        ) : (
          <label htmlFor={`${id}-answer`}>
            你的答案
            <input
              id={`${id}-answer`}
              type="text"
              value={value}
              className="study-console-blank-input"
              data-locked={isAnswerLocked || undefined}
              aria-describedby={`${id}-prompt${phase === "failed" ? ` ${id}-feedback` : ""}`}
              onChange={(event) =>
                setBlankAnswers((current) => ({
                  ...current,
                  [turnKey]: event.target.value,
                }))
              }
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.nativeEvent.isComposing) {
                  event.preventDefault();
                  void submitAttempt();
                }
              }}
              readOnly={disabled || isAnswerLocked}
              placeholder="输入你的答案"
            />
          </label>
        )}
        <div className="study-console-question-actions">
          <button
            type="button"
            className="study-console-check-button study-console-question-action"
            disabled={!value.trim() || disabled || isLocked || isSubmitting}
            onClick={() => void submitAttempt()}
          >
            {submitLabel}
          </button>
          {isLocked && (
            <button
              type="button"
              className="study-console-inline-ghost-btn study-console-question-action"
              aria-expanded={explanationVisible}
              aria-controls={`${id}-explanation`}
              onClick={() =>
                setExpandedExplanation((current) => ({
                  ...current,
                  [turnKey]: !current[turnKey],
                }))
              }
            >
              {explanationVisible ? "收起解析" : "查看解析"}
            </button>
          )}
          {isLocked && question.callBack && onContinueAfterQuestion ? (
            <button
              type="button"
              className="study-console-inline-ghost-btn study-console-question-action"
              disabled={disabled || isSubmitting}
              aria-expanded={showContinuationConfirm}
              aria-controls={`${id}-continuation-confirm`}
              onClick={() => setShowContinuationConfirm(true)}
            >
              生成答题讲解
            </button>
          ) : null}
          <button
            type="button"
            className="study-console-inline-ghost-btn study-console-question-action"
            disabled={disabled || isSubmitting}
            onClick={() => {
              void onAsk(
                `请围绕${question.topic || "本章节核心概念"}再出一道同难度${isChoice ? "选择题" : "填空题"}。`,
                [],
              );
            }}
          >
            再来一题（调用模型）
          </button>
        </div>
      </fieldset>
      {showContinuationConfirm ? (
        <div
          id={`${id}-continuation-confirm`}
          role="status"
          className="study-console-explanation-box"
        >
          <p className="m-0">
            继续会调用学习模型，可能产生费用并需要等待；答案已经记录，取消不会影响评分结果。
          </p>
          <div className="study-console-question-actions">
            <button
              type="button"
              className="study-console-check-button study-console-question-action"
              disabled={disabled}
              onClick={() => {
                setShowContinuationConfirm(false);
                void onContinueAfterQuestion?.(turnKey);
              }}
            >
              继续生成（调用模型）
            </button>
            <button
              type="button"
              className="study-console-inline-ghost-btn study-console-question-action"
              disabled={disabled}
              onClick={() => setShowContinuationConfirm(false)}
            >
              取消
            </button>
          </div>
        </div>
      ) : null}
      <p
        id={`${id}-feedback`}
        ref={feedback}
        tabIndex={-1}
        role={phase === "failed" && !question.result ? "alert" : "status"}
        aria-atomic="true"
        className={
          question.result?.isCorrect
            ? "study-console-feedback-ok"
            : phase === "failed" || question.result
              ? "study-console-feedback-bad"
              : "study-console-question-pending"
        }
      >
        {feedbackText}
      </p>
      {value.trim() && (
        <p className="study-console-answer-inline">
          {isChoice ? "你的选择" : "你的答案"}：{value.trim()}
        </p>
      )}
      {explanationVisible && (
        <div id={`${id}-explanation`} className="study-console-explanation-box">
          <RichTextMessage content={question.result?.explanation || "暂无解析"} />
        </div>
      )}
    </div>
  );
}
