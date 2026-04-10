import type { CharacterStateEvent } from "./character";

export interface Citation {
  sectionId: string;
  title: string;
  pageStart: number;
  pageEnd: number;
}

export interface LearningGoal {
  documentId: string;
  personaId: string;
  // Learner-authored study goal captured at plan creation time.
  objective: string;
}

export interface LearningPlan {
  id: string;
  documentId: string;
  personaId: string;
  // Generated textbook-grounded course title for the plan header.
  courseTitle: string;
  // Stable learner-authored study goal captured at plan creation time.
  objective: string;
  // One or two sentence learner-facing summary of the plan. This is not a title.
  overview: string;
  // Ordered weekly study topics for sequential display.
  weeklyFocus: string[];
  // Actionable learner tasks for the current session/day.
  todayTasks: string[];
  studyUnits: StudyUnit[];
  schedule: StudyScheduleItem[];
  createdAt: string;
}

export interface PlanningSectionRef {
  sectionId: string;
  title: string;
  level: number;
  pageStart: number;
  pageEnd: number;
}

export interface PlanningOutlineNode extends PlanningSectionRef {
  children: PlanningSectionRef[];
}

export interface PlanningChunkExcerpt {
  chunkId: string;
  sectionId: string;
  pageStart: number;
  pageEnd: number;
  charCount: number;
  content: string;
}

export interface PlanningStudyUnitContext {
  unitId: string;
  title: string;
  pageStart: number;
  pageEnd: number;
  summary: string;
  unitKind: string;
  includeInPlan: boolean;
  subsectionTitles: string[];
  relatedSectionIds: string[];
  detailToolTargetId: string;
}

export interface StudyUnitPlanningDetail {
  unitId: string;
  title: string;
  pageStart: number;
  pageEnd: number;
  summary: string;
  unitKind: string;
  includeInPlan: boolean;
  relatedSectionIds: string[];
  subsectionTitles: string[];
  relatedSections: PlanningSectionRef[];
  chunkCount: number;
  chunkExcerpts: PlanningChunkExcerpt[];
}

export interface PlanningToolSpec {
  name: string;
  description: string;
}

export interface DocumentPlanningContext {
  documentId: string;
  courseOutline: PlanningOutlineNode[];
  studyUnits: PlanningStudyUnitContext[];
  detailMap: Record<string, StudyUnitPlanningDetail>;
  availableTools: PlanningToolSpec[];
}

export interface PlanToolCallTrace {
  toolCallId: string;
  toolName: string;
  argumentsJson: string;
  resultSummary: string;
  resultJson: string;
}

export interface PlanGenerationRoundTrace {
  roundIndex: number;
  finishReason: string;
  assistantContent: string;
  thinking: string;
  elapsedMs: number;
  timeoutSeconds: number;
  toolCalls: PlanToolCallTrace[];
}

export interface PlanGenerationTrace {
  documentId: string;
  planId: string | null;
  model: string;
  createdAt: string;
  rounds: PlanGenerationRoundTrace[];
}

export interface PlanGenerationTraceSummary {
  roundCount: number;
  toolCallCount: number;
  latestFinishReason: string;
}

export interface DocumentPlanningTraceResponse {
  documentId: string;
  hasTrace: boolean;
  summary: PlanGenerationTraceSummary;
  trace: PlanGenerationTrace | null;
}

export interface StreamEvent {
  stage: string;
  payload: Record<string, unknown>;
  createdAt: string;
}

export interface StreamReport {
  documentId: string;
  streamKind: string;
  status: string;
  createdAt: string;
  updatedAt: string;
  events: StreamEvent[];
}

export interface StudyChatRequest {
  message: string;
}

export interface StudyChatResponse {
  reply: string;
  citations: Citation[];
  characterEvents: CharacterStateEvent[];
}

export interface Exercise {
  id: string;
  sectionId: string;
  prompt: string;
  type: "short_answer" | "multiple_choice";
  difficulty: "easy" | "medium" | "hard";
  guidance: string;
}

export interface SubmissionFeedback {
  score: number;
  diagnosis: string[];
  recommendation: string;
  characterEvents: CharacterStateEvent[];
}

export interface DocumentSection {
  id: string;
  documentId: string;
  title: string;
  pageStart: number;
  pageEnd: number;
  level: number;
}

export interface StudyUnit {
  id: string;
  documentId: string;
  title: string;
  pageStart: number;
  pageEnd: number;
  unitKind: string;
  includeInPlan: boolean;
  sourceSectionIds: string[];
  summary: string;
  confidence: number;
}

export interface StudyScheduleItem {
  id: string;
  unitId: string;
  title: string;
  focus: string;
  activityType: string;
  status: string;
}

export interface DocumentRecord {
  id: string;
  title: string;
  originalFilename: string;
  storedPath: string;
  status: string;
  ocrStatus: string;
  createdAt: string;
  updatedAt: string;
  sections: DocumentSection[];
  studyUnits: StudyUnit[];
  studyUnitCount: number;
  pageCount: number;
  chunkCount: number;
  previewExcerpt: string;
  debugReady: boolean;
}

export interface StudySessionRecord {
  id: string;
  documentId: string;
  personaId: string;
  sectionId: string;
  status: string;
  createdAt: string;
  updatedAt: string;
}

export interface HeadingCandidate {
  pageNumber: number;
  text: string;
  fontSize: number;
  confidence: number;
}

export interface DocumentPageRecord {
  pageNumber: number;
  charCount: number;
  wordCount: number;
  textPreview: string;
  dominantFontSize: number;
  extractionSource: string;
  headingCandidates: HeadingCandidate[];
}

export interface DocumentChunkRecord {
  id: string;
  documentId: string;
  sectionId: string;
  pageStart: number;
  pageEnd: number;
  charCount: number;
  textPreview: string;
  content: string;
}

export interface ParseWarning {
  code: string;
  message: string;
  pageNumber: number | null;
}

export interface DocumentDebugRecord {
  documentId: string;
  parserName: string;
  processedAt: string;
  pageCount: number;
  totalCharacters: number;
  extractionMethod: string;
  ocrApplied: boolean;
  ocrLanguage: string | null;
  pages: DocumentPageRecord[];
  sections: DocumentSection[];
  studyUnits: StudyUnit[];
  chunks: DocumentChunkRecord[];
  warnings: ParseWarning[];
  dominantLanguageHint: string;
}
