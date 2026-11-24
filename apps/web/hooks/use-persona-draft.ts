"use client";

import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type SetStateAction,
} from "react";
import type { ConfirmFn } from "../components/ui/confirm-provider";
import { useDraftNavigationGuard } from "../lib/app-navigation";
import type { PersonaProfile } from "@vibe-learner/shared";
import { diagnosticContext } from "../lib/diagnostics";
import type { AsyncResultScope } from "../lib/async-result-fence";
import { findLoadablePersona } from "../lib/persona-delete-draft";
import {
  EMPTY_PERSONA_DRAFT,
  personaDraftFingerprint,
  personaToDraft,
  type PersonaDraft,
} from "../lib/persona-draft";

type PersonaNavigationDraft = {
  id: string;
  baseRevision: number | null;
  draft: PersonaDraft;
  baseline: string;
};
// Same-document history traversal cannot reliably be cancelled. Keep one draft
// in the browser document, never in a cross-tab store or the server.
let navigationDraft: PersonaNavigationDraft | null = null;

export function usePersonaDraft(
  {
    getPersonasSnapshot,
    isPersonaDeleting,
    onSelectionChange,
    onPromptDismiss,
  }: {
    getPersonasSnapshot: () => PersonaProfile[];
    isPersonaDeleting: (id: string) => boolean;
    onSelectionChange: () => void;
    onPromptDismiss: () => void;
  },
  confirm: ConfirmFn,
) {
  const [selectedPersonaId, setSelectedPersonaId] = useState("");
  const selectedPersonaIdRef = useRef("");
  const baseRevisionRef = useRef<number | null>(null);
  const [restoredNavigationDraft, setRestoredNavigationDraft] = useState(false);
  const draftRevisionRef = useRef(0);
  const draftEpochRef = useRef(0);
  const ownerRef = useRef<object | null>(null);
  useEffect(() => {
    ownerRef.current = {};
    return () => {
      ownerRef.current = null;
    };
  }, []);
  const captureDraftIntent = useCallback(() => {
    const owner = ownerRef.current;
    const revision = draftRevisionRef.current;
    return () =>
      owner !== null &&
      ownerRef.current === owner &&
      draftRevisionRef.current === revision;
  }, []);
  const readNavigationWarning = useCallback(
    () => ({
      message: "当前人格有未保存修改。站内离开后仍可返回继续编辑；关闭或刷新会丢失。",
      isCurrent: captureDraftIntent(),
    }),
    [captureDraftIntent],
  );
  const diagnosticFlow = useRef<string | null>(null);
  function beginDiagnosticAction() {
    diagnosticFlow.current ??= crypto.randomUUID();
    return diagnosticContext(diagnosticFlow.current);
  }
  const [draft, setDraft] = useState<PersonaDraft>(EMPTY_PERSONA_DRAFT);
  const [draftBaselineFingerprint, setDraftBaselineFingerprint] = useState(
    personaDraftFingerprint(EMPTY_PERSONA_DRAFT),
  );
  const isDraftDirty = useMemo(
    () => personaDraftFingerprint(draft) !== draftBaselineFingerprint,
    [draft, draftBaselineFingerprint],
  );

  useLayoutEffect(() => {
    if (!navigationDraft) return;
    const saved = navigationDraft;
    navigationDraft = null;
    selectedPersonaIdRef.current = saved.id;
    baseRevisionRef.current = saved.baseRevision;
    draftRevisionRef.current++;
    setSelectedPersonaId(saved.id);
    setDraft(saved.draft);
    setDraftBaselineFingerprint(saved.baseline);
    setRestoredNavigationDraft(true);
  }, []);
  const navigationSnapshot = useRef<PersonaNavigationDraft | null>(null);
  useLayoutEffect(() => {
    navigationSnapshot.current = isDraftDirty
      ? {
          id: selectedPersonaId,
          baseRevision: baseRevisionRef.current,
          draft,
          baseline: draftBaselineFingerprint,
        }
      : null;
  });
  useLayoutEffect(
    () => () => {
      navigationDraft = navigationSnapshot.current;
    },
    [],
  );

  function currentPersonaSubject(): string {
    return selectedPersonaIdRef.current || "persona-draft:new";
  }

  function currentPersonaAsyncScope(fieldTarget: string): AsyncResultScope {
    return {
      subjectId: currentPersonaSubject(),
      draftRevision: draftRevisionRef.current,
      fieldTarget,
    };
  }

  function updatePersonaDraft(next: SetStateAction<PersonaDraft>): void {
    draftRevisionRef.current += 1;
    onPromptDismiss();
    setDraft(next);
  }

  function replacePersonaDraft(next: PersonaDraft, markClean: boolean): void {
    draftEpochRef.current++;
    setRestoredNavigationDraft(false);
    updatePersonaDraft(next);
    if (markClean) {
      setDraftBaselineFingerprint(personaDraftFingerprint(next));
    }
  }

  function selectPersonaDraft(
    personaId: string,
    baseRevision: number | null = null,
  ): void {
    const normalizedPersonaId = personaId.trim();
    if (selectedPersonaIdRef.current !== normalizedPersonaId) {
      draftEpochRef.current++;
      draftRevisionRef.current += 1;
      onSelectionChange();
    }
    selectedPersonaIdRef.current = normalizedPersonaId;
    baseRevisionRef.current = baseRevision;
    setSelectedPersonaId(normalizedPersonaId);
  }

  useDraftNavigationGuard(isDraftDirty ? readNavigationWarning : null, confirm);

  async function confirmDiscardPersonaDraft(
    action: string,
    trigger?: HTMLElement,
  ): Promise<boolean> {
    const isCurrent = captureDraftIntent();
    if (!isDraftDirty) return isCurrent();
    const approved = await confirm({
      title: "丢弃未保存修改？",
      message: `${action}会丢弃当前人格的未保存修改。`,
      confirmLabel: "丢弃修改",
      danger: true,
      trigger,
    });
    return approved && isCurrent();
  }

  async function activatePersonaDraft(
    personaId: string,
    action = "切换人格",
    trigger?: HTMLElement,
  ): Promise<boolean> {
    const normalizedPersonaId = personaId.trim();
    if (isPersonaDeleting(normalizedPersonaId)) return false;
    if (normalizedPersonaId === selectedPersonaIdRef.current) {
      return true;
    }
    const target = findLoadablePersona(
      normalizedPersonaId,
      getPersonasSnapshot(),
      isPersonaDeleting,
    );
    if (normalizedPersonaId && !target) return false;
    const isCurrent = captureDraftIntent();
    if (
      !(await confirmDiscardPersonaDraft(action, trigger)) ||
      !isCurrent() ||
      isPersonaDeleting(normalizedPersonaId)
    )
      return false;
    const nextPersona = findLoadablePersona(
      normalizedPersonaId,
      getPersonasSnapshot(),
      isPersonaDeleting,
    );
    if (
      normalizedPersonaId &&
      (!target || !nextPersona || target.revision !== nextPersona.revision)
    )
      return false;
    diagnosticFlow.current = null;
    const nextDraft = nextPersona
      ? personaToDraft(nextPersona)
      : { ...EMPTY_PERSONA_DRAFT };
    selectPersonaDraft(normalizedPersonaId, nextPersona?.revision ?? null);
    replacePersonaDraft(nextDraft, true);
    onPromptDismiss();
    return true;
  }

  function updatePersonaAssistInput(update: () => void): void {
    draftRevisionRef.current += 1;
    onPromptDismiss();
    update();
  }

  useEffect(() => {
    selectedPersonaIdRef.current = selectedPersonaId;
  }, [selectedPersonaId]);

  useEffect(() => {
    if (!isDraftDirty) {
      return;
    }
    const warnBeforeUnload = (event: BeforeUnloadEvent) => {
      event.preventDefault();
    };
    window.addEventListener("beforeunload", warnBeforeUnload);
    return () => window.removeEventListener("beforeunload", warnBeforeUnload);
  }, [isDraftDirty]);

  function getSelectedPersonaId() {
    return selectedPersonaIdRef.current;
  }
  function markPersonaDraftSaved(saved: PersonaDraft) {
    setDraftBaselineFingerprint(personaDraftFingerprint(saved));
  }
  function initializePersonaFromLibrary(persona: PersonaProfile | undefined) {
    // Initial data may arrive after the user started a new draft or imported one.
    if (!persona || selectedPersonaIdRef.current || draftRevisionRef.current !== 0)
      return;
    selectPersonaDraft(persona.id, persona.revision);
    replacePersonaDraft(personaToDraft(persona), true);
  }
  return {
    beginDiagnosticAction,
    resetDiagnosticFlow: () => {
      diagnosticFlow.current = null;
    },
    getDraftEpoch: () => draftEpochRef.current,
    getBasePersonaRevision: () => baseRevisionRef.current,
    restoredNavigationDraft,
    selectedPersonaId,
    draft,
    isDraftDirty,
    currentPersonaSubject,
    currentPersonaAsyncScope,
    captureDraftIntent,
    updatePersonaDraft,
    replacePersonaDraft,
    selectPersonaDraft,
    confirmDiscardPersonaDraft,
    activatePersonaDraft,
    updatePersonaAssistInput,
    markPersonaDraftSaved,
    initializePersonaFromLibrary,
    getSelectedPersonaId,
  };
}

export type PersonaDraftController = ReturnType<typeof usePersonaDraft>;
