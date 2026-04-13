import type {
  CreatePersonaInput,
  CreatePersonaCardInput,
  DocumentPlanningContext,
  DocumentPlanningTraceResponse,
  ModelToolConfig,
  ModelToolToggle,
  PlanGenerationTrace,
  DocumentDebugRecord,
  DocumentRecord,
  LearningGoal,
  LearningPlan,
  PersonaCard,
  PersonaCardGenerationMode,
  PersonaProfile,
  RuntimeOpenAIProbeResult,
  RuntimeSettings,
  RuntimeSettingsPatch,
  StreamReport,
  StudyChatResponse,
  StudySessionRecord,
  TokenUsageStats
} from "@vibe-learner/shared";

import { compactPreviewString, compactPreviewValue } from "./preview";
import { getAiBaseUrl, getDesktopRuntimeConfig } from "./runtime-config";

export interface StudyChatExchangeResponse extends StudyChatResponse {
  session: StudySessionRecord;
}

export interface StudyPlanConfirmationDecisionResponse {
  session: StudySessionRecord;
  plan: LearningPlan | null;
}

export interface PersonaAssets {
  personaId: string;
  renderer: string;
  assetManifest: Record<string, unknown>;
}

export interface PersonaCardGenerateResult {
  mode: PersonaCardGenerationMode;
  usedModel: string;
  usedWebSearch: boolean;
  summary: string;
  relationship: string;
  learnerAddress: string;
  items: PersonaCard[];
  modelRecoveries?: import("@vibe-learner/shared").ModelRecovery[];
}

export interface SceneTreeGenerateResult {
  mode: "keywords" | "long_text";
  usedModel: string;
  usedWebSearch: boolean;
  sceneName: string;
  sceneSummary: string;
  selectedLayerId: string;
  sceneLayers: import("@vibe-learner/shared").SceneTreeNode[];
  modelRecoveries?: import("@vibe-learner/shared").ModelRecovery[];
}

export interface PersonaSettingAssistInput {
  name: string;
  summary: string;
  slots: import("@vibe-learner/shared").PersonaSlot[];
  rewriteStrength: number;
}

export interface PersonaSettingAssistOutput {
  slots: import("@vibe-learner/shared").PersonaSlot[];
  systemPromptSuggestion: string;
  modelRecoveries?: import("@vibe-learner/shared").ModelRecovery[];
}

export interface PersonaSlotAssistInput {
  name: string;
  summary: string;
  slot: import("@vibe-learner/shared").PersonaSlot;
  rewriteStrength: number;
}

export interface PersonaSlotAssistOutput {
  slot: import("@vibe-learner/shared").PersonaSlot;
  modelRecoveries?: import("@vibe-learner/shared").ModelRecovery[];
}

export interface SceneSetupStatePayload {
  updatedAt: string;
  sceneName: string;
  sceneSummary: string;
  sceneLayers: unknown[];
  selectedLayerId: string;
  collapsedLayerIds: string[];
  sceneProfile?: import("@vibe-learner/shared").SceneProfile;
}

export interface SceneLibraryItemPayload {
  sceneId: string;
  createdAt: string;
  updatedAt: string;
  sceneName: string;
  sceneSummary: string;
  sceneLayers: unknown[];
  selectedLayerId: string;
  collapsedLayerIds: string[];
  sceneProfile?: import("@vibe-learner/shared").SceneProfile;
}

export interface ReusableSceneNodePayload {
  nodeId: string;
  nodeType: "layer" | "object";
  title: string;
  summary: string;
  tags: string[];
  reuseId: string;
  reuseHint: string;
  sourceSceneId: string;
  sourceSceneName: string;
  layerNode?: import("@vibe-learner/shared").SceneTreeNode;
  objectNode?: import("@vibe-learner/shared").SceneObjectSnapshot;
  createdAt: string;
  updatedAt: string;
}

export interface DocumentStudyUnitUpdatePayload {
  document: DocumentRecord;
  plans: LearningPlan[];
}

function serializeSceneTree(
  nodes: import("@vibe-learner/shared").SceneTreeNode[] | undefined
): Array<Record<string, unknown>> {
  return (nodes ?? []).map((node) => ({
    id: node.id,
    title: node.title,
    scope_label: node.scopeLabel,
    summary: node.summary,
    atmosphere: node.atmosphere,
    rules: node.rules,
    entrance: node.entrance,
    tags: node.tags,
    reuse_id: node.reuseId,
    reuse_hint: node.reuseHint,
    objects: (node.objects ?? []).map((object) => ({
      id: object.id,
      name: object.name,
      description: object.description,
      interaction: object.interaction,
      tags: object.tags,
      reuse_id: object.reuseId,
      reuse_hint: object.reuseHint,
    })),
    children: serializeSceneTree(node.children),
  }));
}

function serializeSceneProfile(
  sceneProfile: import("@vibe-learner/shared").SceneProfile | null | undefined
) {
  if (!sceneProfile) {
    return null;
  }
  return {
    scene_name: sceneProfile.sceneName,
    scene_id: sceneProfile.sceneId,
    title: sceneProfile.title,
    summary: sceneProfile.summary,
    tags: sceneProfile.tags,
    selected_path: sceneProfile.selectedPath,
    focus_object_names: sceneProfile.focusObjectNames,
    scene_tree: serializeSceneTree(sceneProfile.sceneTree),
  };
}

function normalizeSceneTreeNode(node: any): import("@vibe-learner/shared").SceneTreeNode {
  return {
    id: String(node.id ?? ""),
    title: String(node.title ?? ""),
    scopeLabel: String(node.scope_label ?? ""),
    summary: String(node.summary ?? ""),
    atmosphere: String(node.atmosphere ?? ""),
    rules: String(node.rules ?? ""),
    entrance: String(node.entrance ?? ""),
    tags: String(node.tags ?? ""),
    reuseId: String(node.reuse_id ?? ""),
    reuseHint: String(node.reuse_hint ?? ""),
    objects: Array.isArray(node.objects)
      ? node.objects.map((object: any) => ({
          id: String(object.id ?? ""),
          name: String(object.name ?? ""),
          description: String(object.description ?? ""),
          interaction: String(object.interaction ?? ""),
          tags: String(object.tags ?? ""),
          reuseId: String(object.reuse_id ?? ""),
          reuseHint: String(object.reuse_hint ?? ""),
        }))
      : [],
    children: Array.isArray(node.children) ? node.children.map(normalizeSceneTreeNode) : [],
  };
}

function normalizeSceneProfile(scene: any) {
  if (!scene || typeof scene !== "object") {
    return undefined;
  }
  return {
    sceneId: String(scene.scene_id ?? ""),
    sceneName: String(scene.scene_name ?? ""),
    title: String(scene.title ?? ""),
    summary: String(scene.summary ?? ""),
    tags: Array.isArray(scene.tags) ? scene.tags.map((item: unknown) => String(item)) : [],
    selectedPath: Array.isArray(scene.selected_path)
      ? scene.selected_path.map((item: unknown) => String(item))
      : [],
    focusObjectNames: Array.isArray(scene.focus_object_names)
      ? scene.focus_object_names.map((item: unknown) => String(item))
      : [],
    sceneTree: Array.isArray(scene.scene_tree) ? scene.scene_tree.map(normalizeSceneTreeNode) : [],
  };
}

function normalizeChatToolCalls(toolCalls: any): import("@vibe-learner/shared").ChatToolCallTrace[] {
  if (!Array.isArray(toolCalls)) {
    return [];
  }
  return toolCalls.map((toolCall: any) => ({
    toolCallId: String(toolCall.tool_call_id ?? ""),
    toolName: String(toolCall.tool_name ?? ""),
    argumentsJson: String(toolCall.arguments_json ?? "{}"),
    resultSummary: compactPreviewString(toolCall.result_summary ?? "", 240),
    resultJson: compactPreviewString(toolCall.result_json ?? "", 1200),
  }));
}

function normalizeModelRecoveries(items: any): import("@vibe-learner/shared").ModelRecovery[] {
  if (!Array.isArray(items)) {
    return [];
  }
  return items.map((item: any) => ({
    recoveryId: String(item.recovery_id ?? ""),
    category: String(item.category ?? ""),
    reason: String(item.reason ?? ""),
    strategy: String(item.strategy ?? ""),
    attempts: Number(item.attempts ?? 1),
    note: String(item.note ?? ""),
    createdAt: String(item.created_at ?? ""),
  }));
}

function extractErrorMessage(payload: unknown, fallbackMessage: string) {
  if (typeof payload === "string") {
    const trimmed = payload.trim();
    return trimmed || fallbackMessage;
  }
  if (!payload || typeof payload !== "object") {
    return fallbackMessage;
  }
  const record = payload as Record<string, unknown>;
  const detail = record.detail ?? record.error ?? record.message;
  if (typeof detail === "string") {
    const trimmed = detail.trim();
    return trimmed || fallbackMessage;
  }
  if (detail !== undefined && detail !== null) {
    const text = String(detail).trim();
    if (text) {
      return text;
    }
  }
  return fallbackMessage;
}

const AI_BASE_URL = () => getAiBaseUrl();

function clientLog(stage: string, payload: Record<string, unknown>) {
  console.info(`[vibe-learner] ${stage}`, payload);
}

async function request(input: string, init?: RequestInit): Promise<Response> {
  const method = init?.method ?? "GET";
  const startedAt = performance.now();
  clientLog("request:start", { method, input });
  try {
    const response = await fetch(input, init);
    clientLog("request:end", {
      method,
      input,
      status: response.status,
      durationMs: Math.round(performance.now() - startedAt)
    });
    return response;
  } catch (error) {
    clientLog("request:error", {
      method,
      input,
      durationMs: Math.round(performance.now() - startedAt),
      error: String(error)
    });
    const startupError = getDesktopRuntimeConfig()?.startupError.trim();
    const detail = startupError ? ` (${startupError})` : "";
    throw new Error(`Cannot reach AI service at ${AI_BASE_URL()}${detail}`);
  }
}

async function readJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const text = await response.text();
    const fallbackMessage = text.trim() || `HTTP ${response.status}`;
    let message = fallbackMessage;
    try {
      const parsed = JSON.parse(text) as unknown;
      message = extractErrorMessage(parsed, fallbackMessage);
    } catch {
      // Keep the raw body when it is not JSON.
    }
    throw new Error(message);
  }
  return (await response.json()) as T;
}

function formatStreamErrorPayload(
  payload: Record<string, unknown> | undefined,
  fallbackCode: string
): string {
  const detail = String(payload?.detail ?? payload?.error ?? fallbackCode);
  const internal = payload?.internal_error_code;
  const statusCode = payload?.status_code;
  const retryAttempts = payload?.retry_attempts;
  const suffixParts: string[] = [];
  if (internal) {
    suffixParts.push(`internal=${String(internal)}`);
  }
  if (statusCode) {
    suffixParts.push(`status=${String(statusCode)}`);
  }
  if (typeof retryAttempts === "number" && retryAttempts > 1) {
    suffixParts.push(`retries=${String(retryAttempts - 1)}`);
  }
  if (!suffixParts.length) {
    return detail;
  }
  return `${detail} (${suffixParts.join(", ")})`;
}

function normalizePersona(persona: any): PersonaProfile {
  return {
    id: persona.id,
    name: persona.name,
    source: persona.source,
    summary: persona.summary,
    relationship: String(persona.relationship ?? ""),
    learnerAddress: String(persona.learner_address ?? ""),
    systemPrompt: persona.system_prompt,
    referenceHints: Array.isArray(persona.reference_hints)
      ? persona.reference_hints.map((item: unknown) => String(item)).filter(Boolean)
      : [],
    slots: Array.isArray(persona.slots)
      ? persona.slots.map((s: any) => ({
          kind: String(s.kind ?? "custom"),
          label: String(s.label ?? s.kind ?? ""),
          content: String(s.content ?? ""),
          weight: Number(s.weight ?? 1),
          locked: Boolean(s.locked),
          sortOrder: Number(s.sort_order ?? 0)
        }))
      : [],
    availableEmotions: persona.available_emotions,
    availableActions: persona.available_actions,
    defaultSpeechStyle: persona.default_speech_style
  };
}

function normalizePersonaCard(card: any): PersonaCard {
  return {
    id: String(card.id ?? ""),
    title: String(card.title ?? ""),
    kind: String(card.kind ?? "custom"),
    label: String(card.label ?? card.kind ?? ""),
    content: String(card.content ?? ""),
    tags: Array.isArray(card.tags) ? card.tags.map((item: unknown) => String(item)) : [],
    searchKeywords: String(card.search_keywords ?? "自定义"),
    source: String(card.source ?? "manual") as PersonaCard["source"],
    sourceNote: String(card.source_note ?? ""),
    createdAt: String(card.created_at ?? ""),
    updatedAt: String(card.updated_at ?? "")
  };
}

function serializeSlot(slot: any) {
  return {
    kind: slot.kind,
    label: slot.label,
    content: slot.content,
    weight: slot.weight ?? 1,
    locked: slot.locked ?? false,
    sort_order: slot.sortOrder ?? 0
  };
}

function serializePersonaCardInput(input: CreatePersonaCardInput) {
  return {
    title: input.title,
    kind: input.kind,
    label: input.label,
    content: input.content,
    tags: input.tags ?? [],
    search_keywords: input.searchKeywords ?? "自定义",
    source: input.source ?? "manual",
    source_note: input.sourceNote ?? ""
  };
}

function serializePersonaInput(input: CreatePersonaInput) {
  return {
    name: input.name,
    summary: input.summary,
    relationship: input.relationship,
    learner_address: input.learnerAddress,
    system_prompt: input.systemPrompt,
    reference_hints: input.referenceHints ?? [],
    slots: input.slots.map(serializeSlot),
    available_emotions: input.availableEmotions,
    available_actions: input.availableActions,
    default_speech_style: input.defaultSpeechStyle
  };
}

function normalizeDocument(document: any): DocumentRecord {
  return {
    id: document.id,
    title: document.title,
    originalFilename: document.original_filename,
    storedPath: document.stored_path,
    status: document.status,
    ocrStatus: String(document.ocr_status ?? "pending") as DocumentRecord["ocrStatus"],
    createdAt: document.created_at,
    updatedAt: document.updated_at,
    pageCount: document.page_count,
    chunkCount: document.chunk_count,
    studyUnitCount: document.study_unit_count,
    previewExcerpt: compactPreviewString(document.preview_excerpt, 240),
    debugReady: document.debug_ready,
    sections: document.sections.map((section: any) => ({
      id: section.id,
      documentId: section.document_id,
      title: section.title,
      pageStart: section.page_start,
      pageEnd: section.page_end,
      level: section.level
    })),
    studyUnits: document.study_units.map(normalizeStudyUnit)
  };
}

function normalizeStudyUnit(unit: any) {
  return {
    id: unit.id,
    documentId: unit.document_id,
    title: unit.title,
    pageStart: unit.page_start,
    pageEnd: unit.page_end,
    unitKind: unit.unit_kind,
    includeInPlan: unit.include_in_plan,
    sourceSectionIds: unit.source_section_ids,
    summary: unit.summary ?? "",
    confidence: unit.confidence
  };
}

function normalizeScheduleItem(item: any) {
  return {
    id: item.id,
    unitId: item.unit_id,
    title: item.title,
    focus: item.focus,
    activityType: item.activity_type,
    status: item.status
  };
}

function normalizeDebugRecord(record: any): DocumentDebugRecord {
  return {
    documentId: record.document_id,
    parserName: record.parser_name,
    processedAt: record.processed_at,
    pageCount: record.page_count,
    totalCharacters: record.total_characters,
    extractionMethod: record.extraction_method,
    ocrStatus: String(record.ocr_status ?? "completed") as DocumentDebugRecord["ocrStatus"],
    ocrApplied: record.ocr_applied,
    ocrLanguage: record.ocr_language,
    ocrEngine: record.ocr_engine ? String(record.ocr_engine) : null,
    ocrModelId: record.ocr_model_id ? String(record.ocr_model_id) : null,
    ocrAppliedPageCount: Number(record.ocr_applied_page_count ?? 0),
    ocrWarnings: Array.isArray(record.ocr_warnings)
      ? record.ocr_warnings.map((item: unknown) => String(item))
      : [],
    dominantLanguageHint: record.dominant_language_hint,
    sections: record.sections.map((section: any) => ({
      id: section.id,
      documentId: section.document_id,
      title: section.title,
      pageStart: section.page_start,
      pageEnd: section.page_end,
      level: section.level
    })),
    studyUnits: record.study_units.map(normalizeStudyUnit),
    pages: record.pages.map((page: any) => ({
      pageNumber: page.page_number,
      charCount: page.char_count,
      wordCount: page.word_count,
      textPreview: compactPreviewString(page.text_preview, 320),
      dominantFontSize: page.dominant_font_size,
      extractionSource: page.extraction_source,
      headingCandidates: page.heading_candidates.map((candidate: any) => ({
        pageNumber: candidate.page_number,
        text: candidate.text,
        fontSize: candidate.font_size,
        confidence: candidate.confidence
      }))
    })),
    chunks: record.chunks.map((chunk: any) => ({
      id: chunk.id,
      documentId: chunk.document_id,
      sectionId: chunk.section_id,
      pageStart: chunk.page_start,
      pageEnd: chunk.page_end,
      charCount: chunk.char_count,
      textPreview: compactPreviewString(chunk.text_preview, 240),
      content: compactPreviewString(chunk.content ?? "", 600)
    })),
    warnings: record.warnings.map((warning: any) => ({
      code: warning.code,
      message: warning.message,
      pageNumber: warning.page_number
    }))
  };
}

function normalizePlanningSection(section: any) {
  return {
    sectionId: section.section_id,
    title: section.title,
    level: section.level,
    pageStart: section.page_start,
    pageEnd: section.page_end
  };
}

function normalizePlanningContext(record: any): DocumentPlanningContext {
  return {
    documentId: record.document_id,
    courseOutline: record.course_outline.map((section: any) => ({
      ...normalizePlanningSection(section),
      children: (section.children ?? []).map(normalizePlanningSection)
    })),
    studyUnits: record.study_units.map((unit: any) => ({
      unitId: unit.unit_id,
      title: unit.title,
      pageStart: unit.page_start,
      pageEnd: unit.page_end,
      summary: unit.summary,
      unitKind: unit.unit_kind,
      includeInPlan: unit.include_in_plan,
      subsectionTitles: unit.subsection_titles ?? [],
      relatedSectionIds: unit.related_section_ids ?? [],
      detailToolTargetId: unit.detail_tool_target_id
    })),
    detailMap: Object.fromEntries(
      Object.entries(record.detail_map ?? {}).map(([key, value]: [string, any]) => [
        key,
        {
          unitId: value.unit_id,
          title: value.title,
          pageStart: value.page_start,
          pageEnd: value.page_end,
          summary: value.summary,
          unitKind: value.unit_kind,
          includeInPlan: value.include_in_plan,
          relatedSectionIds: value.related_section_ids ?? [],
          subsectionTitles: value.subsection_titles ?? [],
          relatedSections: (value.related_sections ?? []).map(normalizePlanningSection),
          chunkCount: value.chunk_count,
          chunkExcerpts: (value.chunk_excerpts ?? []).map((chunk: any) => ({
            chunkId: chunk.chunk_id,
            sectionId: chunk.section_id,
            pageStart: chunk.page_start,
            pageEnd: chunk.page_end,
            charCount: chunk.char_count,
            content: compactPreviewString(chunk.content ?? "", 600)
          }))
        }
      ])
    ),
    availableTools: (record.available_tools ?? []).map((tool: any) => ({
      name: tool.name,
      description: tool.description
    }))
  };
}

function normalizePlanningTrace(record: any): PlanGenerationTrace {
  return {
    documentId: record.document_id,
    planId: record.plan_id ?? null,
    model: record.model,
    createdAt: record.created_at,
    rounds: (record.rounds ?? []).map((round: any) => ({
      roundIndex: round.round_index,
      finishReason: round.finish_reason ?? "",
      assistantContent: compactPreviewString(round.assistant_content ?? "", 800),
      thinking: compactPreviewString(round.thinking ?? "", 800),
      elapsedMs: round.elapsed_ms ?? 0,
      timeoutSeconds: round.timeout_seconds ?? 0,
      toolCalls: (round.tool_calls ?? []).map((toolCall: any) => ({
        toolCallId: toolCall.tool_call_id,
        toolName: toolCall.tool_name,
        argumentsJson: compactPreviewString(toolCall.arguments_json ?? "", 800),
        resultSummary: toolCall.result_summary ?? "",
        resultJson: compactPreviewString(toolCall.result_json ?? "", 800)
      })),
      recoveries: normalizeModelRecoveries(round.recoveries),
    }))
  };
}

function normalizePlanningTraceResponse(record: any): DocumentPlanningTraceResponse {
  return {
    documentId: record.document_id,
    hasTrace: Boolean(record.has_trace),
    summary: {
      roundCount: record.summary?.round_count ?? 0,
      toolCallCount: record.summary?.tool_call_count ?? 0,
      latestFinishReason: record.summary?.latest_finish_reason ?? ""
    },
    trace: record.trace ? normalizePlanningTrace(record.trace) : null
  };
}

function normalizeModelToolConfig(record: any): ModelToolConfig {
  return {
    updatedAt: String(record.updated_at ?? ""),
    stages: (record.stages ?? []).map((stage: any) => ({
      name: String(stage.name ?? ""),
      label: String(stage.label ?? stage.name ?? ""),
      description: String(stage.description ?? ""),
      stageEnabled: Boolean(stage.stage_enabled),
      auditBasis: Array.isArray(stage.audit_basis)
        ? stage.audit_basis.map((item: unknown) => String(item))
        : [],
      stageDisabledReason: String(stage.stage_disabled_reason ?? ""),
      tools: (stage.tools ?? []).map((tool: any) => ({
        name: String(tool.name ?? ""),
        label: String(tool.label ?? tool.name ?? ""),
        description: String(tool.description ?? ""),
        category: String(tool.category ?? ""),
        categoryLabel: String(tool.category_label ?? tool.category ?? ""),
        enabled: Boolean(tool.enabled),
        available: Boolean(tool.available),
        effectiveEnabled: Boolean(tool.effective_enabled),
        auditBasis: Array.isArray(tool.audit_basis)
          ? tool.audit_basis.map((item: unknown) => String(item))
          : [],
        unavailableReason: String(tool.unavailable_reason ?? "")
      }))
    }))
  };
}

function normalizeRuntimeSettings(record: any): RuntimeSettings {
  return {
    updatedAt: String(record.updated_at ?? ""),
    planProvider: (record.plan_provider === "mock" ? "mock" : "litellm") as "mock" | "litellm",
    openaiApiKey: String(record.openai_api_key ?? ""),
    openaiApiKeyConfigured: Boolean(record.openai_api_key_configured),
    openaiBaseUrl: String(record.openai_base_url ?? "https://api.openai.com/v1"),
    openaiPlanApiKey: String(record.openai_plan_api_key ?? ""),
    openaiPlanApiKeyConfigured: Boolean(record.openai_plan_api_key_configured),
    openaiPlanBaseUrl: String(record.openai_plan_base_url ?? "https://api.openai.com/v1"),
    openaiPlanModel: String(record.openai_plan_model ?? "gpt-4.1-mini"),
    openaiSettingApiKey: String(record.openai_setting_api_key ?? ""),
    openaiSettingApiKeyConfigured: Boolean(record.openai_setting_api_key_configured),
    openaiSettingBaseUrl: String(record.openai_setting_base_url ?? "https://api.openai.com/v1"),
    openaiSettingModel: String(record.openai_setting_model ?? "gpt-4.1-mini"),
    openaiSettingWebSearchEnabled: Boolean(record.openai_setting_web_search_enabled ?? true),
    openaiChatApiKey: String(record.openai_chat_api_key ?? ""),
    openaiChatApiKeyConfigured: Boolean(record.openai_chat_api_key_configured),
    openaiChatBaseUrl: String(record.openai_chat_base_url ?? "https://api.openai.com/v1"),
    openaiChatModel: String(record.openai_chat_model ?? "gpt-4.1-mini"),
    openaiChatTemperature: Number(record.openai_chat_temperature ?? 0.35),
    openaiSettingTemperature: Number(record.openai_setting_temperature ?? 0.4),
    openaiSettingMaxTokens: Number(record.openai_setting_max_tokens ?? 900),
    openaiChatMaxTokens: Number(record.openai_chat_max_tokens ?? 800),
    openaiChatHistoryMessages: Number(record.openai_chat_history_messages ?? 8),
    openaiChatToolMaxRounds: Number(record.openai_chat_tool_max_rounds ?? 4),
    openaiEmbeddingModel: String(record.openai_embedding_model ?? "text-embedding-3-small"),
    openaiChatModelMultimodal: Boolean(record.openai_chat_model_multimodal),
    openaiTimeoutSeconds: Number(record.openai_timeout_seconds ?? 30),
    openaiPlanModelMultimodal: Boolean(record.openai_plan_model_multimodal),
    openaiPlanFallbackModel: String(record.openai_plan_fallback_model ?? ""),
    openaiPlanFallbackDisableTools: Boolean(record.openai_plan_fallback_disable_tools),
    showDebugInfo: Boolean(record.show_debug_info)
  };
}

function normalizeRuntimeCapabilitySignal(record: any): import("@vibe-learner/shared").RuntimeCapabilitySignal {
  const status = String(record?.status ?? "unknown");
  const source = String(record?.source ?? "unavailable");
  return {
    status:
      status === "supported" || status === "unsupported" || status === "unknown"
        ? status
        : "unknown",
    source:
      source === "metadata" || source === "model_name" || source === "unavailable"
        ? source
        : "unavailable",
    note: String(record?.note ?? "")
  };
}

function normalizeStreamReport(record: any): StreamReport {
  return {
    documentId: record.document_id,
    streamKind: record.stream_kind,
    status: record.status,
    createdAt: record.created_at ?? "",
    updatedAt: record.updated_at ?? "",
    events: (record.events ?? []).map((event: any) => ({
      stage: event.stage,
      payload: compactPreviewValue(event.payload ?? {}) as Record<string, unknown>,
      createdAt: event.created_at ?? ""
    }))
  };
}

function normalizePlan(plan: any): LearningPlan {
  return {
    id: plan.id,
    documentId: plan.document_id,
    personaId: plan.persona_id,
    creationMode: plan.creation_mode === "goal_only" ? "goal_only" : "document",
    courseTitle: plan.course_title,
    objective: plan.objective,
    sceneProfileSummary: String(plan.scene_profile_summary ?? ""),
    sceneProfile: normalizeSceneProfile(plan.scene_profile),
    overview: plan.overview,
    studyChapters: Array.isArray(plan.study_chapters)
      ? plan.study_chapters.map((item: unknown) => String(item))
      : [],
    todayTasks: plan.today_tasks,
    studyUnits: plan.study_units.map(normalizeStudyUnit),
    schedule: plan.schedule.map(normalizeScheduleItem),
    progressSummary: {
      totalScheduleCount: Number(plan.progress_summary?.total_schedule_count ?? 0),
      completedScheduleCount: Number(plan.progress_summary?.completed_schedule_count ?? 0),
      inProgressScheduleCount: Number(plan.progress_summary?.in_progress_schedule_count ?? 0),
      pendingScheduleCount: Number(plan.progress_summary?.pending_schedule_count ?? 0),
      blockedScheduleCount: Number(plan.progress_summary?.blocked_schedule_count ?? 0),
      completionPercent: Number(plan.progress_summary?.completion_percent ?? 0),
    },
    chapterProgress: Array.isArray(plan.chapter_progress)
      ? plan.chapter_progress.map((item: any) => ({
          unitId: String(item.unit_id ?? ""),
          title: String(item.title ?? ""),
          objectiveFragment: String(item.objective_fragment ?? ""),
          scheduleIds: Array.isArray(item.schedule_ids)
            ? item.schedule_ids.map((entry: unknown) => String(entry))
            : [],
          totalScheduleCount: Number(item.total_schedule_count ?? 0),
          completedScheduleCount: Number(item.completed_schedule_count ?? 0),
          inProgressScheduleCount: Number(item.in_progress_schedule_count ?? 0),
          pendingScheduleCount: Number(item.pending_schedule_count ?? 0),
          blockedScheduleCount: Number(item.blocked_schedule_count ?? 0),
          completionPercent: Number(item.completion_percent ?? 0),
          status: String(item.status ?? "planned"),
        }))
      : [],
    progressEvents: Array.isArray(plan.progress_events)
      ? plan.progress_events.map((item: any) => ({
          id: String(item.id ?? ""),
          actor: String(item.actor ?? "user"),
          source: String(item.source ?? "ui"),
          scheduleIds: Array.isArray(item.schedule_ids)
            ? item.schedule_ids.map((entry: unknown) => String(entry))
            : [],
          status: String(item.status ?? "planned"),
          note: String(item.note ?? ""),
          createdAt: String(item.created_at ?? ""),
        }))
      : [],
    planningQuestions: Array.isArray(plan.planning_questions)
      ? plan.planning_questions.map((item: any) => ({
          id: String(item.id ?? ""),
          question: String(item.question ?? ""),
          reason: String(item.reason ?? ""),
          assumptions: Array.isArray(item.assumptions)
            ? item.assumptions.map((entry: unknown) => String(entry))
            : [],
          answer: String(item.answer ?? ""),
          status: String(item.status ?? "pending"),
          sourceToolName: String(item.source_tool_name ?? "ask_planning_question"),
          createdAt: String(item.created_at ?? ""),
          answeredAt: String(item.answered_at ?? ""),
        }))
      : [],
    createdAt: plan.created_at
  };
}

function normalizeSceneSetupState(payload: any): SceneSetupStatePayload {
  return {
    updatedAt: String(payload.updated_at ?? ""),
    sceneName: String(payload.scene_name ?? ""),
    sceneSummary: String(payload.scene_summary ?? ""),
    sceneLayers: Array.isArray(payload.scene_layers) ? payload.scene_layers : [],
    selectedLayerId: String(payload.selected_layer_id ?? ""),
    collapsedLayerIds: Array.isArray(payload.collapsed_layer_ids)
      ? payload.collapsed_layer_ids.map((item: unknown) => String(item))
      : [],
    sceneProfile: normalizeSceneProfile(payload.scene_profile),
  };
}

function normalizeSceneLibraryItem(payload: any): SceneLibraryItemPayload {
  // 尝试从多个源获取sceneSummary：scene_summary, sceneSummary, 或从scene_profile.summary
  const sceneSummary = String(
    payload.scene_summary ??
    payload.sceneSummary ??
    payload.scene_profile?.summary ??
    payload.sceneProfile?.summary ??
    ""
  );
  return {
    sceneId: String(payload.scene_id ?? ""),
    createdAt: String(payload.created_at ?? ""),
    updatedAt: String(payload.updated_at ?? ""),
    sceneName: String(payload.scene_name ?? payload.sceneName ?? ""),
    sceneSummary,
    sceneLayers: Array.isArray(payload.scene_layers) ? payload.scene_layers : (Array.isArray(payload.sceneLayers) ? payload.sceneLayers : []),
    selectedLayerId: String(payload.selected_layer_id ?? payload.selectedLayerId ?? ""),
    collapsedLayerIds: Array.isArray(payload.collapsed_layer_ids)
      ? payload.collapsed_layer_ids.map((item: unknown) => String(item))
      : (Array.isArray(payload.collapsedLayerIds) ? payload.collapsedLayerIds.map((item: unknown) => String(item)) : []),
    sceneProfile: normalizeSceneProfile(payload.scene_profile ?? payload.sceneProfile),
  };
}

function normalizeReusableSceneNode(payload: any): ReusableSceneNodePayload {
  return {
    nodeId: String(payload.node_id ?? ""),
    nodeType: (payload.node_type === "object" ? "object" : "layer") as "layer" | "object",
    title: String(payload.title ?? ""),
    summary: String(payload.summary ?? ""),
    tags: Array.isArray(payload.tags) ? payload.tags.map((item: unknown) => String(item)) : [],
    reuseId: String(payload.reuse_id ?? ""),
    reuseHint: String(payload.reuse_hint ?? ""),
    sourceSceneId: String(payload.source_scene_id ?? ""),
    sourceSceneName: String(payload.source_scene_name ?? ""),
    layerNode: payload.layer_node ? normalizeSceneTreeNode(payload.layer_node) : undefined,
    objectNode: payload.object_node
      ? {
          id: String(payload.object_node.id ?? ""),
          name: String(payload.object_node.name ?? ""),
          description: String(payload.object_node.description ?? ""),
          interaction: String(payload.object_node.interaction ?? ""),
          tags: String(payload.object_node.tags ?? ""),
          reuseId: String(payload.object_node.reuse_id ?? ""),
          reuseHint: String(payload.object_node.reuse_hint ?? ""),
        }
      : undefined,
    createdAt: String(payload.created_at ?? ""),
    updatedAt: String(payload.updated_at ?? ""),
  };
}

function normalizeMemoryTrace(items: any[] | undefined) {
  const raw = Array.isArray(items) ? items : [];
  return raw.map((item: any) => ({
    sessionId: String(item.session_id ?? ""),
    sectionId: String(item.section_id ?? ""),
    sceneTitle: String(item.scene_title ?? ""),
    score: Number(item.score ?? 0),
    snippet: compactPreviewString(String(item.snippet ?? ""), 240),
    createdAt: String(item.created_at ?? ""),
    source: String(item.source ?? "retriever") as "retriever" | "tool_call"
  }));
}

function normalizeSessionFollowUps(items: any[] | undefined) {
  const raw = Array.isArray(items) ? items : [];
  return raw.map((item: any) => ({
    id: String(item.id ?? ""),
    triggerKind: String(item.trigger_kind ?? ""),
    status: String(item.status ?? "pending"),
    delaySeconds: Number(item.delay_seconds ?? 0),
    dueAt: String(item.due_at ?? ""),
    hiddenMessage: String(item.hidden_message ?? ""),
    reason: String(item.reason ?? ""),
    createdAt: String(item.created_at ?? ""),
    completedAt: String(item.completed_at ?? ""),
    canceledAt: String(item.canceled_at ?? ""),
  }));
}

function normalizeSessionMemory(items: any[] | undefined) {
  const raw = Array.isArray(items) ? items : [];
  return raw.map((item: any) => ({
    id: String(item.id ?? ""),
    key: String(item.key ?? ""),
    content: compactPreviewString(String(item.content ?? ""), 280),
    source: String(item.source ?? "tool_call"),
    createdAt: String(item.created_at ?? ""),
    updatedAt: String(item.updated_at ?? ""),
  }));
}

function normalizeSessionAffinityState(value: any) {
  const raw = value && typeof value === "object" ? value : {};
  return {
    score: Number(raw.score ?? 0),
    level: String(raw.level ?? "neutral"),
    summary: String(raw.summary ?? ""),
    updatedAt: String(raw.updated_at ?? ""),
    events: Array.isArray(raw.events)
      ? raw.events.map((item: any) => ({
          id: String(item.id ?? ""),
          delta: Number(item.delta ?? 0),
          reason: String(item.reason ?? ""),
          source: String(item.source ?? "tool_call"),
          createdAt: String(item.created_at ?? ""),
        }))
      : [],
  };
}

function normalizePlanConfirmations(items: any[] | undefined) {
  const raw = Array.isArray(items) ? items : [];
  return raw.map((item: any) => ({
    id: String(item.id ?? ""),
    toolName: String(item.tool_name ?? ""),
    actionType: String(item.action_type ?? ""),
    planId: String(item.plan_id ?? ""),
    title: String(item.title ?? ""),
    summary: String(item.summary ?? ""),
    previewLines: Array.isArray(item.preview_lines)
      ? item.preview_lines.map((line: unknown) => String(line))
      : [],
    payload: item.payload && typeof item.payload === "object"
      ? item.payload as Record<string, unknown>
      : {},
    status: String(item.status ?? "pending"),
    createdAt: String(item.created_at ?? ""),
    resolvedAt: String(item.resolved_at ?? ""),
    resolutionNote: String(item.resolution_note ?? ""),
  }));
}

function normalizeLearnerAttachments(items: any[] | undefined) {
  const raw = Array.isArray(items) ? items : [];
  return raw.map((item: any) => ({
    attachmentId: String(item.attachment_id ?? ""),
    name: String(item.name ?? ""),
    mimeType: String(item.mime_type ?? ""),
    kind: String(item.kind ?? ""),
    sizeBytes: Number(item.size_bytes ?? 0),
    imageUrl: item.image_url ? String(item.image_url) : undefined,
    textExcerpt: item.text_excerpt ? compactPreviewString(String(item.text_excerpt), 240) : undefined,
    source: item.source ? String(item.source) : undefined,
    pageCount: Number(item.page_count ?? 0),
    previewable: Boolean(item.previewable ?? false),
  }));
}

function normalizeProjectedPdf(value: any) {
  const raw = value && typeof value === "object" ? value : null;
  if (!raw) {
    return null;
  }
  return {
    sourceKind: String(raw.source_kind ?? "document"),
    sourceId: String(raw.source_id ?? ""),
    title: String(raw.title ?? ""),
    pageNumber: Number(raw.page_number ?? 1),
    pageCount: Number(raw.page_count ?? 0),
    overlays: Array.isArray(raw.overlays)
      ? raw.overlays.map((overlay: any) => ({
          id: String(overlay.id ?? ""),
          kind: String(overlay.kind ?? ""),
          pageNumber: Number(overlay.page_number ?? 1),
          rects: Array.isArray(overlay.rects)
            ? overlay.rects.map((rect: any) => ({
                x: Number(rect.x ?? 0),
                y: Number(rect.y ?? 0),
                width: Number(rect.width ?? 0),
                height: Number(rect.height ?? 0),
              }))
            : [],
          label: String(overlay.label ?? ""),
          quoteText: overlay.quote_text ? String(overlay.quote_text) : undefined,
          color: overlay.color ? String(overlay.color) : undefined,
          createdAt: String(overlay.created_at ?? ""),
        }))
      : [],
    updatedAt: String(raw.updated_at ?? ""),
  };
}

function normalizeRichBlocks(items: any[] | undefined) {
  const raw = Array.isArray(items) ? items : [];
  return raw
    .map((item: any) => ({
      kind: String(item.kind ?? "").trim(),
      content: String(item.content ?? "").trim(),
    }))
    .filter((item) => item.kind && item.content);
}

function repairLegacyRichReply(
  reply: string,
  existingBlocks: Array<{ kind: string; content: string }>
) {
  const normalizedReply = String(reply ?? "");
  const normalizedBlocks = dedupeRichBlocks(existingBlocks);
  if (!normalizedReply.trimStart().startsWith("```json")) {
    const extracted = extractMermaidBlocksFromReply(normalizedReply);
    return {
      reply: extracted.reply,
      richBlocks: dedupeRichBlocks([...normalizedBlocks, ...extracted.richBlocks]),
    };
  }

  const textKey = '"text": "';
  const textStart = normalizedReply.indexOf(textKey);
  if (textStart === -1) {
    return {
      reply: normalizedReply,
      richBlocks: normalizedBlocks,
    };
  }

  try {
    const rawTextStart = textStart + textKey.length;
    const rawTextEnd = normalizedReply.indexOf('",\n  "mood"', rawTextStart);
    const rawText = (
      rawTextEnd === -1
        ? normalizedReply
            .slice(rawTextStart)
            .replace(/\r\n/g, "\n")
            .replace(/\r/g, "\n")
            .replace(/"\s*}\s*```?\s*$/g, "")
            .replace(/`+\s*$/g, "")
            .trimEnd()
        : normalizedReply.slice(rawTextStart, rawTextEnd)
    );
    const repairedSource = rawText
      .replace(/\\"/g, "__ESCAPED_QUOTE__")
      .replace(/"/g, "\\\"")
      .replace(/__ESCAPED_QUOTE__/g, '\\"')
      .replace(/\r?\n/g, "\\n");
    const recoveredReply = JSON.parse(`"${repairedSource}"`) as string;
    const extracted = extractMermaidBlocksFromReply(recoveredReply);
    return {
      reply: extracted.reply,
      richBlocks: dedupeRichBlocks([...normalizedBlocks, ...extracted.richBlocks]),
    };
  } catch {
    return {
      reply: normalizedReply,
      richBlocks: normalizedBlocks,
    };
  }
}

function extractMermaidBlocksFromReply(reply: string) {
  const richBlocks: Array<{ kind: string; content: string }> = [];
  const cleaned = reply.replace(/```mermaid\s*\n([\s\S]*?)```|```\s*\nmermaid\s*\n([\s\S]*?)```/gi, (_, chartA, chartB) => {
    const content = String(chartA ?? chartB ?? "").trim();
    if (content) {
      richBlocks.push({ kind: "mermaid", content });
    }
    return "\n\n";
  }).replace(/\n{3,}/g, "\n\n").trim();
  return {
    reply: cleaned,
    richBlocks: dedupeRichBlocks(richBlocks),
  };
}

function dedupeRichBlocks(items: Array<{ kind: string; content: string }>) {
  const result: Array<{ kind: string; content: string }> = [];
  const seen = new Set<string>();
  items.forEach((item) => {
    const kind = item.kind.trim();
    const content = item.content.trim();
    if (!kind || !content) {
      return;
    }
    const key = `${kind.toLowerCase()}:${content}`;
    if (seen.has(key)) {
      return;
    }
    seen.add(key);
    result.push({ kind, content });
  });
  return result;
}

function normalizeSession(session: any): StudySessionRecord {
  return {
    id: session.id,
    documentId: session.document_id,
    personaId: session.persona_id,
    planId: session.plan_id ?? null,
    sceneInstanceId: String(session.scene_instance_id ?? ""),
    sceneProfile: normalizeSceneProfile(session.scene_profile),
    sectionId: session.section_id,
    sectionTitle: session.section_title ?? "",
    themeHint: session.theme_hint ?? "",
    sessionSystemPrompt: compactPreviewString(session.session_system_prompt ?? "", 1200),
    status: session.status,
    turns: (session.turns ?? []).map((turn: any) => {
      const repaired = repairLegacyRichReply(
        String(turn.assistant_reply ?? ""),
        normalizeRichBlocks(turn.rich_blocks)
      );
      return {
        learnerMessage: turn.learner_message,
        learnerMessageKind: String(turn.learner_message_kind ?? "learner"),
        learnerAttachments: normalizeLearnerAttachments(turn.learner_attachments),
        assistantReply: repaired.reply,
        citations: (turn.citations ?? []).map((citation: any) => ({
          sectionId: String(citation.section_id ?? ""),
          title: citation.title,
          pageStart: citation.page_start,
          pageEnd: citation.page_end,
          sourceKind: citation.source_kind ? String(citation.source_kind) : undefined,
          sourceId: citation.source_id ? String(citation.source_id) : undefined,
        })),
        characterEvents: (turn.character_events ?? []).map((event: any) => ({
          emotion: event.emotion,
          action: event.action,
          speechStyle: event.speech_style,
          sceneHint: event.scene_hint,
          lineSegmentId: event.line_segment_id,
          timingHint: event.timing_hint,
          toolName: event.tool_name ? String(event.tool_name) : undefined,
          toolSummary: event.tool_summary ? compactPreviewString(event.tool_summary, 240) : undefined,
          deliveryCue: event.delivery_cue ? compactPreviewString(event.delivery_cue, 160) : undefined,
          commentary: event.commentary ? compactPreviewString(event.commentary, 280) : undefined,
        })),
        richBlocks: repaired.richBlocks,
        interactiveQuestion: normalizeInteractiveQuestion(turn.interactive_question),
        personaSlotTrace: (turn.persona_slot_trace ?? []).map((item: any) => ({
          kind: String(item.kind ?? "custom"),
          label: String(item.label ?? item.kind ?? ""),
          contentExcerpt: compactPreviewString(item.content_excerpt ?? "", 280),
          reason: String(item.reason ?? "")
        })),
        memoryTrace: normalizeMemoryTrace(turn.memory_trace),
        toolCalls: normalizeChatToolCalls(turn.tool_calls),
        sceneProfile: normalizeSceneProfile(turn.scene_profile),
        modelRecoveries: normalizeModelRecoveries(turn.model_recoveries),
        createdAt: turn.created_at
      };
    }),
    preparedSectionIds: Array.isArray(session.prepared_section_ids)
      ? session.prepared_section_ids.map((item: unknown) => String(item))
      : [],
    pendingFollowUps: normalizeSessionFollowUps(session.pending_follow_ups),
    sessionMemory: normalizeSessionMemory(session.session_memory),
    affinityState: normalizeSessionAffinityState(session.affinity_state),
    planConfirmations: normalizePlanConfirmations(session.plan_confirmations),
    projectedPdf: normalizeProjectedPdf(session.projected_pdf),
    createdAt: session.created_at,
    updatedAt: session.updated_at
  };
}

export async function listPersonas(): Promise<PersonaProfile[]> {
  const payload = await readJson<{ items: any[] }>(
    await request(`${AI_BASE_URL()}/personas`)
  );
  return payload.items.map(normalizePersona);
}

export async function createPersona(input: CreatePersonaInput): Promise<PersonaProfile> {
  const payload = await readJson<any>(
    await request(`${AI_BASE_URL()}/personas`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify(serializePersonaInput(input))
    })
  );
  return normalizePersona(payload);
}

export async function updatePersona(
  personaId: string,
  input: CreatePersonaInput
): Promise<PersonaProfile> {
  const payload = await readJson<any>(
    await request(`${AI_BASE_URL()}/personas/${personaId}`, {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify(serializePersonaInput(input))
    })
  );
  return normalizePersona(payload);
}

export async function deletePersona(personaId: string): Promise<void> {
  await readJson<{ deleted_persona_id: string }>(
    await request(`${AI_BASE_URL()}/personas/${personaId}`, {
      method: "DELETE"
    })
  );
}

export async function getPersonaAssets(personaId: string): Promise<PersonaAssets> {
  const payload = await readJson<any>(
    await request(`${AI_BASE_URL()}/personas/${personaId}/assets`)
  );
  return {
    personaId: payload.persona_id,
    renderer: payload.renderer,
    assetManifest: payload.asset_manifest ?? {}
  };
}

export async function listPersonaCards(): Promise<PersonaCard[]> {
  const payload = await readJson<{ items: any[] }>(
    await request(`${AI_BASE_URL()}/persona-cards`)
  );
  return payload.items.map(normalizePersonaCard);
}

export async function createPersonaCardsBatch(
  items: CreatePersonaCardInput[]
): Promise<PersonaCard[]> {
  const payload = await readJson<{ items: any[] }>(
    await request(`${AI_BASE_URL()}/persona-cards/batch`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        items: items.map(serializePersonaCardInput)
      })
    })
  );
  return payload.items.map(normalizePersonaCard);
}

export async function deletePersonaCard(cardId: string): Promise<void> {
  await readJson<{ deleted_persona_card_id: string }>(
    await request(`${AI_BASE_URL()}/persona-cards/${cardId}`, {
      method: "DELETE"
    })
  );
}

export async function generatePersonaCards(input: {
  mode: PersonaCardGenerationMode;
  inputText: string;
  count?: number | null;
}): Promise<PersonaCardGenerateResult> {
  const requestBody: Record<string, unknown> = {
    mode: input.mode,
    input_text: input.inputText
  };
  if (typeof input.count === "number" && Number.isFinite(input.count)) {
    requestBody.count = input.count;
  }
  const payload = await readJson<any>(
    await request(`${AI_BASE_URL()}/persona-cards/generate`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify(requestBody)
    })
  );
  return {
    mode: (payload.mode === "keywords" ? "keywords" : "long_text") as PersonaCardGenerationMode,
    usedModel: String(payload.used_model ?? ""),
    usedWebSearch: Boolean(payload.used_web_search),
    summary: String(payload.summary ?? ""),
    relationship: String(payload.relationship ?? ""),
    learnerAddress: String(payload.learner_address ?? ""),
    items: Array.isArray(payload.items) ? payload.items.map(normalizePersonaCard) : [],
    modelRecoveries: normalizeModelRecoveries(payload.model_recoveries)
  };
}

export async function generateSceneTree(input: {
  mode: "keywords" | "long_text";
  inputText: string;
  layerCount?: number | null;
}): Promise<SceneTreeGenerateResult> {
  const requestBody: Record<string, unknown> = {
    mode: input.mode,
    input_text: input.inputText
  };
  if (typeof input.layerCount === "number" && Number.isFinite(input.layerCount)) {
    requestBody.layer_count = input.layerCount;
  }
  const payload = await readJson<any>(
    await request(`${AI_BASE_URL()}/scene-setup/generate`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify(requestBody)
    })
  );
  return {
    mode: (payload.mode === "keywords" ? "keywords" : "long_text") as "keywords" | "long_text",
    usedModel: String(payload.used_model ?? ""),
    usedWebSearch: Boolean(payload.used_web_search),
    sceneName: String(payload.scene_name ?? ""),
    sceneSummary: String(payload.scene_summary ?? ""),
    selectedLayerId: String(payload.selected_layer_id ?? ""),
    sceneLayers: Array.isArray(payload.scene_layers) ? payload.scene_layers.map(normalizeSceneTreeNode) : [],
    modelRecoveries: normalizeModelRecoveries(payload.model_recoveries)
  };
}

export async function assistPersonaSetting(
  input: PersonaSettingAssistInput
): Promise<PersonaSettingAssistOutput> {
  const payload = await readJson<any>(
    await request(`${AI_BASE_URL()}/personas/assist-setting`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        name: input.name,
        summary: input.summary,
        slots: input.slots.map(serializeSlot),
        rewrite_strength: input.rewriteStrength
      })
    })
  );
  const rawSlots: any[] = Array.isArray(payload.slots) ? payload.slots : [];
  return {
    slots: rawSlots.map((s: any) => ({
      kind: String(s.kind ?? "custom"),
      label: String(s.label ?? s.kind ?? ""),
      content: String(s.content ?? ""),
      weight: Number(s.weight ?? 1),
      locked: Boolean(s.locked),
      sortOrder: Number(s.sort_order ?? 0)
    })),
    systemPromptSuggestion: String(payload.system_prompt_suggestion ?? ""),
    modelRecoveries: normalizeModelRecoveries(payload.model_recoveries)
  };
}

export async function assistPersonaSlot(
  input: PersonaSlotAssistInput
): Promise<PersonaSlotAssistOutput> {
  const payload = await readJson<any>(
    await request(`${AI_BASE_URL()}/personas/assist-slot`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        name: input.name,
        summary: input.summary,
        slot: serializeSlot(input.slot),
        rewrite_strength: input.rewriteStrength
      })
    })
  );
  const slot = payload.slot ?? {};
  return {
    slot: {
      kind: String(slot.kind ?? "custom"),
      label: String(slot.label ?? slot.kind ?? ""),
      content: String(slot.content ?? ""),
      weight: Number(slot.weight ?? 1),
      locked: Boolean(slot.locked),
      sortOrder: Number(slot.sort_order ?? 0)
    },
    modelRecoveries: normalizeModelRecoveries(payload.model_recoveries)
  };
}

export async function listDocuments(): Promise<DocumentRecord[]> {
  const payload = await readJson<{ items: any[] }>(
    await request(`${AI_BASE_URL()}/documents`)
  );
  return payload.items.map(normalizeDocument);
}

export async function getDocumentDebug(documentId: string): Promise<DocumentDebugRecord> {
  const payload = await readJson<any>(
    await request(`${AI_BASE_URL()}/documents/${documentId}/debug`)
  );
  return normalizeDebugRecord(payload);
}

export async function getDocumentPlanningContext(
  documentId: string
): Promise<DocumentPlanningContext> {
  const payload = await readJson<any>(
    await request(`${AI_BASE_URL()}/documents/${documentId}/planning-context`)
  );
  return normalizePlanningContext(payload);
}

export async function getDocumentPlanningTrace(
  documentId: string
): Promise<DocumentPlanningTraceResponse> {
  const payload = await readJson<any>(
    await request(`${AI_BASE_URL()}/documents/${documentId}/planning-trace`)
  );
  return normalizePlanningTraceResponse(payload);
}

export async function getModelToolConfig(): Promise<ModelToolConfig> {
  const payload = await readJson<any>(
    await request(`${AI_BASE_URL()}/model-tools/config`)
  );
  return normalizeModelToolConfig(payload);
}

export async function updateModelToolConfig(
  toggles: ModelToolToggle[]
): Promise<ModelToolConfig> {
  const payload = await readJson<any>(
    await request(`${AI_BASE_URL()}/model-tools/config`, {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        toggles: toggles.map((toggle) => ({
          stage_name: toggle.stageName,
          tool_name: toggle.toolName,
          enabled: toggle.enabled
        }))
      })
    })
  );
  return normalizeModelToolConfig(payload);
}

export async function getRuntimeSettings(): Promise<RuntimeSettings> {
  const payload = await readJson<any>(
    await request(`${AI_BASE_URL()}/runtime-settings`)
  );
  return normalizeRuntimeSettings(payload);
}

export async function getSceneSetupState(): Promise<SceneSetupStatePayload> {
  const payload = await readJson<any>(
    await request(`${AI_BASE_URL()}/scene-setup`)
  );
  return normalizeSceneSetupState(payload);
}

export async function updateSceneSetupState(input: {
  sceneLayers: unknown[];
  selectedLayerId: string;
  collapsedLayerIds: string[];
  sceneName?: string;
  sceneSummary?: string;
  sceneProfile?: import("@vibe-learner/shared").SceneProfile | null;
}): Promise<SceneSetupStatePayload> {
  const payload = await readJson<any>(
    await request(`${AI_BASE_URL()}/scene-setup`, {
      method: "PUT",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        scene_name: input.sceneName ?? input.sceneProfile?.sceneName ?? "",
        scene_summary: input.sceneSummary ?? input.sceneProfile?.summary ?? "",
        scene_layers: serializeSceneTree(input.sceneLayers as import("@vibe-learner/shared").SceneTreeNode[]),
        selected_layer_id: input.selectedLayerId,
        collapsed_layer_ids: input.collapsedLayerIds,
        scene_profile: serializeSceneProfile(input.sceneProfile)
      })
    })
  );
  return normalizeSceneSetupState(payload);
}

export async function listSceneLibrary(): Promise<SceneLibraryItemPayload[]> {
  const payload = await readJson<{ items: any[] }>(
    await request(`${AI_BASE_URL()}/scene-library`)
  );
  return payload.items.map(normalizeSceneLibraryItem);
}

export async function getSceneLibraryItem(sceneId: string): Promise<SceneLibraryItemPayload> {
  const payload = await readJson<any>(
    await request(`${AI_BASE_URL()}/scene-library/${sceneId}`)
  );
  return normalizeSceneLibraryItem(payload);
}

export async function createSceneLibraryItem(input: {
  sceneName: string;
  sceneSummary: string;
  sceneLayers: unknown[];
  selectedLayerId: string;
  collapsedLayerIds: string[];
  sceneProfile?: import("@vibe-learner/shared").SceneProfile | null;
}): Promise<SceneLibraryItemPayload> {
  const payload = await readJson<any>(
    await request(`${AI_BASE_URL()}/scene-library`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        scene_name: input.sceneName,
        scene_summary: input.sceneSummary,
        scene_layers: serializeSceneTree(input.sceneLayers as import("@vibe-learner/shared").SceneTreeNode[]),
        selected_layer_id: input.selectedLayerId,
        collapsed_layer_ids: input.collapsedLayerIds,
        scene_profile: serializeSceneProfile(input.sceneProfile)
      })
    })
  );
  return normalizeSceneLibraryItem(payload);
}

export async function updateSceneLibraryItem(sceneId: string, input: {
  sceneName: string;
  sceneSummary: string;
  sceneLayers: unknown[];
  selectedLayerId: string;
  collapsedLayerIds: string[];
  sceneProfile?: import("@vibe-learner/shared").SceneProfile | null;
}): Promise<SceneLibraryItemPayload> {
  const payload = await readJson<any>(
    await request(`${AI_BASE_URL()}/scene-library/${sceneId}`, {
      method: "PUT",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        scene_name: input.sceneName,
        scene_summary: input.sceneSummary,
        scene_layers: serializeSceneTree(input.sceneLayers as import("@vibe-learner/shared").SceneTreeNode[]),
        selected_layer_id: input.selectedLayerId,
        collapsed_layer_ids: input.collapsedLayerIds,
        scene_profile: serializeSceneProfile(input.sceneProfile)
      })
    })
  );
  return normalizeSceneLibraryItem(payload);
}

export async function deleteSceneLibraryItem(sceneId: string): Promise<{ deletedSceneId: string }> {
  const payload = await readJson<any>(
    await request(`${AI_BASE_URL()}/scene-library/${sceneId}`, {
      method: "DELETE"
    })
  );
  return {
    deletedSceneId: String(payload.deleted_scene_id ?? sceneId),
  };
}

export async function listReusableSceneNodes(): Promise<ReusableSceneNodePayload[]> {
  const payload = await readJson<{ items: any[] }>(
    await request(`${AI_BASE_URL()}/reusable-scene-nodes`)
  );
  return payload.items.map(normalizeReusableSceneNode);
}

export async function createReusableSceneNode(input: {
  nodeType: "layer" | "object";
  title: string;
  summary?: string;
  tags?: string[];
  reuseId?: string;
  reuseHint?: string;
  sourceSceneId?: string;
  sourceSceneName?: string;
  layerNode?: import("@vibe-learner/shared").SceneTreeNode | null;
  objectNode?: import("@vibe-learner/shared").SceneObjectSnapshot | null;
}): Promise<ReusableSceneNodePayload> {
  const payload = await readJson<any>(
    await request(`${AI_BASE_URL()}/reusable-scene-nodes`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        node_type: input.nodeType,
        title: input.title,
        summary: input.summary ?? "",
        tags: input.tags ?? [],
        reuse_id: input.reuseId ?? "",
        reuse_hint: input.reuseHint ?? "",
        source_scene_id: input.sourceSceneId ?? "",
        source_scene_name: input.sourceSceneName ?? "",
        layer_node: input.layerNode ? serializeSceneTree([input.layerNode])[0] : null,
        object_node: input.objectNode
          ? {
              id: input.objectNode.id,
              name: input.objectNode.name,
              description: input.objectNode.description,
              interaction: input.objectNode.interaction,
              tags: input.objectNode.tags,
              reuse_id: input.objectNode.reuseId,
              reuse_hint: input.objectNode.reuseHint,
            }
          : null,
      })
    })
  );
  return normalizeReusableSceneNode(payload);
}

export async function deleteReusableSceneNode(nodeId: string): Promise<{ deletedReusableSceneNodeId: string }> {
  const payload = await readJson<any>(
    await request(`${AI_BASE_URL()}/reusable-scene-nodes/${nodeId}`, {
      method: "DELETE"
    })
  );
  return {
    deletedReusableSceneNodeId: String(payload.deleted_reusable_scene_node_id ?? nodeId),
  };
}

export async function updateRuntimeSettings(
  patch: RuntimeSettingsPatch
): Promise<RuntimeSettings> {
  const payload = await readJson<any>(
    await request(`${AI_BASE_URL()}/runtime-settings`, {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        plan_provider: patch.planProvider,
        openai_api_key: patch.openaiApiKey,
        openai_base_url: patch.openaiBaseUrl,
        openai_plan_api_key: patch.openaiPlanApiKey,
        openai_plan_base_url: patch.openaiPlanBaseUrl,
        openai_plan_model: patch.openaiPlanModel,
        openai_setting_api_key: patch.openaiSettingApiKey,
        openai_setting_base_url: patch.openaiSettingBaseUrl,
        openai_setting_model: patch.openaiSettingModel,
        openai_setting_web_search_enabled: patch.openaiSettingWebSearchEnabled,
        openai_chat_api_key: patch.openaiChatApiKey,
        openai_chat_base_url: patch.openaiChatBaseUrl,
        openai_chat_model: patch.openaiChatModel,
        openai_chat_temperature: patch.openaiChatTemperature,
        openai_setting_temperature: patch.openaiSettingTemperature,
        openai_setting_max_tokens: patch.openaiSettingMaxTokens,
        openai_chat_max_tokens: patch.openaiChatMaxTokens,
        openai_chat_history_messages: patch.openaiChatHistoryMessages,
        openai_chat_tool_max_rounds: patch.openaiChatToolMaxRounds,
        openai_embedding_model: patch.openaiEmbeddingModel,
        openai_chat_model_multimodal: patch.openaiChatModelMultimodal,
        openai_timeout_seconds: patch.openaiTimeoutSeconds,
        openai_plan_model_multimodal: patch.openaiPlanModelMultimodal,
        openai_plan_fallback_model: patch.openaiPlanFallbackModel,
        openai_plan_fallback_disable_tools: patch.openaiPlanFallbackDisableTools,
        show_debug_info: patch.showDebugInfo
      })
    })
  );
  return normalizeRuntimeSettings(payload);
}

export async function applyRuntimeSessionSecrets(patch: {
  openaiApiKey?: string;
  openaiPlanApiKey?: string;
  openaiSettingApiKey?: string;
  openaiChatApiKey?: string;
}): Promise<RuntimeSettings> {
  const payload = await readJson<any>(
    await request(`${AI_BASE_URL()}/runtime-settings/session-secrets`, {
      method: "PUT",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        openai_api_key: patch.openaiApiKey,
        openai_plan_api_key: patch.openaiPlanApiKey,
        openai_setting_api_key: patch.openaiSettingApiKey,
        openai_chat_api_key: patch.openaiChatApiKey
      })
    })
  );
  return normalizeRuntimeSettings(payload);
}

export async function clearRuntimeSessionSecrets(): Promise<RuntimeSettings> {
  const payload = await readJson<any>(
    await request(`${AI_BASE_URL()}/runtime-settings/session-secrets`, {
      method: "DELETE"
    })
  );
  return normalizeRuntimeSettings(payload);
}

export async function probeRuntimeOpenAIModels(input: {
  apiKey: string;
  baseUrl: string;
}): Promise<RuntimeOpenAIProbeResult> {
  const payload = await readJson<any>(
    await request(`${AI_BASE_URL()}/runtime-settings/check-openai-models`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        api_key: input.apiKey,
        base_url: input.baseUrl
      })
    })
  );
  return {
    available: Boolean(payload.available),
    models: Array.isArray(payload.models)
      ? payload.models.map((item: unknown) => String(item))
      : [],
    capabilities:
      payload.capabilities && typeof payload.capabilities === "object"
        ? Object.fromEntries(
            Object.entries(payload.capabilities).map(([modelId, capability]) => [
              String(modelId),
              {
                inputModalities: Array.isArray((capability as any)?.input_modalities)
                  ? (capability as any).input_modalities.map((item: unknown) => String(item))
                  : [],
                outputModalities: Array.isArray((capability as any)?.output_modalities)
                  ? (capability as any).output_modalities.map((item: unknown) => String(item))
                  : [],
                toolTypes: Array.isArray((capability as any)?.tool_types)
                  ? (capability as any).tool_types.map((item: unknown) => String(item))
                  : [],
                multimodal: normalizeRuntimeCapabilitySignal((capability as any)?.multimodal),
                webSearch: normalizeRuntimeCapabilitySignal((capability as any)?.web_search)
              }
            ])
          )
        : {},
    error: String(payload.error ?? "")
  };
}

export async function getDocumentProcessEvents(documentId: string): Promise<StreamReport> {
  const payload = await readJson<any>(
    await request(`${AI_BASE_URL()}/documents/${documentId}/process-events`)
  );
  return normalizeStreamReport(payload);
}

export async function getDocumentPlanEvents(documentId: string): Promise<StreamReport> {
  const payload = await readJson<any>(
    await request(`${AI_BASE_URL()}/documents/${documentId}/plan-events`)
  );
  return normalizeStreamReport(payload);
}

export async function uploadDocument(file: File): Promise<DocumentRecord> {
  const form = new FormData();
  form.append("file", file);
  const payload = await readJson<any>(
    await request(`${AI_BASE_URL()}/documents`, {
      method: "POST",
      body: form
    })
  );
  return normalizeDocument(payload);
}

export async function uploadAndProcessDocument(file: File): Promise<DocumentRecord> {
  const uploaded = await uploadDocument(file);
  return processDocument(uploaded.id);
}

export async function processDocument(
  documentId: string,
  options?: {
    forceOcr?: boolean;
  }
): Promise<DocumentRecord> {
  const payload = await readJson<any>(
    await request(`${AI_BASE_URL()}/documents/${documentId}/process`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        force_ocr: Boolean(options?.forceOcr)
      })
    })
  );
  return normalizeDocument(payload);
}

export async function processDocumentStream(
  documentId: string,
  options: {
    forceOcr?: boolean;
  },
  onEvent: (event: { stage: string; payload: Record<string, unknown> }) => void
): Promise<DocumentRecord> {
  const response = await request(`${AI_BASE_URL()}/documents/${documentId}/process/stream`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify({
      force_ocr: Boolean(options.forceOcr)
    })
  });
  if (!response.ok || !response.body) {
    const text = await response.text();
    throw new Error(text || `HTTP ${response.status}`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let finalDocument: DocumentRecord | null = null;
  let streamError: string | null = null;

  while (true) {
    const { done, value } = await reader.read();
    buffer += decoder.decode(value ?? new Uint8Array(), { stream: !done });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";
    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed) {
        continue;
      }
      const event = JSON.parse(trimmed) as {
        stage: string;
        payload?: Record<string, unknown>;
        document?: any;
      };
      onEvent({
        stage: event.stage,
        payload: event.payload ?? {}
      });
      if (event.stage === "stream_error") {
        streamError = formatStreamErrorPayload(event.payload, "processing_stream_error");
      }
      if (event.document) {
        finalDocument = normalizeDocument(event.document);
      }
    }
    if (done) {
      break;
    }
  }

  if (streamError) {
    throw new Error(streamError);
  }
  if (!finalDocument) {
    throw new Error("processing_stream_ended_without_document");
  }
  return finalDocument;
}

export async function createLearningPlan(goal: LearningGoal): Promise<LearningPlan> {
  const sceneSummary = goal.sceneProfileSummary ?? goal.sceneProfile?.summary ?? "";
  const payload = await readJson<any>(
    await request(`${AI_BASE_URL()}/learning-plans`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        document_id: goal.documentId ?? "",
        persona_id: goal.personaId,
        objective: goal.objective,
        scene_profile_summary: sceneSummary,
        scene_profile: serializeSceneProfile(goal.sceneProfile)
      })
    })
  );
  return normalizePlan(payload);
}

export async function listLearningPlans(): Promise<LearningPlan[]> {
  const payload = await readJson<{ items: any[] }>(
    await request(`${AI_BASE_URL()}/learning-plans`)
  );
  return payload.items.map(normalizePlan);
}

export async function updateDocumentStudyUnitTitle(
  documentId: string,
  studyUnitId: string,
  title: string
): Promise<DocumentStudyUnitUpdatePayload> {
  const payload = await readJson<{
    document: any;
    plans: any[];
  }>(
    await request(`${AI_BASE_URL()}/documents/${documentId}/study-units/${studyUnitId}`, {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        title
      })
    })
  );
  return {
    document: normalizeDocument(payload.document),
    plans: payload.plans.map(normalizePlan)
  };
}

export async function updateLearningPlanTitle(
  planId: string,
  courseTitle: string
): Promise<LearningPlan> {
  const payload = await readJson<any>(
    await request(`${AI_BASE_URL()}/learning-plans/${planId}`, {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        course_title: courseTitle
      })
    })
  );
  return normalizePlan(payload);
}

export async function updateLearningPlanStudyChapters(
  planId: string,
  studyChapters: string[]
): Promise<LearningPlan> {
  const payload = await readJson<any>(
    await request(`${AI_BASE_URL()}/learning-plans/${planId}`, {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        study_chapters: studyChapters
      })
    })
  );
  return normalizePlan(payload);
}

export async function updateLearningPlanProgress(input: {
  planId: string;
  scheduleIds: string[];
  status: string;
  note?: string;
}): Promise<LearningPlan> {
  const payload = await readJson<any>(
    await request(`${AI_BASE_URL()}/learning-plans/${input.planId}/progress`, {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        schedule_ids: input.scheduleIds,
        status: input.status,
        note: input.note ?? ""
      })
    })
  );
  return normalizePlan(payload);
}

export async function answerLearningPlanQuestion(input: {
  planId: string;
  questionId: string;
  answer: string;
}): Promise<LearningPlan> {
  const payload = await readJson<any>(
    await request(
      `${AI_BASE_URL()}/learning-plans/${input.planId}/planning-questions/${input.questionId}`,
      {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          answer: input.answer
        })
      }
    )
  );
  return normalizePlan(payload);
}

export async function deleteLearningPlan(planId: string): Promise<void> {
  await readJson<{ deleted_plan_id: string }>(
    await request(`${AI_BASE_URL()}/learning-plans/${planId}`, {
      method: "DELETE"
    })
  );
}

export async function createLearningPlanStream(
  goal: LearningGoal,
  onEvent: (event: { stage: string; payload: Record<string, unknown> }) => void
): Promise<LearningPlan> {
  const sceneSummary = goal.sceneProfileSummary ?? goal.sceneProfile?.summary ?? "";
  const response = await request(`${AI_BASE_URL()}/learning-plans/stream`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify({
      document_id: goal.documentId ?? "",
      persona_id: goal.personaId,
      objective: goal.objective,
      scene_profile_summary: sceneSummary,
      scene_profile: serializeSceneProfile(goal.sceneProfile)
    })
  });
  if (!response.ok || !response.body) {
    const text = await response.text();
    throw new Error(text || `HTTP ${response.status}`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let finalPlan: LearningPlan | null = null;
  let streamError: string | null = null;

  while (true) {
    const { done, value } = await reader.read();
    buffer += decoder.decode(value ?? new Uint8Array(), { stream: !done });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";
    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed) {
        continue;
      }
      const event = JSON.parse(trimmed) as {
        stage: string;
        payload?: Record<string, unknown>;
        plan?: any;
      };
      onEvent({
        stage: event.stage,
        payload: event.payload ?? {}
      });
      if (event.stage === "stream_error") {
        streamError = formatStreamErrorPayload(event.payload, "learning_plan_stream_error");
      }
      if (event.plan) {
        finalPlan = normalizePlan(event.plan);
      }
    }
    if (done) {
      break;
    }
  }

  if (streamError) {
    throw new Error(streamError);
  }
  if (!finalPlan) {
    throw new Error("learning_plan_stream_ended_without_plan");
  }
  return finalPlan;
}

export async function createStudySession(input: {
  documentId: string;
  personaId: string;
  planId?: string | null;
  sceneProfile?: import("@vibe-learner/shared").SceneProfile | null;
  sectionId: string;
  sectionTitle?: string;
  themeHint?: string;
}): Promise<StudySessionRecord> {
  const payload = await readJson<any>(
    await request(`${AI_BASE_URL()}/study-sessions`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        document_id: input.documentId,
        persona_id: input.personaId,
        plan_id: input.planId ?? null,
        scene_profile: serializeSceneProfile(input.sceneProfile),
        section_id: input.sectionId,
        section_title: input.sectionTitle ?? "",
        theme_hint: input.themeHint ?? ""
      })
    })
  );
  return normalizeSession(payload);
}

export async function listStudySessions(input: {
  documentId?: string;
  personaId?: string;
  planId?: string;
  sectionId?: string;
}): Promise<StudySessionRecord[]> {
  const query = new URLSearchParams();
  if (input.documentId) query.set("document_id", input.documentId);
  if (input.personaId) query.set("persona_id", input.personaId);
  if (input.planId) query.set("plan_id", input.planId);
  if (input.sectionId) query.set("section_id", input.sectionId);
  const suffix = query.toString();
  const payload = await readJson<{ items: any[] }>(
    await request(`${AI_BASE_URL()}/study-sessions${suffix ? `?${suffix}` : ""}`)
  );
  return payload.items.map(normalizeSession);
}

export async function updateStudySessionSection(input: {
  sessionId: string;
  sectionId?: string;
  sceneProfile?: import("@vibe-learner/shared").SceneProfile | null;
}): Promise<StudySessionRecord> {
  const body: Record<string, unknown> = {};
  if (typeof input.sectionId === "string") {
    body.section_id = input.sectionId;
  }
  if (Object.prototype.hasOwnProperty.call(input, "sceneProfile")) {
    body.scene_profile = serializeSceneProfile(input.sceneProfile ?? null);
  }
  const payload = await readJson<any>(
    await request(`${AI_BASE_URL()}/study-sessions/${input.sessionId}`, {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify(body)
    })
  );
  return normalizeSession(payload);
}

export async function sendStudyMessage(input: {
  sessionId: string;
  message: string;
  messageKind?: string;
  followUpId?: string;
  attachments?: File[];
}): Promise<StudyChatExchangeResponse> {
  const hasAttachments = Boolean(input.attachments?.length);
  const response = hasAttachments
    ? await request(`${AI_BASE_URL()}/study-sessions/${input.sessionId}/chat-with-attachments`, {
        method: "POST",
        body: (() => {
          const form = new FormData();
          form.set("message", input.message);
          form.set("message_kind", input.messageKind ?? "learner");
          form.set("follow_up_id", input.followUpId ?? "");
          (input.attachments ?? []).forEach((file) => {
            form.append("files", file);
          });
          return form;
        })()
      })
    : await request(`${AI_BASE_URL()}/study-sessions/${input.sessionId}/chat`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          message: input.message,
          message_kind: input.messageKind ?? "learner",
          follow_up_id: input.followUpId ?? "",
        })
      });
  const payload = await readJson<any>(response);
  const repaired = repairLegacyRichReply(
    String(payload.reply ?? ""),
    normalizeRichBlocks(payload.rich_blocks)
  );

  return {
    reply: repaired.reply,
    citations: payload.citations.map((citation: any) => ({
      sectionId: String(citation.section_id ?? ""),
      title: citation.title,
      pageStart: citation.page_start,
      pageEnd: citation.page_end,
      sourceKind: citation.source_kind ? String(citation.source_kind) : undefined,
      sourceId: citation.source_id ? String(citation.source_id) : undefined,
    })),
    characterEvents: payload.character_events.map((event: any) => ({
      emotion: event.emotion,
      action: event.action,
      speechStyle: event.speech_style,
      sceneHint: event.scene_hint,
      lineSegmentId: event.line_segment_id,
      timingHint: event.timing_hint,
      toolName: event.tool_name ? String(event.tool_name) : undefined,
      toolSummary: event.tool_summary ? compactPreviewString(event.tool_summary, 240) : undefined,
      deliveryCue: event.delivery_cue ? compactPreviewString(event.delivery_cue, 160) : undefined,
      commentary: event.commentary ? compactPreviewString(event.commentary, 280) : undefined,
    })),
    richBlocks: repaired.richBlocks,
    interactiveQuestion: normalizeInteractiveQuestion(payload.interactive_question),
    personaSlotTrace: (payload.persona_slot_trace ?? []).map((item: any) => ({
      kind: String(item.kind ?? "custom"),
      label: String(item.label ?? item.kind ?? ""),
      contentExcerpt: String(item.content_excerpt ?? ""),
      reason: String(item.reason ?? "")
    })),
    memoryTrace: normalizeMemoryTrace(payload.memory_trace),
    toolCalls: normalizeChatToolCalls(payload.tool_calls),
    sceneProfile: normalizeSceneProfile(payload.scene_profile),
    modelRecoveries: normalizeModelRecoveries(payload.model_recoveries),
    session: normalizeSession(payload.session)
  };
}

export async function submitStudyQuestionAttempt(input: {
  sessionId: string;
  questionType: "multiple_choice" | "fill_blank";
  prompt: string;
  topic: string;
  difficulty: "easy" | "medium" | "hard";
  options: Array<{ key: string; text: string }>;
  callBack?: boolean;
  answerKey?: string;
  acceptedAnswers: string[];
  submittedAnswer: string;
  isCorrect: boolean;
  explanation: string;
}): Promise<StudySessionRecord> {
  const payload = await readJson<any>(
    await request(`${AI_BASE_URL()}/study-sessions/${input.sessionId}/attempt`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        question_type: input.questionType,
        prompt: input.prompt,
        topic: input.topic,
        difficulty: input.difficulty,
        options: input.options.map((option) => ({ key: option.key, text: option.text })),
        call_back: Boolean(input.callBack),
        answer_key: input.answerKey ?? null,
        accepted_answers: input.acceptedAnswers,
        submitted_answer: input.submittedAnswer,
        is_correct: input.isCorrect,
        explanation: input.explanation
      })
    })
  );
  return normalizeSession(payload);
}

export async function resolveStudyPlanConfirmation(input: {
  sessionId: string;
  confirmationId: string;
  decision: "approve" | "reject";
  note?: string;
}): Promise<StudyPlanConfirmationDecisionResponse> {
  const payload = await readJson<any>(
    await request(
      `${AI_BASE_URL()}/study-sessions/${input.sessionId}/plan-confirmations/${input.confirmationId}`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          decision: input.decision,
          note: input.note ?? "",
        })
      }
    )
  );
  return {
    session: normalizeSession(payload.session),
    plan: payload.plan ? normalizePlan(payload.plan) : null,
  };
}

function normalizeInteractiveQuestion(raw: any) {
  if (!raw || typeof raw !== "object") {
    return undefined;
  }
  const questionType = raw.question_type;
  if (questionType !== "multiple_choice" && questionType !== "fill_blank") {
    return undefined;
  }
  return {
    questionType,
    prompt: String(raw.prompt ?? "").trim(),
    difficulty: (raw.difficulty === "easy" || raw.difficulty === "hard" ? raw.difficulty : "medium") as
      | "easy"
      | "medium"
      | "hard",
    topic: String(raw.topic ?? "").trim(),
    options: Array.isArray(raw.options)
      ? raw.options
          .map((option: any, index: number) => {
            const text = String(option?.text ?? option ?? "").trim();
            if (!text) {
              return null;
            }
            return {
              key: String(option?.key ?? String.fromCharCode(65 + index)),
              text
            };
          })
          .filter(Boolean)
      : [],
    callBack: Boolean(raw.call_back),
    answerKey: raw.answer_key ? String(raw.answer_key) : undefined,
    acceptedAnswers: Array.isArray(raw.accepted_answers)
      ? raw.accepted_answers
          .map((value: unknown) => String(value ?? "").trim())
          .filter((value: string) => value.length > 0)
      : [],
    explanation: String(raw.explanation ?? "").trim(),
    submittedAnswer: String(raw.submitted_answer ?? "").trim() || undefined,
    isCorrect: typeof raw.is_correct === "boolean" ? raw.is_correct : undefined,
    feedbackText: String(raw.feedback_text ?? "").trim() || undefined,
  };
}

export async function getModelUsageStats(): Promise<TokenUsageStats> {
  const response = await request(`${AI_BASE_URL()}/model-usage/stats`);
  const raw = await readJson<any>(response);
  return {
    buckets: (raw.buckets ?? []).map((b: any) => ({
      date: String(b.date ?? ""),
      feature: String(b.feature ?? ""),
      model: String(b.model ?? ""),
      promptTokens: Number(b.prompt_tokens ?? 0),
      completionTokens: Number(b.completion_tokens ?? 0),
      totalTokens: Number(b.total_tokens ?? 0),
    })),
    records: (raw.records ?? []).map((item: any) => ({
      id: String(item.id ?? ""),
      createdAt: String(item.created_at ?? ""),
      feature: String(item.feature ?? ""),
      model: String(item.model ?? ""),
      promptTokens: Number(item.prompt_tokens ?? 0),
      completionTokens: Number(item.completion_tokens ?? 0),
      totalTokens: Number(item.total_tokens ?? 0),
    })),
    totalPromptTokens: Number(raw.total_prompt_tokens ?? 0),
    totalCompletionTokens: Number(raw.total_completion_tokens ?? 0),
    totalTokens: Number(raw.total_tokens ?? 0),
  };
}
