"use client";

import { useEffect, useRef, useState } from "react";
import type { DocumentRecord, LearningPlan, SceneProfile, StudySessionRecord } from "@vibe-learner/shared";
import { createStudySession, listStudySessions, updateStudySessionStudyUnit } from "../lib/data/study-sessions";
import { StudyAsyncViewFence } from "../lib/async-result-fence";
import { buildInitialStudySessionInput } from "../lib/learning-workspace-state";
import { resolveStudySessionErrorNotice } from "../lib/study-session-decode";
import { logWorkspaceError } from "../lib/learning-workspace-telemetry";
import { SESSION_CREATED_NOTICE } from "../lib/learning-workspace-copy";

interface NavigationOptions {
  plan: LearningPlan | null;
  document: DocumentRecord | null;
  view: StudyAsyncViewFence<StudySessionRecord>;
  getSelectedPlanId: () => string;
  resolveSceneProfile: () => SceneProfile | undefined;
  resolveStudyUnitTitle: (id: string) => string;
  resolveThemeHint: (id: string) => string;
  onTransition: (target: string, clearSession: boolean) => void;
  onSession: (session: StudySessionRecord | null, clearResponse: boolean) => void;
  onNotice: (notice: string) => void;
}
export interface StudySessionNavigationPort {
  createStudySession: typeof createStudySession;
  listStudySessions: typeof listStudySessions;
  updateStudySessionStudyUnit: typeof updateStudySessionStudyUnit;
}
const defaultPort: StudySessionNavigationPort = { createStudySession, listStudySessions, updateStudySessionStudyUnit };

export function useStudySessionNavigation(options: NavigationOptions, port: StudySessionNavigationPort = defaultPort) {
  const latest = useRef(options);
  latest.current = options;
  const mounted = useRef(false);
  const [pendingCount, setPendingCount] = useState(0);
  const queue = useRef(Promise.resolve());
  const switches = useRef(new Map<string, { promise: Promise<void>; owner: object }>());
  const latestSwitch = useRef<object | null>(null);
  const creating = useRef(false);
  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; latestSwitch.current = null; };
  }, []);
  const begin = () => setPendingCount(count => count + 1);
  const finish = () => { if (mounted.current) setPendingCount(count => count - 1); };
  function current(planId: string, revision: number) {
    return mounted.current && latest.current.getSelectedPlanId() === planId && latest.current.view.viewRevision === revision;
  }
  async function fetchLatest(captured: NavigationOptions) {
    if (!captured.plan) return null;
    const sessions = await port.listStudySessions({ documentId: captured.document?.id, personaId: captured.plan.personaId, planId: captured.plan.id });
    return [...sessions].sort((a, b) => (Date.parse(b.updatedAt || "") || 0) - (Date.parse(a.updatedAt || "") || 0))[0] ?? null;
  }
  useEffect(() => {
    const captured = latest.current;
    if (!captured.plan) return;
    let active = true;
    const planId = captured.plan.id;
    const revision = captured.view.viewRevision;
    void fetchLatest(captured).then(session => {
      if (!active || !current(planId, revision)) return;
      const visible = latest.current.view.session;
      if (visible && (!session || visible.id === session.id && visible.revision > session.revision)) return;
      latest.current.onSession(session, true);
    }).catch(error => {
      if (!active || !current(planId, revision)) return;
      const notice = resolveStudySessionErrorNotice(error, "", "history");
      if (notice) latest.current.onNotice(notice);
      logWorkspaceError("workflow:study_session:hydrate_error", error);
    });
    return () => { active = false; };
  }, [options.document?.id, options.plan?.id, options.plan?.personaId]);

  async function createSessionForActivePlan() {
    const captured = latest.current;
    if (!mounted.current || !captured.plan || creating.current) return;
    creating.current = true;
    const plan = captured.plan;
    const sceneProfile = captured.resolveSceneProfile();
    captured.onTransition(`study-plan:${plan.id}:session-create`, true);
    const revision = captured.view.viewRevision;
    begin();
    try {
      const session = await port.createStudySession({
        ...buildInitialStudySessionInput({ plan, document: captured.document, planId: plan.id, personaId: plan.personaId }), sceneProfile,
      });
      if (!current(plan.id, revision)) return;
      latest.current.onSession(session, true);
      latest.current.onNotice(SESSION_CREATED_NOTICE);
    } catch (error) {
      if (!current(plan.id, revision)) return;
      latest.current.onNotice(resolveStudySessionErrorNotice(error, `创建会话失败：${String(error)}`, "update"));
      logWorkspaceError("workflow:session_create:error", error);
    } finally { creating.current = false; finish(); }
  }

  async function ensureSessionForSection(studyUnitId: string, settings: {
    clearResponseOnSwitch?: boolean; isStillCurrent?: () => boolean;
  } = {}): Promise<StudySessionRecord | null> {
    const captured = latest.current;
    const plan = captured.plan;
    if (!mounted.current || !plan || !studyUnitId || settings.isStillCurrent?.() === false) return null;
    const sceneProfile = captured.resolveSceneProfile();
    let session = captured.view.session;
    if (session?.planId !== plan.id || session.studyUnitId !== studyUnitId) {
      captured.onTransition(`study-plan:${plan.id}:unit:${studyUnitId}`, false);
    }
    const revision = captured.view.viewRevision;
    const stillCurrent = () => current(plan.id, revision) && settings.isStillCurrent?.() !== false;
    if (!session || session.planId !== plan.id) session = await fetchLatest(captured);
    if (!stillCurrent()) return null;
    if (!session) {
      session = await port.createStudySession({ documentId: captured.document?.id ?? plan.documentId ?? "", personaId: plan.personaId, planId: plan.id,
        sceneProfile: sceneProfile ?? null, studyUnitId, studyUnitTitle: captured.resolveStudyUnitTitle(studyUnitId), themeHint: captured.resolveThemeHint(studyUnitId) });
    } else if (session.studyUnitId !== studyUnitId) {
      session = await port.updateStudySessionStudyUnit({ sessionId: session.id, studyUnitId });
    }
    if (!stillCurrent()) return null;
    latest.current.onSession(session, settings.clearResponseOnSwitch ?? true);
    return session;
  }

  function handleSwitchSection(studyUnitId: string): Promise<void> {
    const unitId = studyUnitId.trim();
    const planId = latest.current.plan?.id;
    if (!unitId || !planId || !mounted.current) return Promise.resolve();
    const key = `${planId}:${unitId}`;
    const existing = switches.current.get(key);
    if (existing) { latestSwitch.current = existing.owner; return existing.promise; }
    const owner = {};
    latestSwitch.current = owner;
    const isCurrent = () => mounted.current && latestSwitch.current === owner && latest.current.getSelectedPlanId() === planId;
    const run = async () => {
      if (!isCurrent()) return;
      begin();
      try {
        const beforeId = latest.current.view.session?.id;
        const session = await ensureSessionForSection(unitId, { clearResponseOnSwitch: true, isStillCurrent: isCurrent });
        if (session && isCurrent()) latest.current.onNotice(beforeId === session.id ? "已切换章节。" : "已切换章节，并打开对应会话。");
      } catch (error) {
        if (!isCurrent()) return;
        latest.current.onNotice(resolveStudySessionErrorNotice(error, `切换章节失败：${String(error)}`, "update"));
        logWorkspaceError("workflow:study_session:section_switch_error", error);
      } finally { finish(); }
    };
    const operation = queue.current.then(run, run).finally(() => {
      if (switches.current.get(key)?.promise === operation) switches.current.delete(key);
    });
    queue.current = operation;
    switches.current.set(key, { promise: operation, owner });
    return operation;
  }
  return { createSessionForActivePlan, ensureSessionForSection, handleSwitchSection, isNavigating: pendingCount > 0 };
}
