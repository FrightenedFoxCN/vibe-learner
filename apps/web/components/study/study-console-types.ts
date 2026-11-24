import type {
  Citation,
  PersonaProfile,
  SceneProfile,
  SessionAffinityState,
  SessionFollowUp,
  SessionPlanConfirmation,
  StudyChatResponse,
  StudyNoteReference,
  StudySessionRecord,
} from "@vibe-learner/shared";
import type { ReactNode } from "react";
import type { StudyChatOperationStatus } from "../../lib/study-chat-operation-decode";
import type { StudyConsolePageCache } from "../../lib/learning-workspace-page-cache";

export interface StudyConsoleProps {
  workspaceTools?: ReactNode;
  isPending: boolean;
  selectedPlanId: string;
  planOptions: Array<{ id: string; title: string }>;
  onSelectPlan: (planId: string) => void;
  onCreateSession?: () => void;
  showCreateSession?: boolean;
  onAsk: (
    message: string,
    attachments: File[],
    outputLanguage?: string,
    onCommitted?: () => void,
  ) => Promise<boolean> | boolean;
  outputLanguage?: string;
  outputLanguageScope?: string;
  onSubmitQuestionAttempt: (input: {
    turnId: string;
    submittedAnswer: string;
  }) => boolean | Promise<boolean>;
  onContinueAfterQuestion?: (turnId: string) => boolean | Promise<boolean>;
  onChangeSchedule: (scheduleId: string) => void;
  onOpenCitation?: (citation: Citation) => void;
  onOpenNoteReference?: (reference: StudyNoteReference) => void;
  onJumpToScheduleStart?: () => void;
  canJumpToScheduleStart?: boolean;
  onCompleteCurrentSchedule?: () => void | Promise<void>;
  canCompleteCurrentSchedule?: boolean;
  chatErrorMessage?: string;
  chatOperationStatus?: StudyChatOperationStatus | "unresolved";
  canQueryLastAsk?: boolean;
  canResendLastAsk?: boolean;
  canRefreshSessionAfterAsk?: boolean;
  onQueryLastAsk?: () => unknown | Promise<unknown>;
  onRetryLastAsk?: () => unknown | Promise<unknown>;
  onRefreshSessionAfterAsk?: () => unknown | Promise<unknown>;
  selectedScheduleId: string;
  scheduleOptions: Array<{ id: string; title: string }>;
  turns: StudySessionRecord["turns"];
  session: StudyChatResponse | null;
  persona: PersonaProfile;
  sceneProfile?: SceneProfile | null;
  pendingFollowUps?: SessionFollowUp[];
  isDialogueInterrupted?: boolean;
  onInterruptDialogue?: () => void | Promise<void>;
  affinityState?: SessionAffinityState;
  planConfirmations?: SessionPlanConfirmation[];
  onResolvePlanConfirmation?: (input: {
    confirmationId: string;
    decision: "approve" | "reject";
    note?: string;
  }) => void | Promise<unknown>;
  chatImageUploadEnabled?: boolean;
  pendingComposerInsert?: {
    id: string;
    text: string;
  } | null;
  onConsumeComposerInsert?: () => void;
  disabled?: boolean;
  cachedState?: StudyConsolePageCache;
  onCachedStateChange?: (state: StudyConsolePageCache) => void;
}
