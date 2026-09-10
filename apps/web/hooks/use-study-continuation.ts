"use client";

import { useEffect, useRef, useState } from "react";
import type { StudySessionRecord } from "@vibe-learner/shared";
import { StudyAsyncViewFence } from "../lib/async-result-fence";
import { cancelStudySessionFollowUps } from "../lib/data/study-sessions";
import { readInterruptedDialogueSessionId, writeInterruptedDialogueSessionId, appendDeferredInteractiveCallback, readDeferredInteractiveCallbacks, clearDeferredInteractiveCallbacks } from "../lib/study-dialogue-interruption";
import { studyOperationStore } from "../lib/study-operation-state";
import { buildInteractiveCallbackMessage, buildSessionPreludeMessage } from "../lib/study-continuation-messages";
import { resolveStudySessionErrorNotice } from "../lib/study-session-decode";
import { logWorkspaceError } from "../lib/learning-workspace-telemetry";
import type { useStudyMessages } from "./use-study-messages";
import type { useStudySessionNavigation } from "./use-study-session-navigation";

interface ContinuationOptions {
  session: StudySessionRecord | null;
  view: StudyAsyncViewFence<StudySessionRecord>;
  busy: boolean;
  ensureSessionForSection: ReturnType<typeof useStudySessionNavigation>["ensureSessionForSection"];
  sendHiddenSessionMessage: ReturnType<typeof useStudyMessages>["sendHiddenSessionMessage"];
  automaticStudyRequest: ReturnType<typeof useStudyMessages>["automaticStudyRequest"];
  onSession: (session: StudySessionRecord) => void;
  onNotice: (notice: string) => void;
}
export interface StudyContinuationPort {
  cancelStudySessionFollowUps: typeof cancelStudySessionFollowUps;
  readInterruptedDialogueSessionId: typeof readInterruptedDialogueSessionId;
  writeInterruptedDialogueSessionId: typeof writeInterruptedDialogueSessionId;
  appendDeferredInteractiveCallback: typeof appendDeferredInteractiveCallback;
  readDeferredInteractiveCallbacks: typeof readDeferredInteractiveCallbacks;
  clearDeferredInteractiveCallbacks: typeof clearDeferredInteractiveCallbacks;
  hasPendingOperation: (sessionId: string) => boolean;
  now: () => number;
  setTimeout: (callback: () => void, delay: number) => number;
  clearTimeout: (id: number) => void;
}
const defaultPort: StudyContinuationPort = {
  cancelStudySessionFollowUps, readInterruptedDialogueSessionId, writeInterruptedDialogueSessionId,
  appendDeferredInteractiveCallback, readDeferredInteractiveCallbacks, clearDeferredInteractiveCallbacks,
  hasPendingOperation: id => studyOperationStore.readPendingStudyOperation()?.sessionId === id,
  now: Date.now, setTimeout: (callback, delay) => window.setTimeout(callback, delay), clearTimeout: id => window.clearTimeout(id),
};

export function useStudyContinuation(options: ContinuationOptions, port: StudyContinuationPort = defaultPort) {
  const latest = useRef(options); latest.current = options;
  const mounted = useRef(false);
  const paused = useRef("");
  const [pausedSession, setPausedSession] = useState("");
  const [pendingCount, setPendingCount] = useState(0);
  const preludes = useRef(new Set<string>());
  const failedPreludes = useRef(new Set<string>());
  const followUps = useRef(new Set<string>());
  const timers = useRef(new Map<string, number>());
  const interrupting = useRef(false);
  const begin = () => setPendingCount(count => count + 1);
  const finish = () => { if (mounted.current) setPendingCount(count => count - 1); };
  const current = (session: StudySessionRecord, revision = latest.current.view.viewRevision) =>
    mounted.current && latest.current.view.session?.id === session.id && latest.current.view.session.studyUnitId === session.studyUnitId && latest.current.view.viewRevision === revision;
  function pause(sessionId: string) {
    paused.current = sessionId.trim(); setPausedSession(paused.current);
    port.writeInterruptedDialogueSessionId(paused.current);
  }
  const isDialogueInterruptedForSession = (id: string) => Boolean(id.trim() && paused.current === id.trim());
  const peekDeferredInteractiveCallbackPrefix = (id: string) => port.readDeferredInteractiveCallbacks(id.trim()).join("\n\n");
  function clearInterruptedDialogueState(id: string, consumedPrefix: string) {
    if (!id.trim()) return;
    const callbacks = port.readDeferredInteractiveCallbacks(id.trim());
    const consumed = consumedPrefix
      ? callbacks.findIndex((_, index) => callbacks.slice(0, index + 1).join("\n\n") === consumedPrefix) + 1
      : 0;
    if (consumed > 0) {
      port.clearDeferredInteractiveCallbacks(id.trim());
      callbacks.slice(consumed).forEach(message => port.appendDeferredInteractiveCallback(id.trim(), message));
    }
    if (callbacks.length === consumed && isDialogueInterruptedForSession(id) && mounted.current) pause("");
  }
  useEffect(() => {
    mounted.current = true;
    paused.current = port.readInterruptedDialogueSessionId(); setPausedSession(paused.current);
    return () => { mounted.current = false; timers.current.forEach(id => port.clearTimeout(id)); timers.current.clear(); };
  }, [port]);

  async function runPrelude(session: StudySessionRecord, input: { studyUnitId: string; sectionTitle: string; themeHint: string; force?: boolean }) {
    if (!current(session) || !input.studyUnitId.trim() || port.hasPendingOperation(session.id)) return false;
    const key = `${session.id}:${input.studyUnitId}`;
    if (preludes.current.has(key)) return false;
    if (input.force) failedPreludes.current.delete(key);
    else if (session.preparedStudyUnitIds?.includes(input.studyUnitId) || failedPreludes.current.has(key)) return false;
    preludes.current.add(key); begin();
    const revision = latest.current.view.viewRevision;
    try {
      const operationKey = `prelude:${key}:${session.revision}`;
      const receipt = await latest.current.sendHiddenSessionMessage({ session, operationKey, ...latest.current.automaticStudyRequest(operationKey, "prelude"),
        message: buildSessionPreludeMessage(input), messageKind: "session_prelude" });
      return receipt !== null;
    } catch (error) {
      failedPreludes.current.add(key);
      if (current(session, revision)) latest.current.onNotice(resolveStudySessionErrorNotice(error, `章节准备失败：${String(error)}`, "response"));
      logWorkspaceError("workflow:study_session:prelude_error", error); return false;
    } finally { preludes.current.delete(key); finish(); }
  }
  async function triggerSessionPrelude(input: { studyUnitId: string; sectionTitle?: string; themeHint?: string }) {
    if (!mounted.current) return false;
    const session = await latest.current.ensureSessionForSection(input.studyUnitId, { clearResponseOnSwitch: false });
    return session ? runPrelude(session, { ...input, sectionTitle: input.sectionTitle || session.studyUnitTitle || session.studyUnitId, themeHint: input.themeHint ?? session.themeHint ?? "", force: true }) : false;
  }
  async function triggerInteractiveQuestionCallback(session: StudySessionRecord, input: { turnId: string; diagnosticFlowId?: string | null }) {
    if (!current(session)) return;
    const question = session.turns.find(turn => turn.id === input.turnId)?.interactiveQuestion;
    if (!question?.callBack) return;
    const result = question.result;
    if (!result?.submittedAnswer || typeof result.isCorrect !== "boolean" || !result.feedbackText.trim()) {
      logWorkspaceError("workflow:study_attempt:callback_read_back_missing", new Error("study_question_attempt_callback_read_back_missing")); return;
    }
    const message = buildInteractiveCallbackMessage({ questionType: question.questionType, prompt: question.prompt, topic: question.topic,
      submittedAnswer: result.submittedAnswer, isCorrect: result.isCorrect, explanation: result.explanation });
    if (isDialogueInterruptedForSession(session.id) || port.hasPendingOperation(session.id)) {
      port.appendDeferredInteractiveCallback(session.id, message);
      if (!isDialogueInterruptedForSession(session.id)) pause(session.id);
      latest.current.onNotice("答案已记录；已暂停自动续接，会在你下次主动发言前补入答题结果。"); return;
    }
    begin(); const revision = latest.current.view.viewRevision;
    try {
      const operationKey = `callback:${session.id}:${input.turnId}:${session.revision}`;
      await latest.current.sendHiddenSessionMessage({ session, operationKey, ...latest.current.automaticStudyRequest(operationKey, "callback"), message, messageKind: "interactive_callback", diagnosticFlowId: input.diagnosticFlowId });
    } catch (error) {
      if (current(session, revision)) latest.current.onNotice(resolveStudySessionErrorNotice(error, `答案已记录，续问失败：${String(error)}`, "response"));
      logWorkspaceError("workflow:study_attempt:callback_error", error);
    } finally { finish(); }
  }
  async function interruptDialogue() {
    const session = latest.current.view.session;
    if (!mounted.current || interrupting.current) return false;
    if (!session) { latest.current.onNotice("当前还没有可打断的学习单元会话。"); return false; }
    const pending = (session.pendingFollowUps ?? []).filter(item => item.status === "pending");
    if (!pending.length) {
      if (isDialogueInterruptedForSession(session.id)) { latest.current.onNotice("当前已暂停自动续接；答题结果会等你下次主动发言时再补入。"); return false; }
      pause(session.id); latest.current.onNotice("已暂停当前自动续接；之后提交答案不会立即续聊。"); return true;
    }
    pending.forEach(item => { const key = `${session.id}:${item.id}`; const timer = timers.current.get(key); if (timer !== undefined) port.clearTimeout(timer); timers.current.delete(key); });
    interrupting.current = true; begin(); const revision = latest.current.view.viewRevision;
    try {
      const next = await port.cancelStudySessionFollowUps({ sessionId: session.id });
      if (!current(session, revision)) return false;
      if (latest.current.view.session!.revision <= next.revision) latest.current.onSession(next);
      pause(next.id); latest.current.onNotice("已打断当前自动续接；之后提交答案不会立即续聊。"); return true;
    } catch (error) {
      if (current(session, revision)) latest.current.onNotice(resolveStudySessionErrorNotice(error, `打断自动续接失败：${String(error)}`, "update"));
      logWorkspaceError("workflow:study_follow_up:interrupt_error", error); return false;
    } finally { interrupting.current = false; finish(); }
  }

  useEffect(() => {
    const session = options.session;
    if (!session || options.busy || pendingCount > 0) return;
    void runPrelude(session, { studyUnitId: session.studyUnitId, sectionTitle: session.studyUnitTitle ?? session.studyUnitId, themeHint: session.themeHint ?? "" });
  }, [options.session, options.busy, pendingCount]);

  useEffect(() => {
    const session = options.session;
    const pending = (session?.pendingFollowUps ?? []).filter(item => item.status === "pending");
    const keys = new Set(pending.map(item => `${session!.id}:${item.id}`));
    timers.current.forEach((timer, key) => { if (!keys.has(key)) { port.clearTimeout(timer); timers.current.delete(key); } });
    if (!session || isDialogueInterruptedForSession(session.id)) return;
    pending.forEach(item => {
      const key = `${session.id}:${item.id}`;
      if (timers.current.has(key) || followUps.current.has(key)) return;
      const due = Date.parse(item.dueAt || "");
      const timer = port.setTimeout(() => {
        timers.current.delete(key);
        const live = latest.current.view.session;
        if (!live || !current(session) || isDialogueInterruptedForSession(live.id) || port.hasPendingOperation(live.id) || followUps.current.has(key)) return;
        const followUp = live.pendingFollowUps?.find(candidate => candidate.id === item.id && candidate.status === "pending");
        if (!followUp) return;
        followUps.current.add(key); begin(); const revision = latest.current.view.viewRevision;
        void (async () => {
          try {
            const operationKey = `follow-up:${live.id}:${item.id}`;
            await latest.current.sendHiddenSessionMessage({ session: live, operationKey, ...latest.current.automaticStudyRequest(operationKey, "follow-up"),
              message: followUp.hiddenMessage, messageKind: "scheduled_follow_up", followUpId: item.id });
          } catch (error) {
            if (current(live, revision) && !String(error).includes("follow_up_not_pending")) latest.current.onNotice(resolveStudySessionErrorNotice(error, `自动续接失败：${String(error)}`, "response"));
            logWorkspaceError("workflow:study_follow_up:error", error);
          } finally { followUps.current.delete(key); finish(); }
        })();
      }, Number.isFinite(due) ? Math.max(0, due - port.now()) : 0);
      timers.current.set(key, timer);
    });
    // A failed timer waits for authoritative Session refresh; busy transitions do not poll it repeatedly.
  }, [options.session, pausedSession]);

  return { triggerSessionPrelude, triggerInteractiveQuestionCallback, interruptDialogue,
    isDialogueInterruptedForSession, peekDeferredInteractiveCallbackPrefix, clearInterruptedDialogueState,
    isDialogueInterrupted: Boolean(options.session?.id && options.session.id === pausedSession), isContinuing: pendingCount > 0 };
}
