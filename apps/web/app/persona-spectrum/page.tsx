"use client";

import {
  Fragment,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ChangeEvent,
  type DragEvent as ReactDragEvent,
  type MouseEvent as ReactMouseEvent
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
  type CreatePersonaCardInput,
  type PersonaCard,
  type PersonaProfile,
  type PersonaSlot,
  type PersonaSlotKind,
  type SpeechStyle
} from "@vibe-learner/shared";

import { TopNav } from "../../components/top-nav";
import {
  assistPersonaSlot,
  assistPersonaSetting,
  createPersona,
  createPersonaCardsBatch,
  deletePersonaCard,
  generatePersonaCards,
  listPersonaCards,
  listPersonas,
  updatePersona,
} from "../../lib/api";

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
  slots: [],
  availableEmotionsText: CHARACTER_EMOTIONS.join(", "),
  availableActionsText: CHARACTER_ACTIONS.join(", "),
  defaultSpeechStyle: "warm"
};

const SLOT_TEMPLATES: Array<{ kind: PersonaSlotKind; text: string }> = [
  { kind: "worldview", text: "你曾在一所强调自学与互助的学院担任导学员，习惯先给学习者稳定感，再推进挑战。" },
  { kind: "past_experiences", text: "曾参与多个跨学科项目，习惯将复杂问题拆解为可验证的小步骤，再带领学习者逐步落地。" },
  { kind: "thinking_style", text: "常用短句确认学习者状态，例如「我们先把这一点站稳」，避免连续高压输出。" },
  { kind: "teaching_method", text: "讲解时遵循「概念-例子-反例-迁移」的节奏，每次只推进一个关键难点。" },
  { kind: "correction_style", text: "纠错优先指出可操作改进，不使用否定人格的措辞；鼓励具体进步，不做空泛夸奨。" }
];

const DEFAULT_CONFIG_TEMPLATE: CreatePersonaInput = {
  name: "模板教师",
  summary: "示例人格：强调章节脉络与可执行反馈。",
  relationship: "标准导学教师",
  learnerAddress: "同学",
  systemPrompt: "优先基于章节内容讲解，通过递进式提问推进理解，并给出简洁可执行的反馈。",
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

export default function PersonaSpectrumPage() {
  const [personas, setPersonas] = useState<PersonaProfile[]>([]);
  const [selectedPersonaId, setSelectedPersonaId] = useState("");

  const [draft, setDraft] = useState<PersonaDraft>(EMPTY_DRAFT);
  const [savingPersona, setSavingPersona] = useState(false);

  const [loadError, setLoadError] = useState("");
  const [saveError, setSaveError] = useState("");
  const [assistPending, setAssistPending] = useState(false);
  const [slotAssistIndex, setSlotAssistIndex] = useState<number | null>(null);
  const [assistError, setAssistError] = useState("");
  const [retainRatio, setRetainRatio] = useState(0.7);
  const [configMessage, setConfigMessage] = useState("");
  const [configError, setConfigError] = useState("");
  const [personaCards, setPersonaCards] = useState<PersonaCard[]>([]);
  const [generatedCards, setGeneratedCards] = useState<PersonaCard[]>([]);
  const [selectedCardIds, setSelectedCardIds] = useState<string[]>([]);
  const [cardKeywordInput, setCardKeywordInput] = useState("");
  const [cardLongTextInput, setCardLongTextInput] = useState("");
  const [cardSearchQuery, setCardSearchQuery] = useState("");
  const [cardGenerateCount, setCardGenerateCount] = useState("");
  const [cardActionPending, setCardActionPending] = useState<
    null | "generate_keywords" | "generate_long_text" | "save_generated" | "create_persona"
  >(null);
  const [cardDeletePendingId, setCardDeletePendingId] = useState("");
  const [cardMessage, setCardMessage] = useState("");
  const [cardError, setCardError] = useState("");
  const [draggingPersonaCardId, setDraggingPersonaCardId] = useState("");
  const [slotInsertIndex, setSlotInsertIndex] = useState<number | null>(null);
  const [generatedPersonaMeta, setGeneratedPersonaMeta] = useState<GeneratedPersonaMeta>({
    summary: "",
    relationship: "",
    learnerAddress: "",
  });

  const [draggingSlotIndex, setDraggingSlotIndex] = useState<number | null>(null);
  const [expandedSlotIndex, setExpandedSlotIndex] = useState<number | null>(null);
  const [movePulse, setMovePulse] = useState<{ index: number; direction: -1 | 1 } | null>(null);

  const [basicPaneWidth, setBasicPaneWidth] = useState(260);
  const [sidebarWidth, setSidebarWidth] = useState(380);
  const [collapsedSidebarSections, setCollapsedSidebarSections] = useState<string[]>([]);
  const colResizeRef = useRef<{ which: "basic" | "sidebar"; startX: number; startWidth: number } | null>(null);

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
        if (initialPersona) { setSelectedPersonaId(initialPersona.id); setDraft(personaToDraft(initialPersona)); }
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
  }, [selectedPersonaId, personas]);

  const selectedPersona = useMemo(
    () => personas.find((p) => p.id === selectedPersonaId) ?? null,
    [personas, selectedPersonaId]
  );
  const isReadonlyPersona = selectedPersona?.source === "builtin";

  const allCards = useMemo(() => [...generatedCards, ...personaCards], [generatedCards, personaCards]);
  const selectedCards = useMemo(
    () => allCards.filter((card) => selectedCardIds.includes(card.id)),
    [allCards, selectedCardIds]
  );
  const filteredGeneratedCards = useMemo(
    () => generatedCards.filter((card) => matchesPersonaCard(card, cardSearchQuery)),
    [generatedCards, cardSearchQuery]
  );
  const filteredPersonaCards = useMemo(
    () => personaCards.filter((card) => matchesPersonaCard(card, cardSearchQuery)),
    [personaCards, cardSearchQuery]
  );

  function updateDraft<K extends keyof PersonaDraft>(key: K, value: PersonaDraft[K]) {
    if (assistError) setAssistError("");
    setDraft((prev) => ({ ...prev, [key]: value }));
  }

  function handleAddSlot(kind: PersonaSlotKind | string) {
    const label = PERSONA_SLOT_KIND_LABELS[kind as PersonaSlotKind] ?? kind;
    const template = SLOT_TEMPLATES.find((t) => t.kind === kind);
    setDraft((prev) => ({
      ...prev,
      slots: [
        ...prev.slots,
        {
          kind,
          label,
          content: template?.text ?? "",
          weight: 50,
          locked: false,
          sortOrder: prev.slots.length * 10,
        },
      ]
    }));
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
      const card = allCards.find((item) => item.id === draggingPersonaCardId);
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
    } catch (error) {
      setAssistError(String(error));
    } finally {
      setSlotAssistIndex(null);
    }
  }

  async function handleAssistSetting() {
    setAssistError("");
    setAssistPending(true);
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
        systemPrompt: result.systemPromptSuggestion || prev.systemPrompt
      }));
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
    if (!payload.systemPrompt) { setSaveError("请先填写系统提示词。"); return; }
    setSavingPersona(true);
    try {
      const created = await createPersona(payload);
      const latest = await listPersonas();
      setPersonas(latest);
      setSelectedPersonaId(created.id);
      setDraft(personaToDraft(created));
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
    if (!payload.systemPrompt) { setSaveError("请先填写系统提示词。"); return; }
    setSavingPersona(true);
    try {
      const updated = await updatePersona(selectedPersonaId, payload);
      const latest = await listPersonas();
      setPersonas(latest);
      setSelectedPersonaId(updated.id);
      setDraft(personaToDraft(updated));
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

  function toggleCardSelection(cardId: string) {
    setSelectedCardIds((prev) => (
      prev.includes(cardId) ? prev.filter((id) => id !== cardId) : [...prev, cardId]
    ));
  }

  function handlePersonaCardClick(cardId: string, event: ReactMouseEvent<HTMLElement>) {
    const target = event.target as HTMLElement;
    if (target.closest("[data-card-action='true']")) {
      return;
    }
    toggleCardSelection(cardId);
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
    const insertion = buildDraftWithInsertedCards(draft, generatedCards);
    const nextName = draft.name.trim() || "未命名人格";
    setDraft({
      ...insertion.draft,
      summary: generatedPersonaMeta.summary || insertion.draft.summary,
      relationship: generatedPersonaMeta.relationship || insertion.draft.relationship,
      learnerAddress: generatedPersonaMeta.learnerAddress || insertion.draft.learnerAddress,
      systemPrompt: insertion.draft.systemPrompt.trim() || buildSystemPromptFromCards(nextName, generatedCards),
    });
    const metaParts = [
      generatedPersonaMeta.summary ? "摘要" : "",
      generatedPersonaMeta.relationship ? "关系" : "",
      generatedPersonaMeta.learnerAddress ? "称呼" : "",
    ].filter(Boolean);
    const summary = [
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
    setDraft(insertion.draft);
    if (!insertion.insertedCount) {
      setCardMessage("所选卡片已存在于当前人格中，未重复插入。");
      return;
    }
    setCardMessage(`已将 ${insertion.insertedCount} 张卡片插入当前人格编辑区。`);
  }

  async function handleGenerateCards(mode: "keywords" | "long_text") {
    const inputText = mode === "keywords" ? cardKeywordInput.trim() : cardLongTextInput.trim();
    if (!inputText) {
      setCardError(mode === "keywords" ? "请先输入关键词。" : "请先输入长文本。");
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
      setSelectedCardIds(result.items.map((item) => item.id));
      setCardMessage(
        `已生成 ${result.items.length} 张卡片。模型：${result.usedModel || "unknown"}${result.usedWebSearch ? "，已启用联网搜索。" : "。"}`
      );
    } catch (error) {
      setCardError(String(error));
    } finally {
      setCardActionPending(null);
    }
  }

  async function handleSaveGeneratedCardsToLibrary() {
    const generatedSelected = selectedCards.filter((card) => card.source !== "manual");
    if (!generatedSelected.length) {
      setCardError("请先选中生成结果中的卡片，再加入卡片库。");
      return;
    }
    setCardError("");
    setCardMessage("");
    setCardActionPending("save_generated");
    try {
      const created = await createPersonaCardsBatch(
        generatedSelected.map((card) => createPersonaCardInputFromCard(card))
      );
      setPersonaCards((prev) => [...created, ...prev]);
      setCardMessage(`已将 ${created.length} 张卡片加入卡片库。`);
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
      setSelectedCardIds((prev) => prev.filter((id) => id !== cardId));
    } catch (error) {
      setCardError(String(error));
    } finally {
      setCardDeletePendingId("");
    }
  }

  async function handleCreatePersonaFromSelectedCards() {
    if (!selectedCards.length) {
      setCardError("请先选择要组装的人格卡片。");
      return;
    }
    const containsGeneratedCards = selectedCards.some((card) => card.source !== "manual");
    const payload = draftToCreatePersonaInput(draft);
    if (!payload.name) {
      setCardError("请先在左侧填写人格名称，再直接组装保存。");
      return;
    }
    if (containsGeneratedCards) {
      payload.summary = generatedPersonaMeta.summary || payload.summary;
      payload.relationship = generatedPersonaMeta.relationship || payload.relationship;
      payload.learnerAddress = generatedPersonaMeta.learnerAddress || payload.learnerAddress;
    }
    if (!payload.systemPrompt) {
      payload.systemPrompt = buildSystemPromptFromCards(draft.name || payload.name, selectedCards);
    }
    payload.slots = cardsToPersonaSlots(selectedCards);
    setCardError("");
    setCardMessage("");
    setCardActionPending("create_persona");
    try {
      const created = await createPersona(payload);
      const latest = await listPersonas();
      setPersonas(latest);
      setSelectedPersonaId(created.id);
      setDraft(personaToDraft(created));
      setCardMessage(`已基于 ${selectedCards.length} 张卡片创建新人格。`);
    } catch (error) {
      setCardError(String(error));
    } finally {
      setCardActionPending(null);
    }
  }

  function renderPersonaCard(card: PersonaCard, badge: string, generated: boolean) {
    const isSelected = selectedCardIds.includes(card.id);
    return (
      <article
        key={card.id}
        style={{
          ...styles.personaSlotLibraryCard,
          ...(isSelected ? styles.personaSlotLibraryCardSelected : null),
          ...(draggingPersonaCardId === card.id ? styles.personaSlotLibraryCardDragging : null),
        }}
        onClick={(event) => handlePersonaCardClick(card.id, event)}
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
              ⋮⋮
            </button>
            <span style={styles.libraryCardTitle}>{card.title}</span>
          </div>
          <span style={styles.libraryCardBadge}>{badge}</span>
        </div>
        <div style={styles.libraryCardMetaRow}>
          <span>{PERSONA_SLOT_KIND_LABELS[card.kind as PersonaSlotKind] ?? card.label}</span>
          {card.tags.length ? <span>{card.tags.join(" · ")}</span> : null}
        </div>
        {generated ? (
          <div style={styles.libraryCardMetaRow}>
            <span>关键词：{card.searchKeywords || "自定义"}</span>
          </div>
        ) : null}
        <p style={styles.libraryCardContent}>{card.content}</p>
        {generated && card.sourceNote ? <p style={styles.libraryCardNote}>{card.sourceNote}</p> : null}
        <div style={styles.actionsRow}>
          <button data-card-action="true" style={styles.ghostBtn} type="button" onClick={() => insertCardsIntoDraft([card])}>
            插入当前人格
          </button>
          {!generated ? (
            <button
              data-card-action="true"
              style={styles.ghostBtn}
              type="button"
              disabled={cardDeletePendingId === card.id}
              onClick={() => void handleDeletePersonaCard(card.id)}
            >
              {cardDeletePendingId === card.id ? "删除中…" : "删除"}
            </button>
          ) : null}
        </div>
      </article>
    );
  }

  function startColumnResize(which: "basic" | "sidebar", e: ReactMouseEvent) {
    e.preventDefault();
    colResizeRef.current = {
      which,
      startX: e.clientX,
      startWidth: which === "basic" ? basicPaneWidth : sidebarWidth,
    };
    function onMove(me: MouseEvent) {
      const s = colResizeRef.current;
      if (!s) return;
      const delta = me.clientX - s.startX;
      const w = Math.max(160, Math.min(560, s.startWidth + (s.which === "basic" ? delta : -delta)));
      if (s.which === "basic") setBasicPaneWidth(w); else setSidebarWidth(w);
    }
    function onUp() {
      colResizeRef.current = null;
      document.removeEventListener("mousemove", onMove);
      document.removeEventListener("mouseup", onUp);
    }
    document.addEventListener("mousemove", onMove);
    document.addEventListener("mouseup", onUp);
  }

  return (
    <main className="with-app-nav" style={styles.page}>
      <div style={styles.pageHeader}>
        <TopNav currentPath="/persona-spectrum" />
        <div style={styles.titleBar}>
          <h1 style={styles.pageTitle}>人格色谱</h1>
        </div>
      </div>
      <div style={styles.workspaceShell}>
        <div style={styles.mainColumn}>
          {loadError ? <div style={styles.errorBanner}>加载失败: {loadError}</div> : null}
          <div style={styles.editorArea}>
            <div style={{ ...styles.basicPane, width: basicPaneWidth, flexShrink: 0 }}>
              <div style={styles.panelHeader}>
                <span style={styles.panelTitle}>基本设定</span>
              </div>
              <div style={styles.panelBody}>
                <div style={styles.fieldGroup}>
                <label style={styles.fieldLabel}>当前人格</label>
                <select style={styles.select} value={selectedPersonaId} onChange={(e) => setSelectedPersonaId(e.target.value)}>
                  {personas.map((p) => (
                    <option key={p.id} value={p.id}>{p.name}（{p.source === "builtin" ? "内置" : "用户"}）</option>
                  ))}
                </select>
              </div>

              {selectedPersona ? (
                <div style={styles.personaCard}>
                  <div style={styles.personaCardHead}>
                    <span style={styles.personaCardName}>{selectedPersona.name}</span>
                    <span style={styles.personaCardSource}>{selectedPersona.source === "builtin" ? "内置人格" : "用户人格"}</span>
                  </div>
                  <p style={styles.personaCardSummary}>{selectedPersona.summary || "未填写摘要"}</p>
                  <div style={styles.personaCardMetaGrid}>
                    <span style={styles.personaCardMetaLabel}>关系</span>
                    <span style={styles.personaCardMetaValue}>{selectedPersona.relationship || "未填写"}</span>
                    <span style={styles.personaCardMetaLabel}>称呼</span>
                    <span style={styles.personaCardMetaValue}>{selectedPersona.learnerAddress || "未填写"}</span>
                  </div>
                </div>
              ) : null}

              <div style={styles.fieldGroup}>
                <label style={styles.fieldLabel}>名称</label>
                <input style={styles.input} value={draft.name} onChange={(e) => updateDraft("name", e.target.value)} />
              </div>

              <div style={styles.fieldGroup}>
                <label style={styles.fieldLabel}>摘要</label>
                <textarea style={styles.textarea} value={draft.summary} onChange={(e) => updateDraft("summary", e.target.value)} />
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

              <div style={styles.fieldGroup}>
                <label style={styles.fieldLabel}>保留原文比例 {(retainRatio * 100).toFixed(0)}%</label>
                <input
                  style={styles.range}
                  type="range"
                  min={0}
                  max={1}
                  step={0.05}
                  value={retainRatio}
                  onChange={(e) => setRetainRatio(Number(e.target.value))}
                />
              </div>

              <div style={styles.actionsRow}>
                <button style={styles.ghostBtn} type="button" disabled={assistPending} onClick={handleAssistSetting}>
                  {assistPending ? "AI 完善中…" : "AI 辅助完善设定"}
                </button>
                {assistError ? <span style={styles.errorInline}>{assistError}</span> : null}
              </div>

              <div style={styles.fieldGroup}>
                <label style={styles.fieldLabel}>系统提示词</label>
                <textarea style={styles.textareaLg} value={draft.systemPrompt} onChange={(e) => updateDraft("systemPrompt", e.target.value)} />
              </div>

              <div style={styles.actionsRow}>
                <button style={styles.primaryBtn} disabled={savingPersona} onClick={handleCreatePersona}>
                  {savingPersona ? "保存中…" : "创建新人格"}
                </button>
                <button style={styles.ghostBtn} disabled={savingPersona || isReadonlyPersona} onClick={handleUpdatePersona}>
                  {savingPersona ? "保存中…" : "更新当前人格"}
                </button>
                {saveError ? <span style={styles.errorInline}>{saveError}</span> : null}
              </div>
              {isReadonlyPersona ? (
                <span style={styles.mutedText}>只读 — 编辑后可另存为新人格</span>
              ) : null}

              <section style={styles.inlinePanel}>
                <div style={styles.panelHead}>
                  <span style={styles.panelTitle}>配置导入/导出</span>
                </div>
                <div style={styles.actionsRow}>
                  <button style={styles.ghostBtn} type="button" onClick={handleDownloadTemplate}>下载模板</button>
                  <button style={styles.ghostBtn} type="button" onClick={handleExportConfig}>导出配置</button>
                  <label style={styles.ghostBtn}>
                    导入配置
                    <input type="file" accept="application/json,.json" style={styles.hiddenInput} onChange={handleImportConfig} />
                  </label>
                </div>
                {configMessage ? <span style={styles.mutedText}>{configMessage}</span> : null}
                {configError ? <span style={styles.errorInline}>{configError}</span> : null}
              </section>
              </div>{/* panelBody */}
            </div>
            <div style={styles.resizer} onMouseDown={(e) => startColumnResize("basic", e)} />
            <div style={styles.slotsPane}>
              <div style={styles.panelHeader}>
                <span style={styles.panelTitle}>人格插槽</span>
                <button type="button" style={styles.ghostBtn} onClick={handleSortSlotsByPriority}>按优先级整理</button>
              </div>
              <div style={styles.panelBody}>
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
                          <span
                            style={styles.dragHandle}
                            title="拖动排序"
                            draggable
                            onDragStart={(e) => { e.stopPropagation(); handleDragStart(index); }}
                            onDragEnd={handleDragEnd}
                            onClick={(e) => e.stopPropagation()}
                          >
                            ⋮⋮
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
                          {expandedSlotIndex !== index ? (
                            <span style={styles.slotPreview}>{slot.content.slice(0, 40) || "—"}</span>
                          ) : null}
                          <button
                            type="button"
                            style={styles.slotToggleBtn}
                            onClick={(e) => { e.stopPropagation(); setExpandedSlotIndex((prev) => (prev === index ? null : index)); }}
                          >
                            {expandedSlotIndex === index ? "▾" : "▸"}
                          </button>
                          <button
                            type="button"
                            style={styles.removeBtn}
                            onClick={(e) => { e.stopPropagation(); handleRemoveSlot(index); }}
                          >×</button>
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
                              <button type="button" style={styles.iconBtn} title="上移" onClick={() => handleMoveSlot(index, -1)}>↑</button>
                              <button type="button" style={styles.iconBtn} title="下移" onClick={() => handleMoveSlot(index, 1)}>↓</button>
                              <button
                                type="button"
                                style={styles.iconBtn}
                                title={slot.locked ? "解锁" : "锁定"}
                                onClick={() => handleUpdateSlot(index, "locked", !slot.locked)}
                              >
                                {slot.locked ? "⊘" : "○"}
                              </button>
                              <button
                                type="button"
                                style={styles.iconBtn}
                                title="AI 重写"
                                onClick={() => void handleAssistSlot(index)}
                                disabled={assistPending || slotAssistIndex === index || Boolean(slot.locked)}
                              >
                                {slotAssistIndex === index ? "…" : "✦"}
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
                <div style={styles.addSlotRow}>
                  {SLOT_TEMPLATES.map((t) => (
                    <button key={t.kind} type="button" style={styles.tagBtn} onClick={() => handleAddSlot(t.kind)}>
                      {PERSONA_SLOT_KIND_LABELS[t.kind]}
                    </button>
                  ))}
                  <button type="button" style={styles.tagBtn} onClick={() => handleAddSlot("custom")}>自定义</button>
                </div>
              </div>
              </div>{/* panelBody */}
            </div>
          </div>
        </div>
        <div style={styles.resizer} onMouseDown={(e) => startColumnResize("sidebar", e)} />
        <aside style={{ ...styles.sidebarPane, width: sidebarWidth, flexShrink: 0 }}>
          <div style={styles.sidebarSection}>
            <button type="button" style={styles.sidebarSectionHeader} onClick={() => toggleSidebarSection("library")}>
              <span style={styles.panelTitle}>人格卡片库</span>
              <span style={styles.sidebarToggleIcon}>{collapsedSidebarSections.includes("library") ? "▸" : "▾"}</span>
            </button>
            {!collapsedSidebarSections.includes("library") ? (
              <div style={styles.sidebarSectionBody}>
                <input
                  style={styles.input}
                  value={cardSearchQuery}
                  onChange={(e) => setCardSearchQuery(e.target.value)}
                  placeholder="搜索标题、内容、标签、关键词"
                />
                <span style={styles.mutedText}>
                  共 {personaCards.length} 张库卡片，{generatedCards.length} 张本轮生成结果，当前选中 {selectedCards.length} 张。
                </span>
              </div>
            ) : null}
          </div>

          <div style={styles.sidebarSection}>
            <button type="button" style={styles.sidebarSectionHeader} onClick={() => toggleSidebarSection("generate")}>
              <span style={styles.panelTitle}>关键词生成 / 长文本提取</span>
              <span style={styles.sidebarToggleIcon}>{collapsedSidebarSections.includes("generate") ? "▸" : "▾"}</span>
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
                <p style={styles.sidebarHint}>留空表示不限制卡片数量，由模型根据关键词或长文本的信息密度自由决定。</p>
                <label style={styles.fieldGroup}>
                  <span style={styles.fieldLabel}>关键词搜索</span>
                  <input
                    style={styles.input}
                    value={cardKeywordInput}
                    onChange={(e) => setCardKeywordInput(e.target.value)}
                    placeholder="例如：冷静学术、学院派导师、侦探式推理"
                  />
                </label>
                <button
                  style={styles.primaryBtn}
                  type="button"
                  disabled={cardActionPending !== null}
                  onClick={() => void handleGenerateCards("keywords")}
                >
                  {cardActionPending === "generate_keywords" ? "生成中…" : "根据关键词生成人格卡片"}
                </button>
                <label style={styles.fieldGroup}>
                  <span style={styles.fieldLabel}>长文本提取</span>
                  <textarea
                    style={styles.textarea}
                    value={cardLongTextInput}
                    onChange={(e) => setCardLongTextInput(e.target.value)}
                    placeholder="输入长文本设定，提取成可复用的人格卡片。"
                  />
                </label>
                <button
                  style={styles.ghostBtn}
                  type="button"
                  disabled={cardActionPending !== null}
                  onClick={() => void handleGenerateCards("long_text")}
                >
                  {cardActionPending === "generate_long_text" ? "提取中…" : "根据长文本提取人格卡片"}
                </button>
                {cardError ? <p style={styles.errorText}>{cardError}</p> : null}
                {cardMessage ? <p style={styles.sidebarHint}>{cardMessage}</p> : null}
                {(generatedCards.length || generatedPersonaMeta.summary || generatedPersonaMeta.relationship || generatedPersonaMeta.learnerAddress) ? (
                  <div style={styles.generatedResultCard}>
                    <strong style={styles.generatedResultTitle}>{generatedPersonaMeta.summary || "本轮生成人格草案"}</strong>
                    <p style={styles.generatedResultSummary}>
                      {generatedPersonaMeta.summary || "已生成一组可继续筛选、写回或组装的人格卡片。"}
                    </p>
                    <p style={styles.generatedResultMeta}>
                      {generatedCards.length} 张卡片
                      {generatedPersonaMeta.relationship ? ` · ${generatedPersonaMeta.relationship}` : ""}
                      {generatedPersonaMeta.learnerAddress ? ` · 称呼：${generatedPersonaMeta.learnerAddress}` : ""}
                    </p>
                    <button
                      style={styles.primaryBtn}
                      type="button"
                      onClick={applyGeneratedCardsToDraft}
                    >
                      应用到当前编辑区
                    </button>
                  </div>
                ) : null}
                <div style={styles.actionsRow}>
                  <button style={styles.ghostBtn} type="button" disabled={!selectedCards.length} onClick={() => insertCardsIntoDraft(selectedCards)}>
                    插入当前人格
                  </button>
                  <button style={styles.ghostBtn} type="button" disabled={cardActionPending !== null} onClick={() => void handleSaveGeneratedCardsToLibrary()}>
                    {cardActionPending === "save_generated" ? "保存中…" : "加入卡片库"}
                  </button>
                  <button style={styles.ghostBtn} type="button" disabled={cardActionPending !== null} onClick={() => void handleCreatePersonaFromSelectedCards()}>
                    {cardActionPending === "create_persona" ? "创建中…" : "直接组装"}
                  </button>
                </div>
              </div>
            ) : null}
          </div>

          <div style={styles.sidebarSection}>
            <button type="button" style={styles.sidebarSectionHeader} onClick={() => toggleSidebarSection("results")}>
              <span style={styles.panelTitle}>生成结果 / 卡片库</span>
              <span style={styles.sidebarToggleIcon}>{collapsedSidebarSections.includes("results") ? "▸" : "▾"}</span>
            </button>
            {!collapsedSidebarSections.includes("results") ? (
              <div style={styles.sidebarSectionBody}>
                <span style={styles.panelTitle}>生成结果</span>
                {filteredGeneratedCards.length ? (
                  <div style={styles.cardList}>
                    {filteredGeneratedCards.map((card) => renderPersonaCard(card, "生成", true))}
                  </div>
                ) : (
                  <span style={styles.mutedText}>暂无匹配的生成结果。</span>
                )}
                <span style={styles.panelTitle}>卡片库</span>
                {filteredPersonaCards.length ? (
                  <div style={styles.cardList}>
                    {filteredPersonaCards.map((card) => renderPersonaCard(card, "卡片库", false))}
                  </div>
                ) : (
                  <span style={styles.mutedText}>暂无匹配的人格卡片。</span>
                )}
              </div>
            ) : null}
          </div>
        </aside>
      </div>
    </main>
  );
}

/* ─── Helpers (unchanged) ─── */

function personaToDraft(persona: PersonaProfile): PersonaDraft {
  return {
    name: persona.name,
    summary: persona.summary,
    relationship: persona.relationship,
    learnerAddress: persona.learnerAddress,
    systemPrompt: persona.systemPrompt,
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

function createPersonaCardInputFromCard(card: PersonaCard): CreatePersonaCardInput {
  return {
    title: card.title,
    kind: card.kind,
    label: card.label,
    content: card.content,
    tags: card.tags,
    searchKeywords: card.searchKeywords,
    source: card.source,
    sourceNote: card.sourceNote,
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

function cardsToPersonaSlots(cards: PersonaCard[]): PersonaSlot[] {
  return cards.map((card, index) => ({
    kind: card.kind,
    label: card.label,
    content: card.content,
    weight: 50,
    locked: false,
    sortOrder: index * 10,
  }));
}

function buildSystemPromptFromCards(name: string, cards: PersonaCard[]): string {
  const slotLines = cards
    .map((card) => `${card.label}：${card.content}`)
    .slice(0, 6)
    .join("\n");
  return [
    `你是一位教材导学型教师人格「${name.trim() || "未命名人格"}」。`,
    "请保持结构清晰、反馈具体、语气稳定，并优先帮助学习者推进下一步。",
    slotLines ? `参考人格卡片：\n${slotLines}` : "",
  ]
    .filter(Boolean)
    .join("\n\n");
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
  if (!systemPrompt) throw new Error("缺少系统提示词字段（systemPrompt）");

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
    height: "100vh",
    overflow: "hidden",
    display: "flex",
    flexDirection: "column",
    maxWidth: 1400,
    margin: "0 auto",
    padding: 0,
  },
  pageHeader: {
    flexShrink: 0,
    borderBottom: "1px solid var(--border)",
  },
  titleBar: {
    padding: "8px 24px",
    display: "flex",
    alignItems: "center",
  },
  workspaceShell: {
    display: "flex",
    flex: 1,
    minHeight: 0,
    overflow: "hidden",
  },
  mainColumn: {
    flex: 1,
    minWidth: 0,
    display: "flex",
    flexDirection: "column",
    overflow: "hidden",
  },
  editorArea: {
    display: "flex",
    flex: 1,
    minHeight: 0,
    overflow: "hidden",
  },
  basicPane: {
    display: "flex",
    flexDirection: "column",
    overflow: "hidden",
  },
  slotsPane: {
    flex: 1,
    minWidth: 0,
    display: "flex",
    flexDirection: "column",
    overflow: "hidden",
  },
  panelHeader: {
    flexShrink: 0,
    padding: "8px 16px",
    borderBottom: "1px solid var(--border)",
    background: "var(--panel)",
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    minHeight: 36,
    gap: 8,
  },
  panelBody: {
    flex: 1,
    minHeight: 0,
    overflowY: "auto",
    padding: "16px 20px",
    display: "flex",
    flexDirection: "column",
    gap: 14,
  },
  slotDropArea: {
    display: "flex",
    flexDirection: "column",
    gap: 0,
  },
  pageTitle: { margin: 0, fontSize: 18, fontWeight: 700, color: "var(--ink)", lineHeight: 1.2 },

  /* Left: editor */
  editorPanel: {
    border: "1px solid var(--border)",
    background: "var(--panel)",
    padding: 20,
    display: "grid",
    gap: 14,
    alignContent: "start",
  },
  inlinePanel: {
    borderTop: "1px solid var(--border)",
    paddingTop: 14,
    display: "grid",
    gap: 10,
    alignContent: "start",
  },
  sidebarPane: {
    display: "flex",
    flexDirection: "column",
    overflowY: "auto",
    background: "var(--bg)",
  },
  resizer: {
    width: 4,
    flexShrink: 0,
    background: "var(--border)",
    cursor: "col-resize",
  },
  sidebarSection: {
    borderBottom: "1px solid var(--border)",
    flexShrink: 0,
  },
  sidebarSectionHeader: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    width: "100%",
    border: "none",
    background: "transparent",
    padding: "14px 16px",
    cursor: "pointer",
    textAlign: "left",
  },
  sidebarSectionBody: {
    padding: "0 16px 14px",
    display: "grid",
    gap: 10,
    alignContent: "start",
  },
  sidebarListSection: {
    flex: 1,
    overflowY: "auto",
    minHeight: 0,
    alignContent: "start",
  },
  sidebarToggleIcon: {
    fontSize: 12,
    color: "var(--muted)",
  },

  /* Panel header */
  panelHead: {
    paddingBottom: 10,
    borderBottom: "1px solid var(--border)",
    marginBottom: 2,
  },
  sidebarHint: {
    margin: 0,
    fontSize: 12,
    color: "var(--muted)",
    lineHeight: 1.6,
  },
  panelTitle: {
    fontSize: 11,
    fontWeight: 700,
    color: "var(--muted)",
    textTransform: "uppercase",
    letterSpacing: "0.06em",
  },

  /* Form elements */
  fieldGroup: {
    display: "grid",
    gap: 6,
  },
  slotDropZoneActive: {
    boxShadow: "0 0 0 2px var(--accent-soft) inset",
    borderRadius: 4,
    padding: 8,
    background: "color-mix(in srgb, white 70%, var(--accent-soft))",
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
    borderColor: "var(--accent)",
    background: "color-mix(in srgb, white 70%, var(--accent-soft))",
    color: "var(--ink)",
  },
  personaCard: {
    display: "grid",
    gap: 8,
    border: "1px solid var(--border)",
    background: "var(--panel)",
    padding: 12,
  },
  personaCardHead: {
    display: "flex",
    alignItems: "baseline",
    justifyContent: "space-between",
    gap: 8,
    flexWrap: "wrap",
  },
  personaCardName: {
    fontSize: 14,
    fontWeight: 700,
    color: "var(--ink)",
  },
  personaCardSource: {
    fontSize: 11,
    color: "var(--muted)",
  },
  personaCardSummary: {
    margin: 0,
    fontSize: 12,
    lineHeight: 1.6,
    color: "var(--muted)",
  },
  personaCardMetaGrid: {
    display: "grid",
    gridTemplateColumns: "auto 1fr",
    gap: "4px 8px",
    alignItems: "center",
  },
  personaCardMetaLabel: {
    fontSize: 11,
    color: "var(--muted)",
    letterSpacing: "0.04em",
  },
  personaCardMetaValue: {
    fontSize: 12,
    color: "var(--ink)",
  },
  fieldLabel: {
    fontSize: 11,
    fontWeight: 600,
    textTransform: "uppercase",
    letterSpacing: "0.07em",
    color: "var(--muted)",
  },
  input: {
    width: "100%",
    height: 36,
    border: "1px solid var(--border)",
    background: "var(--panel)",
    padding: "0 10px",
    color: "var(--ink)",
    fontSize: 13,
  },
  select: {
    width: "100%",
    height: 36,
    border: "1px solid var(--border)",
    background: "var(--panel)",
    padding: "0 8px",
    color: "var(--ink)",
    fontSize: 13,
  },
  selectCompact: {
    width: 88,
    height: 36,
    border: "1px solid var(--border)",
    background: "var(--panel)",
    padding: "0 8px",
    color: "var(--ink)",
    fontSize: 13,
  },
  textarea: {
    width: "100%",
    minHeight: 72,
    border: "1px solid var(--border)",
    background: "var(--panel)",
    padding: "8px 10px",
    resize: "vertical",
    color: "var(--ink)",
    fontSize: 13,
    lineHeight: 1.6,
  },
  textareaLg: {
    width: "100%",
    minHeight: 120,
    border: "1px solid var(--border)",
    background: "var(--panel)",
    padding: "8px 10px",
    resize: "vertical",
    color: "var(--ink)",
    fontSize: 13,
    lineHeight: 1.6,
  },
  range: {
    width: "100%",
  },

  /* Slot card */
  slotCard: {
    border: "1px solid var(--border)",
    background: "var(--panel)",
    padding: "10px",
    display: "grid",
    gap: 8,
    marginBottom: 6,
    transition: "transform 180ms ease, box-shadow 180ms ease, border-color 180ms ease, opacity 180ms ease",
  },
  slotCardDragging: {
    opacity: 0.7,
    transform: "scale(0.99)",
    borderColor: "var(--teal)",
    boxShadow: "0 8px 18px rgba(10, 48, 51, 0.14)",
  },
  slotCardMoveUp: {
    transform: "translateY(-8px)",
    borderColor: "var(--accent)",
    boxShadow: "0 0 0 2px var(--accent-soft) inset",
  },
  slotCardMoveDown: {
    transform: "translateY(8px)",
    borderColor: "var(--accent)",
    boxShadow: "0 0 0 2px var(--accent-soft) inset",
  },
  slotHeader: {
    display: "flex",
    gap: 6,
    alignItems: "center",
    cursor: "pointer",
  },
  dragHandle: {
    color: "var(--muted)",
    cursor: "grab",
    userSelect: "none",
    fontSize: 14,
    lineHeight: 1,
    padding: "0 2px",
  },
  slotKindSelect: {
    flex: "0 0 auto",
    height: 30,
    border: "1px solid var(--border)",
    background: "var(--bg)",
    padding: "0 6px",
    fontSize: 12,
    color: "var(--ink)",
  },
  slotLabelInput: {
    flex: 1,
    height: 30,
    border: "1px solid var(--border)",
    background: "var(--bg)",
    padding: "0 8px",
    fontSize: 12,
    color: "var(--ink)",
  },
  removeBtn: {
    flex: "0 0 auto",
    height: 30,
    width: 30,
    border: "1px solid var(--border)",
    background: "var(--bg)",
    color: "var(--muted)",
    cursor: "pointer",
    fontSize: 16,
    lineHeight: 1,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
  },
  slotContent: {
    width: "100%",
    minHeight: 64,
    border: "1px solid var(--border)",
    background: "var(--bg)",
    padding: "6px 8px",
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
    gap: 8,
    alignItems: "center",
  },
  addSlotRow: {
    display: "flex",
    gap: 6,
    alignItems: "center",
    flexWrap: "wrap",
    paddingTop: 10,
    borderTop: "1px solid var(--border)",
  },
  slotPreview: {
    flex: 1,
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
    fontSize: 12,
    padding: "0 4px",
    height: 28,
    flexShrink: 0,
  },

  /* Compact 2-col grid */
  compactGrid: {
    display: "grid",
    gridTemplateColumns: "1fr 1fr",
    gap: 10,
  },

  /* Buttons */
  primaryBtn: {
    border: "none",
    background: "var(--accent)",
    color: "white",
    height: 36,
    padding: "0 14px",
    cursor: "pointer",
    fontWeight: 600,
    fontSize: 13,
  },
  ghostBtn: {
    border: "1px solid var(--border)",
    background: "transparent",
    color: "var(--ink)",
    height: 36,
    padding: "0 12px",
    cursor: "pointer",
    fontSize: 13,
    display: "inline-flex",
    alignItems: "center",
  },
  iconBtn: {
    border: "1px solid var(--border)",
    background: "transparent",
    color: "var(--muted)",
    height: 26,
    minWidth: 26,
    padding: "0 6px",
    cursor: "pointer",
    fontSize: 12,
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
    flexShrink: 0,
  },
  tagBtn: {
    border: "1px solid var(--border)",
    background: "var(--panel)",
    color: "var(--accent)",
    height: 28,
    padding: "0 10px",
    cursor: "pointer",
    fontSize: 12,
    fontWeight: 500,
  },
  actionsRow: {
    display: "flex",
    gap: 8,
    alignItems: "center",
    flexWrap: "wrap",
  },
  cardSummaryGrid: {
    display: "grid",
    gridTemplateColumns: "repeat(3, minmax(0, 1fr))",
    gap: 10,
  },
  cardSummaryItem: {
    border: "1px solid var(--border)",
    background: "var(--panel)",
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
    gap: 10,
  },
  personaSlotLibraryCard: {
    border: "1px solid var(--border)",
    background: "var(--panel)",
    padding: 12,
    display: "grid",
    gap: 8,
    cursor: "pointer",
    transition: "transform 160ms ease, box-shadow 160ms ease, opacity 160ms ease, border-color 160ms ease, background 160ms ease",
  },
  personaSlotLibraryCardSelected: {
    borderColor: "var(--accent)",
    boxShadow: "0 0 0 2px var(--accent-soft) inset",
    background: "color-mix(in srgb, white 84%, var(--accent-soft))",
  },
  personaSlotLibraryCardDragging: {
    opacity: 0.7,
    transform: "scale(0.99)",
    boxShadow: "0 8px 18px rgba(10, 48, 51, 0.14)",
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
    background: "var(--bg)",
    color: "var(--muted)",
    width: 30,
    height: 30,
    cursor: "grab",
    fontSize: 14,
    lineHeight: 1,
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
    border: "1px solid var(--border)",
    padding: "2px 8px",
    fontSize: 11,
    color: "var(--muted)",
    background: "var(--bg)",
  },
  libraryCardMetaRow: {
    display: "flex",
    gap: 8,
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
    background: "var(--panel)",
    padding: "10px",
    display: "grid",
    gap: 6,
  },
  generatedResultCard: {
    display: "grid",
    gap: 6,
    padding: 10,
    border: "1px solid var(--border)",
    background: "var(--panel)",
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
    padding: "8px 12px",
    fontSize: 13,
  },
  errorText: { fontSize: 12, color: "var(--negative)", lineHeight: 1.5, margin: 0 },
  errorInline: { color: "var(--negative)", fontSize: 12 },
};
