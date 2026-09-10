"use client";

import { useEffect, useRef, useState, type SetStateAction } from "react";
import type { ModelRecovery } from "@vibe-learner/shared";
import { assistPersonaSlot, assistPersonaSetting } from "../lib/data/personas";
import { AsyncResultFence, type AsyncResultScope, type AsyncResultTicket } from "../lib/async-result-fence";
import { mergePersonaAssistSlots, type PersonaDraft } from "../lib/persona-draft";

interface PersonaAssistPort {
  assistPersonaSlot: typeof assistPersonaSlot;
  assistPersonaSetting: typeof assistPersonaSetting;
}
const defaultPort = { assistPersonaSlot, assistPersonaSetting };
export function usePersonaAssist({ draft, updatePersonaDraft, currentPersonaAsyncScope, onSettingStarted }: {
  draft: PersonaDraft;
  updatePersonaDraft: (update: SetStateAction<PersonaDraft>) => void;
  currentPersonaAsyncScope: (fieldTarget: string) => AsyncResultScope;
  onSettingStarted: () => void;
}, port: PersonaAssistPort = defaultPort) {
  const [assistPending, setAssistPending] = useState(false);
  const [slotAssistIndex, setSlotAssistIndex] = useState<number | null>(null);
  const [assistError, setAssistError] = useState("");
  const [assistModelRecoveries, setAssistModelRecoveries] = useState<ModelRecovery[]>([]);
  const [retainRatio, setRetainRatio] = useState(0.7);
  const [systemPromptSuggestion, setSystemPromptSuggestion] = useState("");
  const [systemPromptSuggestionSource, setSystemPromptSuggestionSource] = useState("");
  const assistFenceRef = useRef(new AsyncResultFence());
  const mountedRef = useRef(true);
  const canApply = (ticket: AsyncResultTicket) => mountedRef.current && assistFenceRef.current.decide(ticket, currentPersonaAsyncScope(ticket.fieldTarget)) === "apply";
  useEffect(() => {
    mountedRef.current = true;
    return () => { mountedRef.current = false; assistFenceRef.current.invalidate(); };
  }, []);
  function clearAssistError() { setAssistError(""); }
  function resetPersonaAssist() {
    assistFenceRef.current.invalidate();
    setAssistPending(false); setSlotAssistIndex(null);
    setAssistError(""); setAssistModelRecoveries([]);
    dismissSystemPromptSuggestion();
  }
  function setPromptSuggestion(value: string, source: string) {
    const trimmed = value.trim();
    setSystemPromptSuggestion(trimmed);
    setSystemPromptSuggestionSource(trimmed ? source : "");
  }

  function applySystemPromptSuggestion() {
    if (!systemPromptSuggestion) {
      return;
    }
    setAssistError("");
    updatePersonaDraft(draft => ({ ...draft, systemPrompt: systemPromptSuggestion }));
    setSystemPromptSuggestion("");
    setSystemPromptSuggestionSource("");
  }

  function dismissSystemPromptSuggestion() {
    setSystemPromptSuggestion("");
    setSystemPromptSuggestionSource("");
  }

  async function handleAssistSlot(index: number) {
    if (!mountedRef.current) return;
    const targetSlot = draft.slots[index];
    if (!targetSlot) {
      return;
    }
    setAssistError("");
    setAssistModelRecoveries([]);
    setAssistPending(false);
    setSlotAssistIndex(index);
    const fieldTarget = `persona-slot:${index}`;
    const ticket = assistFenceRef.current.begin(currentPersonaAsyncScope(fieldTarget));
    try {
      const result = await port.assistPersonaSlot({
        name: draft.name.trim(),
        summary: draft.summary.trim(),
        slot: targetSlot,
        rewriteStrength: Number((1 - retainRatio).toFixed(2))
      });
      if (!canApply(ticket)) {
        return;
      }
      updatePersonaDraft((prev) => {
        const next = [...prev.slots];
        next[index] = result.slot;
        return { ...prev, slots: next };
      });
      setAssistModelRecoveries(result.modelRecoveries ?? []);
    } catch (error) {
      if (canApply(ticket)) {
        setAssistError(String(error));
      }
    } finally {
      if (assistFenceRef.current.settle(ticket)) {
        setSlotAssistIndex(null);
      }
    }
  }

  async function handleAssistSetting() {
    if (!mountedRef.current) return;
    setAssistError("");
    setAssistModelRecoveries([]);
    setSlotAssistIndex(null);
    setAssistPending(true);
    onSettingStarted();
    const fieldTarget = "persona-setting";
    const ticket = assistFenceRef.current.begin(currentPersonaAsyncScope(fieldTarget));
    try {
      const result = await port.assistPersonaSetting({
        name: draft.name.trim(),
        summary: draft.summary.trim(),
        slots: draft.slots,
        rewriteStrength: Number((1 - retainRatio).toFixed(2))
      });
      if (!canApply(ticket)) {
        return;
      }
      updatePersonaDraft((prev) => ({
        ...prev,
        slots: result.slots.length
          ? mergePersonaAssistSlots(prev.slots, result.slots)
          : prev.slots,
      }));
      setPromptSuggestion(result.systemPromptSuggestion, "AI 辅助设定");
      setAssistModelRecoveries(result.modelRecoveries ?? []);
    } catch (error) {
      if (canApply(ticket)) {
        setAssistError(String(error));
      }
    } finally {
      if (assistFenceRef.current.settle(ticket)) {
        setAssistPending(false);
      }
    }
  }

  return {
    assistPending,
    slotAssistIndex,
    assistError,
    assistModelRecoveries,
    retainRatio,
    setRetainRatio,
    systemPromptSuggestion,
    systemPromptSuggestionSource,
    applySystemPromptSuggestion,
    dismissSystemPromptSuggestion,
    handleAssistSlot,
    handleAssistSetting,
    resetPersonaAssist,
    clearAssistError,
  };
}
