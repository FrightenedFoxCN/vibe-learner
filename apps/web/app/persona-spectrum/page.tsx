"use client";

import { useEffect, useMemo, useState, type ChangeEvent } from "react";
import type { CSSProperties } from "react";
import {
  CHARACTER_ACTIONS,
  CHARACTER_EMOTIONS,
  PERSONA_SLOT_KIND_LABELS,
  PERSONA_SLOT_KINDS,
  SPEECH_STYLES,
  type CharacterAction,
  type CharacterEmotion,
  type CreatePersonaInput,
  type DocumentRecord,
  type PersonaProfile,
  type PersonaSlot,
  type PersonaSlotKind,
  type SpeechStyle,
  type CharacterStateEvent,
  type StudyChatResponse
} from "@vibe-learner/shared";

import { CharacterShell } from "../../components/character-shell";
import { TopNav } from "../../components/top-nav";
import {
  assistPersonaSlot,
  assistPersonaSetting,
  createPersona,
  createStudySession,
  getPersonaAssets,
  listDocuments,
  listPersonas,
  sendStudyMessage,
  updatePersona,
  type PersonaAssets,
  type StudyChatExchangeResponse
} from "../../lib/api";

type TimingHint = "instant" | "linger" | "after_text";

const TIMING_HINT_LABELS: Record<TimingHint, string> = {
  instant: "立即触发",
  linger: "延迟停留",
  after_text: "文本后触发"
};

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

const EMOTION_LABELS: Record<string, string> = {
  calm: "平静",
  encouraging: "鼓励",
  playful: "活泼",
  serious: "严谨",
  excited: "兴奋",
  concerned: "关切"
};

const ACTION_LABELS: Record<string, string> = {
  idle: "待机",
  nod: "点头",
  point: "指向",
  lean_in: "前倾",
  smile: "微笑",
  pause: "停顿",
  write: "书写比划"
};

const SPEECH_STYLE_LABELS: Record<string, string> = {
  warm: "温和",
  steady: "稳重",
  energetic: "活力",
  concise: "简洁"
};

interface PersonaDraft {
  name: string;
  summary: string;
  systemPrompt: string;
  slots: PersonaSlot[];
  availableEmotionsText: string;
  availableActionsText: string;
  defaultSpeechStyle: SpeechStyle;
}

function clampWeight(value: number): number {
  const n = Number.isFinite(value) ? Math.round(value) : 50;
  return Math.max(0, Math.min(100, n));
}

const EMPTY_DRAFT: PersonaDraft = {
  name: "",
  summary: "",
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
  const [documents, setDocuments] = useState<DocumentRecord[]>([]);
  const [selectedPersonaId, setSelectedPersonaId] = useState("");
  const [selectedDocumentId, setSelectedDocumentId] = useState("");
  const [selectedSectionId, setSelectedSectionId] = useState("");

  const [draft, setDraft] = useState<PersonaDraft>(EMPTY_DRAFT);
  const [savingPersona, setSavingPersona] = useState(false);

  const [assets, setAssets] = useState<PersonaAssets | null>(null);
  const [assetsError, setAssetsError] = useState("");

  const [loadError, setLoadError] = useState("");
  const [saveError, setSaveError] = useState("");
  const [assistPending, setAssistPending] = useState(false);
  const [slotAssistIndex, setSlotAssistIndex] = useState<number | null>(null);
  const [assistError, setAssistError] = useState("");
  const [retainRatio, setRetainRatio] = useState(0.7);
  const [configMessage, setConfigMessage] = useState("");
  const [configError, setConfigError] = useState("");

  const [previewEmotion, setPreviewEmotion] = useState<CharacterEmotion>("calm");
  const [previewAction, setPreviewAction] = useState<CharacterAction>("idle");
  const [previewSpeech, setPreviewSpeech] = useState<SpeechStyle>("warm");
  const [previewTiming, setPreviewTiming] = useState<TimingHint>("instant");

  const [previewSessionId, setPreviewSessionId] = useState("");
  const [previewMessage, setPreviewMessage] = useState("请用这个人格风格解释当前章节的核心概念。");
  const [previewPending, setPreviewPending] = useState(false);
  const [previewError, setPreviewError] = useState("");
  const [previewChat, setPreviewChat] = useState<StudyChatExchangeResponse | null>(null);
  const [draggingSlotIndex, setDraggingSlotIndex] = useState<number | null>(null);
  const [dragOverSlotIndex, setDragOverSlotIndex] = useState<number | null>(null);
  const [movePulse, setMovePulse] = useState<{ index: number; direction: -1 | 1 } | null>(null);

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
        const [personaList, documentList] = await Promise.all([listPersonas(), listDocuments()]);
        if (cancelled) return;
        setPersonas(personaList);
        setDocuments(documentList);
        const initialPersona = personaList[0];
        if (initialPersona) { setSelectedPersonaId(initialPersona.id); setDraft(personaToDraft(initialPersona)); }
        const initialDocument = documentList[0];
        if (initialDocument) {
          setSelectedDocumentId(initialDocument.id);
          const firstSection = resolveSections(initialDocument)[0];
          setSelectedSectionId(firstSection?.id ?? "");
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
    setPreviewEmotion(selectedPersona.availableEmotions[0] ?? "calm");
    setPreviewAction(selectedPersona.availableActions[0] ?? "idle");
    setPreviewSpeech(selectedPersona.defaultSpeechStyle);
    setPreviewChat(null);
    setPreviewSessionId("");
  }, [selectedPersonaId, personas]);

  useEffect(() => {
    if (!selectedPersonaId) { setAssets(null); setAssetsError(""); return; }
    let cancelled = false;
    async function loadAssets() {
      setAssetsError("");
      try {
        const a = await getPersonaAssets(selectedPersonaId);
        if (!cancelled) setAssets(a);
      } catch (error) {
        if (!cancelled) { setAssets(null); setAssetsError(String(error)); }
      }
    }
    loadAssets();
    return () => { cancelled = true; };
  }, [selectedPersonaId]);

  useEffect(() => {
    if (!selectedDocumentId) { setSelectedSectionId(""); return; }
    const doc = documents.find((d) => d.id === selectedDocumentId);
    if (!doc) return;
    const opts = resolveSections(doc);
    if (!opts.find((o) => o.id === selectedSectionId)) {
      setSelectedSectionId(opts[0]?.id ?? "");
    }
  }, [documents, selectedDocumentId, selectedSectionId]);

  const sectionOptions = useMemo(() => {
    const doc = documents.find((d) => d.id === selectedDocumentId);
    return doc ? resolveSections(doc) : [];
  }, [documents, selectedDocumentId]);

  const draftEmotionOptions = useMemo(() => coerceEmotions(draft.availableEmotionsText), [draft.availableEmotionsText]);
  const draftActionOptions = useMemo(() => coerceActions(draft.availableActionsText), [draft.availableActionsText]);

  const selectedPersona = useMemo(
    () => personas.find((p) => p.id === selectedPersonaId) ?? null,
    [personas, selectedPersonaId]
  );
  const isReadonlyPersona = selectedPersona?.source === "builtin";

  const draftPersona = useMemo<PersonaProfile>(() => {
    const emotions: CharacterEmotion[] = draftEmotionOptions.length ? draftEmotionOptions : ["calm"];
    const actions: CharacterAction[] = draftActionOptions.length ? draftActionOptions : ["idle"];
    return {
      id: selectedPersonaId || "persona-draft",
      name: draft.name || "未命名人格",
      source: "user",
      summary: draft.summary,
      systemPrompt: draft.systemPrompt,
      slots: draft.slots,
      availableEmotions: emotions,
      availableActions: actions,
      defaultSpeechStyle: draft.defaultSpeechStyle
    };
  }, [draft, draftActionOptions, draftEmotionOptions, selectedPersonaId]);

  const syntheticPreviewResponse = useMemo<StudyChatResponse>(() => {
    const event: CharacterStateEvent = {
      emotion: previewEmotion,
      action: previewAction,
      speechStyle: previewSpeech,
      sceneHint: "persona_layer_preview",
      lineSegmentId: "persona-spectrum-debug",
      timingHint: previewTiming
    };
    return {
      reply: "这是人格色谱调试预览，不会调用模型。可先调教情绪、动作与语速，再进入章节联动预览。",
      citations: [],
      characterEvents: [event]
    };
  }, [previewAction, previewEmotion, previewSpeech, previewTiming]);

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

  function reorderSlots(fromIndex: number, toIndex: number) {
    setDraft((prev) => {
      if (fromIndex === toIndex || fromIndex < 0 || toIndex < 0 || fromIndex >= prev.slots.length || toIndex >= prev.slots.length) {
        return prev;
      }
      const next = [...prev.slots];
      const [moved] = next.splice(fromIndex, 1);
      next.splice(toIndex, 0, moved);
      return {
        ...prev,
        slots: next.map((slot, i) => ({ ...slot, sortOrder: i * 10 }))
      };
    });
  }

  function handleDragStart(index: number) {
    setDraggingSlotIndex(index);
  }

  function handleDragOver(index: number) {
    setDragOverSlotIndex(index);
  }

  function handleDrop(index: number) {
    if (draggingSlotIndex !== null) {
      reorderSlots(draggingSlotIndex, index);
    }
    setDraggingSlotIndex(null);
    setDragOverSlotIndex(null);
  }

  function handleDragEnd() {
    setDraggingSlotIndex(null);
    setDragOverSlotIndex(null);
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
      const nextDraft = createInputToDraft(normalized);
      setDraft(nextDraft);
      setPreviewEmotion(normalized.availableEmotions?.[0] ?? "calm");
      setPreviewAction(normalized.availableActions?.[0] ?? "idle");
      setPreviewSpeech(normalized.defaultSpeechStyle ?? "warm");
      setConfigMessage("配置导入成功，已应用到当前编辑区。");
    } catch (error) {
      setConfigError(`导入失败: ${String(error)}`);
    } finally {
      event.target.value = "";
    }
  }

  async function ensurePreviewSession(): Promise<string> {
    if (previewSessionId) return previewSessionId;
    if (!selectedDocumentId || !selectedSectionId || !selectedPersonaId) {
      throw new Error("请先选择人格、文档与章节。需要先处理文档，才能创建章节联动预览。");
    }
    const sectionTitle = sectionOptions.find((s) => s.id === selectedSectionId)?.title ?? "";
    const session = await createStudySession({
      documentId: selectedDocumentId,
      personaId: selectedPersonaId,
      sectionId: selectedSectionId,
      sectionTitle,
      themeHint: "人格色谱预览"
    });
    setPreviewSessionId(session.id);
    return session.id;
  }

  async function handleSendPreviewMessage() {
    if (!previewMessage.trim()) { setPreviewError("请输入预览消息。"); return; }
    setPreviewError("");
    setPreviewPending(true);
    try {
      const sessionId = await ensurePreviewSession();
      const response = await sendStudyMessage({ sessionId, message: previewMessage.trim() });
      setPreviewChat(response);
    } catch (error) {
      setPreviewError(String(error));
    } finally {
      setPreviewPending(false);
    }
  }

  return (
    <main className="with-app-nav" style={styles.page}>
      <TopNav currentPath="/persona-spectrum" />

      {/* ── Heading ── */}
      <div style={styles.heading}>
        <h1 style={styles.pageTitle}>人格色谱</h1>
        <p style={styles.pageDesc}>教师人格配置、插槽权重、导入导出与章节联动预览。</p>
      </div>

      {loadError ? <div style={styles.errorBanner}>加载失败: {loadError}</div> : null}

      <div style={styles.contentGrid}>
        {/* ── Left column: persona editor ── */}
        <section style={styles.editorPanel}>
          <div style={styles.panelHead}>
            <span style={styles.panelTitle}>人格参数编辑器</span>
          </div>

          <div style={styles.fieldGroup}>
            <label style={styles.fieldLabel}>当前人格</label>
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

          <div style={styles.fieldGroup}>
            <label style={styles.fieldLabel}>摘要</label>
            <textarea style={styles.textarea} value={draft.summary} onChange={(e) => updateDraft("summary", e.target.value)} />
          </div>

          <div style={styles.fieldGroup}>
            <label style={styles.fieldLabel}>人格插槽</label>
            <span style={styles.mutedText}>插槽属于人格认知层，决定“这个老师怎么想、怎么教”。</span>
            <div style={styles.actionsRow}>
              <button type="button" style={styles.ghostBtn} onClick={handleSortSlotsByPriority}>按优先级整理插槽</button>
              <span style={styles.mutedText}>排序规则：先按排序值（sortOrder）升序，再按权重（weight）降序。</span>
            </div>
            {draft.slots.map((slot, index) => (
              <div
                key={`${slot.kind}:${slot.label}:${index}`}
                style={{
                  ...styles.slotCard,
                  ...(draggingSlotIndex === index ? styles.slotCardDragging : null),
                  ...(dragOverSlotIndex === index && draggingSlotIndex !== index ? styles.slotCardDragOver : null),
                  ...(movePulse?.index === index
                    ? movePulse.direction === -1
                      ? styles.slotCardMoveUp
                      : styles.slotCardMoveDown
                    : null),
                }}
              >
                <div style={styles.slotHeader}>
                  <span
                    style={styles.dragHandle}
                    title="拖动排序"
                    draggable
                    onDragStart={() => handleDragStart(index)}
                    onDragEnd={handleDragEnd}
                    onDragOver={(event) => {
                      event.preventDefault();
                      handleDragOver(index);
                    }}
                    onDrop={(event) => {
                      event.preventDefault();
                      handleDrop(index);
                    }}
                  >
                    ⋮⋮
                  </span>
                  <select
                    style={styles.slotKindSelect}
                    value={slot.kind}
                    onChange={(e) => handleUpdateSlot(index, "kind", e.target.value)}
                    disabled={Boolean(slot.locked)}
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
                  />
                  <button type="button" style={styles.removeBtn} onClick={() => handleRemoveSlot(index)}>×</button>
                </div>
                <span style={styles.slotHintText}>{SLOT_KIND_HINTS[slot.kind] ?? SLOT_KIND_HINTS.custom}</span>
                <textarea
                  style={styles.slotContent}
                  value={slot.content}
                  placeholder={`请填写“${PERSONA_SLOT_KIND_LABELS[slot.kind as PersonaSlotKind] ?? slot.kind}”的具体内容。`}
                  onChange={(e) => handleUpdateSlot(index, "content", e.target.value)}
                  disabled={Boolean(slot.locked)}
                />
                <div style={styles.compactGrid}>
                  <label style={styles.fieldGroup}>
                    <span style={styles.fieldLabel}>权重（0-100）</span>
                    <input
                      style={styles.input}
                      type="number"
                      min={0}
                      max={100}
                      step={1}
                      value={slot.weight ?? 50}
                      onChange={(e) => handleUpdateSlot(index, "weight", Number(e.target.value))}
                      disabled={Boolean(slot.locked)}
                    />
                  </label>
                  <label style={styles.fieldGroup}>
                    <span style={styles.fieldLabel}>权重滑杆</span>
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
                  </label>
                </div>
                <div style={styles.actionsRow}>
                  <button type="button" style={styles.ghostBtn} onClick={() => handleMoveSlot(index, -1)}>上移</button>
                  <button type="button" style={styles.ghostBtn} onClick={() => handleMoveSlot(index, 1)}>下移</button>
                  <button
                    type="button"
                    style={styles.ghostBtn}
                    onClick={() => handleUpdateSlot(index, "locked", !slot.locked)}
                  >
                    {slot.locked ? "解锁" : "锁定"}
                  </button>
                  <button
                    type="button"
                    style={styles.ghostBtn}
                    onClick={() => void handleAssistSlot(index)}
                    disabled={assistPending || slotAssistIndex === index || Boolean(slot.locked)}
                  >
                    {slotAssistIndex === index ? "AI 重写中…" : "AI 重写此卡片"}
                  </button>
                  <span style={styles.mutedText}>逐卡片重写仅作用于当前卡片，不会覆盖其他插槽。</span>
                </div>
              </div>
            ))}
            <div style={styles.addSlotRow}>
              <span style={styles.mutedText}>添加插槽：</span>
              {SLOT_TEMPLATES.map((t) => (
                <button key={t.kind} type="button" style={styles.tagBtn} onClick={() => handleAddSlot(t.kind)}>
                  {PERSONA_SLOT_KIND_LABELS[t.kind]}
                </button>
              ))}
              <button type="button" style={styles.tagBtn} onClick={() => handleAddSlot("custom")}>自定义</button>
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
            <span style={styles.mutedText}>越高越保留原文，越低越允许模型重写。</span>
          </div>

          <div style={styles.actionsRow}>
            <button style={styles.ghostBtn} type="button" disabled={assistPending} onClick={handleAssistSetting}>
              {assistPending ? "AI 完善中…" : "AI 辅助完善设定"}
            </button>
            <span style={styles.mutedText}>该操作会对整套插槽进行联动改写。</span>
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
            <span style={styles.mutedText}>内置人格为只读，可编辑后使用「创建新人格」另存。</span>
          ) : null}
        </section>

        {/* ── Right column: three stacked panels ── */}
        <div style={styles.rightColumn}>
          {/* Panel: emotion/action preview */}
          <section style={styles.rightPanel}>
            <div style={styles.panelHead}>
              <span style={styles.panelTitle}>人格表现调参</span>
            </div>

            <div style={styles.fieldGroup}>
              <label style={styles.fieldLabel}>可用情绪（逗号分隔）</label>
              <input style={styles.input} value={draft.availableEmotionsText} onChange={(e) => updateDraft("availableEmotionsText", e.target.value)} />
              <span style={styles.mutedText}>表现层配置：用于控制角色事件渲染，不直接改写人格插槽文本。</span>
            </div>
            <div style={styles.fieldGroup}>
              <label style={styles.fieldLabel}>可用动作示例（逗号分隔）</label>
              <input style={styles.input} value={draft.availableActionsText} onChange={(e) => updateDraft("availableActionsText", e.target.value)} />
              <span style={styles.mutedText}>这里只是常见动作示例；实际生成时，模型可以输出更自然的动作短句。</span>
            </div>
            <div style={styles.fieldGroup}>
              <label style={styles.fieldLabel}>默认语气</label>
              <select style={styles.select} value={draft.defaultSpeechStyle} onChange={(e) => updateDraft("defaultSpeechStyle", e.target.value as SpeechStyle)}>
                {SPEECH_STYLES.map((s) => <option key={s} value={s}>{SPEECH_STYLE_LABELS[s] ?? s}</option>)}
              </select>
            </div>

            <div style={styles.compactGrid}>
              <div style={styles.fieldGroup}>
                <label style={styles.fieldLabel}>预览情绪</label>
                <select style={styles.select} value={previewEmotion} onChange={(e) => setPreviewEmotion(e.target.value as CharacterEmotion)}>
                  {(draftEmotionOptions.length ? draftEmotionOptions : CHARACTER_EMOTIONS).map((em) => (
                    <option key={em} value={em}>{EMOTION_LABELS[em] ?? em}</option>
                  ))}
                </select>
              </div>
              <div style={styles.fieldGroup}>
                <label style={styles.fieldLabel}>预览动作</label>
                <select style={styles.select} value={previewAction} onChange={(e) => setPreviewAction(e.target.value as CharacterAction)}>
                  {(draftActionOptions.length ? draftActionOptions : CHARACTER_ACTIONS).map((ac) => (
                    <option key={ac} value={ac}>{ACTION_LABELS[ac] ?? ac}</option>
                  ))}
                </select>
              </div>
              <div style={styles.fieldGroup}>
                <label style={styles.fieldLabel}>语气</label>
                <select style={styles.select} value={previewSpeech} onChange={(e) => setPreviewSpeech(e.target.value as SpeechStyle)}>
                  {SPEECH_STYLES.map((s) => <option key={s} value={s}>{SPEECH_STYLE_LABELS[s] ?? s}</option>)}
                </select>
              </div>
              <div style={styles.fieldGroup}>
                <label style={styles.fieldLabel}>时序</label>
                <select style={styles.select} value={previewTiming} onChange={(e) => setPreviewTiming(e.target.value as TimingHint)}>
                    <option value="instant">{TIMING_HINT_LABELS.instant}</option>
                    <option value="linger">{TIMING_HINT_LABELS.linger}</option>
                    <option value="after_text">{TIMING_HINT_LABELS.after_text}</option>
                </select>
              </div>
            </div>

            <CharacterShell persona={draftPersona} response={syntheticPreviewResponse} pending={false} />
          </section>

          {/* Panel: import/export */}
          <section style={styles.rightPanel}>
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
            <span style={styles.mutedText}>导入模板需为人格配置 JSON 结构（包含 slots 数组）。</span>
            <span style={styles.mutedText}>建议先导出一份模板，再基于模板编辑，避免字段缺失。</span>
            {configMessage ? <span style={styles.mutedText}>{configMessage}</span> : null}
            {configError ? <span style={styles.errorInline}>{configError}</span> : null}
          </section>

          {/* Panel: live preview */}
          <section style={styles.rightPanel}>
            <div style={styles.panelHead}>
              <span style={styles.panelTitle}>章节联动实时预览</span>
            </div>

            <div style={styles.compactGrid}>
              <div style={styles.fieldGroup}>
                <label style={styles.fieldLabel}>文档</label>
                <select style={styles.select} value={selectedDocumentId} onChange={(e) => { setSelectedDocumentId(e.target.value); setPreviewSessionId(""); setPreviewChat(null); }}>
                  {documents.map((d) => <option key={d.id} value={d.id}>{d.title}</option>)}
                </select>
              </div>
              <div style={styles.fieldGroup}>
                <label style={styles.fieldLabel}>章节</label>
                <select style={styles.select} value={selectedSectionId} onChange={(e) => { setSelectedSectionId(e.target.value); setPreviewSessionId(""); setPreviewChat(null); }}>
                  {sectionOptions.map((s) => <option key={s.id} value={s.id}>{s.title}</option>)}
                </select>
              </div>
            </div>

            <div style={styles.fieldGroup}>
              <label style={styles.fieldLabel}>联动提问</label>
              <textarea style={styles.textareaLg} value={previewMessage} onChange={(e) => setPreviewMessage(e.target.value)} />
            </div>

            <div style={styles.actionsRow}>
              <button style={styles.primaryBtn} onClick={handleSendPreviewMessage} disabled={previewPending}>
                {previewPending ? "预览生成中…" : "发送预览消息"}
              </button>
              {previewError ? <span style={styles.errorInline}>{previewError}</span> : null}
            </div>

            <div style={styles.assetCard}>
              <div style={styles.assetRow}><span style={styles.assetLabel}>渲染器</span><span>{assets?.renderer ?? "-"}</span></div>
              <div style={styles.assetRow}><span style={styles.assetLabel}>资源清单</span><span>{assets ? JSON.stringify(assets.assetManifest) : "-"}</span></div>
              {assetsError ? <div style={styles.errorInline}>{assetsError}</div> : null}
            </div>

            {previewChat ? (
              <>
                <CharacterShell persona={draftPersona} response={previewChat} pending={previewPending} />
                <div style={styles.chatReply}>{previewChat.reply}</div>
              </>
            ) : (
              <span style={styles.mutedText}>发送一条消息后，这里会展示真实章节联动的返回与角色事件。</span>
            )}
          </section>
        </div>
      </div>
    </main>
  );
}

/* ─── Helpers (unchanged) ─── */

function personaToDraft(persona: PersonaProfile): PersonaDraft {
  return {
    name: persona.name,
    summary: persona.summary,
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

function resolveSections(document: DocumentRecord): Array<{ id: string; title: string }> {
  return document.studyUnits.length
    ? document.studyUnits.map((unit) => ({ id: unit.id, title: `学习单元：${unit.title}` }))
    : document.sections.map((section) => ({ id: section.id, title: `章节：${section.title}` }));
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
    minHeight: "100vh",
    maxWidth: 1400,
    margin: "0 auto",
    padding: "20px 24px 40px",
    display: "grid",
    gap: 20,
    alignContent: "start",
  },
  heading: {
    display: "grid",
    gap: 6,
    paddingBottom: 14,
    borderBottom: "1px solid var(--border)",
  },
  pageTitle: { margin: 0, fontSize: 20, fontWeight: 700, color: "var(--ink)", lineHeight: 1.2 },
  pageDesc: { margin: 0, fontSize: 13, color: "var(--muted)", lineHeight: 1.6 },

  /* 2-column content grid */
  contentGrid: {
    display: "grid",
    gridTemplateColumns: "minmax(0, 3fr) minmax(0, 2fr)",
    border: "1px solid var(--border)",
    alignItems: "start",
  },

  /* Left: editor */
  editorPanel: {
    padding: 20,
    display: "grid",
    gap: 14,
    alignContent: "start",
  },

  /* Right: stacked panels container */
  rightColumn: {
    borderLeft: "1px solid var(--border)",
    display: "grid",
    alignContent: "start",
    gap: 0,
  },

  /* Individual right-column panels */
  rightPanel: {
    padding: 20,
    display: "grid",
    gap: 14,
    alignContent: "start",
    borderBottom: "1px solid var(--border)",
  },

  /* Panel header */
  panelHead: {
    paddingBottom: 10,
    borderBottom: "1px solid var(--border)",
    marginBottom: 2,
  },
  panelTitle: {
    fontSize: 13,
    fontWeight: 700,
    color: "var(--ink)",
    letterSpacing: "0.01em",
  },

  /* Form elements */
  fieldGroup: {
    display: "grid",
    gap: 6,
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
  slotCardDragOver: {
    borderColor: "var(--accent)",
    boxShadow: "0 0 0 2px var(--accent-soft) inset",
    transform: "translateY(-2px)",
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
    background: "white",
    padding: "0 6px",
    fontSize: 12,
    color: "var(--ink)",
  },
  slotLabelInput: {
    flex: 1,
    height: 30,
    border: "1px solid var(--border)",
    background: "white",
    padding: "0 8px",
    fontSize: 12,
    color: "var(--ink)",
  },
  removeBtn: {
    flex: "0 0 auto",
    height: 30,
    width: 30,
    border: "1px solid var(--border)",
    background: "white",
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
    background: "white",
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
  addSlotRow: {
    display: "flex",
    gap: 6,
    alignItems: "center",
    flexWrap: "wrap",
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
    background: "white",
    color: "var(--ink)",
    height: 36,
    padding: "0 12px",
    cursor: "pointer",
    fontSize: 13,
    display: "inline-flex",
    alignItems: "center",
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

  /* Asset info card */
  assetCard: {
    border: "1px solid var(--border)",
    background: "var(--panel)",
    padding: "10px",
    display: "grid",
    gap: 6,
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
    border: "1px solid #f0b8b8",
    background: "#fff4f4",
    color: "#9c2020",
    padding: "8px 12px",
    fontSize: 13,
  },
  errorInline: { color: "#9c2020", fontSize: 12 },
};
