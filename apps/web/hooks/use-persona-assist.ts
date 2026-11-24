"use client";

import { useEffect, useRef, useState, type SetStateAction } from "react";
import type { ModelRecovery } from "@vibe-learner/shared";
import { assistPersonaSlot, assistPersonaSetting } from "../lib/data/personas";
import {
  AsyncResultFence,
  type AsyncResultScope,
  type AsyncResultTicket,
} from "../lib/async-result-fence";
import {
  mergePersonaAssistSlots,
  personaSlotPayload,
  type PersonaDraft,
} from "../lib/persona-draft";
import { updateDraftSlot } from "../lib/persona-slot-edit";

interface PersonaAssistPort {
  assistPersonaSlot: typeof assistPersonaSlot;
  assistPersonaSetting: typeof assistPersonaSetting;
}
const defaultPort = { assistPersonaSlot, assistPersonaSetting };
export function usePersonaAssist(
  {
    draft,
    updatePersonaDraft,
    currentPersonaAsyncScope,
    onSettingStarted,
  }: {
    draft: PersonaDraft;
    updatePersonaDraft: (update: SetStateAction<PersonaDraft>) => void;
    currentPersonaAsyncScope: (fieldTarget: string) => AsyncResultScope;
    onSettingStarted: () => void;
  },
  port: PersonaAssistPort = defaultPort,
) {
  const [assistPending, setAssistPending] = useState(false);
  const [slotAssistId, setSlotAssistId] = useState<string | null>(null);
  const slotAssistIndex = draft.slots.findIndex(
    (slot) => slot.draftSlotId === slotAssistId,
  );
  const [assistError, setAssistError] = useState("");
  const [assistModelRecoveries, setAssistModelRecoveries] = useState<ModelRecovery[]>(
    [],
  );
  const [retainRatio, setRetainRatio] = useState(0.7);
  const [systemPromptSuggestion, setSystemPromptSuggestion] = useState("");
  const [systemPromptSuggestionSource, setSystemPromptSuggestionSource] = useState("");
  const assistFenceRef = useRef(new AsyncResultFence());
  const mountedRef = useRef(true);
  const canApply = (ticket: AsyncResultTicket) =>
    mountedRef.current &&
    assistFenceRef.current.decide(
      ticket,
      currentPersonaAsyncScope(ticket.fieldTarget),
    ) === "apply";
  useEffect(() => {
    const fence = assistFenceRef.current;
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      fence.invalidate();
    };
  }, []);
  function clearAssistError() {
    setAssistError("");
  }
  function resetPersonaAssist() {
    assistFenceRef.current.invalidate();
    setAssistPending(false);
    setSlotAssistId(null);
    setAssistError("");
    setAssistModelRecoveries([]);
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
    updatePersonaDraft((draft) => ({ ...draft, systemPrompt: systemPromptSuggestion }));
    setSystemPromptSuggestion("");
    setSystemPromptSuggestionSource("");
  }

  function dismissSystemPromptSuggestion() {
    setSystemPromptSuggestion("");
    setSystemPromptSuggestionSource("");
  }

  async function handleAssistSlot(slotId: string) {
    if (!mountedRef.current) return;
    const targetSlot = draft.slots.find((slot) => slot.draftSlotId === slotId);
    if (!targetSlot) {
      return;
    }
    setAssistError("");
    setAssistModelRecoveries([]);
    setAssistPending(false);
    setSlotAssistId(slotId);
    const fieldTarget = `persona-slot:${slotId}`;
    const ticket = assistFenceRef.current.begin(currentPersonaAsyncScope(fieldTarget));
    try {
      const result = await port.assistPersonaSlot({
        name: draft.name.trim(),
        summary: draft.summary.trim(),
        slot: personaSlotPayload(targetSlot),
        rewriteStrength: Number((1 - retainRatio).toFixed(2)),
      });
      if (!canApply(ticket)) {
        return;
      }
      updatePersonaDraft((prev) => ({
        ...prev,
        slots: updateDraftSlot(prev.slots, slotId, result.slot),
      }));
      setAssistModelRecoveries(result.modelRecoveries ?? []);
    } catch (error) {
      if (canApply(ticket)) {
        setAssistError(String(error));
      }
    } finally {
      if (assistFenceRef.current.settle(ticket)) {
        setSlotAssistId(null);
      }
    }
  }

  async function handleAssistSetting() {
    if (!mountedRef.current) return;
    setAssistError("");
    setAssistModelRecoveries([]);
    setSlotAssistId(null);
    setAssistPending(true);
    onSettingStarted();
    const fieldTarget = "persona-setting";
    const ticket = assistFenceRef.current.begin(currentPersonaAsyncScope(fieldTarget));
    try {
      const result = await port.assistPersonaSetting({
        name: draft.name.trim(),
        summary: draft.summary.trim(),
        slots: draft.slots.map(personaSlotPayload),
        rewriteStrength: Number((1 - retainRatio).toFixed(2)),
      });
      if (!canApply(ticket)) {
        return;
      }
      const mergedSlots = result.slots.length
        ? mergePersonaAssistSlots(draft.slots, result.slots)
        : null;
      if (mergedSlots) updatePersonaDraft((prev) => ({ ...prev, slots: mergedSlots }));
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
    slotAssistIndex: slotAssistIndex === -1 ? null : slotAssistIndex,
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
