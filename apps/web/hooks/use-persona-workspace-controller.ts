"use client";

import { useEffect, useMemo, useRef, useState, type ChangeEvent, type DragEvent as ReactDragEvent } from "react";
import { PERSONA_SLOT_KIND_LABELS, type CreatePersonaInput, type PersonaProfile, type PersonaSlot, type PersonaSlotKind, renderPersonaRuntimeInstruction } from "@vibe-learner/shared";
import { readBoundedJsonImport } from "../lib/bounded-json-import";
import { exportJson } from "../lib/export-json";
import { usePageDebugSnapshot } from "../components/page-debug-context";
import { usePersonaPersistence } from "./use-persona-persistence";
import { usePersonaLibrary } from "./use-persona-library";
import { applyAsyncResult, AsyncResultFence } from "../lib/async-result-fence";
import { usePersonaAssist } from "./use-persona-assist";
import { usePersonaDraft } from "./use-persona-draft";
import { usePersonaCardGeneration } from "./use-persona-card-generation";
import { matchesPersonaCard, matchesPersonaProfile } from "../lib/persona-editor-model";
import { clampPersonaWeight, createPersonaInputToDraft, draftToCreatePersonaInput, duplicatePersonaDraft, EMPTY_PERSONA_DRAFT, normalizeImportedPersonaConfig, type PersonaDraft } from "../lib/persona-draft";

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

export function usePersonaWorkspaceController() {
  const configImportInputRef = useRef<HTMLInputElement>(null);
  const personaLibrary = usePersonaLibrary();
  const { personas, personaCards, listPersonas, listPersonaCards, deletePersonaCard } = personaLibrary;
  const configImportFenceRef = useRef(new AsyncResultFence());
  const cardDeleteOwnerRef = useRef<object | null>(null);
  useEffect(() => () => {
    configImportFenceRef.current.invalidate();
    cardDeleteOwnerRef.current = null;
  }, []);

  const personaEditor = usePersonaDraft({
    personas,
    onSelectionChange: () => {
      resetPersonaAssist();
      resetCardGeneration();
    },
    onPromptDismiss: () => dismissSystemPromptSuggestion(),
  });
  const {
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
  } = personaEditor;

  const {
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
  } = usePersonaAssist({ draft, updatePersonaDraft, currentPersonaAsyncScope, onSettingStarted: () => setIsRewritePopoverOpen(false) });
  const [configMessage, setConfigMessage] = useState("");
  const [configError, setConfigError] = useState("");
  const {
    generatedCards,
    cardGenerationMode,
    setCardGenerationMode,
    cardKeywordInput,
    setCardKeywordInput,
    cardLongTextFile,
    setCardLongTextFile,
    cardGenerateCount,
    setCardGenerateCount,
    clearBeforeBackfill,
    setClearBeforeBackfill,
    cardActionPending,
    cardMessage,
    setCardMessage,
    cardError,
    setCardError,
    cardModelRecoveries,
    generatedPersonaMeta,
    applyGeneratedCardsToDraft,
    insertCardsIntoDraft,
    handleGenerateCards,
    resetCardGeneration,
  } = usePersonaCardGeneration({ draft, updatePersonaDraft, currentPersonaAsyncScope });
  const [cardSearchQuery, setCardSearchQuery] = useState("");
  const [cardDeletePendingId, setCardDeletePendingId] = useState("");
  const [draggingPersonaCardId, setDraggingPersonaCardId] = useState("");
  const [slotInsertIndex, setSlotInsertIndex] = useState<number | null>(null);
  const [draggingSlotIndex, setDraggingSlotIndex] = useState<number | null>(null);
  const [expandedSlotIndex, setExpandedSlotIndex] = useState<number | null>(null);
  const [movePulse, setMovePulse] = useState<{ index: number; direction: -1 | 1 } | null>(null);

  const [isCompactLayout, setIsCompactLayout] = useState(false);
  const [isRewritePopoverOpen, setIsRewritePopoverOpen] = useState(false);
  const [isSystemPromptExpanded, setIsSystemPromptExpanded] = useState(false);
  const [collapsedSidebarSections, setCollapsedSidebarSections] = useState<string[]>([]);
  const [personaLibraryQuery, setPersonaLibraryQuery] = useState("");
  const {
    savingPersona, saveError, setSaveError, loadError, setLoadError,
    personaDeletePendingId, personaLibraryMessage, setPersonaLibraryMessage, personaLibraryError, setPersonaLibraryError,
    handleCreatePersona, handleUpdatePersona, handleReloadSelectedPersona, handleDeletePersona,
  } = usePersonaPersistence({
    editor: personaEditor, library: personaLibrary,
    onStarted: () => { setConfigError(""); setConfigMessage(""); },
    onPromptDismiss: () => dismissSystemPromptSuggestion(),
  });
  const rewritePopoverRef = useRef<HTMLDivElement | null>(null);
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
      const [personaResult, cardResult] = await Promise.allSettled([
        listPersonas(),
        listPersonaCards(),
      ]);
      if (cancelled) {
        return;
      }
      if (personaResult.status === "fulfilled") {
        const personaList = personaResult.value;
        initializePersonaFromLibrary(personaList[0]);
      } else {
        setLoadError(String(personaResult.reason));
      }
      if (cardResult.status === "rejected") {
        setCardError(`人格卡片库加载失败：${String(cardResult.reason)}`);
      }
    }
    void bootstrap();
    return () => { cancelled = true; };
  }, []);

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
      const dirtySuffix = isDraftDirty ? " · 有未保存修改" : "";
      return isReadonlyPersona
        ? `当前编辑 · ${selectedPersona.name} · 内置只读${dirtySuffix}`
        : `当前编辑 · ${selectedPersona.name}${dirtySuffix}`;
    }
    return isDraftDirty
      ? "新建人格草稿 · 有未保存修改"
      : "新建人格草稿 — 填写名称后保存即可创建";
  }, [
    assistPending,
    cardActionPending,
    isDraftDirty,
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
        { label: "未保存修改", value: isDraftDirty ? "有" : "无" },
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
      isDraftDirty,
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

  function updateDraft<K extends keyof PersonaDraft>(key: K, value: PersonaDraft[K]) {
    if (assistError) clearAssistError();
    updatePersonaDraft((prev) => ({ ...prev, [key]: value }));
  }

  function handleAddSlot(kind: PersonaSlotKind | string) {
    const label = PERSONA_SLOT_KIND_LABELS[kind as PersonaSlotKind] ?? kind;
    updatePersonaDraft((prev) => ({
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
    updatePersonaDraft((prev) => ({ ...prev, slots: [] }));
    setExpandedSlotIndex(null);
    setDraggingSlotIndex(null);
    setSlotInsertIndex(null);
  }

  function handleUpdateSlot(index: number, field: keyof PersonaSlot, value: PersonaSlot[keyof PersonaSlot]) {
    if (assistError) clearAssistError();
    updatePersonaDraft((prev) => {
      const next = [...prev.slots];
      let nextValue = value;
      if (field === "weight") {
        nextValue = clampPersonaWeight(Number(value));
      }
      next[index] = { ...next[index], [field]: nextValue };
      if (field === "kind") next[index].label = PERSONA_SLOT_KIND_LABELS[value as PersonaSlotKind] ?? value;
      return { ...prev, slots: next };
    });
  }

  function handleRemoveSlot(index: number) {
    updatePersonaDraft((prev) => ({ ...prev, slots: prev.slots.filter((_, i) => i !== index) }));
  }

  function handleMoveSlot(index: number, direction: -1 | 1) {
    const target = index + direction;
    if (target < 0 || target >= draft.slots.length) {
      return;
    }
    updatePersonaDraft((prev) => {
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
    updatePersonaDraft((prev) => ({
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
    updatePersonaDraft((prev) => {
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

  function handleNewPersonaDraft() {
    if (!confirmDiscardPersonaDraft("新建空白人格")) {
      return;
    }
    setConfigError("");
    setConfigMessage("");
    setSaveError("");
    setPersonaLibraryError("");
    selectPersonaDraft("");
    replacePersonaDraft({ ...EMPTY_PERSONA_DRAFT }, true);
    dismissSystemPromptSuggestion();
    setPersonaLibraryMessage("已新建人格草稿。填写名称后保存即可创建。");
  }

  function handleDuplicatePersonaDraft() {
    const duplicated = duplicatePersonaDraft(draft);
    setConfigError("");
    setConfigMessage("");
    setSaveError("");
    setPersonaLibraryError("");
    selectPersonaDraft("");
    markPersonaDraftSaved(EMPTY_PERSONA_DRAFT);
    replacePersonaDraft(duplicated, false);
    dismissSystemPromptSuggestion();
    setPersonaLibraryMessage(`已复制为新草稿「${duplicated.name}」，保存后创建新人格。`);
  }

  async function handleExportConfig() {
    setConfigError(""); setConfigMessage("");
    try {
      const payload = draftToCreatePersonaInput(draft);
      const baseName = (payload.name || "persona-config").trim().toLowerCase().replace(/\s+/g, "-");
      const saved = await exportJson(`${baseName || "persona-config"}.json`, payload);
      setConfigMessage(saved ? "已导出当前配置。" : "已取消导出。");
    } catch {
      setConfigError("导出失败，请检查保存位置后重试。");
    }
  }

  async function handleDownloadTemplate() {
    setConfigError(""); setConfigMessage("");
    try {
      const saved = await exportJson("persona-config-template.json", DEFAULT_CONFIG_TEMPLATE);
      setConfigMessage(saved ? "已下载配置模板，可直接导入后编辑。" : "已取消下载。");
    } catch {
      setConfigError("模板下载失败，请检查保存位置后重试。");
    }
  }

  async function handleImportConfig(event: ChangeEvent<HTMLInputElement>) {
    setConfigError(""); setConfigMessage("");
    const file = event.target.files?.[0];
    if (!file) return;
    if (
      isDraftDirty &&
      !window.confirm("导入配置会覆盖当前未保存草稿。是否继续？")
    ) {
      event.target.value = "";
      return;
    }
    const fieldTarget = "persona-config-import";
    const ticket = configImportFenceRef.current.begin(
      currentPersonaAsyncScope(fieldTarget),
    );
    try {
      const parsed = await readBoundedJsonImport(file, "persona") as Record<string, unknown>;
      const normalized = normalizeImportedPersonaConfig(parsed);
      const decision = applyAsyncResult({
        fence: configImportFenceRef.current,
        ticket,
        currentScope: currentPersonaAsyncScope(fieldTarget),
        value: createPersonaInputToDraft(normalized),
        apply: updatePersonaDraft,
      });
      if (decision !== "apply") {
        return;
      }
      setConfigMessage("配置导入成功，已应用到当前编辑区。");
    } catch (error) {
      if (
        configImportFenceRef.current.decide(
          ticket,
          currentPersonaAsyncScope(fieldTarget),
        ) === "apply"
      ) {
        setConfigError(`导入失败: ${String(error)}`);
      }
    } finally {
      configImportFenceRef.current.settle(ticket);
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

  async function handleDeletePersonaCard(cardId: string) {
    setCardError("");
    setCardMessage("");
    const owner = {};
    cardDeleteOwnerRef.current = owner;
    setCardDeletePendingId(cardId);
    try {
      await deletePersonaCard(cardId);
    } catch (error) {
      if (cardDeleteOwnerRef.current === owner) setCardError(String(error));
    } finally {
      if (cardDeleteOwnerRef.current === owner) {
        cardDeleteOwnerRef.current = null;
        setCardDeletePendingId("");
      }
    }
  }

  function activateLibraryPersona(persona: PersonaProfile) {
    if (!activatePersonaDraft(persona.id, `载入人格「${persona.name}」`)) return;
    setPersonaLibraryError("");
    setPersonaLibraryMessage(`已载入人格「${persona.name}」。`);
  }

  return {
    activateLibraryPersona,
    configImportInputRef,
    personas,
    selectedPersonaId,
    draft,
    activatePersonaDraft,
    updatePersonaAssistInput,
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
    configMessage,
    configError,
    generatedCards,
    cardGenerationMode,
    setCardGenerationMode,
    cardKeywordInput,
    setCardKeywordInput,
    cardLongTextFile,
    setCardLongTextFile,
    cardGenerateCount,
    setCardGenerateCount,
    clearBeforeBackfill,
    setClearBeforeBackfill,
    cardActionPending,
    cardMessage,
    cardError,
    generatedPersonaMeta,
    applyGeneratedCardsToDraft,
    insertCardsIntoDraft,
    handleGenerateCards,
    cardSearchQuery,
    setCardSearchQuery,
    cardDeletePendingId,
    draggingPersonaCardId,
    slotInsertIndex,
    draggingSlotIndex,
    expandedSlotIndex,
    setExpandedSlotIndex,
    movePulse,
    isCompactLayout,
    isRewritePopoverOpen,
    setIsRewritePopoverOpen,
    isSystemPromptExpanded,
    setIsSystemPromptExpanded,
    collapsedSidebarSections,
    personaLibraryQuery,
    setPersonaLibraryQuery,
    savingPersona,
    saveError,
    loadError,
    personaDeletePendingId,
    personaLibraryMessage,
    personaLibraryError,
    handleCreatePersona,
    handleUpdatePersona,
    handleReloadSelectedPersona,
    handleDeletePersona,
    rewritePopoverRef,
    selectedPersona,
    isReadonlyPersona,
    filteredPersonaCards,
    builtinPersonas,
    userPersonas,
    runtimePromptPreview,
    pageNotice,
    updateDraft,
    handleAddSlot,
    handleClearSlots,
    handleUpdateSlot,
    handleRemoveSlot,
    handleMoveSlot,
    handleSortSlotsByPriority,
    handleDragStart,
    handleSlotInsertDragOver,
    handleSlotCardDragOver,
    handleSlotCardDrop,
    handleSlotInsertDrop,
    handleDragEnd,
    handleNewPersonaDraft,
    handleDuplicatePersonaDraft,
    handleExportConfig,
    handleDownloadTemplate,
    handleImportConfig,
    handlePersonaCardDragStart,
    handlePersonaCardDragEnd,
    toggleSidebarSection,
    handleDeletePersonaCard,
  };
}

export type PersonaWorkspaceController = ReturnType<typeof usePersonaWorkspaceController>;
