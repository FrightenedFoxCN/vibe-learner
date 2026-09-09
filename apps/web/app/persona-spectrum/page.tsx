"use client";

import {
  Fragment,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ChangeEvent,
  type DragEvent as ReactDragEvent,
  type SetStateAction,
} from "react";
import type { CSSProperties } from "react";
import {
  PERSONA_SLOT_KIND_LABELS,
  PERSONA_SLOT_KINDS,
  type CreatePersonaInput,
  type PersonaCard,
  type ModelRecovery,
  type PersonaProfile,
  type PersonaSlot,
  type PersonaSlotKind,
  renderPersonaRuntimeInstruction,
} from "@vibe-learner/shared";

import { exportJson } from "../../lib/export-json";
import { TopNav } from "../../components/top-nav";
import { MaterialIcon, type MaterialIconName } from "../../components/material-icon";
import { usePageDebugSnapshot } from "../../components/page-debug-context";
import { ModelFallbackNotice } from "../../components/model-fallback-notice";
import { ProviderTruth } from "../../components/provider-truth";
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
import {
  applyAsyncResult,
  AsyncResultFence,
  type AsyncResultScope,
} from "../../lib/async-result-fence";
import { isApiHttpError } from "../../lib/http-error";
import {
  clampPersonaWeight,
  clearPersonaDraftForGeneratedBackfill,
  createPersonaInputToDraft,
  draftToCreatePersonaInput,
  duplicatePersonaDraft,
  EMPTY_PERSONA_DRAFT,
  mergePersonaAssistSlots,
  mergeReferenceHints,
  normalizeImportedPersonaConfig,
  personaDraftFingerprint,
  personaToDraft,
  type PersonaDraft,
} from "../../lib/persona-draft";

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

interface GeneratedPersonaMeta {
  summary: string;
  relationship: string;
  learnerAddress: string;
}

type CardGenerationMode = "keywords" | "long_text";

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
  const configImportInputRef = useRef<HTMLInputElement>(null);
  const [personas, setPersonas] = useState<PersonaProfile[]>([]);
  const [selectedPersonaId, setSelectedPersonaId] = useState("");
  const selectedPersonaIdRef = useRef("");
  const draftRevisionRef = useRef(0);
  const assistFenceRef = useRef(new AsyncResultFence());
  const cardGenerationFenceRef = useRef(new AsyncResultFence());
  const configImportFenceRef = useRef(new AsyncResultFence());
  const saveFenceRef = useRef(new AsyncResultFence());
  const reloadFenceRef = useRef(new AsyncResultFence());

  const [draft, setDraft] = useState<PersonaDraft>(EMPTY_PERSONA_DRAFT);
  const [draftBaselineFingerprint, setDraftBaselineFingerprint] = useState(
    personaDraftFingerprint(EMPTY_PERSONA_DRAFT),
  );
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
  const [clearBeforeBackfill, setClearBeforeBackfill] = useState(false);
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
      assistFenceRef.current.invalidate();
      cardGenerationFenceRef.current.invalidate();
      reloadFenceRef.current.invalidate();
      setAssistPending(false);
      setSlotAssistIndex(null);
      setCardActionPending(null);
      setGeneratedCards([]);
      setGeneratedPersonaMeta({
        summary: "",
        relationship: "",
        learnerAddress: "",
      });
      setCardMessage("");
      setCardError("");
      setCardModelRecoveries([]);
    }
    selectedPersonaIdRef.current = normalizedPersonaId;
    setSelectedPersonaId(normalizedPersonaId);
  }

  function confirmDiscardPersonaDraft(action: string): boolean {
    if (!isDraftDirty) {
      return true;
    }
    return window.confirm(`当前人格有未保存修改。${action}会丢弃这些修改，是否继续？`);
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
    dismissSystemPromptSuggestion();
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
      if (!window.confirm("当前人格有未保存修改。离开页面会丢弃这些修改，是否继续？")) {
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
        setPersonas(personaList);
        const initialPersona = personaList[0];
        if (initialPersona && !selectedPersonaIdRef.current) {
          selectPersonaDraft(initialPersona.id);
          replacePersonaDraft(personaToDraft(initialPersona), true);
        }
      } else {
        setLoadError(String(personaResult.reason));
      }
      if (cardResult.status === "fulfilled") {
        setPersonaCards(cardResult.value);
      } else {
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
    if (assistError) setAssistError("");
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

  async function handleAssistSlot(index: number) {
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
      const result = await assistPersonaSlot({
        name: draft.name.trim(),
        summary: draft.summary.trim(),
        slot: targetSlot,
        rewriteStrength: Number((1 - retainRatio).toFixed(2))
      });
      if (assistFenceRef.current.decide(ticket, currentPersonaAsyncScope(fieldTarget)) !== "apply") {
        return;
      }
      updatePersonaDraft((prev) => {
        const next = [...prev.slots];
        next[index] = result.slot;
        return { ...prev, slots: next };
      });
      setAssistModelRecoveries(result.modelRecoveries ?? []);
    } catch (error) {
      if (assistFenceRef.current.decide(ticket, currentPersonaAsyncScope(fieldTarget)) === "apply") {
        setAssistError(String(error));
      }
    } finally {
      if (assistFenceRef.current.settle(ticket)) {
        setSlotAssistIndex(null);
      }
    }
  }

  async function handleAssistSetting() {
    setAssistError("");
    setAssistModelRecoveries([]);
    setSlotAssistIndex(null);
    setAssistPending(true);
    setIsRewritePopoverOpen(false);
    const fieldTarget = "persona-setting";
    const ticket = assistFenceRef.current.begin(currentPersonaAsyncScope(fieldTarget));
    try {
      const result = await assistPersonaSetting({
        name: draft.name.trim(),
        summary: draft.summary.trim(),
        slots: draft.slots,
        rewriteStrength: Number((1 - retainRatio).toFixed(2))
      });
      if (assistFenceRef.current.decide(ticket, currentPersonaAsyncScope(fieldTarget)) !== "apply") {
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
      if (assistFenceRef.current.decide(ticket, currentPersonaAsyncScope(fieldTarget)) === "apply") {
        setAssistError(String(error));
      }
    } finally {
      if (assistFenceRef.current.settle(ticket)) {
        setAssistPending(false);
      }
    }
  }

  async function handleCreatePersona() {
    setConfigError(""); setConfigMessage(""); setSaveError("");
    const payload = draftToCreatePersonaInput(draft);
    if (!payload.name) { setSaveError("请先填写人格名称。"); return; }
    const saveScope = currentPersonaAsyncScope("persona-save");
    const ticket = saveFenceRef.current.begin(saveScope);
    setSavingPersona(true);
    try {
      const created = await createPersona(payload);
      mergePersonaIntoList(created);
      broadcastPersonaLibraryUpdated();
      const decision = saveFenceRef.current.decide(
        ticket,
        currentPersonaAsyncScope("persona-save"),
      );
      if (decision === "apply") {
        selectPersonaDraft(created.id);
        replacePersonaDraft(personaToDraft(created), true);
        dismissSystemPromptSuggestion();
      } else if (selectedPersonaIdRef.current === "") {
        // The create committed, but the user kept editing the same new draft.
        // Bind that draft to the new record without replacing the newer edits.
        selectPersonaDraft(created.id);
        setDraftBaselineFingerprint(personaDraftFingerprint(personaToDraft(created)));
      }
      setPersonaLibraryMessage(`已创建人格「${created.name}」。`);
      setPersonaLibraryError("");
      try {
        setPersonas(await listPersonas());
      } catch (refreshError) {
        setPersonaLibraryMessage(
          `已创建人格「${created.name}」，但人格库刷新失败：${String(refreshError)}`,
        );
      }
    } catch (error) {
      setSaveError(humanizePersonaSaveError(error));
    } finally {
      saveFenceRef.current.settle(ticket);
      setSavingPersona(false);
    }
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
    setDraftBaselineFingerprint(personaDraftFingerprint(EMPTY_PERSONA_DRAFT));
    updatePersonaDraft(duplicated);
    dismissSystemPromptSuggestion();
    setPersonaLibraryMessage(`已复制为新草稿「${duplicated.name}」，保存后创建新人格。`);
  }

  async function handleReloadSelectedPersona() {
    if (!selectedPersonaId) {
      return;
    }
    if (!confirmDiscardPersonaDraft("重新载入人格")) {
      return;
    }
    setLoadError("");
    const targetPersonaId = selectedPersonaIdRef.current;
    const reloadScope = currentPersonaAsyncScope("persona-reload");
    const ticket = reloadFenceRef.current.begin(reloadScope);
    try {
      const latest = await listPersonas();
      setPersonas(latest);
      const decision = reloadFenceRef.current.decide(
        ticket,
        currentPersonaAsyncScope("persona-reload"),
      );
      if (decision !== "apply") {
        setPersonaLibraryMessage("人格库已刷新，期间的编辑已保留。");
        return;
      }
      const reloaded = latest.find((persona) => persona.id === targetPersonaId);
      if (!reloaded) {
        setLoadError("当前人格已不存在，请选择其他人格。");
        return;
      }
      replacePersonaDraft(personaToDraft(reloaded), true);
      dismissSystemPromptSuggestion();
      setPersonaLibraryMessage(`已重新载入人格「${reloaded.name}」。`);
    } catch (error) {
      setLoadError(String(error));
    } finally {
      reloadFenceRef.current.settle(ticket);
    }
  }

  async function handleUpdatePersona() {
    setConfigError(""); setConfigMessage("");
    if (!selectedPersonaId) { setSaveError("请先选择要更新的人格。"); return; }
    if (isReadonlyPersona) { setSaveError("内置人格为只读，无法更新。请使用「创建新人格」另存。"); return; }
    setSaveError("");
    const payload = draftToCreatePersonaInput(draft);
    if (!payload.name) { setSaveError("请先填写人格名称。"); return; }
    if (!selectedPersona) { setSaveError("当前人格不存在，请刷新人格库后重试。"); return; }
    const targetPersonaId = selectedPersona.id;
    const saveScope = currentPersonaAsyncScope("persona-save");
    const ticket = saveFenceRef.current.begin(saveScope);
    setSavingPersona(true);
    try {
      const updated = await updatePersona(targetPersonaId, {
        ...payload,
        expectedRevision: selectedPersona.revision,
      });
      mergePersonaIntoList(updated);
      broadcastPersonaLibraryUpdated();
      const decision = saveFenceRef.current.decide(
        ticket,
        currentPersonaAsyncScope("persona-save"),
      );
      if (decision === "apply") {
        replacePersonaDraft(personaToDraft(updated), true);
        dismissSystemPromptSuggestion();
      } else if (selectedPersonaIdRef.current === updated.id) {
        // Preserve edits made while PATCH was in flight, but advance the
        // comparison baseline to the exact committed response.
        setDraftBaselineFingerprint(personaDraftFingerprint(personaToDraft(updated)));
      }
      setPersonaLibraryMessage(`已更新人格「${updated.name}」。`);
      setPersonaLibraryError("");
      try {
        setPersonas(await listPersonas());
      } catch (refreshError) {
        setPersonaLibraryMessage(
          `已更新人格「${updated.name}」，但人格库刷新失败：${String(refreshError)}`,
        );
      }
    } catch (error) {
      setSaveError(humanizePersonaSaveError(error));
    } finally {
      saveFenceRef.current.settle(ticket);
      setSavingPersona(false);
    }
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
      if (file.size > 8 * 1024 * 1024) throw new Error("persona_import_file_too_large");
      const raw = await file.text();
      const parsed = JSON.parse(raw) as Record<string, unknown>;
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

  function applyGeneratedCardsToDraft() {
    if (!generatedCards.length && !generatedPersonaMeta.summary && !generatedPersonaMeta.relationship && !generatedPersonaMeta.learnerAddress) {
      setCardError("当前没有可回填的生成人格内容。");
      return;
    }
    if (
      clearBeforeBackfill &&
      !window.confirm("应用后会清空现有摘要、关系、称呼、参考提示和全部插槽。是否继续？")
    ) {
      return;
    }
    setCardError("");
    setCardMessage("");
    const baseDraft = clearBeforeBackfill
      ? clearPersonaDraftForGeneratedBackfill(draft)
      : draft;
    const insertion = buildDraftWithInsertedCards(baseDraft, generatedCards);
    updatePersonaDraft({
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
      clearBeforeBackfill ? "已清空摘要、关系、称呼、参考提示和全部插槽" : "",
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
    updatePersonaDraft({
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
    const requestScope = currentPersonaAsyncScope("persona-card-candidate");
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
      if (!Number.isInteger(parsedCount) || parsedCount < 1 || parsedCount > 24) {
        setCardError("精确卡片数量必须是 1 到 24 的整数，或留空交给模型决定。");
        return;
      }
      count = parsedCount;
    }
    setCardError("");
    setCardMessage("");
    setCardModelRecoveries([]);
    setCardActionPending(mode === "keywords" ? "generate_keywords" : "generate_long_text");
    const ticket = cardGenerationFenceRef.current.begin(requestScope);
    if (
      cardGenerationFenceRef.current.decide(
        ticket,
        currentPersonaAsyncScope("persona-card-candidate"),
      ) !== "apply"
    ) {
      cardGenerationFenceRef.current.settle(ticket);
      setCardActionPending(null);
      return;
    }
    try {
      const result = await generatePersonaCards({
        mode,
        inputText,
        count,
      });
      if (
        cardGenerationFenceRef.current.decide(
          ticket,
          currentPersonaAsyncScope("persona-card-candidate"),
        ) !== "apply"
      ) {
        return;
      }
      setGeneratedCards(result.items);
      setGeneratedPersonaMeta({
        summary: result.summary,
        relationship: result.relationship,
        learnerAddress: result.learnerAddress,
      });
      setCardModelRecoveries(result.modelRecoveries ?? []);
      setCardMessage(
        `已生成 ${result.items.length} 张卡片。${
          result.usedWebSearch
            ? "已使用联网搜索。"
            : result.usedModel === "mock"
              ? "本地模拟结果。"
              : ""
        }`
      );
    } catch (error) {
      if (
        cardGenerationFenceRef.current.decide(
          ticket,
          currentPersonaAsyncScope("persona-card-candidate"),
        ) === "apply"
      ) {
        setCardError(humanizePersonaCardGenerationError(error));
      }
    } finally {
      if (cardGenerationFenceRef.current.settle(ticket)) {
        setCardActionPending(null);
      }
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
    const dirtyWarning = selectedPersonaId === persona.id && isDraftDirty
      ? " 当前草稿的未保存修改也会丢失。"
      : "";
    if (!window.confirm(`确认删除人格「${persona.name}」？${dirtyWarning}`)) {
      return;
    }
    setPersonaDeletePendingId(persona.id);
    try {
      await deletePersona(persona.id, persona.revision);
      let latest = personas.filter((item) => item.id !== persona.id);
      let refreshFailed = false;
      try {
        latest = await listPersonas();
      } catch (refreshError) {
        refreshFailed = true;
        setPersonaLibraryMessage(
          `已删除人格「${persona.name}」，但人格库刷新失败：${String(refreshError)}`,
        );
      }
      setPersonas(latest);
      broadcastPersonaLibraryUpdated();
      if (
        selectedPersonaId === persona.id ||
        !latest.some((item) => item.id === selectedPersonaId)
      ) {
        const nextSelectedPersona = latest[0] ?? null;
        selectPersonaDraft(nextSelectedPersona?.id ?? "");
        replacePersonaDraft(
          nextSelectedPersona ? personaToDraft(nextSelectedPersona) : { ...EMPTY_PERSONA_DRAFT },
          true,
        );
        dismissSystemPromptSuggestion();
      }
      if (!refreshFailed) {
        setPersonaLibraryMessage(`已删除人格「${persona.name}」。`);
      }
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
            <MaterialIcon name="input" size={16} />
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
            <MaterialIcon name={cardDeletePendingId === card.id ? "hourglass_top" : "delete"} size={16} />
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
              if (!activatePersonaDraft(persona.id, `载入人格「${persona.name}」`)) {
                return;
              }
              setPersonaLibraryError("");
              setPersonaLibraryMessage(`已载入人格「${persona.name}」。`);
            }}
            title={isSelected ? "编辑中" : "载入"}
            aria-label={isSelected ? "编辑中" : "载入"}
          >
            <MaterialIcon name={isSelected ? "check_circle" : "file_open"} size={16} />
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
              <MaterialIcon name={personaDeletePendingId === persona.id ? "hourglass_top" : "delete"} size={16} />
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
          <ProviderTruth scope="persona" />
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
                      <MaterialIcon name={assistPending ? "hourglass_top" : "auto_awesome"} size={16} />
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
                          onChange={(e) => updatePersonaAssistInput(() => setRetainRatio(Number(e.target.value)))}
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
                    onClick={handleNewPersonaDraft}
                    title={savingPersona ? "保存中" : "新建人格草稿"}
                    aria-label={savingPersona ? "保存中" : "新建人格草稿"}
                  >
                    <MaterialIcon name="add_circle" size={18} />
                  </button>
                  <button
                    type="button"
                    style={{ ...styles.basicIconButton, ...(!selectedPersona || savingPersona ? styles.basicIconButtonDisabled : {}) }}
                    disabled={!selectedPersona || savingPersona}
                    onClick={handleDuplicatePersonaDraft}
                    title={savingPersona ? "保存中" : "复制为新人格"}
                    aria-label={savingPersona ? "保存中" : "复制为新人格"}
                  >
                    <MaterialIcon name="library_add" size={16} />
                  </button>
                  <button
                    type="button"
                    style={{ ...styles.basicIconButton, ...(!selectedPersona || savingPersona ? styles.basicIconButtonDisabled : {}) }}
                    disabled={!selectedPersona || savingPersona}
                    onClick={() => { void handleReloadSelectedPersona(); }}
                    title={savingPersona ? "保存中" : "重新载入人格"}
                    aria-label={savingPersona ? "保存中" : "重新载入人格"}
                  >
                    <MaterialIcon name="refresh" size={16} />
                  </button>
                  <button
                    type="button"
                    style={{ ...styles.basicIconButton, ...(savingPersona || isReadonlyPersona ? styles.basicIconButtonDisabled : {}) }}
                    disabled={savingPersona || isReadonlyPersona}
                    onClick={() => void (selectedPersonaId ? handleUpdatePersona() : handleCreatePersona())}
                    title={savingPersona ? "保存中" : selectedPersonaId ? "更新人格" : "创建人格"}
                    aria-label={savingPersona ? "保存中" : selectedPersonaId ? "更新人格" : "创建人格"}
                  >
                    <MaterialIcon name="save" size={16} />
                  </button>
                </div>
              </div>
              <section style={styles.basicPaneCard}>
                <div style={styles.basicPanePrimarySection}>
                <div style={styles.fieldGroup}>
                <label style={styles.fieldLabel}>人格</label>
                <select
                  style={styles.select}
                  value={selectedPersonaId}
                  onChange={(event) => {
                    void activatePersonaDraft(event.target.value);
                  }}
                >
                  <option value="">新建人格（未保存）</option>
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

              <ModelFallbackNotice recoveries={assistModelRecoveries} />
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
                  <button type="button" style={styles.ghostBtn} onClick={() => configImportInputRef.current?.click()}>导入配置</button>
                  <input ref={configImportInputRef} type="file" accept="application/json,.json" style={styles.hiddenInput} onChange={handleImportConfig} />
                </div>
                {saveError ? <span style={styles.errorInline}>{saveError}</span> : null}
                {isReadonlyPersona ? (
                  <span style={styles.mutedText}>内置人格只读；点击复制按钮可保留当前设定并另存为新人格。</span>
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
                              {!PERSONA_SLOT_KINDS.some((kind) => kind === slot.kind) ? (
                                <option value={slot.kind}>{slot.label || slot.kind}（自定义）</option>
                              ) : null}
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
                                <MaterialIcon name={slotAssistIndex === index ? "hourglass_top" : "auto_awesome"} size={15} />
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
                  <span style={styles.fieldLabel}>精确卡片数量（可选）</span>
                  <input
                    style={styles.input}
                    type="number"
                    min={1}
                    max={24}
                    step={1}
                    value={cardGenerateCount}
                    onChange={(e) => updatePersonaAssistInput(() => setCardGenerateCount(e.target.value))}
                    placeholder="留空由模型决定，填写后精确生成 1–24 张"
                  />
                </label>
                <label style={styles.checkboxRow}>
                  <input
                    type="checkbox"
                    checked={clearBeforeBackfill}
                    onChange={(event) => setClearBeforeBackfill(event.target.checked)}
                  />
                  <span style={styles.checkboxLabel}>应用前清空摘要、关系、称呼、参考提示和全部插槽</span>
                </label>
                <div style={styles.modeSwitchRow}>
                  <div style={styles.modeSwitch}>
                    <button
                      type="button"
                      style={cardGenerationMode === "keywords" ? styles.modeSwitchButtonActive : styles.modeSwitchButton}
                      onClick={() => updatePersonaAssistInput(() => setCardGenerationMode("keywords"))}
                    >
                      关键词搜索
                    </button>
                    <button
                      type="button"
                      style={cardGenerationMode === "long_text" ? styles.modeSwitchButtonActive : styles.modeSwitchButton}
                      onClick={() => updatePersonaAssistInput(() => setCardGenerationMode("long_text"))}
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
                          ? (cardActionPending === "generate_keywords" ? "hourglass_top" : "auto_awesome")
                          : (cardActionPending === "generate_long_text" ? "hourglass_top" : "description")
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
                      onChange={(e) => updatePersonaAssistInput(() => setCardKeywordInput(e.target.value))}
                      placeholder="例如：冷静学术、学院派导师、侦探式推理"
                    />
                  </label>
                ) : (
                  <label key="long-text-mode" style={styles.fieldGroup}>
                    <input
                      type="file"
                      accept=".txt,.md,text/plain,text/markdown"
                      style={styles.fileInput}
                      onChange={(event) => updatePersonaAssistInput(() => setCardLongTextFile(event.target.files?.[0] ?? null))}
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
                    {generatedCards.length ? (
                      <ul style={styles.generatedCardPreviewList}>
                        {generatedCards.map((card) => (
                          <li key={card.id} style={styles.generatedCardPreviewItem}>
                            <strong>{card.title}</strong>
                            <span>{card.label}：{card.content}</span>
                          </li>
                        ))}
                      </ul>
                    ) : null}
                    <div style={styles.sidebarActionRow}>
                      <button
                        style={styles.sidebarIconButton}
                        type="button"
                        disabled={!(generatedCards.length || generatedPersonaMeta.summary || generatedPersonaMeta.relationship || generatedPersonaMeta.learnerAddress)}
                        onClick={applyGeneratedCardsToDraft}
                        title="应用到当前编辑区"
                        aria-label="应用到当前编辑区"
                      >
                        <MaterialIcon name="input" size={14} />
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

/* ─── Helpers ─── */

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
    { key: "tavern_rooms", label: "酒馆房间" },
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

function humanizePersonaSaveError(error: unknown): string {
  if (isApiHttpError(error) && error.code === "persona_revision_conflict") {
    return "人格已在其他窗口更新。当前草稿已保留，请重新载入最新人格后再合并保存。";
  }
  if (isApiHttpError(error) && error.status === 422) {
    return "人格内容未通过校验，请检查名称、插槽权重和排序。";
  }
  return String(error).replace(/^Error:\s*/, "");
}

function humanizePersonaCardGenerationError(error: unknown): string {
  if (!isApiHttpError(error)) {
    return "人格卡片生成失败，请稍后重试。";
  }
  const code = error.code || error.message;
  if (code === "setting_persona_card_count_mismatch") {
    return "模型返回的卡片数量不符合精确数量要求，请重试或调整数量。";
  }
  if (code === "keyword_generation_requires_openai") {
    return "当前提供器暂不支持关键词生成，请切换提供器或使用长文本提取。";
  }
  if (error.status === 422) {
    return "生成条件未通过校验，请检查关键词和精确卡片数量。";
  }
  return "人格卡片生成失败，请稍后重试。";
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
  generatedCardPreviewList: {
    margin: 0,
    padding: "4px 0 0 18px",
    display: "grid",
    gap: 6,
    maxHeight: 180,
    overflowY: "auto",
  },
  generatedCardPreviewItem: {
    display: "grid",
    gap: 2,
    fontSize: 11,
    lineHeight: 1.45,
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
