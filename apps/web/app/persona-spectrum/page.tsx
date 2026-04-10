"use client";

import { useEffect, useMemo, useState } from "react";
import type { CSSProperties } from "react";
import {
  CHARACTER_ACTIONS,
  CHARACTER_EMOTIONS,
  SPEECH_STYLES,
  type CharacterAction,
  type CharacterEmotion,
  type CharacterStateEvent,
  type CreatePersonaInput,
  type DocumentRecord,
  type PersonaProfile,
  type SpeechStyle,
  type StudyChatResponse
} from "@gal-learner/shared";

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

const VERSION_STORAGE_KEY = "gal-persona-spectrum-versions";

type TimingHint = "instant" | "linger" | "after_text";

interface PersonaDraft {
  name: string;
  summary: string;
  backgroundStory: string;
  systemPrompt: string;
  teachingStyleText: string;
  narrativeMode: "grounded" | "light_story";
  encouragementStyle: string;
  correctionStyle: string;
  availableEmotionsText: string;
  availableActionsText: string;
  defaultSpeechStyle: SpeechStyle;
}

interface PersonaVersion {
  id: string;
  label: string;
  createdAt: string;
  snapshot: CreatePersonaInput;
}

const EMPTY_DRAFT: PersonaDraft = {
  name: "",
  summary: "",
  backgroundStory: "",
  systemPrompt: "",
  teachingStyleText: "",
  narrativeMode: "grounded",
  encouragementStyle: "",
  correctionStyle: "",
  availableEmotionsText: CHARACTER_EMOTIONS.join(", "),
  availableActionsText: CHARACTER_ACTIONS.join(", "),
  defaultSpeechStyle: "warm"
};

const BACKGROUND_TEMPLATES: Array<{ id: string; label: string; text: string }> = [
  {
    id: "origin",
    label: "世界观起点",
    text: "你曾在一所强调自学与互助的学院担任导学员，习惯先给学习者稳定感，再推进挑战。"
  },
  {
    id: "style",
    label: "教学方法",
    text: "讲解时遵循“概念-例子-反例-迁移”的节奏，每次只推进一个关键难点。"
  },
  {
    id: "tone",
    label: "语气口癖",
    text: "常用短句确认学习者状态，例如“我们先把这一点站稳”，避免连续高压输出。"
  },
  {
    id: "boundary",
    label: "互动边界",
    text: "纠错优先指出可操作改进，不使用否定人格的措辞；鼓励具体进步，不做空泛夸奖。"
  }
];

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

  const [versionsByPersona, setVersionsByPersona] = useState<Record<string, PersonaVersion[]>>({});
  const [versionLabel, setVersionLabel] = useState("");

  const [previewEmotion, setPreviewEmotion] = useState<CharacterEmotion>("calm");
  const [previewAction, setPreviewAction] = useState<CharacterAction>("idle");
  const [previewSpeech, setPreviewSpeech] = useState<SpeechStyle>("warm");
  const [previewIntensity, setPreviewIntensity] = useState(0.6);
  const [previewSceneHint, setPreviewSceneHint] = useState("persona_spectrum_preview");
  const [previewTiming, setPreviewTiming] = useState<TimingHint>("instant");

  const [previewSessionId, setPreviewSessionId] = useState("");
  const [previewMessage, setPreviewMessage] = useState("请用这个人格风格解释当前章节的核心概念。");
  const [previewPending, setPreviewPending] = useState(false);
  const [previewError, setPreviewError] = useState("");
  const [previewChat, setPreviewChat] = useState<StudyChatExchangeResponse | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function bootstrap() {
      setLoadError("");
      try {
        const [personaList, documentList] = await Promise.all([listPersonas(), listDocuments()]);
        if (cancelled) {
          return;
        }
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
        if (!cancelled) {
          setLoadError(String(error));
        }
      }
    }

    bootstrap();
    const savedVersions = readSavedVersions();
    setVersionsByPersona(savedVersions);

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const selectedPersona = personas.find((persona) => persona.id === selectedPersonaId);
    if (!selectedPersona) {
      return;
    }
    setDraft(personaToDraft(selectedPersona));
    setPreviewEmotion(selectedPersona.availableEmotions[0] ?? "calm");
    setPreviewAction(selectedPersona.availableActions[0] ?? "idle");
    setPreviewSpeech(selectedPersona.defaultSpeechStyle);
    setPreviewChat(null);
    setPreviewSessionId("");
  }, [selectedPersonaId, personas]);

  useEffect(() => {
    if (!selectedPersonaId) {
      setAssets(null);
      setAssetsError("");
      return;
    }
    let cancelled = false;

    async function loadAssets() {
      setAssetsError("");
      try {
        const nextAssets = await getPersonaAssets(selectedPersonaId);
        if (!cancelled) {
          setAssets(nextAssets);
        }
      } catch (error) {
        if (!cancelled) {
          setAssets(null);
          setAssetsError(String(error));
        }
      }
    }

    loadAssets();

    return () => {
      cancelled = true;
    };
  }, [selectedPersonaId]);

  useEffect(() => {
    if (!selectedDocumentId) {
      setSelectedSectionId("");
      return;
    }
    const document = documents.find((item) => item.id === selectedDocumentId);
    if (!document) {
      return;
    }
    const options = resolveSections(document);
    if (!options.find((option) => option.id === selectedSectionId)) {
      setSelectedSectionId(options[0]?.id ?? "");
    }
  }, [documents, selectedDocumentId, selectedSectionId]);

  const sectionOptions = useMemo(() => {
    const document = documents.find((item) => item.id === selectedDocumentId);
    return document ? resolveSections(document) : [];
  }, [documents, selectedDocumentId]);

  const draftEmotionOptions = useMemo(
    () => coerceEmotions(draft.availableEmotionsText),
    [draft.availableEmotionsText]
  );

  const draftActionOptions = useMemo(
    () => coerceActions(draft.availableActionsText),
    [draft.availableActionsText]
  );

  const versions = versionsByPersona[selectedPersonaId] ?? [];
  const selectedPersona = useMemo(
    () => personas.find((persona) => persona.id === selectedPersonaId) ?? null,
    [personas, selectedPersonaId]
  );
  const isReadonlyPersona = selectedPersona?.source === "builtin";

  const draftPersona = useMemo<PersonaProfile>(() => {
    const emotionOptions: CharacterEmotion[] = draftEmotionOptions.length
      ? draftEmotionOptions
      : ["calm"];
    const actionOptions: CharacterAction[] = draftActionOptions.length
      ? draftActionOptions
      : ["idle"];
    return {
      id: selectedPersonaId || "persona-draft",
      name: draft.name || "未命名人格",
      source: "user",
      summary: draft.summary,
      backgroundStory: draft.backgroundStory,
      systemPrompt: draft.systemPrompt,
      teachingStyle: splitCsv(draft.teachingStyleText),
      narrativeMode: draft.narrativeMode,
      encouragementStyle: draft.encouragementStyle,
      correctionStyle: draft.correctionStyle,
      availableEmotions: emotionOptions,
      availableActions: actionOptions,
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
      reply: "这是色谱调试预览，不会调用模型。可先调教情绪、动作与语速，再进入章节联动预览。",
      citations: [],
      characterEvents: [event]
    };
  }, [previewAction, previewEmotion, previewIntensity, previewSceneHint, previewSpeech, previewTiming]);

  function updateDraft<K extends keyof PersonaDraft>(key: K, value: PersonaDraft[K]) {
    if (assistError) {
      setAssistError("");
    }
    setDraft((prev) => ({ ...prev, [key]: value }));
  }

  function handleInsertTemplate(templateText: string) {
    setDraft((prev) => ({
      ...prev,
      backgroundStory: prev.backgroundStory.trim()
        ? `${prev.backgroundStory.trim()}\n\n${templateText}`
        : templateText
    }));
  }

  async function handleAssistSetting() {
    setAssistError("");
    setAssistPending(true);
    try {
      const result = await assistPersonaSetting({
        name: draft.name.trim(),
        summary: draft.summary.trim(),
        backgroundStory: draft.backgroundStory.trim(),
        teachingStyle: splitCsv(draft.teachingStyleText),
        narrativeMode: draft.narrativeMode,
        encouragementStyle: draft.encouragementStyle.trim(),
        correctionStyle: draft.correctionStyle.trim(),
        rewriteStrength: Number((1 - retainRatio).toFixed(2))
      });
      setDraft((prev) => ({
        ...prev,
        backgroundStory: result.backgroundStory || prev.backgroundStory,
        systemPrompt: result.systemPromptSuggestion || prev.systemPrompt
      }));
    } catch (error) {
      setAssistError(String(error));
    } finally {
      setAssistPending(false);
    }
  }

  async function handleCreatePersona() {
    setSaveError("");
    const payload = draftToCreatePersonaInput(draft);
    if (!payload.name) {
      setSaveError("请先填写人格名称。");
      return;
    }
    if (!payload.systemPrompt) {
      setSaveError("请先填写系统提示词。");
      return;
    }

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
    if (!selectedPersonaId) {
      setSaveError("请先选择要更新的人格。");
      return;
    }
    if (isReadonlyPersona) {
      setSaveError("内置人格为只读，无法更新。请使用“创建新人格”另存。");
      return;
    }
    setSaveError("");
    const payload = draftToCreatePersonaInput(draft);
    if (!payload.name) {
      setSaveError("请先填写人格名称。");
      return;
    }
    if (!payload.systemPrompt) {
      setSaveError("请先填写系统提示词。");
      return;
    }

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

  function handleSaveVersion() {
    if (!selectedPersonaId) {
      return;
    }
    const label = versionLabel.trim() || `版本 ${new Date().toLocaleString()}`;
    const nextVersion: PersonaVersion = {
      id: `v-${Date.now()}`,
      label,
      createdAt: new Date().toISOString(),
      snapshot: draftToCreatePersonaInput(draft)
    };
    const nextVersions = {
      ...versionsByPersona,
      [selectedPersonaId]: [nextVersion, ...(versionsByPersona[selectedPersonaId] ?? [])].slice(0, 20)
    };
    setVersionsByPersona(nextVersions);
    writeSavedVersions(nextVersions);
    setVersionLabel("");
  }

  function handleReplayVersion(versionId: string) {
    const matched = versions.find((item) => item.id === versionId);
    if (!matched) {
      return;
    }
    setDraft(createInputToDraft(matched.snapshot));
    setPreviewEmotion(matched.snapshot.availableEmotions?.[0] ?? "calm");
    setPreviewAction(matched.snapshot.availableActions?.[0] ?? "idle");
    setPreviewSpeech(matched.snapshot.defaultSpeechStyle ?? "warm");
  }

  async function ensurePreviewSession(): Promise<string> {
    if (previewSessionId) {
      return previewSessionId;
    }
    if (!selectedDocumentId || !selectedSectionId || !selectedPersonaId) {
      throw new Error("请先选择人格、文档与章节。\n需要先处理文档，才能创建章节联动预览。".replace("\\n", ""));
    }
    const sectionTitle = sectionOptions.find((section) => section.id === selectedSectionId)?.title ?? "";
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
    if (!previewMessage.trim()) {
      setPreviewError("请输入预览消息。");
      return;
    }
    setPreviewError("");
    setPreviewPending(true);
    try {
      const sessionId = await ensurePreviewSession();
      const response = await sendStudyMessage({
        sessionId,
        message: previewMessage.trim()
      });
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
        <span style={styles.topbarSub}>教师人格配置、情绪区间、版本回放与章节联动预览。</span>
      </div>

      {loadError ? <div style={styles.error}>加载失败: {loadError}</div> : null}

      <div style={styles.contentGrid}>
        <section style={styles.panel}>
          <h2 style={styles.sectionTitle}>人格参数编辑器</h2>
          <label style={styles.fieldLabel}>当前人格</label>
          <select
            style={styles.select}
            value={selectedPersonaId}
            onChange={(event) => setSelectedPersonaId(event.target.value)}
          >
            {personas.map((persona) => (
              <option key={persona.id} value={persona.id}>
                {persona.name} ({persona.source})
              </option>
            ))}
          </select>

          <label style={styles.fieldLabel}>名称</label>
          <input
            style={styles.input}
            value={draft.name}
            onChange={(event) => updateDraft("name", event.target.value)}
          />

          <label style={styles.fieldLabel}>摘要</label>
          <textarea
            style={styles.textarea}
            value={draft.summary}
            onChange={(event) => updateDraft("summary", event.target.value)}
          />

          <label style={styles.fieldLabel}>设定：背景故事</label>
          <textarea
            style={styles.textareaLg}
            value={draft.backgroundStory}
            onChange={(event) => updateDraft("backgroundStory", event.target.value)}
            placeholder="例如：人物成长经历、教学信念、口头禅、与学习者互动时的叙事基调。"
          />
          <div style={styles.actionsRow}>
            {BACKGROUND_TEMPLATES.map((template) => (
              <button
                key={template.id}
                type="button"
                style={styles.linkButton}
                onClick={() => handleInsertTemplate(template.text)}
              >
                {template.label}
              </button>
            ))}
          </div>
          <label style={styles.fieldLabel}>保留原文比例 {(retainRatio * 100).toFixed(0)}%</label>
          <input
            style={styles.range}
            type="range"
            min={0}
            max={1}
            step={0.05}
            value={retainRatio}
            onChange={(event) => setRetainRatio(Number(event.target.value))}
          />
          <div style={styles.muted}>越高越保留原文，越低越允许模型重写。</div>
          <div style={styles.actionsRow}>
            <button
              style={styles.ghostButton}
              type="button"
              disabled={assistPending}
              onClick={handleAssistSetting}
            >
              {assistPending ? "AI 完善中..." : "人工智能辅助完善设定"}
            </button>
            {assistError ? <span style={styles.errorInline}>{assistError}</span> : null}
          </div>

          <label style={styles.fieldLabel}>教学风格（逗号分隔）</label>
          <input
            style={styles.input}
            value={draft.teachingStyleText}
            onChange={(event) => updateDraft("teachingStyleText", event.target.value)}
          />

          <label style={styles.fieldLabel}>叙事模式</label>
          <select
            style={styles.select}
            value={draft.narrativeMode}
            onChange={(event) => updateDraft("narrativeMode", event.target.value as PersonaDraft["narrativeMode"])}
          >
            <option value="grounded">grounded</option>
            <option value="light_story">light_story</option>
          </select>

          <label style={styles.fieldLabel}>鼓励策略</label>
          <input
            style={styles.input}
            value={draft.encouragementStyle}
            onChange={(event) => updateDraft("encouragementStyle", event.target.value)}
          />

          <label style={styles.fieldLabel}>纠错策略</label>
          <input
            style={styles.input}
            value={draft.correctionStyle}
            onChange={(event) => updateDraft("correctionStyle", event.target.value)}
          />

          <label style={styles.fieldLabel}>系统提示词</label>
          <textarea
            style={styles.textareaLg}
            value={draft.systemPrompt}
            onChange={(event) => updateDraft("systemPrompt", event.target.value)}
          />

          <div style={styles.actionsRow}>
            <button style={styles.primaryButton} disabled={savingPersona} onClick={handleCreatePersona}>
              {savingPersona ? "保存中..." : "创建新人格"}
            </button>
            <button
              style={styles.ghostButton}
              disabled={savingPersona || isReadonlyPersona}
              onClick={handleUpdatePersona}
            >
              {savingPersona ? "保存中..." : "更新当前人格"}
            </button>
            {saveError ? <span style={styles.errorInline}>{saveError}</span> : null}
          </div>
          {isReadonlyPersona ? (
            <div style={styles.muted}>内置人格为只读，无法直接更新。可编辑后使用“创建新人格”另存。</div>
          ) : null}
        </section>

        <section style={styles.panel}>
          <h2 style={styles.sectionTitle}>情绪与动作色谱调试面板</h2>
          <label style={styles.fieldLabel}>可用情绪（逗号分隔）</label>
          <input
            style={styles.input}
            value={draft.availableEmotionsText}
            onChange={(event) => updateDraft("availableEmotionsText", event.target.value)}
          />

          <label style={styles.fieldLabel}>可用动作（逗号分隔）</label>
          <input
            style={styles.input}
            value={draft.availableActionsText}
            onChange={(event) => updateDraft("availableActionsText", event.target.value)}
          />

          <label style={styles.fieldLabel}>默认语气</label>
          <select
            style={styles.select}
            value={draft.defaultSpeechStyle}
            onChange={(event) => updateDraft("defaultSpeechStyle", event.target.value as SpeechStyle)}
          >
            {SPEECH_STYLES.map((styleOption) => (
              <option key={styleOption} value={styleOption}>
                {styleOption}
              </option>
            ))}
          </select>

          <div style={styles.compactGrid}>
            <div>
              <label style={styles.fieldLabel}>预览情绪</label>
              <select
                style={styles.select}
                value={previewEmotion}
                onChange={(event) => setPreviewEmotion(event.target.value as CharacterEmotion)}
              >
                {(draftEmotionOptions.length ? draftEmotionOptions : CHARACTER_EMOTIONS).map((emotion) => (
                  <option key={emotion} value={emotion}>
                    {emotion}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label style={styles.fieldLabel}>预览动作</label>
              <select
                style={styles.select}
                value={previewAction}
                onChange={(event) => setPreviewAction(event.target.value as CharacterAction)}
              >
                {(draftActionOptions.length ? draftActionOptions : CHARACTER_ACTIONS).map((action) => (
                  <option key={action} value={action}>
                    {action}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label style={styles.fieldLabel}>语气</label>
              <select
                style={styles.select}
                value={previewSpeech}
                onChange={(event) => setPreviewSpeech(event.target.value as SpeechStyle)}
              >
                {SPEECH_STYLES.map((styleOption) => (
                  <option key={styleOption} value={styleOption}>
                    {styleOption}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label style={styles.fieldLabel}>时序</label>
              <select
                style={styles.select}
                value={previewTiming}
                onChange={(event) => setPreviewTiming(event.target.value as TimingHint)}
              >
                <option value="instant">instant</option>
                <option value="linger">linger</option>
                <option value="after_text">after_text</option>
              </select>
            </div>
          </div>

          <label style={styles.fieldLabel}>强度 {previewIntensity.toFixed(2)}</label>
          <input
            style={styles.range}
            type="range"
            min={0}
            max={1}
            step={0.05}
            value={previewIntensity}
            onChange={(event) => setPreviewIntensity(Number(event.target.value))}
          />

          <label style={styles.fieldLabel}>场景提示</label>
          <input
            style={styles.input}
            value={previewSceneHint}
            onChange={(event) => setPreviewSceneHint(event.target.value)}
          />

          <CharacterShell persona={draftPersona} response={syntheticPreviewResponse} pending={false} />
        </section>

        <section style={styles.panel}>
          <h2 style={styles.sectionTitle}>配置版本管理与回放</h2>
          <div style={styles.actionsRow}>
            <input
              style={styles.input}
              placeholder="版本标签（可选）"
              value={versionLabel}
              onChange={(event) => setVersionLabel(event.target.value)}
            />
            <button style={styles.ghostButton} onClick={handleSaveVersion} disabled={!selectedPersonaId}>
              保存当前版本
            </button>
          </div>
          {versions.length === 0 ? (
            <div style={styles.muted}>暂无版本记录，可先保存一份当前配置。</div>
          ) : (
            <div style={styles.versionList}>
              {versions.map((version) => (
                <div key={version.id} style={styles.versionItem}>
                  <div style={styles.versionMeta}>
                    <strong>{version.label}</strong>
                    <span>{new Date(version.createdAt).toLocaleString()}</span>
                  </div>
                  <button style={styles.linkButton} onClick={() => handleReplayVersion(version.id)}>
                    回放
                  </button>
                </div>
              ))}
            </div>
          )}
        </section>

        <section style={styles.panel}>
          <h2 style={styles.sectionTitle}>与章节对话联动的实时人格预览</h2>
          <div style={styles.compactGrid}>
            <div>
              <label style={styles.fieldLabel}>文档</label>
              <select
                style={styles.select}
                value={selectedDocumentId}
                onChange={(event) => {
                  setSelectedDocumentId(event.target.value);
                  setPreviewSessionId("");
                  setPreviewChat(null);
                }}
              >
                {documents.map((document) => (
                  <option key={document.id} value={document.id}>
                    {document.title}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label style={styles.fieldLabel}>章节</label>
              <select
                style={styles.select}
                value={selectedSectionId}
                onChange={(event) => {
                  setSelectedSectionId(event.target.value);
                  setPreviewSessionId("");
                  setPreviewChat(null);
                }}
              >
                {sectionOptions.map((section) => (
                  <option key={section.id} value={section.id}>
                    {section.title}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <label style={styles.fieldLabel}>联动提问</label>
          <textarea
            style={styles.textareaLg}
            value={previewMessage}
            onChange={(event) => setPreviewMessage(event.target.value)}
          />

          <div style={styles.actionsRow}>
            <button style={styles.primaryButton} onClick={handleSendPreviewMessage} disabled={previewPending}>
              {previewPending ? "预览生成中..." : "发送预览消息"}
            </button>
            {previewError ? <span style={styles.errorInline}>{previewError}</span> : null}
          </div>

          <div style={styles.assetCard}>
            <div style={styles.assetRow}>
              <span style={styles.assetLabel}>Renderer</span>
              <span>{assets?.renderer ?? "-"}</span>
            </div>
            <div style={styles.assetRow}>
              <span style={styles.assetLabel}>Manifest</span>
              <span>{assets ? JSON.stringify(assets.assetManifest) : "-"}</span>
            </div>
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
    backgroundStory: persona.backgroundStory ?? "",
    systemPrompt: persona.systemPrompt,
    teachingStyleText: persona.teachingStyle.join(", "),
    narrativeMode: persona.narrativeMode,
    encouragementStyle: persona.encouragementStyle,
    correctionStyle: persona.correctionStyle,
    availableEmotionsText: persona.availableEmotions.join(", "),
    availableActionsText: persona.availableActions.join(", "),
    defaultSpeechStyle: persona.defaultSpeechStyle
  };
}

function draftToCreatePersonaInput(draft: PersonaDraft): CreatePersonaInput {
  return {
    name: draft.name.trim(),
    summary: draft.summary.trim(),
    backgroundStory: draft.backgroundStory.trim(),
    systemPrompt: draft.systemPrompt.trim(),
    teachingStyle: splitCsv(draft.teachingStyleText),
    narrativeMode: draft.narrativeMode,
    encouragementStyle: draft.encouragementStyle.trim(),
    correctionStyle: draft.correctionStyle.trim(),
    availableEmotions: coerceEmotions(draft.availableEmotionsText),
    availableActions: coerceActions(draft.availableActionsText),
    defaultSpeechStyle: draft.defaultSpeechStyle
  };
}

function createInputToDraft(snapshot: CreatePersonaInput): PersonaDraft {
  return {
    name: snapshot.name,
    summary: snapshot.summary,
    backgroundStory: snapshot.backgroundStory ?? "",
    systemPrompt: snapshot.systemPrompt,
    teachingStyleText: snapshot.teachingStyle.join(", "),
    narrativeMode: snapshot.narrativeMode,
    encouragementStyle: snapshot.encouragementStyle,
    correctionStyle: snapshot.correctionStyle,
    availableEmotionsText: (snapshot.availableEmotions ?? CHARACTER_EMOTIONS).join(", "),
    availableActionsText: (snapshot.availableActions ?? CHARACTER_ACTIONS).join(", "),
    defaultSpeechStyle: snapshot.defaultSpeechStyle ?? "warm"
  };
}

function splitCsv(value: string): string[] {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function coerceEmotions(value: string): CharacterEmotion[] {
  const allowed = new Set<string>(CHARACTER_EMOTIONS);
  const result = splitCsv(value).filter((item): item is CharacterEmotion => allowed.has(item));
  return result;
}

function coerceActions(value: string): CharacterAction[] {
  const allowed = new Set<string>(CHARACTER_ACTIONS);
  const result = splitCsv(value).filter((item): item is CharacterAction => allowed.has(item));
  return result;
}

function resolveSections(document: DocumentRecord): Array<{ id: string; title: string }> {
  const sections = document.studyUnits.length
    ? document.studyUnits.map((unit) => ({ id: unit.id, title: `Study Unit: ${unit.title}` }))
    : document.sections.map((section) => ({ id: section.id, title: `Section: ${section.title}` }));
  return sections;
}

function readSavedVersions(): Record<string, PersonaVersion[]> {
  if (typeof window === "undefined") {
    return {};
  }
  try {
    const raw = window.localStorage.getItem(VERSION_STORAGE_KEY);
    if (!raw) {
      return {};
    }
    const parsed = JSON.parse(raw) as Record<string, PersonaVersion[]>;
    return parsed ?? {};
  } catch {
    return {};
  }
}

function writeSavedVersions(data: Record<string, PersonaVersion[]>) {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.setItem(VERSION_STORAGE_KEY, JSON.stringify(data));
}

const styles: Record<string, CSSProperties> = {
  page: {
    minHeight: "100vh",
    maxWidth: 1360,
    margin: "0 auto",
    padding: "20px 24px 32px",
    display: "grid",
    gap: 16,
    alignContent: "start"
  },
  topbar: {
    display: "flex",
    alignItems: "baseline",
    gap: 12,
    paddingBottom: 12,
    flexWrap: "wrap"
  },
  topbarTitle: {
    fontSize: 16,
    fontWeight: 700,
    color: "var(--ink)"
  },
  topbarSub: {
    fontSize: 13,
    color: "var(--muted)"
  },
  contentGrid: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fit, minmax(360px, 1fr))",
    gap: 14,
    alignItems: "start"
  },
  panel: {
    border: "1px solid var(--border)",
    background: "white",
    padding: 14,
    display: "grid",
    gap: 8,
    alignContent: "start"
  },
  sectionTitle: {
    margin: 0,
    fontSize: 14,
    fontWeight: 700
  },
  fieldLabel: {
    fontSize: 12,
    color: "var(--muted)"
  },
  input: {
    width: "100%",
    minHeight: 36,
    border: "1px solid var(--border)",
    background: "white",
    padding: "8px 10px"
  },
  select: {
    width: "100%",
    minHeight: 36,
    border: "1px solid var(--border)",
    background: "white",
    padding: "8px 10px"
  },
  textarea: {
    width: "100%",
    minHeight: 72,
    border: "1px solid var(--border)",
    background: "white",
    padding: "8px 10px",
    resize: "vertical"
  },
  textareaLg: {
    width: "100%",
    minHeight: 120,
    border: "1px solid var(--border)",
    background: "white",
    padding: "8px 10px",
    resize: "vertical"
  },
  primaryButton: {
    border: "1px solid var(--accent)",
    background: "var(--accent)",
    color: "white",
    minHeight: 36,
    padding: "0 12px",
    cursor: "pointer"
  },
  ghostButton: {
    border: "1px solid var(--border)",
    background: "white",
    color: "var(--ink)",
    minHeight: 36,
    padding: "0 12px",
    cursor: "pointer"
  },
  linkButton: {
    border: "1px solid var(--border)",
    background: "white",
    color: "var(--accent)",
    minHeight: 30,
    padding: "0 10px",
    cursor: "pointer"
  },
  actionsRow: {
    display: "flex",
    gap: 8,
    alignItems: "center",
    flexWrap: "wrap"
  },
  compactGrid: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
    gap: 8
  },
  range: {
    width: "100%"
  },
  muted: {
    fontSize: 12,
    color: "var(--muted)"
  },
  versionList: {
    display: "grid",
    gap: 6
  },
  versionItem: {
    border: "1px solid var(--border)",
    background: "var(--panel)",
    padding: "8px 10px",
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 10
  },
  versionMeta: {
    display: "grid",
    gap: 2,
    fontSize: 12
  },
  assetCard: {
    border: "1px solid var(--border)",
    background: "var(--panel)",
    padding: "8px 10px",
    display: "grid",
    gap: 6
  },
  assetRow: {
    display: "grid",
    gridTemplateColumns: "96px 1fr",
    gap: 8,
    fontSize: 12,
    wordBreak: "break-all"
  },
  assetLabel: {
    color: "var(--muted)"
  },
  chatReply: {
    padding: "10px 12px",
    border: "1px solid var(--border)",
    background: "var(--panel)",
    fontSize: 13,
    lineHeight: 1.6
  },
  error: {
    border: "1px solid #f0b8b8",
    background: "#fff4f4",
    color: "#9c2020",
    padding: "8px 10px",
    fontSize: 13
  },
  errorInline: {
    color: "#9c2020",
    fontSize: 12
  }
};
