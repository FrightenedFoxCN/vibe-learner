import type {
  CreatePersonaInput,
  DocumentPlanningContext,
  DocumentPlanningTraceResponse,
  PlanGenerationTrace,
  DocumentDebugRecord,
  DocumentRecord,
  LearningGoal,
  LearningPlan,
  PersonaProfile,
  StreamReport,
  StudyChatResponse,
  StudySessionRecord
} from "@vibe-learner/shared";

import { compactPreviewString, compactPreviewValue } from "./preview";

export interface StudyChatExchangeResponse extends StudyChatResponse {
  session: StudySessionRecord;
}

export interface PersonaAssets {
  personaId: string;
  renderer: string;
  assetManifest: Record<string, unknown>;
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
}

export interface PersonaSlotAssistInput {
  name: string;
  summary: string;
  slot: import("@vibe-learner/shared").PersonaSlot;
  rewriteStrength: number;
}

export interface PersonaSlotAssistOutput {
  slot: import("@vibe-learner/shared").PersonaSlot;
}

const AI_BASE_URL = process.env.NEXT_PUBLIC_AI_BASE_URL ?? "http://127.0.0.1:8000";

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
    throw new Error(`Cannot reach AI service at ${AI_BASE_URL}`);
  }
}

async function readJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `HTTP ${response.status}`);
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
  const suffixParts: string[] = [];
  if (internal) {
    suffixParts.push(`internal=${String(internal)}`);
  }
  if (statusCode) {
    suffixParts.push(`status=${String(statusCode)}`);
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
    systemPrompt: persona.system_prompt,
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

function normalizeDocument(document: any): DocumentRecord {
  return {
    id: document.id,
    title: document.title,
    originalFilename: document.original_filename,
    storedPath: document.stored_path,
    status: document.status,
    ocrStatus: document.ocr_status,
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
    ocrApplied: record.ocr_applied,
    ocrLanguage: record.ocr_language,
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
      }))
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
    courseTitle: plan.course_title,
    objective: plan.objective,
    overview: plan.overview,
    weeklyFocus: plan.weekly_focus,
    todayTasks: plan.today_tasks,
    studyUnits: plan.study_units.map(normalizeStudyUnit),
    schedule: plan.schedule.map(normalizeScheduleItem),
    createdAt: plan.created_at
  };
}

function normalizeSession(session: any): StudySessionRecord {
  return {
    id: session.id,
    documentId: session.document_id,
    personaId: session.persona_id,
    sectionId: session.section_id,
    sectionTitle: session.section_title ?? "",
    themeHint: session.theme_hint ?? "",
    sessionSystemPrompt: compactPreviewString(session.session_system_prompt ?? "", 1200),
    status: session.status,
    turns: (session.turns ?? []).map((turn: any) => ({
      learnerMessage: turn.learner_message,
      assistantReply: turn.assistant_reply,
      citations: (turn.citations ?? []).map((citation: any) => ({
        sectionId: citation.section_id,
        title: citation.title,
        pageStart: citation.page_start,
        pageEnd: citation.page_end
      })),
      characterEvents: (turn.character_events ?? []).map((event: any) => ({
        emotion: event.emotion,
        action: event.action,
        intensity: event.intensity,
        speechStyle: event.speech_style,
        sceneHint: event.scene_hint,
        lineSegmentId: event.line_segment_id,
        timingHint: event.timing_hint
      })),
      interactiveQuestion: normalizeInteractiveQuestion(turn.interactive_question),
      personaSlotTrace: (turn.persona_slot_trace ?? []).map((item: any) => ({
        kind: String(item.kind ?? "custom"),
        label: String(item.label ?? item.kind ?? ""),
        contentExcerpt: compactPreviewString(item.content_excerpt ?? "", 280),
        reason: String(item.reason ?? "")
      })),
      createdAt: turn.created_at
    })),
    createdAt: session.created_at,
    updatedAt: session.updated_at
  };
}

export async function listPersonas(): Promise<PersonaProfile[]> {
  const payload = await readJson<{ items: any[] }>(
    await request(`${AI_BASE_URL}/personas`)
  );
  return payload.items.map(normalizePersona);
}

export async function createPersona(input: CreatePersonaInput): Promise<PersonaProfile> {
  const payload = await readJson<any>(
    await request(`${AI_BASE_URL}/personas`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        name: input.name,
        summary: input.summary,
        system_prompt: input.systemPrompt,
        slots: input.slots.map(serializeSlot),
        available_emotions: input.availableEmotions,
        available_actions: input.availableActions,
        default_speech_style: input.defaultSpeechStyle
      })
    })
  );
  return normalizePersona(payload);
}

export async function updatePersona(
  personaId: string,
  input: CreatePersonaInput
): Promise<PersonaProfile> {
  const payload = await readJson<any>(
    await request(`${AI_BASE_URL}/personas/${personaId}`, {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        name: input.name,
        summary: input.summary,
        system_prompt: input.systemPrompt,
        slots: input.slots.map(serializeSlot),
        available_emotions: input.availableEmotions,
        available_actions: input.availableActions,
        default_speech_style: input.defaultSpeechStyle
      })
    })
  );
  return normalizePersona(payload);
}

export async function getPersonaAssets(personaId: string): Promise<PersonaAssets> {
  const payload = await readJson<any>(
    await request(`${AI_BASE_URL}/personas/${personaId}/assets`)
  );
  return {
    personaId: payload.persona_id,
    renderer: payload.renderer,
    assetManifest: payload.asset_manifest ?? {}
  };
}

export async function assistPersonaSetting(
  input: PersonaSettingAssistInput
): Promise<PersonaSettingAssistOutput> {
  const payload = await readJson<any>(
    await request(`${AI_BASE_URL}/personas/assist-setting`, {
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
    systemPromptSuggestion: String(payload.system_prompt_suggestion ?? "")
  };
}

export async function assistPersonaSlot(
  input: PersonaSlotAssistInput
): Promise<PersonaSlotAssistOutput> {
  const payload = await readJson<any>(
    await request(`${AI_BASE_URL}/personas/assist-slot`, {
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
    }
  };
}

export async function listDocuments(): Promise<DocumentRecord[]> {
  const payload = await readJson<{ items: any[] }>(
    await request(`${AI_BASE_URL}/documents`)
  );
  return payload.items.map(normalizeDocument);
}

export async function getDocumentDebug(documentId: string): Promise<DocumentDebugRecord> {
  const payload = await readJson<any>(
    await request(`${AI_BASE_URL}/documents/${documentId}/debug`)
  );
  return normalizeDebugRecord(payload);
}

export async function getDocumentPlanningContext(
  documentId: string
): Promise<DocumentPlanningContext> {
  const payload = await readJson<any>(
    await request(`${AI_BASE_URL}/documents/${documentId}/planning-context`)
  );
  return normalizePlanningContext(payload);
}

export async function getDocumentPlanningTrace(
  documentId: string
): Promise<DocumentPlanningTraceResponse> {
  const payload = await readJson<any>(
    await request(`${AI_BASE_URL}/documents/${documentId}/planning-trace`)
  );
  return normalizePlanningTraceResponse(payload);
}

export async function getDocumentProcessEvents(documentId: string): Promise<StreamReport> {
  const payload = await readJson<any>(
    await request(`${AI_BASE_URL}/documents/${documentId}/process-events`)
  );
  return normalizeStreamReport(payload);
}

export async function getDocumentPlanEvents(documentId: string): Promise<StreamReport> {
  const payload = await readJson<any>(
    await request(`${AI_BASE_URL}/documents/${documentId}/plan-events`)
  );
  return normalizeStreamReport(payload);
}

export async function uploadDocument(file: File): Promise<DocumentRecord> {
  const form = new FormData();
  form.append("file", file);
  const payload = await readJson<any>(
    await request(`${AI_BASE_URL}/documents`, {
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
    await request(`${AI_BASE_URL}/documents/${documentId}/process`, {
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
  const response = await request(`${AI_BASE_URL}/documents/${documentId}/process/stream`, {
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
  const payload = await readJson<any>(
    await request(`${AI_BASE_URL}/learning-plans`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        document_id: goal.documentId,
        persona_id: goal.personaId,
        objective: goal.objective
      })
    })
  );
  return normalizePlan(payload);
}

export async function listLearningPlans(): Promise<LearningPlan[]> {
  const payload = await readJson<{ items: any[] }>(
    await request(`${AI_BASE_URL}/learning-plans`)
  );
  return payload.items.map(normalizePlan);
}

export async function createLearningPlanStream(
  goal: LearningGoal,
  onEvent: (event: { stage: string; payload: Record<string, unknown> }) => void
): Promise<LearningPlan> {
  const response = await request(`${AI_BASE_URL}/learning-plans/stream`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify({
      document_id: goal.documentId,
      persona_id: goal.personaId,
      objective: goal.objective
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
  sectionId: string;
  sectionTitle?: string;
  themeHint?: string;
}): Promise<StudySessionRecord> {
  const payload = await readJson<any>(
    await request(`${AI_BASE_URL}/study-sessions`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        document_id: input.documentId,
        persona_id: input.personaId,
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
  sectionId?: string;
}): Promise<StudySessionRecord[]> {
  const query = new URLSearchParams();
  if (input.documentId) query.set("document_id", input.documentId);
  if (input.personaId) query.set("persona_id", input.personaId);
  if (input.sectionId) query.set("section_id", input.sectionId);
  const suffix = query.toString();
  const payload = await readJson<{ items: any[] }>(
    await request(`${AI_BASE_URL}/study-sessions${suffix ? `?${suffix}` : ""}`)
  );
  return payload.items.map(normalizeSession);
}

export async function updateStudySessionSection(input: {
  sessionId: string;
  sectionId: string;
}): Promise<StudySessionRecord> {
  const payload = await readJson<any>(
    await request(`${AI_BASE_URL}/study-sessions/${input.sessionId}`, {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        section_id: input.sectionId
      })
    })
  );
  return normalizeSession(payload);
}

export async function sendStudyMessage(input: {
  sessionId: string;
  message: string;
}): Promise<StudyChatExchangeResponse> {
  const payload = await readJson<any>(
    await request(`${AI_BASE_URL}/study-sessions/${input.sessionId}/chat`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        message: input.message
      })
    })
  );

  return {
    reply: payload.reply,
    citations: payload.citations.map((citation: any) => ({
      sectionId: citation.section_id,
      title: citation.title,
      pageStart: citation.page_start,
      pageEnd: citation.page_end
    })),
    characterEvents: payload.character_events.map((event: any) => ({
      emotion: event.emotion,
      action: event.action,
      intensity: event.intensity,
      speechStyle: event.speech_style,
      sceneHint: event.scene_hint,
      lineSegmentId: event.line_segment_id,
      timingHint: event.timing_hint
    })),
    interactiveQuestion: normalizeInteractiveQuestion(payload.interactive_question),
    personaSlotTrace: (payload.persona_slot_trace ?? []).map((item: any) => ({
      kind: String(item.kind ?? "custom"),
      label: String(item.label ?? item.kind ?? ""),
      contentExcerpt: String(item.content_excerpt ?? ""),
      reason: String(item.reason ?? "")
    })),
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
  answerKey?: string;
  acceptedAnswers: string[];
  submittedAnswer: string;
  isCorrect: boolean;
  explanation: string;
}): Promise<StudySessionRecord> {
  const payload = await readJson<any>(
    await request(`${AI_BASE_URL}/study-sessions/${input.sessionId}/attempt`, {
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
    answerKey: raw.answer_key ? String(raw.answer_key) : undefined,
    acceptedAnswers: Array.isArray(raw.accepted_answers)
      ? raw.accepted_answers
          .map((value: unknown) => String(value ?? "").trim())
          .filter((value: string) => value.length > 0)
      : [],
    explanation: String(raw.explanation ?? "").trim()
  };
}
