"use client";

import { useEffect, useRef, useState } from "react";
import type { ConfirmFn } from "../components/ui/confirm-provider";
import type { PersonaProfile } from "@vibe-learner/shared";
import type { PersonaDraftController } from "./use-persona-draft";
import type { PersonaLibraryController } from "./use-persona-library";
import {
  draftToCreatePersonaInput,
  EMPTY_PERSONA_DRAFT,
  personaToDraft,
} from "../lib/persona-draft";
import {
  humanizePersonaDeleteError,
  humanizePersonaSaveError,
} from "../lib/persona-persistence-errors";

export function usePersonaPersistence(
  {
    editor,
    library,
    onStarted,
    onPromptDismiss,
  }: {
    editor: PersonaDraftController;
    library: PersonaLibraryController;
    onStarted: () => void;
    onPromptDismiss: () => void;
  },
  confirmDelete: ConfirmFn,
) {
  const [savingPersona, setSavingPersona] = useState(false);
  const [saveError, setSaveError] = useState("");
  const [loadError, setLoadError] = useState("");
  const [personaDeletePendingId, setPersonaDeletePendingId] = useState("");
  const [personaLibraryMessage, setPersonaLibraryMessage] = useState("");
  const [personaLibraryError, setPersonaLibraryError] = useState("");
  const active = useRef(true);
  const saveRunning = useRef(false);
  const deleteRunning = useRef(false);
  const feedback = useRef({ sequence: 0 });
  useEffect(() => {
    const feedbackState = feedback.current;
    active.current = true;
    return () => {
      active.current = false;
      feedbackState.sequence++;
    };
  }, []);
  const ownsFeedback = (request: number) =>
    active.current && feedback.current.sequence === request;

  async function save(mode: "create" | "update") {
    if (!active.current || saveRunning.current) return;
    onStarted();
    setSaveError("");
    const payload = draftToCreatePersonaInput(editor.draft);
    const target = library.personas.find(
      (persona) => persona.id === editor.getSelectedPersonaId(),
    );
    if (mode === "update") {
      if (!editor.getSelectedPersonaId()) {
        setSaveError("请先选择要更新的人格。");
        return;
      }
      if (!target) {
        setSaveError("当前人格不存在，请刷新人格库后重试。");
        return;
      }
      if (target.source === "builtin") {
        setSaveError("内置人格为只读，无法更新。请使用「创建新人格」另存。");
        return;
      }
    }
    if (!payload.name) {
      setSaveError("请先填写人格名称。");
      return;
    }
    const epoch = editor.getDraftEpoch();
    const scope = editor.currentPersonaAsyncScope("persona-save");
    const request = ++feedback.current.sequence;
    const diagnostic = editor.beginDiagnosticAction();
    saveRunning.current = true;
    setSavingPersona(true);
    try {
      const committed =
        mode === "create"
          ? await library.createPersona(payload, diagnostic)
          : await library.updatePersona(
              target!.id,
              { ...payload, expectedRevision: target!.revision },
              diagnostic,
            );
      if (!active.current) return;
      if (editor.getDraftEpoch() === epoch) {
        const current = editor.currentPersonaAsyncScope("persona-save");
        if (
          current.subjectId === scope.subjectId &&
          current.draftRevision === scope.draftRevision
        ) {
          if (mode === "create") editor.selectPersonaDraft(committed.id);
          editor.replacePersonaDraft(personaToDraft(committed), true);
          onPromptDismiss();
        } else if (
          (mode === "create" && !editor.getSelectedPersonaId()) ||
          editor.getSelectedPersonaId() === committed.id
        ) {
          // Only continuing edits to the same draft inherit the committed base.
          if (mode === "create") editor.selectPersonaDraft(committed.id);
          editor.markPersonaDraftSaved(personaToDraft(committed));
        }
      }
      const message = `已${mode === "create" ? "创建" : "更新"}人格「${committed.name}」。`;
      if (ownsFeedback(request)) {
        setPersonaLibraryMessage(message);
        setPersonaLibraryError("");
      }
      try {
        await library.listPersonas(diagnostic);
      } catch (error) {
        if (ownsFeedback(request))
          setPersonaLibraryMessage(`${message}但人格库刷新失败：${String(error)}`);
      }
    } catch (error) {
      if (ownsFeedback(request) && editor.getDraftEpoch() === epoch)
        setSaveError(humanizePersonaSaveError(error));
    } finally {
      saveRunning.current = false;
      if (active.current) setSavingPersona(false);
    }
  }

  async function handleReloadSelectedPersona(trigger?: HTMLElement) {
    const id = editor.getSelectedPersonaId();
    if (!active.current || !id) return;
    const epoch = editor.getDraftEpoch();
    const scope = editor.currentPersonaAsyncScope("persona-reload");
    const isCurrent = editor.captureDraftIntent();
    const previousFeedback = feedback.current.sequence;
    if (
      !(await editor.confirmDiscardPersonaDraft("重新载入人格", trigger)) ||
      !isCurrent() ||
      feedback.current.sequence !== previousFeedback
    )
      return;
    const request = ++feedback.current.sequence;
    setLoadError("");
    const diagnostic = editor.beginDiagnosticAction();
    try {
      const latest = await library.listPersonas(diagnostic);
      if (!ownsFeedback(request)) return;
      const current = editor.currentPersonaAsyncScope("persona-reload");
      if (
        editor.getDraftEpoch() !== epoch ||
        current.draftRevision !== scope.draftRevision ||
        current.subjectId !== scope.subjectId
      ) {
        setPersonaLibraryMessage("人格库已刷新，期间的编辑已保留。");
        return;
      }
      const reloaded = latest.find((persona) => persona.id === id);
      if (!reloaded) {
        setLoadError("当前人格已不存在，请选择其他人格。");
        return;
      }
      editor.replacePersonaDraft(personaToDraft(reloaded), true);
      onPromptDismiss();
      setPersonaLibraryMessage(`已重新载入人格「${reloaded.name}」。`);
    } catch (error) {
      if (ownsFeedback(request) && editor.getDraftEpoch() === epoch)
        setLoadError(String(error));
    }
  }

  async function handleDeletePersona(persona: PersonaProfile, trigger?: HTMLElement) {
    if (!active.current || deleteRunning.current) return;
    if (persona.source === "builtin") {
      setPersonaLibraryError("内置人格不能删除。");
      return;
    }
    const warning =
      editor.getSelectedPersonaId() === persona.id && editor.isDraftDirty
        ? " 当前草稿的未保存修改也会丢失。"
        : "";
    const epoch = editor.getDraftEpoch();
    const scope = editor.currentPersonaAsyncScope("persona-delete");
    const isCurrent = editor.captureDraftIntent();
    deleteRunning.current = true;
    const invoker =
      trigger ??
      (document.activeElement instanceof HTMLElement
        ? document.activeElement
        : undefined);
    try {
      const approved = await confirmDelete({
        title: "删除人格？",
        message: `即将删除人格「${persona.name}」。${warning}`,
        confirmLabel: "删除",
        danger: true,
        trigger: invoker,
        fallbackFocus: () => document.getElementById("persona-draft-name"),
      });
      if (!approved || !active.current || !isCurrent()) return;
      const target = library
        .getPersonasSnapshot()
        .find((item) => item.id === persona.id);
      if (
        !target ||
        target.revision !== persona.revision ||
        target.source === "builtin"
      )
        return;
      await deleteConfirmedPersona(persona, epoch, scope, invoker);
    } finally {
      deleteRunning.current = false;
    }
  }

  async function deleteConfirmedPersona(
    persona: PersonaProfile,
    epoch: number,
    scope: ReturnType<PersonaDraftController["currentPersonaAsyncScope"]>,
    trigger?: HTMLElement,
  ) {
    const request = ++feedback.current.sequence;
    setPersonaDeletePendingId(persona.id);
    setPersonaLibraryError("");
    setPersonaLibraryMessage("");
    try {
      await library.deletePersona(persona.id, persona.revision);
      let latest = library.getPersonasSnapshot();
      let refreshError = "";
      try {
        latest = await library.listPersonas();
      } catch (error) {
        refreshError = String(error);
      }
      if (!active.current) return;
      let retained = false;
      if (
        editor.getDraftEpoch() === epoch &&
        editor.getSelectedPersonaId() === persona.id
      ) {
        if (
          editor.currentPersonaAsyncScope("persona-delete").draftRevision !==
          scope.draftRevision
        ) {
          editor.selectPersonaDraft("");
          editor.markPersonaDraftSaved(EMPTY_PERSONA_DRAFT);
          retained = true;
        } else {
          const next = latest[0];
          editor.selectPersonaDraft(next?.id ?? "");
          editor.replacePersonaDraft(
            next ? personaToDraft(next) : { ...EMPTY_PERSONA_DRAFT },
            true,
          );
          onPromptDismiss();
        }
      }
      if (trigger && document.activeElement === document.body)
        document.getElementById("persona-draft-name")?.focus();
      if (ownsFeedback(request))
        setPersonaLibraryMessage(
          `已删除人格「${persona.name}」。${retained ? "期间的编辑已保留为新草稿。" : ""}${refreshError ? `人格库刷新失败：${refreshError}` : ""}`,
        );
    } catch (error) {
      if (ownsFeedback(request))
        setPersonaLibraryError(humanizePersonaDeleteError(error));
    } finally {
      if (active.current) setPersonaDeletePendingId("");
    }
  }

  return {
    savingPersona,
    saveError,
    setSaveError,
    loadError,
    setLoadError,
    personaDeletePendingId,
    personaLibraryMessage,
    setPersonaLibraryMessage,
    personaLibraryError,
    setPersonaLibraryError,
    handleCreatePersona: () => save("create"),
    handleUpdatePersona: () => save("update"),
    handleReloadSelectedPersona,
    handleDeletePersona,
  };
}
