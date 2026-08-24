import type { PersonaProfile } from "./persona";
import type { SceneProfile } from "./learning";
import type { HarnessTrace } from "./harness";

export type TavernRoomStatus = "active" | "archived";
export type TavernAuthorKind = "user" | "persona" | "director" | "system";
export type TavernInteractionMode = "direct" | "facilitated";
export type TavernRunStatus = "pending" | "completed" | "partial" | "failed" | "canceled";
export type TavernRunTriggerKind = "user_message" | "continue" | "retry";
export type TavernSpeakerStepStatus =
  | "pending"
  | "generating"
  | "completed"
  | "failed"
  | "blocked"
  | "canceled";
export type TavernRecoveryAction =
  | "none"
  | "replay_same_request"
  | "reload_room"
  | "wait_and_resume"
  | "retry_leaf";
export type TavernRunChainStatus =
  | "active"
  | "recoverable"
  | "recovered"
  | "completed"
  | "canceled";

export interface TavernHarnessPolicy {
  version: "tavern-harness-v1" | string;
  maxCharacterMessages: number;
  maxReplyCharacters: number;
  contextMessageLimit: number;
  preventSpeakerImpersonation: boolean;
}

export interface TavernRoom {
  id: string;
  creationKey?: string;
  creationInputDigest?: string;
  title: string;
  sceneProfile?: SceneProfile;
  harnessPolicy: TavernHarnessPolicy;
  status: TavernRoomStatus;
  revision: number;
  lastSequence: number;
  createdAt: string;
  updatedAt: string;
}

export interface TavernRoomState {
  id: string;
  status: TavernRoomStatus;
  revision: number;
  lastSequence: number;
  updatedAt: string;
}

export interface TavernParticipant {
  roomId: string;
  personaId: string;
  displayOrder: number;
  displayName: string;
  personaSnapshot: PersonaProfile;
  promptHash: string;
  joinedAt: string;
}

export interface TavernMessage {
  id: string;
  roomId: string;
  sequence: number;
  runId?: string;
  authorKind: TavernAuthorKind;
  personaId?: string;
  personaName?: string;
  content: string;
  emotion: string;
  action?: string;
  speechStyle?: string;
  addressedParticipantIds: string[];
  replyToMessageId?: string;
  clientRequestId?: string;
  createdAt: string;
  harnessTrace?: HarnessTrace;
}

/** Complete app-owned digest projection; store content only in protected artifacts. */
export interface TavernPersonaMessageCommittedProjectionV1 {
  schemaName: "TavernPersonaMessageCommittedProjection";
  schemaVersion: "tavern-persona-message-committed-projection-v1";
  operationId: string;
  effectBatchId: string;
  roomId: string;
  messageId: string;
  sequence: number;
  runId: string;
  stepIndex: number;
  replyToMessageId: string;
  authorKind: "persona";
  personaId: string;
  personaName: string;
  content: string;
  emotion: string;
  action: string;
  speechStyle: string;
  addressedParticipantIds: string[];
  clientRequestId: string;
  createdAt: string;
}

export interface TavernRun {
  id: string;
  roomId: string;
  idempotencyKey: string;
  requestDigest?: string;
  contextDigest?: string;
  mode: TavernInteractionMode;
  triggerKind: TavernRunTriggerKind;
  parentRunId?: string;
  rootRunId?: string;
  inputMessageId: string | null;
  anchorMessageId?: string;
  scheduledParticipantIds: string[];
  speakerSteps: TavernSpeakerStep[];
  guidance: string;
  status: TavernRunStatus;
  expectedRoomRevision: number;
  generatedMessageIds: string[];
  harnessTrace: HarnessTrace[];
  errorCode?: string;
  terminalSequence: number;
  createdAt: string;
  completedAt?: string;
}

export interface TavernRunRecoveryChain {
  rootRunId: string;
  runIds: string[];
  rootStatus: TavernRunStatus;
  leafRun: TavernRun;
  chainStatus: TavernRunChainStatus;
  recoveryAction: TavernRecoveryAction;
  completedParticipantIds: string[];
  unfinishedParticipantIds: string[];
}

export interface TavernErrorDetail {
  code: string;
  runId?: string;
  childRunId?: string;
  currentRevision: number | null;
  recoveryAction: TavernRecoveryAction;
}

export interface TavernSpeakerStep {
  runId: string;
  stepIndex: number;
  personaId: string;
  participantPromptHash: string;
  status: TavernSpeakerStepStatus;
  messageId?: string;
  replyToMessageId?: string;
  errorCode?: string;
  harnessTrace?: HarnessTrace;
  claimCount: number;
  startedAt?: string;
  completedAt?: string;
}

export interface TavernRoomDetail {
  room: TavernRoom;
  participants: TavernParticipant[];
  messages: TavernMessage[];
  messageCount: number;
  nextAfterSequence: number | null;
  nextBeforeSequence: number | null;
}

export interface TavernRoomSummary {
  id: string;
  title: string;
  participantPersonaIds: string[];
  participantNames: string[];
  messageCount: number;
  revision: number;
  status: TavernRoomStatus;
  createdAt: string;
  updatedAt: string;
}

export interface CreateTavernRoomInput {
  title: string;
  personaIds: string[];
  sceneProfile?: SceneProfile;
  openingPrompt?: string;
  harnessPolicy?: TavernHarnessPolicy;
  idempotencyKey: string;
}

export interface UpdateTavernRoomInput {
  title?: string;
  personaIds?: string[];
  sceneProfile?: SceneProfile | null;
  status?: TavernRoomStatus;
  expectedRoomRevision: number;
}

export type TavernTurnTrigger =
  | { kind: "user_message"; content: string }
  | { kind: "continue"; anchorMessageId: string };

export interface TavernTurnInput {
  input: TavernTurnTrigger;
  mode: TavernInteractionMode;
  targetPersonaIds: string[];
  guidance?: string;
  idempotencyKey: string;
  expectedRoomRevision: number;
}

export interface RetryTavernRunInput {
  idempotencyKey: string;
  expectedRoomRevision: number;
}

export interface TavernTurnResult {
  run: TavernRun;
  inputMessage: TavernMessage | null;
  generatedMessages: TavernMessage[];
  roomState: TavernRoomState;
}

export interface TavernRunListResult {
  items: TavernRun[];
}

export interface TavernRunRecoveryResult {
  items: TavernRunRecoveryChain[];
}
