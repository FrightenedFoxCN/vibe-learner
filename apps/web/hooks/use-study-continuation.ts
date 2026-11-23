"use client";

import { useCallback, useEffect, useEffectEvent, useRef, useState } from "react";
import type { StudySessionRecord } from "@vibe-learner/shared";
import { StudyAsyncViewFence } from "../lib/async-result-fence";
import {
  cancelStudySessionFollowUps,
  getStudySession,
} from "../lib/data/study-sessions";
import { readBackFollowUpCancellation } from "../lib/study-follow-up-cancel";
import {
  STUDY_QUERY_WAIT_MS,
  withStudyRequestDeadline,
} from "../lib/study-request-deadline";
import {
  readInterruptedDialogueSessionId,
  writeInterruptedDialogueSessionId,
  appendDeferredInteractiveCallback,
} from "../lib/study-dialogue-interruption";
import { studyOperationStore } from "../lib/study-operation-state";
import {
  buildInteractiveCallbackMessage,
  buildSessionPreludeMessage,
} from "../lib/study-continuation-messages";
import { resolveStudySessionErrorNotice } from "../lib/study-session-decode";
import { logWorkspaceError } from "../lib/learning-workspace-telemetry";
import type { useStudyMessages } from "./use-study-messages";
import type { useStudySessionNavigation } from "./use-study-session-navigation";

interface ContinuationOptions {
  session: StudySessionRecord | null;
  view: StudyAsyncViewFence<StudySessionRecord>;
  ensureSessionForSection: ReturnType<
    typeof useStudySessionNavigation
  >["ensureSessionForSection"];
  sendHiddenSessionMessage: ReturnType<
    typeof useStudyMessages
  >["sendHiddenSessionMessage"];
  automaticStudyRequest: ReturnType<typeof useStudyMessages>["automaticStudyRequest"];
  onSession: (session: StudySessionRecord) => void;
  onNotice: (notice: string) => void;
}
export interface StudyContinuationPort {
  cancelStudySessionFollowUps: typeof cancelStudySessionFollowUps;
  getStudySession: typeof getStudySession;
  readInterruptedDialogueSessionId: typeof readInterruptedDialogueSessionId;
  writeInterruptedDialogueSessionId: typeof writeInterruptedDialogueSessionId;
  appendDeferredInteractiveCallback: typeof appendDeferredInteractiveCallback;
  hasPendingOperation: (sessionId: string) => boolean;
  now: () => number;
  setTimeout: (callback: () => void, delay: number) => number;
  clearTimeout: (id: number) => void;
}
const defaultPort: StudyContinuationPort = {
  cancelStudySessionFollowUps,
  getStudySession,
  readInterruptedDialogueSessionId,
  writeInterruptedDialogueSessionId,
  appendDeferredInteractiveCallback,
  hasPendingOperation: (id) =>
    studyOperationStore.readPendingStudyOperation()?.sessionId === id,
  now: Date.now,
  setTimeout: (callback, delay) => window.setTimeout(callback, delay),
  clearTimeout: (id) => window.clearTimeout(id),
};

export function useStudyContinuation(
  options: ContinuationOptions,
  port: StudyContinuationPort = defaultPort,
) {
  const latest = useRef(options);
  latest.current = options;
  const mounted = useRef(false);
  const paused = useRef("");
  const [pausedSession, setPausedSession] = useState("");
  const [pendingCount, setPendingCount] = useState(0);
  const preludes = useRef(new Set<string>());
  const failedPreludes = useRef(new Set<string>());
  const followUps = useRef(new Set<string>());
  const timers = useRef(new Map<string, number>());
  const interrupting = useRef(false);
  const withheldFollowUps = useRef(new Map<string, ReadonlySet<string>>());
  const [timerGeneration, setTimerGeneration] = useState(0);
  const begin = () => setPendingCount((count) => count + 1);
  const finish = () => {
    if (mounted.current) setPendingCount((count) => count - 1);
  };
  const current = (
    session: StudySessionRecord,
    revision = latest.current.view.viewRevision,
  ) =>
    mounted.current &&
    latest.current.view.session?.id === session.id &&
    latest.current.view.session.studyUnitId === session.studyUnitId &&
    latest.current.view.viewRevision === revision;
  function pause(sessionId: string) {
    paused.current = sessionId.trim();
    setPausedSession(paused.current);
    port.writeInterruptedDialogueSessionId(paused.current);
  }
  const isDialogueInterruptedForSession = (id: string) =>
    Boolean(id.trim() && paused.current === id.trim());
  const syncDialogueInterruption = useCallback(() => {
    if (!mounted.current) return;
    paused.current = port.readInterruptedDialogueSessionId();
    setPausedSession(paused.current);
  }, [port]);
  useEffect(() => {
    mounted.current = true;
    syncDialogueInterruption();
    const scheduledTimers = timers.current;
    return () => {
      mounted.current = false;
      scheduledTimers.forEach((id) => port.clearTimeout(id));
      scheduledTimers.clear();
    };
  }, [port, syncDialogueInterruption]);

  async function runPrelude(
    session: StudySessionRecord,
    input: {
      studyUnitId: string;
      sectionTitle: string;
      themeHint: string;
      force?: boolean;
    },
  ) {
    if (
      !current(session) ||
      !input.studyUnitId.trim() ||
      port.hasPendingOperation(session.id)
    )
      return false;
    const key = `${session.id}:${input.studyUnitId}`;
    if (preludes.current.has(key)) return false;
    if (input.force) failedPreludes.current.delete(key);
    else if (
      session.preparedStudyUnitIds?.includes(input.studyUnitId) ||
      failedPreludes.current.has(key)
    )
      return false;
    preludes.current.add(key);
    begin();
    const revision = latest.current.view.viewRevision;
    try {
      const operationKey = `prelude:${key}:${session.revision}`;
      const receipt = await latest.current.sendHiddenSessionMessage({
        session,
        operationKey,
        ...latest.current.automaticStudyRequest(operationKey, "prelude"),
        message: buildSessionPreludeMessage(input),
        messageKind: "session_prelude",
      });
      return receipt !== null;
    } catch (error) {
      failedPreludes.current.add(key);
      if (current(session, revision))
        latest.current.onNotice(
          resolveStudySessionErrorNotice(
            error,
            `章节准备失败：${String(error)}`,
            "response",
          ),
        );
      logWorkspaceError("workflow:study_session:prelude_error", error);
      return false;
    } finally {
      preludes.current.delete(key);
      finish();
    }
  }
  async function triggerSessionPrelude(input: {
    studyUnitId: string;
    sectionTitle?: string;
    themeHint?: string;
  }) {
    if (!mounted.current) return false;
    const session = await latest.current.ensureSessionForSection(input.studyUnitId, {
      clearResponseOnSwitch: false,
    });
    return session
      ? runPrelude(session, {
          ...input,
          sectionTitle:
            input.sectionTitle || session.studyUnitTitle || session.studyUnitId,
          themeHint: input.themeHint ?? session.themeHint ?? "",
          force: true,
        })
      : false;
  }
  async function triggerInteractiveQuestionCallback(
    session: StudySessionRecord,
    input: { turnId: string; diagnosticFlowId?: string | null },
  ) {
    if (!current(session)) return false;
    const question = session.turns.find(
      (turn) => turn.id === input.turnId,
    )?.interactiveQuestion;
    if (!question?.callBack) return false;
    const result = question.result;
    if (
      !result?.submittedAnswer ||
      typeof result.isCorrect !== "boolean" ||
      !result.feedbackText.trim()
    ) {
      logWorkspaceError(
        "workflow:study_attempt:callback_read_back_missing",
        new Error("study_question_attempt_callback_read_back_missing"),
      );
      return false;
    }
    const message = buildInteractiveCallbackMessage({
      questionType: question.questionType,
      prompt: question.prompt,
      topic: question.topic,
      submittedAnswer: result.submittedAnswer,
      isCorrect: result.isCorrect,
      explanation: result.explanation,
    });
    if (
      isDialogueInterruptedForSession(session.id) ||
      port.hasPendingOperation(session.id)
    ) {
      port.appendDeferredInteractiveCallback(session.id, message);
      if (!isDialogueInterruptedForSession(session.id)) pause(session.id);
      latest.current.onNotice(
        "答案已记录；已暂停自动续接，会在你下次主动发言前补入答题结果。",
      );
      return false;
    }
    begin();
    const revision = latest.current.view.viewRevision;
    try {
      const operationKey = `callback:${session.id}:${input.turnId}:${session.revision}`;
      const receipt = await latest.current.sendHiddenSessionMessage({
        session,
        operationKey,
        ...latest.current.automaticStudyRequest(operationKey, "callback"),
        message,
        messageKind: "interactive_callback",
        diagnosticFlowId: input.diagnosticFlowId,
      });
      return receipt !== null;
    } catch (error) {
      if (current(session, revision))
        latest.current.onNotice(
          resolveStudySessionErrorNotice(
            error,
            `答案已记录，续问失败：${String(error)}`,
            "response",
          ),
        );
      logWorkspaceError("workflow:study_attempt:callback_error", error);
      return false;
    } finally {
      finish();
    }
  }
  async function interruptDialogue() {
    const session = latest.current.view.session;
    if (!mounted.current || interrupting.current) return false;
    if (!session) {
      latest.current.onNotice("当前还没有可打断的学习单元会话。");
      return false;
    }
    const pending = (session.pendingFollowUps ?? []).filter(
      (item) => item.status === "pending",
    );
    if (!pending.length) {
      if (isDialogueInterruptedForSession(session.id)) {
        latest.current.onNotice(
          "当前已暂停自动续接；答题结果会等你下次主动发言时再补入。",
        );
        return false;
      }
      pause(session.id);
      latest.current.onNotice("已暂停当前自动续接；之后提交答案不会立即续聊。");
      return true;
    }
    pending.forEach((item) => {
      const key = `${session.id}:${item.id}`;
      const timer = timers.current.get(key);
      if (timer !== undefined) port.clearTimeout(timer);
      timers.current.delete(key);
    });
    interrupting.current = true;
    const targetIds = new Set(pending.map((item) => item.id));
    withheldFollowUps.current.set(session.id, targetIds);
    begin();
    const revision = latest.current.view.viewRevision;
    try {
      const next = await withStudyRequestDeadline(STUDY_QUERY_WAIT_MS, (signal) =>
        port.cancelStudySessionFollowUps({ sessionId: session.id, signal }),
      );
      withheldFollowUps.current.delete(session.id);
      if (!current(session, revision)) return false;
      if (latest.current.view.session!.revision <= next.revision)
        latest.current.onSession(next);
      pause(next.id);
      latest.current.onNotice("已打断当前自动续接；之后提交答案不会立即续聊。");
      return true;
    } catch (error) {
      const readBack = await readBackFollowUpCancellation(session, targetIds, () =>
        withStudyRequestDeadline(STUDY_QUERY_WAIT_MS, (signal) =>
          port.getStudySession(session.id, undefined, signal),
        ),
      );
      if (current(session, revision)) {
        const visible = latest.current.view.session!;
        if (
          readBack.state === "unknown" ||
          readBack.session.revision < visible.revision
        ) {
          latest.current.onNotice(
            "无法确认是否已打断。相关续接暂不自动发送，请再次举手重试。",
          );
        } else {
          withheldFollowUps.current.delete(session.id);
          if (readBack.session.revision > visible.revision)
            latest.current.onSession(readBack.session);
          if (readBack.state === "stopped") {
            pause(session.id);
            latest.current.onNotice("已确认原续接不再等待；之后提交答案不会立即续聊。");
            return true;
          }
          latest.current.onNotice(
            resolveStudySessionErrorNotice(
              error,
              "打断未完成，已恢复仍待执行的自动续接。",
              "update",
            ),
          );
        }
      } else if (readBack.state !== "unknown") {
        withheldFollowUps.current.delete(session.id);
      }
      logWorkspaceError("workflow:study_follow_up:interrupt_error", error);
      return false;
    } finally {
      interrupting.current = false;
      if (mounted.current) setTimerGeneration((generation) => generation + 1);
      finish();
    }
  }

  const reconcileFollowUpTimers = useEffectEvent(
    (session: StudySessionRecord | null) => {
      const pending = (session?.pendingFollowUps ?? []).filter(
        (item) => item.status === "pending",
      );
      const keys = new Set(pending.map((item) => `${session!.id}:${item.id}`));
      timers.current.forEach((timer, key) => {
        if (!keys.has(key)) {
          port.clearTimeout(timer);
          timers.current.delete(key);
        }
      });
      if (!session || isDialogueInterruptedForSession(session.id)) return;
      pending.forEach((item) => {
        const key = `${session.id}:${item.id}`;
        if (
          timers.current.has(key) ||
          followUps.current.has(key) ||
          withheldFollowUps.current.get(session.id)?.has(item.id)
        )
          return;
        const due = Date.parse(item.dueAt || "");
        const timer = port.setTimeout(
          () => {
            timers.current.delete(key);
            const live = latest.current.view.session;
            if (
              !live ||
              !current(session) ||
              isDialogueInterruptedForSession(live.id) ||
              withheldFollowUps.current.get(live.id)?.has(item.id) ||
              port.hasPendingOperation(live.id) ||
              followUps.current.has(key)
            )
              return;
            const followUp = live.pendingFollowUps?.find(
              (candidate) => candidate.id === item.id && candidate.status === "pending",
            );
            if (!followUp) return;
            followUps.current.add(key);
            begin();
            const revision = latest.current.view.viewRevision;
            void (async () => {
              try {
                const operationKey = `follow-up:${live.id}:${item.id}`;
                await latest.current.sendHiddenSessionMessage({
                  session: live,
                  operationKey,
                  ...latest.current.automaticStudyRequest(operationKey, "follow-up"),
                  message: followUp.hiddenMessage,
                  messageKind: "scheduled_follow_up",
                  followUpId: item.id,
                });
              } catch (error) {
                if (
                  current(live, revision) &&
                  !String(error).includes("follow_up_not_pending")
                )
                  latest.current.onNotice(
                    resolveStudySessionErrorNotice(
                      error,
                      `自动续接失败：${String(error)}`,
                      "response",
                    ),
                  );
                logWorkspaceError("workflow:study_follow_up:error", error);
              } finally {
                followUps.current.delete(key);
                finish();
              }
            })();
          },
          Number.isFinite(due) ? Math.max(0, due - port.now()) : 0,
        );
        timers.current.set(key, timer);
      });
    },
  );

  useEffect(() => {
    // A failed timer waits for authoritative Session refresh; busy transitions do not poll it repeatedly.
    reconcileFollowUpTimers(options.session);
  }, [options.session, pausedSession, timerGeneration]);

  return {
    triggerSessionPrelude,
    triggerInteractiveQuestionCallback,
    interruptDialogue,
    isDialogueInterruptedForSession,
    syncDialogueInterruption,
    isDialogueInterrupted: Boolean(
      options.session?.id && options.session.id === pausedSession,
    ),
    isContinuing: pendingCount > 0,
  };
}
