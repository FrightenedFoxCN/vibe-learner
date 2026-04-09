import type {
  DocumentRecord,
  LearningGoal,
  LearningPlan,
  PersonaProfile,
  StudyChatResponse,
  StudySessionRecord
} from "@gal-learner/shared";

const AI_BASE_URL = process.env.NEXT_PUBLIC_AI_BASE_URL ?? "http://127.0.0.1:8000";

async function readJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `HTTP ${response.status}`);
  }
  return (await response.json()) as T;
}

function normalizePersona(persona: any): PersonaProfile {
  return {
    id: persona.id,
    name: persona.name,
    source: persona.source,
    summary: persona.summary,
    systemPrompt: persona.system_prompt,
    teachingStyle: persona.teaching_style,
    narrativeMode: persona.narrative_mode,
    encouragementStyle: persona.encouragement_style,
    correctionStyle: persona.correction_style,
    availableEmotions: persona.available_emotions,
    availableActions: persona.available_actions,
    defaultSpeechStyle: persona.default_speech_style
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
    sections: document.sections.map((section: any) => ({
      id: section.id,
      documentId: section.document_id,
      title: section.title,
      pageStart: section.page_start,
      pageEnd: section.page_end,
      level: section.level
    }))
  };
}

function normalizePlan(plan: any): LearningPlan {
  return {
    id: plan.id,
    documentId: plan.document_id,
    personaId: plan.persona_id,
    overview: plan.overview,
    weeklyFocus: plan.weekly_focus,
    todayTasks: plan.today_tasks
  };
}

function normalizeSession(session: any): StudySessionRecord {
  return {
    id: session.id,
    documentId: session.document_id,
    personaId: session.persona_id,
    sectionId: session.section_id,
    status: session.status,
    createdAt: session.created_at,
    updatedAt: session.updated_at
  };
}

export async function listPersonas(): Promise<PersonaProfile[]> {
  const payload = await readJson<{ items: any[] }>(await fetch(`${AI_BASE_URL}/personas`));
  return payload.items.map(normalizePersona);
}

export async function uploadAndProcessDocument(file: File): Promise<DocumentRecord> {
  const form = new FormData();
  form.append("file", file);
  const uploaded = normalizeDocument(
    await readJson<any>(
      await fetch(`${AI_BASE_URL}/documents`, {
        method: "POST",
        body: form
      })
    )
  );
  const processed = normalizeDocument(
    await readJson<any>(
      await fetch(`${AI_BASE_URL}/documents/${uploaded.id}/process`, {
        method: "POST"
      })
    )
  );
  return processed;
}

export async function createLearningPlan(goal: LearningGoal): Promise<LearningPlan> {
  const payload = await readJson<any>(
    await fetch(`${AI_BASE_URL}/learning-plans`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        document_id: goal.documentId,
        persona_id: goal.personaId,
        objective: goal.objective,
        deadline: goal.deadline,
        study_days_per_week: goal.studyDaysPerWeek,
        session_minutes: goal.sessionMinutes
      })
    })
  );
  return normalizePlan(payload);
}

export async function createStudySession(input: {
  documentId: string;
  personaId: string;
  sectionId: string;
}): Promise<StudySessionRecord> {
  const payload = await readJson<any>(
    await fetch(`${AI_BASE_URL}/study-sessions`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        document_id: input.documentId,
        persona_id: input.personaId,
        section_id: input.sectionId
      })
    })
  );
  return normalizeSession(payload);
}

export async function sendStudyMessage(input: {
  sessionId: string;
  message: string;
}): Promise<StudyChatResponse> {
  const payload = await readJson<any>(
    await fetch(`${AI_BASE_URL}/study-sessions/${input.sessionId}/chat`, {
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
    }))
  };
}
