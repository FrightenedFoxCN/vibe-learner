import type { CharacterStateEvent } from "./character";

export interface PersonaSlotTraceEntry {
  kind: string;
  label: string;
  contentExcerpt: string;
  reason: string;
}

export interface MemoryTraceHit {
  sessionId: string;
  sectionId: string;
  sceneTitle: string;
  score: number;
  snippet: string;
  createdAt: string;
  source?: "retriever" | "tool_call";
}

export interface Citation {
  sectionId: string;
  title: string;
  pageStart: number;
  pageEnd: number;
}

export interface LearningGoal {
  documentId: string;
  personaId: string;
  // 创建学习计划时记录的学习者原始目标文本。
  objective: string;
  // Optional scene summary chosen before planning.
  sceneProfileSummary?: string;
  // Optional structured scene profile chosen before planning.
  sceneProfile?: SceneProfile;
}

export interface SceneProfile {
  sceneName: string;
  sceneId: string;
  title: string;
  summary: string;
  tags: string[];
  selectedPath: string[];
  focusObjectNames: string[];
  sceneTree: SceneTreeNode[];
}

export interface SceneObjectSnapshot {
  id: string;
  name: string;
  description: string;
  interaction: string;
  tags: string;
}

export interface SceneTreeNode {
  id: string;
  title: string;
  scopeLabel: string;
  summary: string;
  atmosphere: string;
  rules: string;
  entrance: string;
  objects: SceneObjectSnapshot[];
  children: SceneTreeNode[];
}

export interface LearningPlan {
  id: string;
  documentId: string;
  personaId: string;
  // 系统生成的教材贴合型课程标题，用于计划头部展示。
  courseTitle: string;
  // Stable learner-authored study goal captured at plan creation time.
  objective: string;
  // Optional scene summary captured at plan creation time.
  sceneProfileSummary?: string;
  // Optional structured scene profile captured at plan creation time.
  sceneProfile?: SceneProfile;
  // One or two sentence learner-facing summary of the plan. This is not a title.
  overview: string;
  // Ordered study-chapter list used for navigation.
  studyChapters: string[];
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

export interface ModelToolConfigItem {
  name: string;
  label: string;
  description: string;
  category: string;
  categoryLabel: string;
  enabled: boolean;
  available: boolean;
  effectiveEnabled: boolean;
  auditBasis: string[];
  unavailableReason: string;
}

export interface ModelToolStageConfig {
  name: string;
  label: string;
  description: string;
  stageEnabled: boolean;
  auditBasis: string[];
  stageDisabledReason: string;
  tools: ModelToolConfigItem[];
}

export interface ModelToolConfig {
  updatedAt: string;
  stages: ModelToolStageConfig[];
}

export interface ModelToolToggle {
  stageName: string;
  toolName: string;
  enabled: boolean;
}

export interface RuntimeSettings {
  updatedAt: string;
  planProvider: "mock" | "openai";
  openaiApiKey: string;
  openaiBaseUrl: string;
  openaiPlanApiKey: string;
  openaiPlanBaseUrl: string;
  openaiPlanModel: string;
  openaiSettingApiKey: string;
  openaiSettingBaseUrl: string;
  openaiSettingModel: string;
  openaiChatApiKey: string;
  openaiChatBaseUrl: string;
  openaiChatModel: string;
  openaiChatTemperature: number;
  openaiSettingTemperature: number;
  openaiSettingMaxTokens: number;
  openaiChatMaxTokens: number;
  openaiChatHistoryMessages: number;
  openaiChatToolMaxRounds: number;
  openaiChatToolsEnabled: boolean;
  openaiChatMemoryToolEnabled: boolean;
  openaiEmbeddingModel: string;
  openaiChatModelMultimodal: boolean;
  openaiTimeoutSeconds: number;
  openaiPlanModelMultimodal: boolean;
  openaiPlanToolsEnabled: boolean;
  openaiPlanFallbackModel: string;
  openaiPlanFallbackDisableTools: boolean;
  showDebugInfo: boolean;
}

export interface RuntimeSettingsPatch {
  planProvider?: "mock" | "openai";
  openaiApiKey?: string;
  openaiBaseUrl?: string;
  openaiPlanApiKey?: string;
  openaiPlanBaseUrl?: string;
  openaiPlanModel?: string;
  openaiSettingApiKey?: string;
  openaiSettingBaseUrl?: string;
  openaiSettingModel?: string;
  openaiChatApiKey?: string;
  openaiChatBaseUrl?: string;
  openaiChatModel?: string;
  openaiChatTemperature?: number;
  openaiSettingTemperature?: number;
  openaiSettingMaxTokens?: number;
  openaiChatMaxTokens?: number;
  openaiChatHistoryMessages?: number;
  openaiChatToolMaxRounds?: number;
  openaiChatToolsEnabled?: boolean;
  openaiChatMemoryToolEnabled?: boolean;
  openaiEmbeddingModel?: string;
  openaiChatModelMultimodal?: boolean;
  openaiTimeoutSeconds?: number;
  openaiPlanModelMultimodal?: boolean;
  openaiPlanToolsEnabled?: boolean;
  openaiPlanFallbackModel?: string;
  openaiPlanFallbackDisableTools?: boolean;
  showDebugInfo?: boolean;
}

export interface RuntimeOpenAIProbeResult {
  available: boolean;
  models: string[];
  error: string;
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

export interface ChatToolCallTrace {
  toolCallId: string;
  toolName: string;
  argumentsJson: string;
  resultSummary: string;
  resultJson: string;
}

export interface RichTextBlock {
  kind: string;
  content: string;
}

export interface StudyChatResponse {
  reply: string;
  citations: Citation[];
  characterEvents: CharacterStateEvent[];
  richBlocks?: RichTextBlock[];
  interactiveQuestion?: InteractiveQuestion;
  personaSlotTrace?: PersonaSlotTraceEntry[];
  memoryTrace?: MemoryTraceHit[];
  toolCalls?: ChatToolCallTrace[];
  sceneProfile?: SceneProfile;
}

export interface InteractiveQuestionOption {
  key: string;
  text: string;
}

export interface InteractiveQuestion {
  questionType: "multiple_choice" | "fill_blank";
  prompt: string;
  difficulty: "easy" | "medium" | "hard";
  topic: string;
  options: InteractiveQuestionOption[];
  callBack?: boolean;
  answerKey?: string;
  acceptedAnswers: string[];
  explanation: string;
  submittedAnswer?: string;
  isCorrect?: boolean;
  feedbackText?: string;
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

export interface DialogueTurnRecord {
  learnerMessage: string;
  assistantReply: string;
  citations: Citation[];
  characterEvents: CharacterStateEvent[];
  richBlocks?: RichTextBlock[];
  interactiveQuestion?: InteractiveQuestion;
  personaSlotTrace?: PersonaSlotTraceEntry[];
  memoryTrace?: MemoryTraceHit[];
  toolCalls?: ChatToolCallTrace[];
  sceneProfile?: SceneProfile;
  createdAt: string;
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
  sceneInstanceId?: string;
  sceneProfile?: SceneProfile;
  sectionId: string;
  sectionTitle?: string;
  themeHint?: string;
  sessionSystemPrompt?: string;
  status: string;
  turns: DialogueTurnRecord[];
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
