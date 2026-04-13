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

export interface SessionFollowUp {
  id: string;
  triggerKind: string;
  status: string;
  delaySeconds: number;
  dueAt: string;
  hiddenMessage: string;
  reason: string;
  createdAt: string;
  completedAt?: string;
  canceledAt?: string;
}

export interface SessionMemoryEntry {
  id: string;
  key: string;
  content: string;
  source: string;
  createdAt: string;
  updatedAt: string;
}

export interface SessionAffinityEvent {
  id: string;
  delta: number;
  reason: string;
  source: string;
  createdAt: string;
}

export interface SessionAffinityState {
  score: number;
  level: string;
  summary: string;
  updatedAt: string;
  events: SessionAffinityEvent[];
}

export interface SessionPlanConfirmation {
  id: string;
  toolName: string;
  actionType: string;
  planId: string;
  title: string;
  summary: string;
  previewLines: string[];
  payload: Record<string, unknown>;
  status: string;
  createdAt: string;
  resolvedAt?: string;
  resolutionNote?: string;
}

export interface LearnerAttachment {
  attachmentId: string;
  name: string;
  mimeType: string;
  kind: string;
  sizeBytes: number;
  imageUrl?: string;
  textExcerpt?: string;
  source?: string;
  pageCount?: number;
  previewable?: boolean;
}

export interface Citation {
  sectionId: string;
  title: string;
  pageStart: number;
  pageEnd: number;
  sourceKind?: string;
  sourceId?: string;
}

export interface PdfRect {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface ProjectedPdfOverlay {
  id: string;
  kind: string;
  pageNumber: number;
  rects: PdfRect[];
  label: string;
  quoteText?: string;
  color?: string;
  createdAt: string;
}

export interface SessionProjectedPdf {
  sourceKind: string;
  sourceId: string;
  title: string;
  pageNumber: number;
  pageCount: number;
  imageUrl?: string;
  overlays: ProjectedPdfOverlay[];
  updatedAt: string;
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
  reuseId: string;
  reuseHint: string;
}

export interface SceneTreeNode {
  id: string;
  title: string;
  scopeLabel: string;
  summary: string;
  atmosphere: string;
  rules: string;
  entrance: string;
  tags: string;
  reuseId: string;
  reuseHint: string;
  objects: SceneObjectSnapshot[];
  children: SceneTreeNode[];
}

export interface LearningPlan {
  id: string;
  documentId: string;
  personaId: string;
  creationMode: "document" | "goal_only";
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
  progressSummary: LearningPlanProgressSummary;
  chapterProgress: LearningPlanChapterProgress[];
  progressEvents: LearningPlanProgressEvent[];
  planningQuestions: PlanningQuestion[];
  createdAt: string;
}

export interface LearningPlanProgressSummary {
  totalScheduleCount: number;
  completedScheduleCount: number;
  inProgressScheduleCount: number;
  pendingScheduleCount: number;
  blockedScheduleCount: number;
  completionPercent: number;
}

export interface LearningPlanProgressEvent {
  id: string;
  actor: string;
  source: string;
  scheduleIds: string[];
  status: string;
  note: string;
  createdAt: string;
}

export interface LearningPlanChapterProgress {
  unitId: string;
  title: string;
  objectiveFragment: string;
  scheduleIds: string[];
  totalScheduleCount: number;
  completedScheduleCount: number;
  inProgressScheduleCount: number;
  pendingScheduleCount: number;
  blockedScheduleCount: number;
  completionPercent: number;
  status: string;
}

export interface PlanningQuestion {
  id: string;
  question: string;
  reason: string;
  assumptions: string[];
  answer: string;
  status: string;
  sourceToolName: string;
  createdAt: string;
  answeredAt: string;
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
  planProvider: "mock" | "litellm";
  openaiApiKey: string;
  openaiApiKeyConfigured: boolean;
  openaiBaseUrl: string;
  openaiPlanApiKey: string;
  openaiPlanApiKeyConfigured: boolean;
  openaiPlanBaseUrl: string;
  openaiPlanModel: string;
  openaiSettingApiKey: string;
  openaiSettingApiKeyConfigured: boolean;
  openaiSettingBaseUrl: string;
  openaiSettingModel: string;
  openaiSettingWebSearchEnabled: boolean;
  openaiChatApiKey: string;
  openaiChatApiKeyConfigured: boolean;
  openaiChatBaseUrl: string;
  openaiChatModel: string;
  openaiChatTemperature: number;
  openaiSettingTemperature: number;
  openaiSettingMaxTokens: number;
  openaiChatMaxTokens: number;
  openaiChatHistoryMessages: number;
  openaiChatToolMaxRounds: number;
  openaiEmbeddingModel: string;
  openaiChatModelMultimodal: boolean;
  openaiTimeoutSeconds: number;
  openaiPlanModelMultimodal: boolean;
  openaiPlanFallbackModel: string;
  openaiPlanFallbackDisableTools: boolean;
  showDebugInfo: boolean;
}

export interface RuntimeSettingsPatch {
  planProvider?: "mock" | "litellm";
  openaiApiKey?: string;
  openaiBaseUrl?: string;
  openaiPlanApiKey?: string;
  openaiPlanBaseUrl?: string;
  openaiPlanModel?: string;
  openaiSettingApiKey?: string;
  openaiSettingBaseUrl?: string;
  openaiSettingModel?: string;
  openaiSettingWebSearchEnabled?: boolean;
  openaiChatApiKey?: string;
  openaiChatBaseUrl?: string;
  openaiChatModel?: string;
  openaiChatTemperature?: number;
  openaiSettingTemperature?: number;
  openaiSettingMaxTokens?: number;
  openaiChatMaxTokens?: number;
  openaiChatHistoryMessages?: number;
  openaiChatToolMaxRounds?: number;
  openaiEmbeddingModel?: string;
  openaiChatModelMultimodal?: boolean;
  openaiTimeoutSeconds?: number;
  openaiPlanModelMultimodal?: boolean;
  openaiPlanFallbackModel?: string;
  openaiPlanFallbackDisableTools?: boolean;
  showDebugInfo?: boolean;
}

export type RuntimeCapabilityStatus = "supported" | "unsupported" | "unknown";

export type RuntimeCapabilitySource = "metadata" | "model_name" | "unavailable";

export interface RuntimeCapabilitySignal {
  status: RuntimeCapabilityStatus;
  source: RuntimeCapabilitySource;
  note: string;
}

export interface RuntimeModelCapability {
  inputModalities: string[];
  outputModalities: string[];
  toolTypes: string[];
  multimodal: RuntimeCapabilitySignal;
  webSearch: RuntimeCapabilitySignal;
}

export interface RuntimeOpenAIProbeResult {
  available: boolean;
  models: string[];
  capabilities: Record<string, RuntimeModelCapability>;
  error: string;
}

export interface PlanToolCallTrace {
  toolCallId: string;
  toolName: string;
  argumentsJson: string;
  resultSummary: string;
  resultJson: string;
}

export interface ModelRecovery {
  recoveryId: string;
  category: string;
  reason: string;
  strategy: string;
  attempts: number;
  note: string;
  createdAt: string;
}

export interface PlanGenerationRoundTrace {
  roundIndex: number;
  finishReason: string;
  assistantContent: string;
  thinking: string;
  elapsedMs: number;
  timeoutSeconds: number;
  toolCalls: PlanToolCallTrace[];
  recoveries: ModelRecovery[];
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
  messageKind?: string;
  followUpId?: string;
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
  modelRecoveries?: ModelRecovery[];
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
  learnerMessageKind?: string;
  learnerAttachments?: LearnerAttachment[];
  assistantReply: string;
  citations: Citation[];
  characterEvents: CharacterStateEvent[];
  richBlocks?: RichTextBlock[];
  interactiveQuestion?: InteractiveQuestion;
  personaSlotTrace?: PersonaSlotTraceEntry[];
  memoryTrace?: MemoryTraceHit[];
  toolCalls?: ChatToolCallTrace[];
  sceneProfile?: SceneProfile;
  modelRecoveries?: ModelRecovery[];
  createdAt: string;
}

export interface DocumentRecord {
  id: string;
  title: string;
  originalFilename: string;
  storedPath: string;
  status: string;
  ocrStatus: OcrStatus;
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
  planId?: string | null;
  sceneInstanceId?: string;
  sceneProfile?: SceneProfile;
  sectionId: string;
  sectionTitle?: string;
  themeHint?: string;
  sessionSystemPrompt?: string;
  status: string;
  turns: DialogueTurnRecord[];
  preparedSectionIds?: string[];
  pendingFollowUps?: SessionFollowUp[];
  sessionMemory?: SessionMemoryEntry[];
  affinityState?: SessionAffinityState;
  planConfirmations?: SessionPlanConfirmation[];
  projectedPdf?: SessionProjectedPdf | null;
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

export type OcrStatus =
  | "pending"
  | "completed"
  | "fallback_used"
  | "forced"
  | "required"
  | "unavailable"
  | "failed";

export interface DocumentDebugRecord {
  documentId: string;
  parserName: string;
  processedAt: string;
  pageCount: number;
  totalCharacters: number;
  extractionMethod: string;
  ocrStatus: OcrStatus;
  ocrApplied: boolean;
  ocrLanguage: string | null;
  ocrEngine: string | null;
  ocrModelId: string | null;
  ocrAppliedPageCount: number;
  ocrWarnings: string[];
  pages: DocumentPageRecord[];
  sections: DocumentSection[];
  studyUnits: StudyUnit[];
  chunks: DocumentChunkRecord[];
  warnings: ParseWarning[];
  dominantLanguageHint: string;
}


export interface TokenUsageDailyBucket {
  date: string;
  feature: string;
  model: string;
  promptTokens: number;
  completionTokens: number;
  totalTokens: number;
}

export interface TokenUsageCallRecord {
  id: string;
  createdAt: string;
  feature: string;
  model: string;
  promptTokens: number;
  completionTokens: number;
  totalTokens: number;
}

export interface TokenUsageStats {
  buckets: TokenUsageDailyBucket[];
  records: TokenUsageCallRecord[];
  totalPromptTokens: number;
  totalCompletionTokens: number;
  totalTokens: number;
}
