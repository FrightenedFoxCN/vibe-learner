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

interface PersonaDraft {
  name: string;
  summary: string;
  systemPrompt: string;
  slots: PersonaSlot[];
  availableEmotionsText: string;
  availableActionsText: string;
  defaultSpeechStyle: SpeechStyle;
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
  {
    kind: "worldview",
    text: "你曾在一所强调自学与互助的学院担任导学员，习惯先给学习者稳定感，再推进挑战。"
  },
  {
    kind: "past_experiences",
    text: "曾参与多个跨学科项目，习惯将复杂问题拆解为可验证的小步骤，再带领学习者逐步落地。"
  },
  {
    kind: "thinking_style",
    text: "常用短句确认学习者状态，例如「我们先把这一点站稳」，避免连续高压输出。"
  },
  {
    kind: "teaching_method",
    text: "讲解时遵循「概念-例子-反例-迁移」的节奏，每次只推进一个关键难点。"
  },
  {
    kind: "correction_style",
    text: "纠错优先指出可操作改进，不使用否定人格的措辞；鼓励具体进步，不做空泛夸奨。"
  }
];

const DEFAULT_CONFIG_TEMPLATE: CreatePersonaInput = {
  name: "模板教师",
  summary: "示例人格：强调章节脉络与可执行反馈。",
  systemPrompt:
    "Prioritize chapter-grounded explanation, progressive questioning, and concise actionable feedback.",
  slots: [
    { kind: "worldview", label: "世界观起点", content: "来自学院导学中心，擅长把抽象概念拆成可验证的小步任务，并用温和语气引导学习者持续推进。" },
    { kind: "teaching_method", label: "教学方法", content: "structured, guided" },
    { kind: "narrative_mode", label: "叙事模式", content: "grounded" },
    { kind: "encouragement_style", label: "鼓励策略", content: "small wins" },
    { kind: "correction_style", label: "纠错策略", content: "precise but warm" }
  ],
  availableEmotions: ["calm", "encouraging", "serious"],
  availableActions: ["idle", "explain", "point", "reflect"],
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
  const [assistError, setAssistError] = useState("");
  const [retainRatio, setRetainRatio] = useState(0.7);
  const [configMessage, setConfigMessage] = useState("");
  const [configError, setConfigError] = useState("");

  const [previewEmotion, setPreviewEmotion] = useState<CharacterEmotion>("calm");
  const [previewAction, setPreviewAction] = useState<CharacterAction>("idle");
  const [previewSpeech, setPreviewSpeech] = useState<SpeechStyle>("warm");
  const [previewIntensity, setPreviewIntensity] = useState(0.6);
  const [previewSceneHint, setPreviewSceneHint] = useState("persona_spectrum_preview");
  const [previewTiming, setPreviewTiming] = useState<TimingHint>("instant");

  const [previewSessionId, setPreviewSessionId] = useState("");
  const [previewMessage, setPreviewMessage] = useState(
    "请用这个人格风格解释当前章节的核心概念。"
  );
  const [previewPending, setPreviewPending] = useState(false);
  const [previewError, setPreviewError] = useState("");
  const [previewChat, setPreviewChat] = useState<StudyChatExchangeResponse | null>(null);

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
        if (initialPersona) {
          setSelectedPersonaId(initialPersona.id);
          setDraft(personaToDraft(initialPersona));
        }
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

  const draftEmotionOptions = useMemo(
    () => coerceEmotions(draft.availableEmotionsText),
    [draft.availableEmotionsText]
  );
  const draftActionOptions = useMemo(
    () => coerceActions(draft.availableActionsText),
    [draft.availableActionsText]
  );

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
      intensity: previewIntensity,
      speechStyle: previewSpeech,
      sceneHint: previewSceneHint,
      lineSegmentId: "persona-spectrum-debug",
      timingHint: previewTiming
    };
    return {
      reply:
        "这是色谱调试预览，不会调用模型。可先调教情绪、动作与语速，再进入章节联动预览。",
      citations: [],
      characterEvents: [event]
    };
  }, [previewAction, previewEmotion, previewIntensity, previewSceneHint, previewSpeech, previewTiming]);

  function updateDraft<K extends keyof PersonaDraft>(key: K, value: PersonaDraft[K]) {
    if (assistError) setAssistError("");
    setDraft((prev) => ({ ...prev, [key]: value }));
  }

  function handleAddSlot(kind: PersonaSlotKind | string) {
    const label = PERSONA_SLOT_KIND_LABELS[kind as PersonaSlotKind] ?? kind;
    const template = SLOT_TEMPLATES.find((t) => t.kind === kind);
    setDraft((prev) => ({
      ...prev,
      slots: [...prev.slots, { kind, label, content: template?.text ?? "" }]
    }));
  }

  function handleUpdateSlot(index: number, field: keyof PersonaSlot, value: string) {
    if (assistError) setAssistError("");
    setDraft((prev) => {
      const next = [...prev.slots];
      next[index] = { ...next[index], [field]: value };
      if (field === "kind") {
        next[index].label = PERSONA_SLOT_KIND_LABELS[value as PersonaSlotKind] ?? value;
      }
      return { ...prev, slots: next };
    });
  }

  function handleRemoveSlot(index: number) {
    setDraft((prev) => ({ ...prev, slots: prev.slots.filter((_, i) => i !== index) }));
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
        slots: result.slots.length ? result.slots : prev.slots,
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
    if (isReadonlyPersona) {
      setSaveError("内置人格为只读，无法更新。请使用「创建新人格」另存。");
      return;
    }
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
      throw new Error(
        "\u8bf7\u5148\u9009\u62e9\u4eba\u683c\u3001\u6587\u6863\u4e0e\u7ae0\u8282\u3002\u9700\u8981\u5148\u5904\u7406\u6587\u6863\uff0c\u624d\u80fd\u521b\u5efa\u7ae0\u8282\u8054\u52a8\u9884\u89c8\u3002"
      );
    }
    const sectionTitle = sectionOptions.find((s) => s.id === selectedSectionId)?.title ?? "";
    const session = await createStudySession({
      documentId: selectedDocumentId,
      personaId: selectedPersonaId,
      sectionId: selectedSectionId,
      sectionTitle,
      themeHint: "persona_spectrum_preview"
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

      <div style={styles.topbar}>
        <span style={styles.topbarTitle}>人格色谱</span>
        <span style={styles.topbarSub}>
          教师人格配置、情绪区间、导入导出与章节联动预览。
        </span>
      </div>

      {loadError ? <div style={styles.error}>加载失败: {loadError}</div> : null}

      <div style={styles.contentGrid}>
        {/* Persona editor */}
        <section style={styles.panel}>
          <h2 style={styles.sectionTitle}>人格参数编辑器</h2>
          <label style={styles.fieldLabel}>当前人格</label>
          <select
            style={styles.select}
            value={selectedPersonaId}
            onChange={(e) => setSelectedPersonaId(e.target.value)}
          >
            {personas.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name} ({p.source})
              </option>
            ))}
          </select>

          <label style={styles.fieldLabel}>名称</label>
          <input style={styles.input} value={draft.name} onChange={(e) => updateDraft("name", e.target.value)} />

          <label style={styles.fieldLabel}>摘要</label>
          <textarea style={styles.textarea} value={draft.summary} onChange={(e) => updateDraft("summary", e.target.value)} />

          <label style={styles.fieldLabel}>人格插槽</label>
          {draft.slots.map((slot, index) => (
            <div key={index} style={styles.slotCard}>
              <div style={styles.slotHeader}>
                <select
                  style={styles.slotKindSelect}
                  value={slot.kind}
                  onChange={(e) => handleUpdateSlot(index, "kind", e.target.value)}
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
                />
                <button type="button" style={styles.removeButton} onClick={() => handleRemoveSlot(index)} title="移除">
                  ×
                </button>
              </div>
              <textarea
                style={styles.slotContent}
                value={slot.content}
                placeholder={`${PERSONA_SLOT_KIND_LABELS[slot.kind as PersonaSlotKind] ?? slot.kind}内容…`}
                onChange={(e) => handleUpdateSlot(index, "content", e.target.value)}
              />
            </div>
          ))}

          <div style={styles.addSlotRow}>
            <span style={styles.fieldLabel}>添加插槽：</span>
            {SLOT_TEMPLATES.map((t) => (
              <button key={t.kind} type="button" style={styles.linkButton} onClick={() => handleAddSlot(t.kind)}>
                {PERSONA_SLOT_KIND_LABELS[t.kind]}
              </button>
            ))}
            <button type="button" style={styles.linkButton} onClick={() => handleAddSlot("custom")}>
              自定义
            </button>
          </div>

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
          <div style={styles.muted}>越高越保留原文，越低越允许模型重写。</div>
          <div style={styles.actionsRow}>
            <button style={styles.ghostButton} type="button" disabled={assistPending} onClick={handleAssistSetting}>
              {assistPending ? "AI 完善中..." : "人工智能辅助完善设定"}
            </button>
            {assistError ? <span style={styles.errorInline}>{assistError}</span> : null}
          </div>

          <label style={styles.fieldLabel}>系统提示词</label>
          <textarea style={styles.textareaLg} value={draft.systemPrompt} onChange={(e) => updateDraft("systemPrompt", e.target.value)} />

          <div style={styles.actionsRow}>
            <button style={styles.primaryButton} disabled={savingPersona} onClick={handleCreatePersona}>
              {savingPersona ? "保存中..." : "创建新人格"}
            </button>
            <button style={styles.ghostButton} disabled={savingPersona || isReadonlyPersona} onClick={handleUpdatePersona}>
              {savingPersona ? "保存中..." : "更新当前人格"}
            </button>
            {saveError ? <span style={styles.errorInline}>{saveError}</span> : null}
          </div>
          {isReadonlyPersona ? (
            <div style={styles.muted}>内置人格为只读，可编辑后使用「创建新人格」另存。</div>
          ) : null}
        </section>

        {/* Emotion/action preview panel */}
        <section style={styles.panel}>
          <h2 style={styles.sectionTitle}>情绪与动作色谱调试面板</h2>
          <label style={styles.fieldLabel}>可用情绪（逗号分隔）</label>
          <input style={styles.input} value={draft.availableEmotionsText} onChange={(e) => updateDraft("availableEmotionsText", e.target.value)} />
          <label style={styles.fieldLabel}>可用动作（逗号分隔）</label>
          <input style={styles.input} value={draft.availableActionsText} onChange={(e) => updateDraft("availableActionsText", e.target.value)} />
          <label style={styles.fieldLabel}>默认语气</label>
          <select style={styles.select} value={draft.defaultSpeechStyle} onChange={(e) => updateDraft("defaultSpeechStyle", e.target.value as SpeechStyle)}>
            {SPEECH_STYLES.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>

          <div style={styles.compactGrid}>
            <div>
              <label style={styles.fieldLabel}>预览情绪</label>
              <select style={styles.select} value={previewEmotion} onChange={(e) => setPreviewEmotion(e.target.value as CharacterEmotion)}>
                {(draftEmotionOptions.length ? draftEmotionOptions : CHARACTER_EMOTIONS).map((em) => (
                  <option key={em} value={em}>{em}</option>
                ))}
              </select>
            </div>
            <div>
              <label style={styles.fieldLabel}>预览动作</label>
              <select style={styles.select} value={previewAction} onChange={(e) => setPreviewAction(e.target.value as CharacterAction)}>
                {(draftActionOptions.length ? draftActionOptions : CHARACTER_ACTIONS).map((ac) => (
                  <option key={ac} value={ac}>{ac}</option>
                ))}
              </select>
            </div>
            <div>
              <label style={styles.fieldLabel}>语气</label>
              <select style={styles.select} value={previewSpeech} onChange={(e) => setPreviewSpeech(e.target.value as SpeechStyle)}>
                {SPEECH_STYLES.map((s) => <option key={s} value={s}>{s}</option>)}
              </select>
            </div>
            <div>
              <label style={styles.fieldLabel}>时序</label>
              <select style={styles.select} value={previewTiming} onChange={(e) => setPreviewTiming(e.target.value as TimingHint)}>
                <option value="instant">instant</option>
                <option value="linger">linger</option>
                <option value="after_text">after_text</option>
              </select>
            </div>
          </div>

          <label style={styles.fieldLabel}>强度 {previewIntensity.toFixed(2)}</label>
          <input style={styles.range} type="range" min={0} max={1} step={0.05} value={previewIntensity} onChange={(e) => setPreviewIntensity(Number(e.target.value))} />
          <label style={styles.fieldLabel}>场景提示</label>
          <input style={styles.input} value={previewSceneHint} onChange={(e) => setPreviewSceneHint(e.target.value)} />
          <CharacterShell persona={draftPersona} response={syntheticPreviewResponse} pending={false} />
        </section>

        {/* Import/export panel */}
        <section style={styles.panel}>
          <h2 style={styles.sectionTitle}>配置导入/导出</h2>
          <div style={styles.actionsRow}>
            <button style={styles.ghostButton} type="button" onClick={handleDownloadTemplate}>下载配置模板</button>
            <button style={styles.ghostButton} type="button" onClick={handleExportConfig}>导出当前配置</button>
            <label style={styles.ghostButton}>
              导入配置文件
              <input type="file" accept="application/json,.json" style={styles.hiddenFileInput} onChange={handleImportConfig} />
            </label>
          </div>
          <div style={styles.muted}>
            导入模板需为 <code>CreatePersonaInput</code> JSON 结构（包含 slots 数组）。
          </div>
          {configMessage ? <div style={styles.muted}>{configMessage}</div> : null}
          {configError ? <div style={styles.errorInline}>{configError}</div> : null}
        </section>

        {/* Live preview panel */}
        <section style={styles.panel}>
          <h2 style={styles.sectionTitle}>与章节对话联动的实时人格预览</h2>
          <div style={styles.compactGrid}>
            <div>
              <label style={styles.fieldLabel}>文档</label>
              <select style={styles.select} value={selectedDocumentId} onChange={(e) => { setSelectedDocumentId(e.target.value); setPreviewSessionId(""); setPreviewChat(null); }}>
                {documents.map((d) => <option key={d.id} value={d.id}>{d.title}</option>)}
              </select>
            </div>
            <div>
              <label style={styles.fieldLabel}>章节</label>
              <select style={styles.select} value={selectedSectionId} onChange={(e) => { setSelectedSectionId(e.target.value); setPreviewSessionId(""); setPreviewChat(null); }}>
                {sectionOptions.map((s) => <option key={s.id} value={s.id}>{s.title}</option>)}
              </select>
            </div>
          </div>
          <label style={styles.fieldLabel}>联动提问</label>
          <textarea style={styles.textareaLg} value={previewMessage} onChange={(e) => setPreviewMessage(e.target.value)} />
          <div style={styles.actionsRow}>
            <button style={styles.primaryButton} onClick={handleSendPreviewMessage} disabled={previewPending}>
              {previewPending ? "预览生成中..." : "发送预览消息"}
            </button>
            {previewError ? <span style={styles.errorInline}>{previewError}</span> : null}
          </div>
          <div style={styles.assetCard}>
            <div style={styles.assetRow}><span style={styles.assetLabel}>Renderer</span><span>{assets?.renderer ?? "-"}</span></div>
            <div style={styles.assetRow}><span style={styles.assetLabel}>Manifest</span><span>{assets ? JSON.stringify(assets.assetManifest) : "-"}</span></div>
            {assetsError ? <div style={styles.errorInline}>{assetsError}</div> : null}
          </div>
          {previewChat ? (
            <>
              <CharacterShell persona={draftPersona} response={previewChat} pending={previewPending} />
              <div style={styles.chatReply}>{previewChat.reply}</div>
            </>
          ) : (
            <div style={styles.muted}>发送一条消息后，这里会展示真实章节联动的返回与角色事件。</div>
          )}
        </section>
      </div>
    </main>
  );
}

function personaToDraft(persona: PersonaProfile): PersonaDraft {
  return {
    name: persona.name,
    summary: persona.summary,
    systemPrompt: persona.systemPrompt,
    slots: persona.slots ?? [],
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
    slots: draft.slots,
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
    slots: snapshot.slots ?? [],
    availableEmotionsText: (snapshot.availableEmotions ?? CHARACTER_EMOTIONS).join(", "),
    availableActionsText: (snapshot.availableActions ?? CHARACTER_ACTIONS).join(", "),
    defaultSpeechStyle: snapshot.defaultSpeechStyle ?? "warm"
  };
}

function splitCsv(value: string): string[] {
  return value.split(",").map((item) => item.trim()).filter(Boolean);
}

function coerceEmotions(value: string): CharacterEmotion[] {
  const allowed = new Set<string>(CHARACTER_EMOTIONS);
  return splitCsv(value).filter((item): item is CharacterEmotion => allowed.has(item));
}

function coerceActions(value: string): CharacterAction[] {
  const allowed = new Set<string>(CHARACTER_ACTIONS);
  return splitCsv(value).filter((item): item is CharacterAction => allowed.has(item));
}

function resolveSections(document: DocumentRecord): Array<{ id: string; title: string }> {
  return document.studyUnits.length
    ? document.studyUnits.map((unit) => ({ id: unit.id, title: `Study Unit: ${unit.title}` }))
    : document.sections.map((section) => ({ id: section.id, title: `Section: ${section.title}` }));
}

function normalizeImportedPersonaConfig(parsed: Record<string, unknown>): CreatePersonaInput {
  const name = String(parsed.name ?? "").trim();
  const systemPrompt = String(parsed.systemPrompt ?? parsed.system_prompt ?? "").trim();
  if (!name) throw new Error("缺少 name 字段");
  if (!systemPrompt) throw new Error("缺少 systemPrompt 字段");

  let slots: PersonaSlot[] = [];
  if (Array.isArray(parsed.slots)) {
    slots = parsed.slots
      .filter((s): s is Record<string, unknown> => typeof s === "object" && s !== null)
      .map((s) => ({
        kind: String(s.kind ?? "custom"),
        label: String(s.label ?? s.kind ?? ""),
        content: String(s.content ?? "")
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

const styles: Record<string, CSSProperties> = {
  page: { minHeight: "100vh", maxWidth: 1360, margin: "0 auto", padding: "20px 24px 32px", display: "grid", gap: 16, alignContent: "start" },
  topbar: { display: "flex", alignItems: "baseline", gap: 12, paddingBottom: 12, flexWrap: "wrap" },
  topbarTitle: { fontSize: 16, fontWeight: 700, color: "var(--ink)" },
  topbarSub: { fontSize: 13, color: "var(--muted)" },
  contentGrid: { display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(360px, 1fr))", gap: 14, alignItems: "start" },
  panel: { border: "1px solid var(--border)", background: "white", padding: 14, display: "grid", gap: 8, alignContent: "start" },
  sectionTitle: { margin: 0, fontSize: 14, fontWeight: 700 },
  fieldLabel: { fontSize: 12, color: "var(--muted)" },
  input: { width: "100%", minHeight: 36, border: "1px solid var(--border)", background: "white", padding: "8px 10px" },
  select: { width: "100%", minHeight: 36, border: "1px solid var(--border)", background: "white", padding: "8px 10px" },
  textarea: { width: "100%", minHeight: 72, border: "1px solid var(--border)", background: "white", padding: "8px 10px", resize: "vertical" },
  textareaLg: { width: "100%", minHeight: 120, border: "1px solid var(--border)", background: "white", padding: "8px 10px", resize: "vertical" },
  slotCard: { border: "1px solid var(--border)", background: "var(--panel)", padding: "8px 10px", display: "grid", gap: 6 },
  slotHeader: { display: "flex", gap: 6, alignItems: "center" },
  slotKindSelect: { flex: "0 0 auto", minHeight: 30, border: "1px solid var(--border)", background: "white", padding: "4px 6px", fontSize: 12 },
  slotLabelInput: { flex: 1, minHeight: 30, border: "1px solid var(--border)", background: "white", padding: "4px 6px", fontSize: 12 },
  removeButton: { flex: "0 0 auto", minHeight: 30, minWidth: 30, border: "1px solid var(--border)", background: "white", color: "var(--muted)", cursor: "pointer", fontSize: 14, lineHeight: 1 },
  slotContent: { width: "100%", minHeight: 72, border: "1px solid var(--border)", background: "white", padding: "6px 8px", resize: "vertical", fontSize: 12 },
  addSlotRow: { display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" },
  primaryButton: { border: "1px solid var(--accent)", background: "var(--accent)", color: "white", minHeight: 36, padding: "0 12px", cursor: "pointer" },
  ghostButton: { border: "1px solid var(--border)", background: "white", color: "var(--ink)", minHeight: 36, padding: "0 12px", cursor: "pointer" },
  linkButton: { border: "1px solid var(--border)", background: "white", color: "var(--accent)", minHeight: 30, padding: "0 10px", cursor: "pointer", fontSize: 12 },
  actionsRow: { display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" },
  compactGrid: { display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: 8 },
  range: { width: "100%" },
  muted: { fontSize: 12, color: "var(--muted)" },
  hiddenFileInput: { display: "none" },
  assetCard: { border: "1px solid var(--border)", background: "var(--panel)", padding: "8px 10px", display: "grid", gap: 6 },
  assetRow: { display: "grid", gridTemplateColumns: "96px 1fr", gap: 8, fontSize: 12, wordBreak: "break-all" },
  assetLabel: { color: "var(--muted)" },
  chatReply: { padding: "10px 12px", border: "1px solid var(--border)", background: "var(--panel)", fontSize: 13, lineHeight: 1.6 },
  error: { border: "1px solid #f0b8b8", background: "#fff4f4", color: "#9c2020", padding: "8px 10px", fontSize: 13 },
  errorInline: { color: "#9c2020", fontSize: 12 }
};
