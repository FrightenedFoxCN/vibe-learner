"use client";

import {
  Fragment,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ChangeEvent,
  type DragEvent as ReactDragEvent
} from "react";
import type { CSSProperties } from "react";
import {
  type CharacterAction,
  type CharacterEmotion,
  CHARACTER_ACTIONS,
  CHARACTER_EMOTIONS,
  PERSONA_SLOT_KIND_LABELS,
  PERSONA_SLOT_KINDS,
  type CreatePersonaInput,
  type PersonaCard,
  type ModelRecovery,
  type PersonaProfile,
  type PersonaSlot,
  type PersonaSlotKind,
  renderPersonaRuntimeInstruction,
  type SpeechStyle
} from "@vibe-learner/shared";

import { TopNav } from "../../components/top-nav";
import { MaterialIcon, type MaterialIconName } from "../../components/material-icon";
import { usePageDebugSnapshot } from "../../components/page-debug-context";
import {
  assistPersonaSlot,
  assistPersonaSetting,
  createPersona,
  deletePersona,
  listPersonas,
  updatePersona,
} from "../../lib/data/personas";
import {
  deletePersonaCard,
  generatePersonaCards,
  listPersonaCards,
} from "../../lib/data/persona-cards";
import { broadcastPersonaLibraryUpdated } from "../../lib/persona-library-sync";

const SLOT_KIND_HINTS: Record<string, string> = {
  worldview: "描述人格对学习、知识、成长的基本信念，会长期影响讲解立场。",
  past_experiences: "描述关键经历与背景，解释“为什么这个人格会这样教学”。",
  thinking_style: "描述推理与验证方式，例如是否先讲前提、是否强调反例。",
  teaching_method: "描述课堂推进方法，例如拆解步骤、提问节奏、练习设计。",
  narrative_mode: "描述叙事密度，建议直接使用“稳态导学”或“轻剧情陪伴”等中文表达。",
  encouragement_style: "描述鼓励策略，应当具体可执行，避免泛泛鼓励。",
  correction_style: "描述纠错方式，建议先指出可改进点，再给下一步动作。",
  custom: "自定义插槽，用于补充特殊设定。"
};

interface PersonaDraft {
  name: string;
  summary: string;
  relationship: string;
  learnerAddress: string;
  systemPrompt: string;
  referenceHints: string[];
  slots: PersonaSlot[];
  availableEmotionsText: string;
  availableActionsText: string;
  defaultSpeechStyle: SpeechStyle;
}

interface GeneratedPersonaMeta {
  summary: string;
  relationship: string;
  learnerAddress: string;
}

type CardGenerationMode = "keywords" | "long_text";

function clampWeight(value: number): number {
  const n = Number.isFinite(value) ? Math.round(value) : 50;
  return Math.max(0, Math.min(100, n));
}

const EMPTY_DRAFT: PersonaDraft = {
  name: "",
  summary: "",
  relationship: "",
  learnerAddress: "",
  systemPrompt: "",
  referenceHints: [],
  slots: [],
  availableEmotionsText: CHARACTER_EMOTIONS.join(", "),
  availableActionsText: CHARACTER_ACTIONS.join(", "),
  defaultSpeechStyle: "warm"
};

const DEFAULT_CONFIG_TEMPLATE: CreatePersonaInput = {
  name: "模板教师",
  summary: "示例人格：强调章节脉络与可执行反馈。",
  relationship: "标准导学教师",
  learnerAddress: "同学",
  systemPrompt: "优先基于章节内容讲解，通过递进式提问推进理解，并给出简洁可执行的反馈。",
  referenceHints: [],
  slots: [
    { kind: "worldview", label: "世界观起点", content: "来自学院导学中心，擅长把抽象概念拆成可验证的小步任务，并用温和语气引导学习者持续推进。" },
    { kind: "teaching_method", label: "教学方法", content: "结构化、引导式推进" },
    { kind: "narrative_mode", label: "叙事模式", content: "稳态导学" },
    { kind: "encouragement_style", label: "鼓励策略", content: "强调小步成功与可见进展" },
    { kind: "correction_style", label: "纠错策略", content: "准确指出问题，同时保持温和语气" }
  ],
  availableEmotions: ["calm", "encouraging", "serious"],
  availableActions: ["idle", "nod", "point", "pause"],
  defaultSpeechStyle: "warm"
};

const BASIC_PANE_WIDTH = 300;
const SIDEBAR_PANE_WIDTH = 360;

export default function PersonaSpectrumPage() {
  const [personas, setPersonas] = useState<PersonaProfile[]>([]);
  const [selectedPersonaId, setSelectedPersonaId] = useState("");
  const selectedPersonaIdRef = useRef("");

  const [draft, setDraft] = useState<PersonaDraft>(EMPTY_DRAFT);
  const [savingPersona, setSavingPersona] = useState(false);

  const [loadError, setLoadError] = useState("");
  const [saveError, setSaveError] = useState("");
  const [assistPending, setAssistPending] = useState(false);
  const [slotAssistIndex, setSlotAssistIndex] = useState<number | null>(null);
  const [assistError, setAssistError] = useState("");
  const [assistModelRecoveries, setAssistModelRecoveries] = useState<ModelRecovery[]>([]);
  const [retainRatio, setRetainRatio] = useState(0.7);
  const [configMessage, setConfigMessage] = useState("");
  const [configError, setConfigError] = useState("");
  const [personaCards, setPersonaCards] = useState<PersonaCard[]>([]);
  const [generatedCards, setGeneratedCards] = useState<PersonaCard[]>([]);
  const [cardGenerationMode, setCardGenerationMode] = useState<CardGenerationMode>("keywords");
  const [cardKeywordInput, setCardKeywordInput] = useState("");
  const [cardLongTextFile, setCardLongTextFile] = useState<File | null>(null);
  const [cardSearchQuery, setCardSearchQuery] = useState("");
  const [cardGenerateCount, setCardGenerateCount] = useState("");
  const [clearBeforeBackfill, setClearBeforeBackfill] = useState(true);
  const [cardActionPending, setCardActionPending] = useState<null | "generate_keywords" | "generate_long_text">(null);
  const [cardDeletePendingId, setCardDeletePendingId] = useState("");
  const [cardMessage, setCardMessage] = useState("");
  const [cardError, setCardError] = useState("");
  const [cardModelRecoveries, setCardModelRecoveries] = useState<ModelRecovery[]>([]);
  const [draggingPersonaCardId, setDraggingPersonaCardId] = useState("");
  const [slotInsertIndex, setSlotInsertIndex] = useState<number | null>(null);
  const [systemPromptSuggestion, setSystemPromptSuggestion] = useState("");
  const [systemPromptSuggestionSource, setSystemPromptSuggestionSource] = useState("");
  const [generatedPersonaMeta, setGeneratedPersonaMeta] = useState<GeneratedPersonaMeta>({
    summary: "",
    relationship: "",
    learnerAddress: "",
  });

  const [draggingSlotIndex, setDraggingSlotIndex] = useState<number | null>(null);
  const [expandedSlotIndex, setExpandedSlotIndex] = useState<number | null>(null);
  const [movePulse, setMovePulse] = useState<{ index: number; direction: -1 | 1 } | null>(null);

  const [isCompactLayout, setIsCompactLayout] = useState(false);
  const [isRewritePopoverOpen, setIsRewritePopoverOpen] = useState(false);
  const [isSystemPromptExpanded, setIsSystemPromptExpanded] = useState(false);
  const [collapsedSidebarSections, setCollapsedSidebarSections] = useState<string[]>([]);
  const [personaLibraryQuery, setPersonaLibraryQuery] = useState("");
  const [personaDeletePendingId, setPersonaDeletePendingId] = useState("");
  const [personaLibraryMessage, setPersonaLibraryMessage] = useState("");
  const [personaLibraryError, setPersonaLibraryError] = useState("");
  const rewritePopoverRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    selectedPersonaIdRef.current = selectedPersonaId;
  }, [selectedPersonaId]);

  useEffect(() => {
    if (!movePulse) {
      return;
    }
    const timer = window.setTimeout(() => {
      setMovePulse(null);
    }, 140);
    return () => window.clearTimeout(timer);
  }, [movePulse]);

  useEffect(() => {
    const syncLayout = () => {
      setIsCompactLayout(window.innerWidth < 1320);
    };
    syncLayout();
    window.addEventListener("resize", syncLayout);
    return () => window.removeEventListener("resize", syncLayout);
  }, []);

  useEffect(() => {
    if (!isRewritePopoverOpen) {
      return;
    }
    const handlePointerDown = (event: MouseEvent) => {
      if (!rewritePopoverRef.current?.contains(event.target as Node)) {
        setIsRewritePopoverOpen(false);
      }
    };
    document.addEventListener("mousedown", handlePointerDown);
    return () => document.removeEventListener("mousedown", handlePointerDown);
  }, [isRewritePopoverOpen]);

  useEffect(() => {
    let cancelled = false;
    async function bootstrap() {
      setLoadError("");
      try {
        const [personaList, cardList] = await Promise.all([
          listPersonas(),
          listPersonaCards()
        ]);
        if (cancelled) return;
        setPersonas(personaList);
        setPersonaCards(cardList);
        const initialPersona = personaList[0];
        if (initialPersona && !selectedPersonaIdRef.current) {
          setSelectedPersonaId(initialPersona.id);
          setDraft(personaToDraft(initialPersona));
        }
      } catch (error) {
        if (!cancelled) setLoadError(String(error));
      }
    }
    bootstrap();
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    const selectedPersona = personas.find((p) => p.id === selectedPersonaId);
    if (!selectedPersona) return;
    setDraft(personaToDraft(selectedPersona));
    setSystemPromptSuggestion("");
    setSystemPromptSuggestionSource("");
  }, [selectedPersonaId, personas]);

  const selectedPersona = useMemo(
    () => personas.find((p) => p.id === selectedPersonaId) ?? null,
    [personas, selectedPersonaId]
  );
  const isReadonlyPersona = selectedPersona?.source === "builtin";
  const filteredPersonaCards = useMemo(
    () => personaCards.filter((card) => matchesPersonaCard(card, cardSearchQuery)),
    [personaCards, cardSearchQuery]
  );
  const filteredPersonas = useMemo(
    () => personas.filter((persona) => matchesPersonaProfile(persona, personaLibraryQuery)),
    [personas, personaLibraryQuery]
  );
  const builtinPersonas = useMemo(
    () => filteredPersonas.filter((persona) => persona.source === "builtin"),
    [filteredPersonas]
  );
  const userPersonas = useMemo(
    () => filteredPersonas.filter((persona) => persona.source === "user"),
    [filteredPersonas]
  );
  const runtimePromptPreview = useMemo(
    () => renderPersonaRuntimeInstruction({
      name: draft.name,
      summary: draft.summary,
      relationship: draft.relationship,
      learnerAddress: draft.learnerAddress,
      systemPrompt: draft.systemPrompt,
      referenceHints: draft.referenceHints,
      slots: draft.slots,
      defaultSpeechStyle: draft.defaultSpeechStyle,
    }),
    [draft]
  );
  const pageNotice = useMemo(() => {
    if (savingPersona) {
      return "人格保存中";
    }
    if (assistPending) {
      return "AI 正在润色基础设定";
    }
    if (slotAssistIndex !== null) {
      return `AI 正在改写第 ${slotAssistIndex + 1} 个插槽`;
    }
    if (cardActionPending === "generate_keywords") {
      return "正在根据关键词生成人格卡片";
    }
    if (cardActionPending === "generate_long_text") {
      return "正在从长文本提取人格卡片";
    }
    if (selectedPersona) {
      return isReadonlyPersona
        ? `当前编辑 · ${selectedPersona.name} · 内置只读`
        : `当前编辑 · ${selectedPersona.name}`;
    }
    return "从人格库选择或创建一个教师人格";
  }, [
    assistPending,
    cardActionPending,
    isReadonlyPersona,
    savingPersona,
    selectedPersona,
    slotAssistIndex,
  ]);
  const debugSnapshot = useMemo(
    () => ({
      title: "人格页调试面板",
      subtitle: "查看草稿、卡片状态和错误。",
      error: [loadError, saveError, assistError, configError, cardError, personaLibraryError]
        .filter(Boolean)
        .join("；"),
      summary: [
        { label: "加载状态", value: loadError ? "异常" : "就绪" },
        { label: "人格", value: selectedPersona?.name || "-" },
        { label: "槽位数", value: String(draft.slots.length) },
        { label: "生成卡片", value: String(generatedCards.length) },
        { label: "卡片库", value: String(personaCards.length) },
        { label: "人格库", value: String(personas.length) },
        { label: "附加约束建议", value: systemPromptSuggestion ? "待确认" : "无" },
        { label: "回填前清空", value: clearBeforeBackfill ? "开启" : "关闭" },
        { label: "AI 恢复记录", value: String(assistModelRecoveries.length + cardModelRecoveries.length) }
      ],
      details: [
        { title: "当前选中人格", value: selectedPersona },
        { title: "编辑草稿", value: draft },
        { title: "运行时人格提示词预览", value: runtimePromptPreview },
        { title: "附加约束建议", value: { source: systemPromptSuggestionSource, value: systemPromptSuggestion } },
        { title: "生成摘要信息", value: generatedPersonaMeta },
        { title: "生成卡片（前 24 条）", value: generatedCards.slice(0, 24) },
        { title: "设定/槽位辅助恢复记录", value: assistModelRecoveries },
        { title: "卡片生成恢复记录", value: cardModelRecoveries }
      ]
    }),
    [
      assistError,
      cardError,
      configError,
      draft,
      generatedCards,
      generatedPersonaMeta,
      loadError,
      clearBeforeBackfill,
      cardModelRecoveries,
      personas.length,
      personaLibraryError,
      personaCards.length,
      saveError,
      selectedPersona,
      runtimePromptPreview,
      assistModelRecoveries,
      systemPromptSuggestion,
      systemPromptSuggestionSource
    ]
  );

  usePageDebugSnapshot(debugSnapshot);

  function mergePersonaIntoList(nextPersona: PersonaProfile) {
    setPersonas((prev) => {
      const exists = prev.some((item) => item.id === nextPersona.id);
      if (exists) {
        return prev.map((item) => (item.id === nextPersona.id ? nextPersona : item));
      }
      return [nextPersona, ...prev];
    });
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
    updateDraft("systemPrompt", systemPromptSuggestion);
    setSystemPromptSuggestion("");
    setSystemPromptSuggestionSource("");
  }

  function dismissSystemPromptSuggestion() {
    setSystemPromptSuggestion("");
    setSystemPromptSuggestionSource("");
  }

  function updateDraft<K extends keyof PersonaDraft>(key: K, value: PersonaDraft[K]) {
    if (assistError) setAssistError("");
    setDraft((prev) => ({ ...prev, [key]: value }));
  }

  function handleAddSlot(kind: PersonaSlotKind | string) {
    const label = PERSONA_SLOT_KIND_LABELS[kind as PersonaSlotKind] ?? kind;
    setDraft((prev) => ({
      ...prev,
      slots: [
        ...prev.slots,
        {
          kind,
          label,
          content: "",
          weight: 50,
          locked: false,
          sortOrder: prev.slots.length * 10,
        },
      ]
    }));
  }

  function handleClearSlots() {
    setDraft((prev) => ({ ...prev, slots: [] }));
    setExpandedSlotIndex(null);
    setDraggingSlotIndex(null);
    setSlotInsertIndex(null);
  }

  function handleUpdateSlot(index: number, field: keyof PersonaSlot, value: PersonaSlot[keyof PersonaSlot]) {
    if (assistError) setAssistError("");
    setDraft((prev) => {
      const next = [...prev.slots];
      let nextValue = value;
      if (field === "weight") {
        nextValue = clampWeight(Number(value));
      }
      next[index] = { ...next[index], [field]: nextValue };
      if (field === "kind") next[index].label = PERSONA_SLOT_KIND_LABELS[value as PersonaSlotKind] ?? value;
      return { ...prev, slots: next };
    });
  }

  function handleRemoveSlot(index: number) {
    setDraft((prev) => ({ ...prev, slots: prev.slots.filter((_, i) => i !== index) }));
  }

  function handleMoveSlot(index: number, direction: -1 | 1) {
    const target = index + direction;
    if (target < 0 || target >= draft.slots.length) {
      return;
    }
    setDraft((prev) => {
      const next = [...prev.slots];
      const temp = next[index];
      next[index] = next[target];
      next[target] = temp;
      return {
        ...prev,
        slots: next.map((slot, i) => ({ ...slot, sortOrder: i * 10 })),
      };
    });
    setMovePulse({ index: target, direction });
  }

  function handleSortSlotsByPriority() {
    setDraft((prev) => ({
      ...prev,
      slots: [...prev.slots]
        .sort((a, b) => {
          const orderA = a.sortOrder ?? 0;
          const orderB = b.sortOrder ?? 0;
          if (orderA !== orderB) {
            return orderA - orderB;
          }
          const weightA = a.weight ?? 50;
          const weightB = b.weight ?? 50;
          return weightB - weightA;
        })
        .map((slot, i) => ({ ...slot, sortOrder: i * 10 })),
    }));
  }

  function reorderSlots(fromIndex: number, insertIndex: number) {
    setDraft((prev) => {
      if (fromIndex < 0 || insertIndex < 0 || fromIndex >= prev.slots.length || insertIndex > prev.slots.length) {
        return prev;
      }
      const targetIndex = fromIndex < insertIndex ? insertIndex - 1 : insertIndex;
      if (fromIndex === targetIndex) {
        return prev;
      }
      const next = [...prev.slots];
      const [moved] = next.splice(fromIndex, 1);
      next.splice(targetIndex, 0, moved);
      return {
        ...prev,
        slots: next.map((slot, i) => ({ ...slot, sortOrder: i * 10 }))
      };
    });
  }

  function handleDragStart(index: number) {
    setDraggingSlotIndex(index);
    setSlotInsertIndex(index);
  }

  function handleSlotInsertDragOver(index: number) {
    setSlotInsertIndex(index);
  }

  function resolveSlotInsertIndex(event: ReactDragEvent<HTMLDivElement>, index: number) {
    const rect = event.currentTarget.getBoundingClientRect();
    const offsetY = event.clientY - rect.top;
    return offsetY < rect.height / 2 ? index : index + 1;
  }

  function handleSlotCardDragOver(event: ReactDragEvent<HTMLDivElement>, index: number) {
    if (!draggingPersonaCardId && draggingSlotIndex === null) {
      return;
    }
    event.preventDefault();
    handleSlotInsertDragOver(resolveSlotInsertIndex(event, index));
  }

  function handleSlotCardDrop(event: ReactDragEvent<HTMLDivElement>, index: number) {
    if (!draggingPersonaCardId && draggingSlotIndex === null) {
      return;
    }
    event.preventDefault();
    handleSlotInsertDrop(resolveSlotInsertIndex(event, index));
  }

  function handleSlotInsertDrop(index: number) {
    if (draggingPersonaCardId) {
      const card = personaCards.find((item) => item.id === draggingPersonaCardId);
      setDraggingPersonaCardId("");
      setSlotInsertIndex(null);
      if (!card) {
        return;
      }
      insertCardsIntoDraft([card], index);
      return;
    }
    if (draggingSlotIndex !== null) {
      reorderSlots(draggingSlotIndex, index);
    }
    setDraggingSlotIndex(null);
    setSlotInsertIndex(null);
  }

  function handleDragEnd() {
    setDraggingSlotIndex(null);
    setSlotInsertIndex(null);
  }

  async function handleAssistSlot(index: number) {
    const targetSlot = draft.slots[index];
    if (!targetSlot) {
      return;
    }
    setAssistError("");
    setAssistModelRecoveries([]);
    setSlotAssistIndex(index);
    try {
      const result = await assistPersonaSlot({
        name: draft.name.trim(),
        summary: draft.summary.trim(),
        slot: targetSlot,
        rewriteStrength: Number((1 - retainRatio).toFixed(2))
      });
      setDraft((prev) => {
        const next = [...prev.slots];
        next[index] = result.slot;
        return { ...prev, slots: next };
      });
      setAssistModelRecoveries(result.modelRecoveries ?? []);
    } catch (error) {
      setAssistError(String(error));
    } finally {
      setSlotAssistIndex(null);
    }
  }

  async function handleAssistSetting() {
    setAssistError("");
    setAssistModelRecoveries([]);
    setAssistPending(true);
    setIsRewritePopoverOpen(false);
    try {
      const result = await assistPersonaSetting({
        name: draft.name.trim(),
        summary: draft.summary.trim(),
        slots: draft.slots,
        rewriteStrength: Number((1 - retainRatio).toFixed(2))
      });
      setDraft((prev) => ({
        ...prev,
        slots: result.slots.length
          ? prev.slots.map((slot, index) => {
              if (slot.locked) {
                return slot;
              }
              const nextSlot = result.slots[index] ?? slot;
              return {
                ...nextSlot,
                weight: slot.weight ?? nextSlot.weight ?? 1,
                locked: slot.locked ?? nextSlot.locked ?? false,
                sortOrder: slot.sortOrder ?? nextSlot.sortOrder ?? index * 10,
              };
            })
          : prev.slots,
      }));
      setPromptSuggestion(result.systemPromptSuggestion, "AI 辅助设定");
      setAssistModelRecoveries(result.modelRecoveries ?? []);
    } catch (error) {
      setAssistError(String(error));
    } finally {
      setAssistPending(false);
    }
  }

  async function handleCreatePersona() {
    setConfigError(""); setConfigMessage(""); setSaveError("");
    const payload = draftToCreatePersonaInput(draft);
    if (!payload.name) { setSaveError("请先填写人格名称。"); return; }
    setSavingPersona(true);
    try {
      const created = await createPersona(payload);
      mergePersonaIntoList(created);
      const latest = await listPersonas();
      setPersonas(latest);
      broadcastPersonaLibraryUpdated();
      setSelectedPersonaId(created.id);
      setDraft(personaToDraft(created));
      dismissSystemPromptSuggestion();
      setPersonaLibraryMessage(`已创建人格「${created.name}」。`);
      setPersonaLibraryError("");
    } catch (error) {
      setSaveError(String(error));
    } finally {
      setSavingPersona(false);
    }
  }

  async function handleUpdatePersona() {
    setConfigError(""); setConfigMessage("");
    if (!selectedPersonaId) { setSaveError("请先选择要更新的人格。"); return; }
    if (isReadonlyPersona) { setSaveError("内置人格为只读，无法更新。请使用「创建新人格」另存。"); return; }
    setSaveError("");
    const payload = draftToCreatePersonaInput(draft);
    if (!payload.name) { setSaveError("请先填写人格名称。"); return; }
    setSavingPersona(true);
    try {
      const updated = await updatePersona(selectedPersonaId, payload);
      mergePersonaIntoList(updated);
      const latest = await listPersonas();
      setPersonas(latest);
      broadcastPersonaLibraryUpdated();
      setSelectedPersonaId(updated.id);
      setDraft(personaToDraft(updated));
      dismissSystemPromptSuggestion();
      setPersonaLibraryMessage(`已更新人格「${updated.name}」。`);
      setPersonaLibraryError("");
    } catch (error) {
      setSaveError(String(error));
    } finally {
      setSavingPersona(false);
    }
  }

  function handleExportConfig() {
    setConfigError(""); setConfigMessage("");
    const payload = draftToCreatePersonaInput(draft);
    const json = JSON.stringify(payload, null, 2);
    const blob = new Blob([json], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    const baseName = (payload.name || "persona-config").trim().toLowerCase().replace(/\s+/g, "-");
    link.href = url;
    link.download = `${baseName || "persona-config"}.json`;
    link.click();
    URL.revokeObjectURL(url);
    setConfigMessage("已导出当前配置。");
  }

  function handleDownloadTemplate() {
    setConfigError(""); setConfigMessage("");
    const json = JSON.stringify(DEFAULT_CONFIG_TEMPLATE, null, 2);
    const blob = new Blob([json], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "persona-config-template.json";
    link.click();
    URL.revokeObjectURL(url);
    setConfigMessage("已下载配置模板，可直接导入后编辑。");
  }

  async function handleImportConfig(event: ChangeEvent<HTMLInputElement>) {
    setConfigError(""); setConfigMessage("");
    const file = event.target.files?.[0];
    if (!file) return;
    try {
      const raw = await file.text();
      const parsed = JSON.parse(raw) as Record<string, unknown>;
      const normalized = normalizeImportedPersonaConfig(parsed);
      setDraft(createInputToDraft(normalized));
      setConfigMessage("配置导入成功，已应用到当前编辑区。");
    } catch (error) {
      setConfigError(`导入失败: ${String(error)}`);
    } finally {
      event.target.value = "";
    }
  }

  function handlePersonaCardDragStart(cardId: string) {
    setDraggingPersonaCardId(cardId);
    setSlotInsertIndex(draft.slots.length);
  }

  function handlePersonaCardDragEnd() {
    setDraggingPersonaCardId("");
    setSlotInsertIndex(null);
  }

  function toggleSidebarSection(key: string) {
    setCollapsedSidebarSections((current) => (
      current.includes(key)
        ? current.filter((item) => item !== key)
        : [...current, key]
    ));
  }

  function applyGeneratedCardsToDraft() {
    if (!generatedCards.length && !generatedPersonaMeta.summary && !generatedPersonaMeta.relationship && !generatedPersonaMeta.learnerAddress) {
      setCardError("当前没有可回填的生成人格内容。");
      return;
    }
    setCardError("");
    setCardMessage("");
    const baseDraft = clearBeforeBackfill ? clearDraftForGeneratedBackfill(draft) : draft;
    const insertion = buildDraftWithInsertedCards(baseDraft, generatedCards);
    setDraft({
      ...insertion.draft,
      summary: generatedPersonaMeta.summary || insertion.draft.summary,
      relationship: generatedPersonaMeta.relationship || insertion.draft.relationship,
      learnerAddress: generatedPersonaMeta.learnerAddress || insertion.draft.learnerAddress,
      referenceHints: mergeReferenceHints(
        insertion.draft.referenceHints,
        collectReferenceHintsFromCards(generatedCards)
      ),
    });
    const metaParts = [
      generatedPersonaMeta.summary ? "摘要" : "",
      generatedPersonaMeta.relationship ? "关系" : "",
      generatedPersonaMeta.learnerAddress ? "称呼" : "",
    ].filter(Boolean);
    const summary = [
      clearBeforeBackfill ? "已清空摘要、关系、称呼和卡片插槽" : "",
      metaParts.length ? `已回填${metaParts.join("、")}` : "",
      insertion.insertedCount ? `并插入 ${insertion.insertedCount} 张卡片` : generatedCards.length ? "卡片已存在，未重复插入" : "",
    ].filter(Boolean).join("，");
    setCardMessage(summary || "已将本轮生成内容应用到当前编辑区。");
  }

  function insertCardsIntoDraft(cards: PersonaCard[], insertIndex?: number) {
    if (!cards.length) {
      setCardError("请先选择至少一张人格卡片。");
      return;
    }
    setCardError("");
    setCardMessage("");
    const insertion = buildDraftWithInsertedCards(draft, cards, insertIndex);
    setDraft({
      ...insertion.draft,
      referenceHints: mergeReferenceHints(
        insertion.draft.referenceHints,
        collectReferenceHintsFromCards(cards)
      ),
    });
    if (!insertion.insertedCount) {
      setCardMessage("所选卡片已存在于当前人格中，未重复插入。");
      return;
    }
    setCardMessage(`已将 ${insertion.insertedCount} 张卡片插入当前人格编辑区。`);
  }

  async function handleGenerateCards(mode: "keywords" | "long_text") {
    let inputText = "";
    if (mode === "keywords") {
      inputText = cardKeywordInput.trim();
    } else {
      if (!cardLongTextFile) {
        setCardError("请先上传纯文本文件。");
        return;
      }
      try {
        inputText = (await cardLongTextFile.text()).trim();
      } catch (error) {
        setCardError(`读取文本文件失败：${String(error)}`);
        return;
      }
    }
    if (!inputText) {
      setCardError(mode === "keywords" ? "请先输入关键词。" : "上传的文本文件为空。");
      return;
    }
    const countText = cardGenerateCount.trim();
    let count: number | null = null;
    if (countText) {
      const parsedCount = Number(countText);
      if (!Number.isInteger(parsedCount) || parsedCount < 1) {
        setCardError("卡片数量偏好必须是大于 0 的整数，或留空交给模型决定。");
        return;
      }
      count = parsedCount;
    }
    setCardError("");
    setCardMessage("");
    setCardModelRecoveries([]);
    setCardActionPending(mode === "keywords" ? "generate_keywords" : "generate_long_text");
    try {
      const result = await generatePersonaCards({
        mode,
        inputText,
        count,
      });
      setGeneratedCards(result.items);
      setGeneratedPersonaMeta({
        summary: result.summary,
        relationship: result.relationship,
        learnerAddress: result.learnerAddress,
      });
      setCardModelRecoveries(result.modelRecoveries ?? []);
      setCardMessage(
        `已生成 ${result.items.length} 张卡片。模型：${result.usedModel || "unknown"}${result.usedWebSearch ? "，已启用联网搜索。" : "。"}`
      );
    } catch (error) {
      setCardError(String(error));
    } finally {
      setCardActionPending(null);
    }
  }

  async function handleDeletePersonaCard(cardId: string) {
    setCardError("");
    setCardMessage("");
    setCardDeletePendingId(cardId);
    try {
      await deletePersonaCard(cardId);
      setPersonaCards((prev) => prev.filter((card) => card.id !== cardId));
    } catch (error) {
      setCardError(String(error));
    } finally {
      setCardDeletePendingId("");
    }
  }

  async function handleDeletePersona(persona: PersonaProfile) {
    if (persona.source === "builtin") {
      setPersonaLibraryError("内置人格不能删除。");
      return;
    }
    setPersonaLibraryError("");
    setPersonaLibraryMessage("");
    if (!window.confirm(`确认删除人格「${persona.name}」？该操作不会影响内置人格。`)) {
      return;
    }
    setPersonaDeletePendingId(persona.id);
    try {
      await deletePersona(persona.id);
      const latest = await listPersonas();
      setPersonas(latest);
      broadcastPersonaLibraryUpdated();
      const nextSelectedId =
        selectedPersonaId === persona.id || !latest.some((item) => item.id === selectedPersonaId)
          ? (latest[0]?.id ?? "")
          : selectedPersonaId;
      setSelectedPersonaId(nextSelectedId);
      const nextSelectedPersona = latest.find((item) => item.id === nextSelectedId) ?? null;
      if (nextSelectedPersona) {
        setDraft(personaToDraft(nextSelectedPersona));
      }
      dismissSystemPromptSuggestion();
      setPersonaLibraryMessage(`已删除人格「${persona.name}」。`);
    } catch (error) {
      setPersonaLibraryError(humanizePersonaDeleteError(error));
    } finally {
      setPersonaDeletePendingId("");
    }
  }

  function renderPersonaCard(card: PersonaCard) {
    return (
      <article
        key={card.id}
        style={{
          ...styles.personaSlotLibraryCard,
          ...(draggingPersonaCardId === card.id ? styles.personaSlotLibraryCardDragging : null),
        }}
      >
        <div style={styles.libraryCardHeader}>
          <div style={styles.libraryCardTitleRow}>
            <button
              data-card-action="true"
              type="button"
              style={styles.libraryCardDragHandle}
              title="拖拽插入到左侧人格插槽"
              draggable
              onDragStart={() => handlePersonaCardDragStart(card.id)}
              onDragEnd={handlePersonaCardDragEnd}
            >
              <MaterialIcon name="drag_indicator" size={16} />
            </button>
            <span style={styles.libraryCardTitle}>{card.title}</span>
          </div>
          <span style={styles.libraryCardBadge}>卡片</span>
        </div>
        <div style={styles.libraryCardMetaRow}>
          <span>{PERSONA_SLOT_KIND_LABELS[card.kind as PersonaSlotKind] ?? card.label}</span>
          {card.tags.length ? <span>{card.tags.join(" · ")}</span> : null}
        </div>
        <p style={styles.libraryCardContent}>{card.content}</p>
        <div style={styles.sidebarCardActions}>
          <button
            data-card-action="true"
            style={styles.sidebarIconButton}
            type="button"
            onClick={() => insertCardsIntoDraft([card])}
            title="插入当前人格"
            aria-label="插入当前人格"
          >
            <MaterialIcon name="subdirectory_arrow_right" size={16} />
          </button>
          <button
            data-card-action="true"
            style={styles.sidebarIconButton}
            type="button"
            disabled={cardDeletePendingId === card.id}
            onClick={() => void handleDeletePersonaCard(card.id)}
            title={cardDeletePendingId === card.id ? "删除中" : "删除"}
            aria-label={cardDeletePendingId === card.id ? "删除中" : "删除"}
          >
            <MaterialIcon name={cardDeletePendingId === card.id ? "replay" : "delete"} size={16} />
          </button>
        </div>
      </article>
    );
  }

  function renderPersonaLibraryCard(persona: PersonaProfile) {
    const isSelected = persona.id === selectedPersonaId;
    return (
      <article
        key={persona.id}
        style={{
          ...styles.personaLibraryCard,
          ...(isSelected ? styles.personaLibraryCardSelected : null),
        }}
      >
        <div style={styles.libraryCardHeader}>
          <div style={styles.libraryCardTitleRow}>
            <span style={styles.libraryCardTitle}>{persona.name}</span>
          </div>
          <span style={styles.libraryCardBadge}>
            {persona.source === "builtin" ? "内置人格" : "用户人格"}
          </span>
        </div>
        <p style={styles.libraryCardContent}>{persona.summary || "未填写摘要"}</p>
        <div style={styles.libraryCardMetaRow}>
          <span>{persona.relationship || "未填写关系"}</span>
          <span>称呼：{persona.learnerAddress || "未填写"}</span>
          <span>{persona.slots.length} 个插槽</span>
        </div>
        <div style={styles.sidebarCardActions}>
          <button
            type="button"
            style={isSelected ? { ...styles.sidebarIconButton, ...styles.sidebarIconButtonPrimary } : styles.sidebarIconButton}
            onClick={() => {
              setSelectedPersonaId(persona.id);
              setPersonaLibraryError("");
              setPersonaLibraryMessage(`已载入人格「${persona.name}」。`);
            }}
            title={isSelected ? "编辑中" : "载入"}
            aria-label={isSelected ? "编辑中" : "载入"}
          >
            <MaterialIcon name={isSelected ? "adjust" : "arrow_forward"} size={16} />
          </button>
          {persona.source === "user" ? (
            <button
              type="button"
              style={styles.sidebarIconButton}
              disabled={personaDeletePendingId === persona.id}
              onClick={() => void handleDeletePersona(persona)}
              title={personaDeletePendingId === persona.id ? "删除中" : "删除"}
              aria-label={personaDeletePendingId === persona.id ? "删除中" : "删除"}
            >
              <MaterialIcon name={personaDeletePendingId === persona.id ? "replay" : "delete"} size={16} />
            </button>
          ) : null}
        </div>
      </article>
    );
  }

  return (
    <main className="with-app-nav" style={styles.page}>
      <TopNav currentPath="/persona-spectrum" />

      <div style={styles.heading}>
        <div style={styles.headingRow}>
          <h1 style={styles.pageTitle}>人格色谱</h1>
          <div style={styles.notice}>{pageNotice}</div>
        </div>
      </div>

      {loadError ? <div style={styles.errorBanner}>加载失败: {loadError}</div> : null}

      <div
        style={{
          ...styles.workspaceShell,
          ...(isCompactLayout ? styles.workspaceShellCompact : {}),
        }}
      >
        <div
          style={{
            ...styles.mainColumn,
            ...(isCompactLayout ? styles.mainColumnCompact : {}),
          }}
        >
          <div
            style={{
              ...styles.editorArea,
              ...(isCompactLayout ? styles.editorAreaCompact : {}),
            }}
          >
            <div
              style={{
                ...styles.basicPane,
                ...(isCompactLayout ? styles.compactPane : {}),
                width: isCompactLayout ? "100%" : BASIC_PANE_WIDTH,
                flexShrink: 0,
              }}
            >
              <div style={styles.basicPaneHead}>
                <span style={styles.basicPaneTitle}>基本设定</span>
                <div style={styles.basicPaneActions}>
                  <div ref={rewritePopoverRef} style={styles.rewritePopoverWrap}>
                    <button
                      type="button"
                      style={{ ...styles.basicIconButton, ...(assistPending ? styles.basicIconButtonDisabled : {}) }}
                      disabled={assistPending}
                      onClick={() => setIsRewritePopoverOpen((current) => !current)}
                      title={assistPending ? "AI 重写中" : "AI 重写"}
                      aria-label={assistPending ? "AI 重写中" : "AI 重写"}
                    >
                      <MaterialIcon name={assistPending ? "replay" : "auto_awesome"} size={16} />
                    </button>
                    {isRewritePopoverOpen ? (
                      <div style={styles.rewritePopover}>
                        <div style={styles.rewritePopoverSection}>
                          <span style={styles.panelTitle}>保留原文比例</span>
                          <span style={styles.rewritePopoverValue}>{(retainRatio * 100).toFixed(0)}%</span>
                        </div>
                        <input
                          style={styles.range}
                          type="range"
                          min={0}
                          max={1}
                          step={0.05}
                          value={retainRatio}
                          onChange={(e) => setRetainRatio(Number(e.target.value))}
                        />
                        <p style={styles.rewritePopoverHint}>数值越高，AI 重写时越接近原始设定。</p>
                        <button
                          type="button"
                          style={styles.rewritePopoverButton}
                          onClick={() => { void handleAssistSetting(); }}
                        >
                          开始重写
                        </button>
                      </div>
                    ) : null}
                  </div>
                  <button
                    type="button"
                    style={{ ...styles.basicIconButton, ...styles.basicIconButtonPrimary, ...(savingPersona ? styles.basicIconButtonDisabled : {}) }}
                    disabled={savingPersona}
                    onClick={handleCreatePersona}
                    title={savingPersona ? "创建人格中" : "创建人格"}
                    aria-label={savingPersona ? "创建人格中" : "创建人格"}
                  >
                    <MaterialIcon name="add" size={18} />
                  </button>
                  <button
                    type="button"
                    style={{ ...styles.basicIconButton, ...(savingPersona || isReadonlyPersona ? styles.basicIconButtonDisabled : {}) }}
                    disabled={savingPersona || isReadonlyPersona}
                    onClick={handleUpdatePersona}
                    title={savingPersona ? "更新人格中" : "更新人格"}
                    aria-label={savingPersona ? "更新人格中" : "更新人格"}
                  >
                    <MaterialIcon name="upload" size={16} />
                  </button>
                </div>
              </div>
              <section style={styles.basicPaneCard}>
                <div style={styles.basicPanePrimarySection}>
                <div style={styles.fieldGroup}>
                <label style={styles.fieldLabel}>人格</label>
                <select style={styles.select} value={selectedPersonaId} onChange={(e) => setSelectedPersonaId(e.target.value)}>
                  {personas.map((p) => (
                    <option key={p.id} value={p.id}>{p.name}（{p.source === "builtin" ? "内置" : "用户"}）</option>
                  ))}
                </select>
              </div>

              <div style={styles.fieldGroup}>
                <label style={styles.fieldLabel}>名称</label>
                <input style={styles.input} value={draft.name} onChange={(e) => updateDraft("name", e.target.value)} />
              </div>

              <div style={styles.summaryFieldGroup}>
                <label style={styles.fieldLabel}>摘要</label>
                <textarea style={styles.summaryTextarea} value={draft.summary} onChange={(e) => updateDraft("summary", e.target.value)} />
              </div>

              <div style={styles.compactGrid}>
                <div style={styles.fieldGroup}>
                  <label style={styles.fieldLabel}>关系</label>
                  <input
                    style={styles.input}
                    value={draft.relationship}
                    onChange={(e) => updateDraft("relationship", e.target.value)}
                    placeholder="例如：师生、学伴、导师"
                  />
                </div>
                <div style={styles.fieldGroup}>
                  <label style={styles.fieldLabel}>学习者称呼</label>
                  <input
                    style={styles.input}
                    value={draft.learnerAddress}
                    onChange={(e) => updateDraft("learnerAddress", e.target.value)}
                    placeholder="例如：同学、伙伴、学员"
                  />
                </div>
              </div>

              {assistError ? <span style={styles.errorInline}>{assistError}</span> : null}
                </div>

              <div style={{ ...styles.basicPaneSection, ...styles.basicPaneSectionSeparated }}>
                <div style={styles.fieldGroup}>
                  <button
                    type="button"
                    style={styles.collapsibleFieldToggle}
                    onClick={() => setIsSystemPromptExpanded((current) => !current)}
                  >
                    <span style={styles.fieldLabel}>附加系统约束（可选）</span>
                    <span style={styles.sidebarToggleIcon}>
                      <MaterialIcon name={isSystemPromptExpanded ? "expand_more" : "chevron_right"} size={16} />
                    </span>
                  </button>
                  {isSystemPromptExpanded ? (
                    <>
                      <textarea
                        style={styles.textareaLg}
                        value={draft.systemPrompt}
                        onChange={(e) => updateDraft("systemPrompt", e.target.value)}
                        placeholder="例如：始终优先引用教材原话；避免过度角色扮演；默认先给步骤再给总结。"
                      />
                      {systemPromptSuggestion ? (
                        <div style={styles.promptSuggestionCard}>
                          <div style={styles.promptSuggestionHeader}>
                            <span style={styles.panelTitle}>AI 建议</span>
                            <span style={styles.promptSuggestionSource}>{systemPromptSuggestionSource || "AI 生成"}</span>
                          </div>
                          <p style={styles.promptSuggestionNote}>
                            这只会写入上面的附加约束。
                          </p>
                          <p style={styles.promptSuggestionBody}>{systemPromptSuggestion}</p>
                          <div style={styles.actionsRow}>
                            <button type="button" style={styles.primaryBtn} onClick={applySystemPromptSuggestion}>
                              应用建议
                            </button>
                            <button type="button" style={styles.ghostBtn} onClick={dismissSystemPromptSuggestion}>
                              忽略建议
                            </button>
                          </div>
                        </div>
                      ) : null}
                    </>
                  ) : null}
                </div>
              </div>

              <section style={{ ...styles.basicPaneSection, ...styles.basicPaneSectionSeparated }}>
                <div style={styles.actionsRow}>
                  <button style={styles.ghostBtn} type="button" onClick={handleDownloadTemplate}>下载模板</button>
                  <button style={styles.ghostBtn} type="button" onClick={handleExportConfig}>导出配置</button>
                  <label style={styles.ghostBtn}>
                    导入配置
                    <input type="file" accept="application/json,.json" style={styles.hiddenInput} onChange={handleImportConfig} />
                  </label>
                </div>
                {saveError ? <span style={styles.errorInline}>{saveError}</span> : null}
                {isReadonlyPersona ? (
                  <span style={styles.mutedText}>只读 — 编辑后可另存为新人格</span>
                ) : null}
                {configMessage ? <span style={styles.mutedText}>{configMessage}</span> : null}
                {configError ? <span style={styles.errorInline}>{configError}</span> : null}
              </section>
              </section>
            </div>
            <div
              style={{
                ...styles.slotsPane,
                ...(isCompactLayout ? styles.compactPane : {}),
              }}
            >
              <div style={styles.panelHeader}>
                <span style={styles.panelTitle}>人格插槽</span>
                <div style={styles.panelHeaderActions}>
                  <button type="button" style={styles.ghostBtn} onClick={handleClearSlots} disabled={!draft.slots.length}>清空</button>
                  <button type="button" style={styles.ghostBtn} onClick={() => handleAddSlot("custom")}>添加</button>
                  <button type="button" style={styles.ghostBtn} onClick={handleSortSlotsByPriority}>按优先级整理</button>
                </div>
              </div>
              <div style={styles.panelBody}>
              <div style={styles.slotPaneContent}>
              <div
                style={{
                  ...styles.slotDropArea,
                  ...((slotInsertIndex !== null || draggingSlotIndex !== null) ? styles.slotDropZoneActive : null),
                }}
              >
                <div style={styles.slotList}>
                  <div
                    style={{
                      ...styles.slotInsertMarker,
                      ...(slotInsertIndex === 0 ? styles.slotInsertMarkerActive : null),
                    }}
                    onDragOver={(event) => {
                      if (!draggingPersonaCardId && draggingSlotIndex === null) return;
                      event.preventDefault();
                      handleSlotInsertDragOver(0);
                    }}
                    onDrop={(event) => {
                      if (!draggingPersonaCardId && draggingSlotIndex === null) return;
                      event.preventDefault();
                      handleSlotInsertDrop(0);
                    }}
                  />
                  {draft.slots.length ? draft.slots.map((slot, index) => (
                    <Fragment key={`${slot.kind}:${slot.label}:${index}`}>
                      <div
                        style={{
                          ...styles.slotCard,
                          ...(draggingSlotIndex === index ? styles.slotCardDragging : null),
                          ...(movePulse?.index === index
                            ? movePulse.direction === -1
                              ? styles.slotCardMoveUp
                              : styles.slotCardMoveDown
                            : null),
                        }}
                        onDragOver={(event) => handleSlotCardDragOver(event, index)}
                        onDrop={(event) => handleSlotCardDrop(event, index)}
                      >
                        <div
                          style={styles.slotHeader}
                          onClick={() => setExpandedSlotIndex((prev) => (prev === index ? null : index))}
                        >
                          <div style={styles.slotHeaderMain}>
                            <span
                              style={styles.dragHandle}
                              title="拖动排序"
                              draggable
                              onDragStart={(e) => { e.stopPropagation(); handleDragStart(index); }}
                              onDragEnd={handleDragEnd}
                              onClick={(e) => e.stopPropagation()}
                            >
                              <MaterialIcon name="drag_indicator" size={16} />
                            </span>
                            <select
                              style={styles.slotKindSelect}
                              value={slot.kind}
                              onChange={(e) => handleUpdateSlot(index, "kind", e.target.value)}
                              disabled={Boolean(slot.locked)}
                              onClick={(e) => e.stopPropagation()}
                            >
                              {PERSONA_SLOT_KINDS.map((k) => (
                                <option key={k} value={k}>{PERSONA_SLOT_KIND_LABELS[k]}</option>
                              ))}
                            </select>
                            <input
                              style={styles.slotLabelInput}
                              value={slot.label}
                              placeholder="显示标签"
                              onChange={(e) => handleUpdateSlot(index, "label", e.target.value)}
                              disabled={Boolean(slot.locked)}
                              onClick={(e) => e.stopPropagation()}
                            />
                            <div style={styles.slotHeaderActions}>
                              <button
                                type="button"
                                style={styles.slotToggleBtn}
                                onClick={(e) => { e.stopPropagation(); setExpandedSlotIndex((prev) => (prev === index ? null : index)); }}
                              >
                                <MaterialIcon name={expandedSlotIndex === index ? "expand_more" : "chevron_right"} size={16} />
                              </button>
                              <button
                                type="button"
                                style={styles.removeBtn}
                                onClick={(e) => { e.stopPropagation(); handleRemoveSlot(index); }}
                              ><MaterialIcon name="close" size={16} /></button>
                            </div>
                          </div>
                          {expandedSlotIndex !== index ? (
                            <span style={styles.slotPreview}>{slot.content.slice(0, 56) || "—"}</span>
                          ) : null}
                        </div>
                        {expandedSlotIndex === index ? (
                          <>
                            <textarea
                              style={styles.slotContent}
                              value={slot.content}
                              placeholder={`请填写"${PERSONA_SLOT_KIND_LABELS[slot.kind as PersonaSlotKind] ?? slot.kind}"的具体内容。`}
                              onChange={(e) => handleUpdateSlot(index, "content", e.target.value)}
                              disabled={Boolean(slot.locked)}
                            />
                            <div style={styles.weightRow}>
                              <span style={styles.fieldLabel}>权重 {slot.weight ?? 50}</span>
                              <input
                                style={styles.range}
                                type="range"
                                min={0}
                                max={100}
                                step={1}
                                value={slot.weight ?? 50}
                                onChange={(e) => handleUpdateSlot(index, "weight", Number(e.target.value))}
                                disabled={Boolean(slot.locked)}
                              />
                            </div>
                            <div style={styles.actionsRow}>
                              <IconGlyphButton icon="arrow_upward" label="上移" onClick={() => handleMoveSlot(index, -1)} />
                              <IconGlyphButton icon="arrow_downward" label="下移" onClick={() => handleMoveSlot(index, 1)} />
                              <button
                                type="button"
                                style={styles.iconBtn}
                                title={slot.locked ? "解锁" : "锁定"}
                                onClick={() => handleUpdateSlot(index, "locked", !slot.locked)}
                              >
                                <MaterialIcon name={slot.locked ? "lock_open" : "lock"} size={15} />
                              </button>
                              <button
                                type="button"
                                style={styles.iconBtn}
                                title="AI 重写"
                                onClick={() => void handleAssistSlot(index)}
                                disabled={assistPending || slotAssistIndex === index || Boolean(slot.locked)}
                              >
                                <MaterialIcon name={slotAssistIndex === index ? "replay" : "auto_awesome"} size={15} />
                              </button>
                            </div>
                          </>
                        ) : null}
                      </div>
                      <div
                        style={{
                          ...styles.slotInsertMarker,
                          ...(slotInsertIndex === index + 1 ? styles.slotInsertMarkerActive : null),
                        }}
                        onDragOver={(event) => {
                          if (!draggingPersonaCardId && draggingSlotIndex === null) return;
                          event.preventDefault();
                          handleSlotInsertDragOver(index + 1);
                        }}
                        onDrop={(event) => {
                          if (!draggingPersonaCardId && draggingSlotIndex === null) return;
                          event.preventDefault();
                          handleSlotInsertDrop(index + 1);
                        }}
                      />
                    </Fragment>
                  )) : (
                    <div
                      style={{
                        ...styles.emptySlotDropTarget,
                        ...(slotInsertIndex === 0 ? styles.emptySlotDropTargetActive : null),
                      }}
                      onDragOver={(event) => {
                        if (!draggingPersonaCardId) return;
                        event.preventDefault();
                        handleSlotInsertDragOver(0);
                      }}
                      onDrop={(event) => {
                        if (!draggingPersonaCardId) return;
                        event.preventDefault();
                        handleSlotInsertDrop(0);
                      }}
                    >
                      拖到这里插入第一张人格卡片
                    </div>
                  )}
                </div>
              </div>
              </div>

              <div style={{ ...styles.basicPaneSection, ...styles.basicPaneSectionSeparated }}>
                <div style={styles.fieldGroup}>
                  <div style={styles.fieldHeaderRow}>
                    <label style={styles.fieldLabel}>运行时人格提示词预览</label>
                  </div>
                  <pre style={styles.runtimePromptPreview}>{runtimePromptPreview}</pre>
                </div>
              </div>
              </div>{/* panelBody */}
            </div>
          </div>
        </div>
        <aside
          style={{
            ...styles.sidebarPane,
            ...(isCompactLayout ? styles.sidebarPaneCompact : {}),
            width: isCompactLayout ? "100%" : SIDEBAR_PANE_WIDTH,
            flexShrink: 0,
          }}
        >
          <div style={styles.sidebarSection}>
            <button type="button" style={styles.sidebarSectionHeader} onClick={() => toggleSidebarSection("generate")}>
              <span style={styles.panelTitle}>生成卡片</span>
              <span style={styles.sidebarToggleIcon}><MaterialIcon name={collapsedSidebarSections.includes("generate") ? "chevron_right" : "expand_more"} size={16} /></span>
            </button>
            {!collapsedSidebarSections.includes("generate") ? (
              <div style={styles.sidebarSectionBody}>
                <label style={styles.fieldGroup}>
                  <span style={styles.fieldLabel}>卡片数量偏好（可选）</span>
                  <input
                    style={styles.input}
                    type="number"
                    min={1}
                    step={1}
                    value={cardGenerateCount}
                    onChange={(e) => setCardGenerateCount(e.target.value)}
                    placeholder="留空表示不限制卡片数量"
                  />
                </label>
                <label style={styles.checkboxRow}>
                  <input
                    type="checkbox"
                    checked={clearBeforeBackfill}
                    onChange={(event) => setClearBeforeBackfill(event.target.checked)}
                  />
                  <span style={styles.checkboxLabel}>应用前清空已有摘要与插槽</span>
                </label>
                <div style={styles.modeSwitchRow}>
                  <div style={styles.modeSwitch}>
                    <button
                      type="button"
                      style={cardGenerationMode === "keywords" ? styles.modeSwitchButtonActive : styles.modeSwitchButton}
                      onClick={() => setCardGenerationMode("keywords")}
                    >
                      关键词搜索
                    </button>
                    <button
                      type="button"
                      style={cardGenerationMode === "long_text" ? styles.modeSwitchButtonActive : styles.modeSwitchButton}
                      onClick={() => setCardGenerationMode("long_text")}
                    >
                      长文本提取
                    </button>
                  </div>
                  <button
                    style={styles.sidebarIconButton}
                    type="button"
                    disabled={cardActionPending !== null}
                    onClick={() => void handleGenerateCards(cardGenerationMode)}
                    title={
                      cardGenerationMode === "keywords"
                        ? (cardActionPending === "generate_keywords" ? "生成中" : "根据关键词生成人格卡片")
                        : (cardActionPending === "generate_long_text" ? "提取中" : "根据长文本提取人格卡片")
                    }
                    aria-label={
                      cardGenerationMode === "keywords"
                        ? (cardActionPending === "generate_keywords" ? "生成中" : "根据关键词生成人格卡片")
                        : (cardActionPending === "generate_long_text" ? "提取中" : "根据长文本提取人格卡片")
                    }
                  >
                    <MaterialIcon
                      name={
                        cardGenerationMode === "keywords"
                          ? (cardActionPending === "generate_keywords" ? "replay" : "auto_awesome")
                          : (cardActionPending === "generate_long_text" ? "replay" : "description")
                      }
                      size={14}
                    />
                  </button>
                </div>
                {cardGenerationMode === "keywords" ? (
                  <label key="keywords-mode" style={styles.fieldGroup}>
                    <input
                      style={styles.input}
                      value={cardKeywordInput}
                      onChange={(e) => setCardKeywordInput(e.target.value)}
                      placeholder="例如：冷静学术、学院派导师、侦探式推理"
                    />
                  </label>
                ) : (
                  <label key="long-text-mode" style={styles.fieldGroup}>
                    <input
                      type="file"
                      accept=".txt,.md,text/plain,text/markdown"
                      style={styles.fileInput}
                      onChange={(event) => setCardLongTextFile(event.target.files?.[0] ?? null)}
                    />
                    {cardLongTextFile ? <span style={styles.mutedText}>{cardLongTextFile.name}</span> : null}
                  </label>
                )}
                {cardError ? <p style={styles.errorText}>{cardError}</p> : null}
                {cardMessage ? <p style={styles.sidebarHint}>{cardMessage}</p> : null}
                {(generatedCards.length || generatedPersonaMeta.summary || generatedPersonaMeta.relationship || generatedPersonaMeta.learnerAddress) ? (
                  <div style={styles.generatedResultCard}>
                    <strong style={styles.generatedResultTitle}>{generatedPersonaMeta.summary || "本轮生成人格草案"}</strong>
                    <p style={styles.generatedResultMeta}>
                      {generatedCards.length} 张卡片
                      {generatedPersonaMeta.relationship ? ` · ${generatedPersonaMeta.relationship}` : ""}
                      {generatedPersonaMeta.learnerAddress ? ` · 称呼：${generatedPersonaMeta.learnerAddress}` : ""}
                    </p>
                    <div style={styles.sidebarActionRow}>
                      <button
                        style={styles.sidebarIconButton}
                        type="button"
                        disabled={!(generatedCards.length || generatedPersonaMeta.summary || generatedPersonaMeta.relationship || generatedPersonaMeta.learnerAddress)}
                        onClick={applyGeneratedCardsToDraft}
                        title="应用到当前编辑区"
                        aria-label="应用到当前编辑区"
                      >
                        <MaterialIcon name="subdirectory_arrow_right" size={14} />
                      </button>
                    </div>
                  </div>
                ) : null}
              </div>
            ) : null}
          </div>

          <div style={styles.sidebarSection}>
            <button type="button" style={styles.sidebarSectionHeader} onClick={() => toggleSidebarSection("results")}>
              <span style={styles.panelTitle}>卡片库</span>
              <span style={styles.sidebarToggleIcon}><MaterialIcon name={collapsedSidebarSections.includes("results") ? "chevron_right" : "expand_more"} size={16} /></span>
            </button>
            {!collapsedSidebarSections.includes("results") ? (
              <div style={styles.sidebarSectionBody}>
                <input
                  style={styles.input}
                  value={cardSearchQuery}
                  onChange={(e) => setCardSearchQuery(e.target.value)}
                  placeholder="搜索标题、内容、标签、关键词"
                />
                {filteredPersonaCards.length ? (
                  <div style={styles.cardList}>
                    {filteredPersonaCards.map((card) => renderPersonaCard(card))}
                  </div>
                ) : null}
              </div>
            ) : null}
          </div>

          <div style={styles.sidebarSection}>
            <button type="button" style={styles.sidebarSectionHeader} onClick={() => toggleSidebarSection("persona-library")}>
              <span style={styles.panelTitle}>人格库</span>
              <span style={styles.sidebarToggleIcon}><MaterialIcon name={collapsedSidebarSections.includes("persona-library") ? "chevron_right" : "expand_more"} size={16} /></span>
            </button>
            {!collapsedSidebarSections.includes("persona-library") ? (
              <div style={styles.sidebarSectionBody}>
                <input
                  style={styles.input}
                  value={personaLibraryQuery}
                  onChange={(e) => setPersonaLibraryQuery(e.target.value)}
                  placeholder="搜索人格名称、摘要、关系或称呼"
                />
                {personaLibraryMessage ? <p style={styles.sidebarHint}>{personaLibraryMessage}</p> : null}
                {personaLibraryError ? <p style={styles.errorText}>{personaLibraryError}</p> : null}

                {builtinPersonas.length ? (
                  <div style={styles.cardList}>
                    {builtinPersonas.map(renderPersonaLibraryCard)}
                  </div>
                ) : null}

                {userPersonas.length ? (
                  <div style={styles.cardList}>
                    {userPersonas.map(renderPersonaLibraryCard)}
                  </div>
                ) : null}
              </div>
            ) : null}
          </div>

        </aside>
      </div>
    </main>
  );
}

/* ─── Helpers (unchanged) ─── */

function IconGlyphButton({
  icon,
  label,
  onClick,
}: {
  icon: MaterialIconName;
  label: string;
  onClick: () => void;
}) {
  return (
    <button type="button" style={styles.iconBtn} title={label} aria-label={label} onClick={onClick}>
      <MaterialIcon name={icon} size={15} />
    </button>
  );
}

function personaToDraft(persona: PersonaProfile): PersonaDraft {
  return {
    name: persona.name,
    summary: persona.summary,
    relationship: persona.relationship,
    learnerAddress: persona.learnerAddress,
    systemPrompt: persona.systemPrompt,
    referenceHints: persona.referenceHints ?? [],
    slots: (persona.slots ?? []).map((slot, index) => ({
      ...slot,
      weight: slot.weight ?? 50,
      locked: slot.locked ?? false,
      sortOrder: slot.sortOrder ?? index * 10,
    })),
    availableEmotionsText: persona.availableEmotions.join(", "),
    availableActionsText: persona.availableActions.join(", "),
    defaultSpeechStyle: persona.defaultSpeechStyle
  };
}

function draftToCreatePersonaInput(draft: PersonaDraft): CreatePersonaInput {
  return {
    name: draft.name.trim(),
    summary: draft.summary.trim(),
    relationship: draft.relationship.trim(),
    learnerAddress: draft.learnerAddress.trim(),
    systemPrompt: draft.systemPrompt.trim(),
    referenceHints: mergeReferenceHints([], draft.referenceHints),
    slots: [...draft.slots]
      .sort((a, b) => {
        const orderA = a.sortOrder ?? 0;
        const orderB = b.sortOrder ?? 0;
        if (orderA !== orderB) {
          return orderA - orderB;
        }
        return (b.weight ?? 50) - (a.weight ?? 50);
      })
      .map((slot, index) => ({
        ...slot,
        weight: clampWeight(Number(slot.weight ?? 50)),
        sortOrder: index * 10,
      })),
    availableEmotions: coerceEmotions(draft.availableEmotionsText),
    availableActions: coerceActions(draft.availableActionsText),
    defaultSpeechStyle: draft.defaultSpeechStyle
  };
}

function createInputToDraft(snapshot: CreatePersonaInput): PersonaDraft {
  return {
    name: snapshot.name,
    summary: snapshot.summary,
    relationship: snapshot.relationship,
    learnerAddress: snapshot.learnerAddress,
    systemPrompt: snapshot.systemPrompt,
    referenceHints: mergeReferenceHints([], snapshot.referenceHints ?? []),
    slots: (snapshot.slots ?? []).map((slot, index) => ({
      ...slot,
      weight: clampWeight(Number(slot.weight ?? 50)),
      locked: slot.locked ?? false,
      sortOrder: slot.sortOrder ?? index * 10,
    })),
    availableEmotionsText: (snapshot.availableEmotions ?? CHARACTER_EMOTIONS).join(", "),
    availableActionsText: (snapshot.availableActions ?? CHARACTER_ACTIONS).join(", "),
    defaultSpeechStyle: snapshot.defaultSpeechStyle ?? "warm"
  };
}

function buildDraftWithInsertedCards(
  draft: PersonaDraft,
  cards: PersonaCard[],
  insertIndex?: number,
): { draft: PersonaDraft; insertedCount: number } {
  const safeInsertIndex = Math.max(0, Math.min(insertIndex ?? draft.slots.length, draft.slots.length));
  const existingKeys = new Set(
    draft.slots.map((slot) => `${slot.kind}::${slot.label}::${slot.content.trim()}`)
  );
  const appended = cards
    .filter((card) => {
      const key = `${card.kind}::${card.label}::${card.content.trim()}`;
      if (existingKeys.has(key)) {
        return false;
      }
      existingKeys.add(key);
      return true;
    })
    .map((card, index) => ({
      kind: card.kind,
      label: card.label,
      content: card.content,
      weight: 50,
      locked: false,
      sortOrder: (safeInsertIndex + index) * 10,
    }));
  if (!appended.length) {
    return { draft, insertedCount: 0 };
  }
  const nextSlots = [...draft.slots];
  nextSlots.splice(safeInsertIndex, 0, ...appended);
  return {
    draft: {
      ...draft,
      slots: nextSlots.map((slot, index) => ({ ...slot, sortOrder: index * 10 })),
    },
    insertedCount: appended.length,
  };
}

function clearDraftForGeneratedBackfill(draft: PersonaDraft): PersonaDraft {
  return {
    ...draft,
    summary: "",
    relationship: "",
    learnerAddress: "",
    referenceHints: [],
    slots: [],
  };
}

function matchesPersonaCard(card: PersonaCard, query: string): boolean {
  const trimmed = query.trim().toLowerCase();
  if (!trimmed) {
    return true;
  }
  const haystack = [
    card.title,
    card.label,
    card.content,
    card.sourceNote,
    card.searchKeywords,
    card.tags.join(" "),
  ]
    .join("\n")
    .toLowerCase();
  return haystack.includes(trimmed);
}

function matchesPersonaProfile(persona: PersonaProfile, query: string): boolean {
  const trimmed = query.trim().toLowerCase();
  if (!trimmed) {
    return true;
  }
  const haystack = [
    persona.name,
    persona.summary,
    persona.relationship,
    persona.learnerAddress,
    persona.systemPrompt,
    (persona.referenceHints ?? []).join(" "),
    persona.source === "builtin" ? "内置人格" : "用户人格",
  ]
    .join("\n")
    .toLowerCase();
  return haystack.includes(trimmed);
}

function collectReferenceHintsFromCards(cards: PersonaCard[]): string[] {
  return mergeReferenceHints(
    [],
    cards.map((card) => card.sourceNote)
  );
}

function mergeReferenceHints(base: string[], incoming: string[]): string[] {
  const seen = new Set<string>();
  return [...base, ...incoming]
    .map((hint) => hint.trim())
    .filter(Boolean)
    .filter((hint) => {
      const key = hint.toLowerCase();
      if (seen.has(key)) {
        return false;
      }
      seen.add(key);
      return true;
    });
}

function humanizePersonaDeleteError(error: unknown): string {
  const raw = String(error).replace(/^Error:\s*/, "");
  if (raw.includes("persona_readonly_builtin")) {
    return "内置人格不能删除。";
  }
  if (!raw.includes("persona_in_use")) {
    return raw;
  }

  const countSpecs = [
    { key: "plans", label: "学习计划" },
    { key: "sessions", label: "学习会话" },
    { key: "scene_instances", label: "场景实例" },
  ];
  const parts = countSpecs.flatMap(({ key, label }) => {
    const match = raw.match(new RegExp(`${key}=(\\d+)`));
    const count = Number(match?.[1] ?? 0);
    if (!count) {
      return [];
    }
    return [`${label} ${count} 条`];
  });
  return parts.length
    ? `该人格仍被${parts.join("、")}引用，暂时不能删除。`
    : "该人格仍被现有数据引用，暂时不能删除。";
}

function splitCsv(value: string): string[] {
  return value.split(",").map((item) => item.trim()).filter(Boolean);
}

function coerceEmotions(value: string): CharacterEmotion[] {
  return dedupeCsvValues(splitCsv(value));
}

function coerceActions(value: string): CharacterAction[] {
  return dedupeCsvValues(splitCsv(value));
}

function dedupeCsvValues<T extends string>(values: T[]): T[] {
  const seen = new Set<string>();
  const result: T[] = [];
  values.forEach((value) => {
    const key = value.toLowerCase();
    if (seen.has(key)) {
      return;
    }
    seen.add(key);
    result.push(value);
  });
  return result;
}

function normalizeImportedPersonaConfig(parsed: Record<string, unknown>): CreatePersonaInput {
  const name = String(parsed.name ?? "").trim();
  const systemPrompt = String(parsed.systemPrompt ?? parsed.system_prompt ?? "").trim();
  if (!name) throw new Error("缺少名称字段（name）");

  let slots: PersonaSlot[] = [];
  if (Array.isArray(parsed.slots)) {
    slots = parsed.slots
      .filter((s): s is Record<string, unknown> => typeof s === "object" && s !== null)
      .map((s, index) => ({
        kind: String(s.kind ?? "custom"),
        label: String(s.label ?? s.kind ?? ""),
        content: String(s.content ?? ""),
        weight: clampWeight(Number(s.weight ?? 50)),
        locked: Boolean(s.locked),
        sortOrder: Number(s.sortOrder ?? s.sort_order ?? index * 10),
      }));
  }

  const availableEmotions = Array.isArray(parsed.availableEmotions)
    ? coerceEmotions(parsed.availableEmotions.map((item) => String(item)).join(","))
    : Array.isArray(parsed.available_emotions)
      ? coerceEmotions(parsed.available_emotions.map((item) => String(item)).join(","))
      : undefined;
  const availableActions = Array.isArray(parsed.availableActions)
    ? coerceActions(parsed.availableActions.map((item) => String(item)).join(","))
    : Array.isArray(parsed.available_actions)
      ? coerceActions(parsed.available_actions.map((item) => String(item)).join(","))
      : undefined;

  return {
    name,
    summary: String(parsed.summary ?? "").trim(),
    relationship: String(parsed.relationship ?? parsed.relation ?? "").trim(),
    learnerAddress: String(parsed.learnerAddress ?? parsed.learner_address ?? parsed.address ?? "").trim(),
    systemPrompt,
    slots,
    availableEmotions,
    availableActions,
    defaultSpeechStyle: String(parsed.defaultSpeechStyle ?? parsed.default_speech_style ?? "warm") as SpeechStyle
  };
}

/* ─── Styles ─── */

const styles: Record<string, CSSProperties> = {
  /* Page shell */
  page: {
    width: "100%",
    height: "100vh",
    overflow: "hidden",
    display: "flex",
    flexDirection: "column",
    boxSizing: "border-box",
    maxWidth: 1600,
    margin: "0 auto",
    padding: "0 28px 28px",
    background: "var(--bg)",
  },
  heading: {
    display: "grid",
    gap: 8,
    position: "sticky",
    top: 0,
    zIndex: 15,
    paddingTop: 20,
    marginBottom: 16,
    paddingBottom: 16,
    borderBottom: "1px solid color-mix(in srgb, var(--border) 76%, white)",
    background: "color-mix(in srgb, white 92%, var(--bg))",
  },
  headingRow: {
    display: "flex",
    alignItems: "center",
    gap: 12,
    flexWrap: "wrap",
  },
  pageTitle: {
    margin: 0,
    fontSize: 20,
    fontWeight: 700,
    color: "var(--ink)",
    lineHeight: 1.2,
  },
  notice: {
    width: "fit-content",
    maxWidth: "100%",
    minHeight: 24,
    padding: "0 8px",
    border: "none",
    background: "color-mix(in srgb, white 72%, var(--accent-soft))",
    color: "var(--ink-2)",
    fontSize: 12,
    lineHeight: 1,
    display: "inline-flex",
    alignItems: "center",
  },
  workspaceShell: {
    display: "flex",
    flex: 1,
    minHeight: 0,
    overflow: "hidden",
    gap: 14,
  },
  workspaceShellCompact: {
    flexDirection: "column",
    overflowY: "auto",
  },
  mainColumn: {
    flex: 1,
    minWidth: 0,
    display: "flex",
    flexDirection: "column",
    overflow: "hidden",
  },
  mainColumnCompact: {
    overflow: "visible",
  },
  editorArea: {
    display: "flex",
    flex: 1,
    minHeight: 0,
    overflow: "hidden",
    gap: 14,
  },
  editorAreaCompact: {
    flexDirection: "column",
    overflow: "visible",
  },
  basicPane: {
    display: "flex",
    flexDirection: "column",
    minHeight: 0,
    overflow: "hidden",
    minWidth: 0,
    border: "none",
    background: "transparent",
  },
  slotsPane: {
    flex: 1,
    minWidth: 0,
    display: "flex",
    flexDirection: "column",
    overflow: "hidden",
    border: "1px solid var(--border)",
    background: "var(--panel)",
  },
  compactPane: {
    overflow: "visible",
  },
  basicPaneHead: {
    position: "relative",
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 12,
    flexWrap: "wrap",
    minHeight: 24,
    padding: "0 4px 10px 0",
  },
  basicPaneTitle: {
    fontSize: 10,
    fontWeight: 700,
    letterSpacing: "0.12em",
    textTransform: "uppercase",
    color: "var(--muted)",
  },
  basicPaneActions: {
    display: "flex",
    flexWrap: "wrap",
    gap: 8,
  },
  rewritePopoverWrap: {
    position: "static",
    display: "inline-flex",
  },
  basicIconButton: {
    border: "1px solid color-mix(in srgb, var(--border) 76%, white)",
    width: 32,
    height: 32,
    padding: 0,
    background: "color-mix(in srgb, white 72%, var(--surface))",
    color: "var(--ink)",
    cursor: "pointer",
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
  },
  basicIconButtonPrimary: {
    border: "none",
    background: "var(--accent)",
    color: "white",
  },
  basicIconButtonDisabled: {
    opacity: 0.45,
    cursor: "not-allowed",
  },
  rewritePopover: {
    position: "absolute",
    top: "calc(100% + 8px)",
    left: 0,
    zIndex: 20,
    width: 220,
    display: "grid",
    gap: 10,
    padding: "12px 12px 10px",
    border: "1px solid color-mix(in srgb, var(--border) 76%, white)",
    background: "var(--panel)",
    boxShadow: "0 12px 28px rgba(13, 32, 40, 0.12)",
  },
  rewritePopoverSection: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 8,
  },
  rewritePopoverValue: {
    fontSize: 12,
    fontWeight: 600,
    color: "var(--ink)",
  },
  rewritePopoverHint: {
    margin: 0,
    fontSize: 12,
    lineHeight: 1.5,
    color: "var(--muted)",
  },
  rewritePopoverButton: {
    border: "none",
    minHeight: 32,
    padding: "0 12px",
    background: "var(--accent)",
    color: "white",
    fontWeight: 600,
    cursor: "pointer",
    fontSize: 12,
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
  },
  basicPaneCard: {
    display: "flex",
    flexDirection: "column",
    gap: 0,
    paddingTop: 12,
    background: "transparent",
    flex: 1,
    minHeight: 0,
  },
  basicPaneSection: {
    display: "grid",
    gap: 12,
  },
  basicPanePrimarySection: {
    display: "flex",
    flexDirection: "column",
    gap: 12,
    flex: 1,
    minHeight: 0,
  },
  basicPaneSectionSeparated: {
    paddingTop: 14,
    marginTop: 14,
    borderTop: "1px solid color-mix(in srgb, var(--border) 68%, white)",
  },
  panelHeader: {
    flexShrink: 0,
    padding: "10px 16px",
    borderBottom: "1px solid color-mix(in srgb, var(--border) 76%, white)",
    background: "transparent",
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    minHeight: 40,
    gap: 8,
  },
  panelHeaderActions: {
    display: "inline-flex",
    alignItems: "center",
    gap: 8,
    flexWrap: "wrap",
  },
  panelBody: {
    flex: 1,
    minHeight: 0,
    overflowY: "auto",
    padding: "16px 18px 18px",
    display: "flex",
    flexDirection: "column",
    gap: 12,
  },
  slotDropArea: {
    display: "flex",
    flexDirection: "column",
    gap: 0,
  },

  /* Left: editor */
  editorPanel: {
    border: "1px solid var(--border)",
    background: "var(--panel)",
    padding: 20,
    display: "grid",
    gap: 14,
    alignContent: "start",
  },
  sidebarPane: {
    display: "flex",
    flexDirection: "column",
    gap: 10,
    minHeight: 0,
    overflowY: "auto",
  },
  sidebarPaneCompact: {
    overflow: "visible",
  },
  resizer: {
    width: 4,
    flexShrink: 0,
    alignSelf: "stretch",
    background: "var(--border)",
    cursor: "col-resize",
  },
  resizerHidden: {
    display: "none",
  },
  sidebarSection: {
    border: "1px solid var(--border)",
    background: "color-mix(in srgb, white 99%, var(--panel))",
    overflow: "hidden",
    flexShrink: 0,
  },
  sidebarSectionHeader: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    width: "100%",
    border: "none",
    background: "transparent",
    padding: "10px 12px",
    cursor: "pointer",
    textAlign: "left",
  },
  sidebarSectionBody: {
    padding: "0 12px 12px",
    display: "grid",
    gap: 8,
    alignContent: "start",
  },
  sidebarListSection: {
    flex: 1,
    overflowY: "auto",
    minHeight: 0,
    alignContent: "start",
  },
  sidebarToggleIcon: {
    color: "var(--muted)",
    display: "inline-flex",
    alignItems: "center",
  },

  /* Panel header */
  panelHead: {
    paddingBottom: 10,
    borderBottom: "1px solid color-mix(in srgb, var(--border) 68%, white)",
    marginBottom: 0,
  },
  sidebarHint: {
    margin: 0,
    fontSize: 12,
    color: "var(--muted)",
    lineHeight: 1.6,
  },
  checkboxRow: {
    display: "flex",
    alignItems: "center",
    gap: 8,
    fontSize: 12,
    color: "var(--ink)",
    lineHeight: 1.4,
  },
  checkboxLabel: {
    color: "var(--muted)",
  },
  panelTitle: {
    fontSize: 10,
    fontWeight: 700,
    letterSpacing: "0.12em",
    textTransform: "uppercase",
    color: "var(--muted)",
  },

  /* Form elements */
  fieldGroup: {
    display: "grid",
    gap: 4,
  },
  collapsibleFieldToggle: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    width: "100%",
    border: "none",
    background: "transparent",
    padding: 0,
    cursor: "pointer",
    textAlign: "left",
  },
  summaryFieldGroup: {
    display: "flex",
    flexDirection: "column",
    gap: 4,
    flex: 1,
    minHeight: 0,
  },
  fieldHeaderRow: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 8,
    flexWrap: "wrap",
  },
  fieldHint: {
    fontSize: 11,
    color: "var(--muted)",
    letterSpacing: "0.03em",
  },
  slotDropZoneActive: {
    boxShadow: "0 0 0 2px var(--accent-soft) inset",
    borderRadius: 4,
    padding: 8,
    background: "color-mix(in srgb, white 70%, var(--accent-soft))",
  },
  slotPaneContent: {
    width: "100%",
    maxWidth: 760,
    margin: "0 auto",
    minWidth: 0,
    display: "grid",
    gap: 0,
  },
  slotList: {
    display: "grid",
    gap: 0,
  },
  slotInsertMarker: {
    height: 10,
    borderRadius: 999,
    transition: "background 140ms ease, transform 140ms ease, box-shadow 140ms ease",
  },
  slotInsertMarkerActive: {
    background: "var(--accent)",
    boxShadow: "0 0 0 3px var(--accent-soft)",
    transform: "scaleY(1.2)",
  },
  modeSwitch: {
    display: "inline-flex",
    border: "1px solid var(--border)",
    background: "color-mix(in srgb, white 88%, var(--panel))",
    minHeight: 28,
    minWidth: 0,
    flex: 1,
  },
  modeSwitchRow: {
    display: "flex",
    alignItems: "center",
    gap: 8,
    justifyContent: "space-between",
    flexWrap: "nowrap",
  },
  modeSwitchButton: {
    border: "none",
    background: "transparent",
    color: "var(--muted)",
    padding: "0 10px",
    fontSize: 12,
    cursor: "pointer",
    minHeight: 28,
    flex: 1,
  },
  modeSwitchButtonActive: {
    border: "none",
    background: "color-mix(in srgb, white 65%, var(--accent-soft))",
    color: "var(--ink)",
    fontWeight: 600,
    padding: "0 10px",
    fontSize: 12,
    cursor: "pointer",
    minHeight: 28,
    flex: 1,
  },
  emptySlotDropTarget: {
    border: "1px dashed var(--border)",
    background: "var(--panel)",
    color: "var(--muted)",
    padding: "14px 12px",
    fontSize: 12,
    lineHeight: 1.6,
    textAlign: "center",
  },
  emptySlotDropTargetActive: {
    border: "1px dashed var(--accent)",
    background: "color-mix(in srgb, white 70%, var(--accent-soft))",
    color: "var(--ink)",
  },
  fieldLabel: {
    fontSize: 11,
    fontWeight: 600,
    letterSpacing: "0.04em",
    textTransform: "uppercase",
    color: "var(--muted)",
  },
  input: {
    width: "100%",
    height: 38,
    border: "1px solid color-mix(in srgb, var(--border) 76%, white)",
    background: "color-mix(in srgb, white 72%, var(--surface))",
    padding: "0 10px",
    color: "var(--ink)",
    fontSize: 14,
  },
  select: {
    width: "100%",
    height: 38,
    border: "1px solid color-mix(in srgb, var(--border) 76%, white)",
    background: "color-mix(in srgb, white 72%, var(--surface))",
    padding: "0 10px",
    color: "var(--ink)",
    fontSize: 14,
  },
  selectCompact: {
    width: 88,
    height: 38,
    border: "1px solid color-mix(in srgb, var(--border) 76%, white)",
    background: "color-mix(in srgb, white 72%, var(--surface))",
    padding: "0 8px",
    color: "var(--ink)",
    fontSize: 14,
  },
  textarea: {
    width: "100%",
    minHeight: 96,
    border: "1px solid color-mix(in srgb, var(--border) 76%, white)",
    background: "color-mix(in srgb, white 72%, var(--surface))",
    padding: "10px 12px",
    resize: "vertical",
    color: "var(--ink)",
    fontSize: 14,
    lineHeight: 1.65,
  },
  summaryTextarea: {
    width: "100%",
    minHeight: 0,
    flex: 1,
    border: "1px solid color-mix(in srgb, var(--border) 76%, white)",
    background: "color-mix(in srgb, white 72%, var(--surface))",
    padding: "10px 12px",
    resize: "vertical",
    color: "var(--ink)",
    fontSize: 14,
    lineHeight: 1.65,
  },
  textareaLg: {
    width: "100%",
    minHeight: 120,
    border: "1px solid color-mix(in srgb, var(--border) 76%, white)",
    background: "color-mix(in srgb, white 72%, var(--surface))",
    padding: "10px 12px",
    resize: "vertical",
    color: "var(--ink)",
    fontSize: 14,
    lineHeight: 1.65,
  },
  fileInput: {
    width: "100%",
    border: "1px solid color-mix(in srgb, var(--border) 76%, white)",
    padding: "8px 10px",
    background: "color-mix(in srgb, white 72%, var(--surface))",
    color: "var(--ink)",
    fontSize: 14,
  },
  promptSuggestionCard: {
    border: "none",
    borderLeft: "2px solid color-mix(in srgb, var(--accent) 52%, var(--border))",
    background: "transparent",
    padding: "4px 0 4px 10px",
    display: "grid",
    gap: 6,
  },
  promptSuggestionHeader: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 8,
    flexWrap: "wrap",
  },
  promptSuggestionSource: {
    fontSize: 12,
    color: "var(--muted)",
  },
  promptSuggestionNote: {
    margin: 0,
    fontSize: 12,
    lineHeight: 1.5,
    color: "var(--muted)",
  },
  promptSuggestionBody: {
    margin: 0,
    fontSize: 14,
    lineHeight: 1.65,
    color: "var(--ink)",
    whiteSpace: "pre-wrap",
  },
  runtimePromptPreview: {
    margin: 0,
    minHeight: 96,
    maxHeight: 156,
    border: "1px solid var(--border)",
    background: "var(--bg)",
    padding: "10px 12px",
    color: "var(--ink)",
    fontSize: 12,
    lineHeight: 1.6,
    whiteSpace: "pre-wrap",
    overflowY: "auto",
    overflowX: "auto",
  },
  range: {
    width: "100%",
  },

  /* Slot card */
  slotCard: {
    border: "none",
    borderBottom: "1px solid color-mix(in srgb, var(--border) 68%, white)",
    background: "transparent",
    padding: "6px 0 8px",
    display: "grid",
    gap: 4,
    marginBottom: 0,
    transition: "transform 180ms ease, box-shadow 180ms ease, border-color 180ms ease, opacity 180ms ease",
  },
  slotCardDragging: {
    opacity: 0.7,
    transform: "scale(0.99)",
    borderBottom: "1px solid var(--teal)",
  },
  slotCardMoveUp: {
    transform: "translateY(-8px)",
    borderBottom: "1px solid var(--accent)",
  },
  slotCardMoveDown: {
    transform: "translateY(8px)",
    borderBottom: "1px solid var(--accent)",
  },
  slotHeader: {
    display: "grid",
    gap: 4,
    cursor: "pointer",
    minWidth: 0,
  },
  slotHeaderMain: {
    display: "grid",
    gridTemplateColumns: "18px minmax(110px, 132px) minmax(0, 1fr) auto",
    gap: 6,
    alignItems: "center",
    minWidth: 0,
  },
  slotHeaderActions: {
    display: "inline-flex",
    alignItems: "center",
    gap: 2,
    flexShrink: 0,
  },
  dragHandle: {
    color: "var(--muted)",
    cursor: "grab",
    userSelect: "none",
    padding: 0,
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
  },
  slotKindSelect: {
    width: "100%",
    minWidth: 0,
    height: 28,
    border: "none",
    borderBottom: "1px solid color-mix(in srgb, var(--border) 68%, white)",
    background: "transparent",
    padding: "0 2px 0 0",
    fontSize: 12,
    color: "var(--ink)",
  },
  slotLabelInput: {
    width: "100%",
    minWidth: 0,
    height: 28,
    border: "none",
    borderBottom: "1px solid color-mix(in srgb, var(--border) 68%, white)",
    background: "transparent",
    padding: "0 2px",
    fontSize: 12,
    color: "var(--ink)",
  },
  removeBtn: {
    flex: "0 0 auto",
    height: 24,
    width: 24,
    border: "none",
    background: "transparent",
    color: "var(--muted)",
    cursor: "pointer",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
  },
  slotContent: {
    width: "100%",
    minHeight: 60,
    border: "1px solid color-mix(in srgb, var(--border) 62%, white)",
    background: "color-mix(in srgb, white 55%, var(--bg))",
    padding: "8px 10px",
    resize: "vertical",
    fontSize: 12,
    lineHeight: 1.6,
    color: "var(--ink)",
  },
  slotHintText: {
    fontSize: 12,
    color: "var(--muted)",
    lineHeight: 1.6,
  },
  weightRow: {
    display: "grid",
    gridTemplateColumns: "auto 1fr",
    gap: 6,
    alignItems: "center",
  },
  slotPreview: {
    display: "block",
    maxWidth: "56ch",
    paddingLeft: 24,
    fontSize: 11,
    color: "var(--muted)",
    overflow: "hidden",
    whiteSpace: "nowrap",
    textOverflow: "ellipsis",
    minWidth: 0,
  },
  slotToggleBtn: {
    border: "none",
    background: "transparent",
    color: "var(--muted)",
    cursor: "pointer",
    padding: 0,
    width: 24,
    height: 24,
    flexShrink: 0,
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
  },

  /* Compact 2-col grid */
  compactGrid: {
    display: "grid",
    gridTemplateColumns: "1fr",
    gap: 10,
  },

  /* Buttons */
  primaryBtn: {
    border: "1px solid color-mix(in srgb, var(--accent) 38%, var(--border))",
    background: "color-mix(in srgb, white 86%, var(--accent-soft))",
    color: "var(--ink)",
    height: 36,
    padding: "0 14px",
    cursor: "pointer",
    fontWeight: 700,
    fontSize: 12,
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
  },
  ghostBtn: {
    border: "1px solid var(--border)",
    background: "color-mix(in srgb, white 98%, var(--panel))",
    color: "var(--ink)",
    height: 36,
    padding: "0 12px",
    cursor: "pointer",
    fontSize: 12,
    fontWeight: 600,
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
  },
  iconBtn: {
    border: "none",
    background: "transparent",
    color: "var(--muted)",
    height: 24,
    minWidth: 24,
    padding: 0,
    cursor: "pointer",
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
    flexShrink: 0,
  },
  tagBtn: {
    border: "1px solid var(--border)",
    background: "transparent",
    color: "var(--ink)",
    height: 28,
    padding: "0 10px",
    cursor: "pointer",
    fontSize: 12,
    fontWeight: 600,
  },
  actionsRow: {
    display: "flex",
    gap: 8,
    alignItems: "center",
    flexWrap: "wrap",
  },
  sidebarActionRow: {
    display: "flex",
    gap: 4,
    alignItems: "center",
    justifyContent: "flex-end",
    flexWrap: "wrap",
  },
  sidebarCardActions: {
    display: "flex",
    gap: 4,
    alignItems: "center",
    justifyContent: "flex-end",
  },
  sidebarIconButton: {
    border: "1px solid color-mix(in srgb, var(--border) 76%, white)",
    width: 28,
    height: 28,
    padding: 0,
    background: "color-mix(in srgb, white 72%, var(--surface))",
    color: "var(--ink)",
    cursor: "pointer",
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
    flexShrink: 0,
  },
  sidebarIconButtonPrimary: {
    border: "none",
    background: "var(--accent)",
    color: "white",
  },
  cardSummaryGrid: {
    display: "grid",
    gridTemplateColumns: "repeat(3, minmax(0, 1fr))",
    gap: 10,
  },
  cardSummaryItem: {
    border: "1px solid var(--border)",
    background: "color-mix(in srgb, white 98%, var(--panel))",
    padding: "10px 12px",
    display: "grid",
    gap: 4,
  },
  cardSummaryValue: {
    fontSize: 18,
    fontWeight: 700,
    color: "var(--ink)",
  },
  cardSummaryLabel: {
    fontSize: 11,
    color: "var(--muted)",
    textTransform: "uppercase",
    letterSpacing: "0.06em",
  },
  cardList: {
    display: "grid",
    gap: 6,
  },
  personaSlotLibraryCard: {
    border: "1px solid var(--border)",
    background: "transparent",
    padding: 10,
    display: "grid",
    gap: 6,
    cursor: "pointer",
    transition: "transform 160ms ease, box-shadow 160ms ease, opacity 160ms ease, border-color 160ms ease, background 160ms ease",
  },
  personaSlotLibraryCardSelected: {
    border: "1px solid var(--accent)",
    background: "color-mix(in srgb, white 92%, var(--accent-soft))",
  },
  personaSlotLibraryCardDragging: {
    opacity: 0.7,
    transform: "scale(0.99)",
  },
  personaLibraryCard: {
    border: "1px solid var(--border)",
    background: "transparent",
    padding: 10,
    display: "grid",
    gap: 6,
  },
  personaLibraryCardSelected: {
    border: "1px solid var(--accent)",
    background: "color-mix(in srgb, white 94%, var(--accent-soft))",
  },
  libraryCardHeader: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 8,
    flexWrap: "wrap",
  },
  libraryCardTitleRow: {
    display: "inline-flex",
    alignItems: "center",
    gap: 8,
    minWidth: 0,
  },
  libraryCardDragHandle: {
    border: "1px solid var(--border)",
    background: "var(--panel)",
    color: "var(--ink)",
    width: 30,
    height: 30,
    cursor: "grab",
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
    flex: "0 0 auto",
  },
  libraryCardTitle: {
    fontSize: 13,
    fontWeight: 700,
    color: "var(--ink)",
    minWidth: 0,
  },
  libraryCardBadge: {
    padding: 0,
    fontSize: 11,
    color: "var(--muted)",
  },
  libraryCardMetaRow: {
    display: "flex",
    gap: 6,
    flexWrap: "wrap",
    fontSize: 11,
    color: "var(--muted)",
  },
  libraryCardContent: {
    margin: 0,
    fontSize: 13,
    lineHeight: 1.7,
    color: "var(--ink)",
  },
  libraryCardNote: {
    margin: 0,
    fontSize: 12,
    lineHeight: 1.6,
    color: "var(--muted)",
  },

  /* Asset info card */
  assetCard: {
    border: "1px solid var(--border)",
    background: "transparent",
    padding: "10px",
    display: "grid",
    gap: 6,
  },
  generatedResultCard: {
    display: "grid",
    gap: 4,
    paddingTop: 8,
    border: "none",
    borderTop: "1px solid color-mix(in srgb, var(--border) 68%, white)",
    background: "transparent",
  },
  generatedResultTitle: {
    fontSize: 13,
    color: "var(--ink)",
  },
  generatedResultSummary: {
    margin: 0,
    fontSize: 12,
    lineHeight: 1.5,
    color: "var(--muted)",
  },
  generatedResultMeta: {
    margin: 0,
    fontSize: 11,
    lineHeight: 1.4,
    color: "var(--muted)",
  },
  assetRow: {
    display: "grid",
    gridTemplateColumns: "80px 1fr",
    gap: 8,
    fontSize: 12,
    wordBreak: "break-all",
  },
  assetLabel: { color: "var(--muted)" },

  /* Chat reply */
  chatReply: {
    padding: "10px 12px",
    border: "1px solid var(--border)",
    background: "var(--panel)",
    fontSize: 13,
    lineHeight: 1.6,
    color: "var(--ink)",
  },

  /* Text helpers */
  mutedText: { fontSize: 12, color: "var(--muted)" },
  hiddenInput: { display: "none" },

  /* Error states */
  errorBanner: {
    border: "1px solid color-mix(in srgb, var(--negative) 40%, transparent)",
    background: "color-mix(in srgb, var(--negative) 8%, white)",
    color: "var(--negative)",
    padding: "10px 12px",
    marginBottom: 14,
    fontSize: 13,
  },
  errorText: { fontSize: 12, color: "var(--negative)", lineHeight: 1.5, margin: 0 },
  errorInline: { color: "var(--negative)", fontSize: 12 },
};
