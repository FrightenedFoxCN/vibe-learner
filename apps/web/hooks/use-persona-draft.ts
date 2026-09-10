"use client";

import { useEffect, useMemo, useRef, useState, type SetStateAction } from "react";
import type { PersonaProfile } from "@vibe-learner/shared";
import type { AsyncResultScope } from "../lib/async-result-fence";
import { EMPTY_PERSONA_DRAFT, personaDraftFingerprint, personaToDraft, type PersonaDraft } from "../lib/persona-draft";

const confirmDiscard = (message: string) => window.confirm(message);

export function usePersonaDraft({ personas, onSelectionChange, onPromptDismiss }: {
  personas: PersonaProfile[];
  onSelectionChange: () => void;
  onPromptDismiss: () => void;
}, confirm = confirmDiscard) {
  const [selectedPersonaId, setSelectedPersonaId] = useState("");
  const selectedPersonaIdRef = useRef("");
  const draftRevisionRef = useRef(0);
  const [draft, setDraft] = useState<PersonaDraft>(EMPTY_PERSONA_DRAFT);
  const [draftBaselineFingerprint, setDraftBaselineFingerprint] = useState(
    personaDraftFingerprint(EMPTY_PERSONA_DRAFT),
  );
  const isDraftDirty = useMemo(
    () => personaDraftFingerprint(draft) !== draftBaselineFingerprint,
    [draft, draftBaselineFingerprint],
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
    setDraft(next);
  }

  function replacePersonaDraft(next: PersonaDraft, markClean: boolean): void {
    updatePersonaDraft(next);
    if (markClean) {
      setDraftBaselineFingerprint(personaDraftFingerprint(next));
    }
  }

  function selectPersonaDraft(personaId: string): void {
    const normalizedPersonaId = personaId.trim();
    if (selectedPersonaIdRef.current !== normalizedPersonaId) {
      draftRevisionRef.current += 1;
      onSelectionChange();
    }
    selectedPersonaIdRef.current = normalizedPersonaId;
    setSelectedPersonaId(normalizedPersonaId);
  }

  function confirmDiscardPersonaDraft(action: string): boolean {
    if (!isDraftDirty) {
      return true;
    }
    return confirm(`当前人格有未保存修改。${action}会丢弃这些修改，是否继续？`);
  }

  function activatePersonaDraft(personaId: string, action = "切换人格"): boolean {
    const normalizedPersonaId = personaId.trim();
    if (normalizedPersonaId === selectedPersonaIdRef.current) {
      return true;
    }
    if (!confirmDiscardPersonaDraft(action)) {
      return false;
    }
    const nextPersona = personas.find((persona) => persona.id === normalizedPersonaId) ?? null;
    const nextDraft = nextPersona ? personaToDraft(nextPersona) : { ...EMPTY_PERSONA_DRAFT };
    selectPersonaDraft(normalizedPersonaId);
    replacePersonaDraft(nextDraft, true);
    onPromptDismiss();
    return true;
  }

  function updatePersonaAssistInput(update: () => void): void {
    draftRevisionRef.current += 1;
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
    const guardLinkNavigation = (event: MouseEvent) => {
      if (
        event.defaultPrevented ||
        event.button !== 0 ||
        event.metaKey ||
        event.ctrlKey ||
        event.shiftKey ||
        event.altKey
      ) {
        return;
      }
      const target = event.target;
      const anchor = target instanceof Element ? target.closest("a[href]") : null;
      if (!(anchor instanceof HTMLAnchorElement) || anchor.hasAttribute("download")) {
        return;
      }
      const destination = new URL(anchor.href, window.location.href);
      if (destination.href === window.location.href) {
        return;
      }
      if (!confirm("当前人格有未保存修改。离开页面会丢弃这些修改，是否继续？")) {
        event.preventDefault();
      }
    };
    window.addEventListener("beforeunload", warnBeforeUnload);
    document.addEventListener("click", guardLinkNavigation, true);
    return () => {
      window.removeEventListener("beforeunload", warnBeforeUnload);
      document.removeEventListener("click", guardLinkNavigation, true);
    };
  }, [isDraftDirty]);

  function getSelectedPersonaId() { return selectedPersonaIdRef.current; }
  function markPersonaDraftSaved(saved: PersonaDraft) {
    setDraftBaselineFingerprint(personaDraftFingerprint(saved));
  }
  function initializePersonaFromLibrary(persona: PersonaProfile | undefined) {
    // Initial data may arrive after the user started a new draft or imported one.
    if (!persona || selectedPersonaIdRef.current || draftRevisionRef.current !== 0) return;
    selectPersonaDraft(persona.id);
    replacePersonaDraft(personaToDraft(persona), true);
  }
  return {
    selectedPersonaId,
    draft,
    isDraftDirty,
    currentPersonaSubject,
    currentPersonaAsyncScope,
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
