import { useEffect, useRef, useState } from "react";
import type { StudyNoteReference } from "@vibe-learner/shared";
import { orderStudySessionTurns } from "../../lib/study-session-decode";
import { RichTextMessage } from "../ui/rich-text-message";
import type { StudyConsoleProps } from "./study-console-types";
import { StudyQuestionCard, type StudyQuestionCardProps } from "./study-question-card";
import { CharacterEventDetails } from "./study-character-event-details";
import { StudyTurnAttachments } from "./study-attachments";
import {
  buildRenderableReply,
  formatTurnTime,
  isHiddenLearnerMessage,
  formatLearnerMessage,
} from "./study-console-format";

type StudyMessageFlowProps = Pick<
  StudyConsoleProps,
  | "turns"
  | "session"
  | "onOpenCitation"
  | "onOpenNoteReference"
  | "onAsk"
  | "onSubmitQuestionAttempt"
  | "onContinueAfterQuestion"
  | "disabled"
  | "isPending"
  | "chatErrorMessage"
> &
  Pick<
    StudyQuestionCardProps,
    | "selectedChoices"
    | "blankAnswers"
    | "expandedExplanation"
    | "setSelectedChoices"
    | "setBlankAnswers"
    | "setExpandedExplanation"
  > & { personaName: string };

export function StudyMessageFlow({
  turns,
  session,
  onOpenCitation,
  onOpenNoteReference,
  onAsk,
  onSubmitQuestionAttempt,
  onContinueAfterQuestion,
  disabled,
  isPending,
  chatErrorMessage,
  personaName,
  selectedChoices,
  blankAnswers,
  expandedExplanation,
  setSelectedChoices,
  setBlankAnswers,
  setExpandedExplanation,
}: StudyMessageFlowProps) {
  const [questionAttemptStates, setQuestionAttemptStates] = useState<
    Record<string, "submitting" | "failed">
  >({});
  const questionAttemptInFlightRef = useRef(new Set<string>());
  const transcriptRef = useRef<HTMLDivElement | null>(null);

  const sortedTurns = orderStudySessionTurns(turns);

  useEffect(() => {
    const node = transcriptRef.current;
    if (!node) return;
    node.scrollTop = node.scrollHeight;
  }, [sortedTurns.length, session?.reply, chatErrorMessage]);

  return (
    <div className="study-console-transcript">
      {turns.length ? (
        <div ref={transcriptRef} className="study-console-turn-list">
          {sortedTurns.map((turn) => (
            <div key={turn.id} className="study-console-turn-card">
              {!isHiddenLearnerMessage(turn) ? (
                <div className="study-console-user-section">
                  <div className="study-console-turn-meta study-console-turn-meta-right">
                    <span className="study-console-time-label">
                      {formatTurnTime(turn.createdAt)}
                    </span>
                    <span className="study-console-role-label">你</span>
                  </div>
                  <p className="study-console-user-message">
                    {formatLearnerMessage(turn)}
                  </p>
                  <StudyTurnAttachments attachments={turn.learnerAttachments} />
                </div>
              ) : null}

              <div className="study-console-ai-section">
                <div className="study-console-turn-meta">
                  <span className="study-console-ai-label">{personaName}</span>
                  <span className="study-console-time-label">
                    {formatTurnTime(turn.createdAt)}
                  </span>
                </div>
                <div className="study-console-ai-bubble">
                  <RichTextMessage
                    content={buildRenderableReply(turn.assistantReply, turn.richBlocks)}
                    className="study-console-ai-message"
                  />
                  <CharacterEventDetails events={turn.characterEvents} />
                  <SearchedNotes
                    references={turn.studyNoteReferences}
                    onOpen={onOpenNoteReference}
                  />
                  {turn.interactiveQuestion ? (
                    <div className="study-console-question-wrap">
                      <StudyQuestionCard
                        {...{
                          question: turn.interactiveQuestion,
                          turnKey: turn.id,
                          selectedChoices,
                          blankAnswers,
                          setSelectedChoices,
                          setBlankAnswers,
                          attemptState: questionAttemptStates[turn.id],
                          onAttemptStateChange: (state) => {
                            setQuestionAttemptStates((current) => {
                              if (state) return { ...current, [turn.id]: state };
                              const next = { ...current };
                              delete next[turn.id];
                              return next;
                            });
                          },
                          attemptInFlight: questionAttemptInFlightRef.current,
                          expandedExplanation,
                          setExpandedExplanation,
                          onAsk,
                          onSubmitQuestionAttempt,
                          onContinueAfterQuestion,
                          disabled: Boolean(disabled || isPending),
                        }}
                      />
                    </div>
                  ) : null}
                  {turn.citations.length ? (
                    <div className="study-console-citations">
                      {turn.citations.map((citation, citationIndex) => (
                        <button
                          key={`${turn.id}:${citation.sectionId}:${citation.pageStart}:${citation.pageEnd}:${citationIndex}`}
                          type="button"
                          className="study-console-citation"
                          onClick={() => {
                            if (onOpenCitation) onOpenCitation(citation);
                          }}
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
        <div ref={transcriptRef} className="study-console-turn-list">
          <div className="study-console-turn-card">
            <div className="study-console-ai-section">
              <div className="study-console-turn-meta">
                <span className="study-console-ai-label">{personaName}</span>
              </div>
              <div className="study-console-ai-bubble">
                <RichTextMessage
                  content={buildRenderableReply(session.reply, session.richBlocks)}
                  className="study-console-ai-message"
                />
                <CharacterEventDetails events={session.characterEvents} />
                <SearchedNotes
                  references={session.studyNoteReferences}
                  onOpen={onOpenNoteReference}
                />
                {session.citations.length ? (
                  <div className="study-console-citations">
                    {session.citations.map((citation, index) => (
                      <button
                        key={`${citation.sectionId}:${citation.pageStart}:${citation.pageEnd}:${index}`}
                        type="button"
                        className="study-console-citation"
                        onClick={() => {
                          if (onOpenCitation) onOpenCitation(citation);
                        }}
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
        <div className="study-console-empty-transcript-card">
          <p className="study-console-empty-transcript-text">
            开始提问后会显示在这里。
          </p>
        </div>
      )}
    </div>
  );
}

function SearchedNotes({
  references,
  onOpen,
}: {
  references: StudyNoteReference[] | undefined;
  onOpen: ((reference: StudyNoteReference) => void) | undefined;
}) {
  if (!references?.length) return null;
  return (
    <div className="study-console-citations" role="group" aria-label="检索到的笔记">
      <span>检索到的笔记</span>
      {references.map((reference) => (
        <button
          key={reference.noteId}
          type="button"
          className="study-console-citation"
          onClick={() => onOpen?.(reference)}
          disabled={!onOpen}
        >
          {reference.title}
        </button>
      ))}
    </div>
  );
}
