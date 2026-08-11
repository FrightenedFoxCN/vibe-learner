import type { PersonaProfile } from "./persona";
import type { SceneProfile } from "./learning";
import type { HarnessTrace } from "./harness";

export type TavernRoomStatus = "active" | "archived";
export type TavernAuthorKind = "user" | "persona" | "director" | "system";
export type TavernInteractionMode = "direct" | "facilitated";
export type TavernRunStatus = "pending" | "completed" | "failed" | "canceled";

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
  clientRequestId?: string;
  createdAt: string;
  harnessTrace?: HarnessTrace;
}

export interface TavernRun {
  id: string;
  roomId: string;
  idempotencyKey: string;
  requestDigest?: string;
  mode: TavernInteractionMode;
  inputMessageId: string;
  requestedParticipantIds: string[];
  maxCharacterMessages: number;
  guidance: string;
  status: TavernRunStatus;
  expectedRoomRevision: number;
  generatedMessageIds: string[];
  harnessTrace: HarnessTrace[];
  errorCode?: string;
  createdAt: string;
  completedAt?: string;
}

export interface TavernRoomDetail {
  room: TavernRoom;
  participants: TavernParticipant[];
  messages: TavernMessage[];
  messageCount: number;
  nextAfterSequence?: number;
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

export interface TavernTurnInput {
  message: string;
  mode: TavernInteractionMode;
  targetPersonaIds: string[];
  guidance?: string;
  maxCharacterMessages: number;
  idempotencyKey: string;
  expectedRoomRevision: number;
}

export interface TavernTurnResult {
  run: TavernRun;
  generatedMessages: TavernMessage[];
  room: TavernRoomDetail;
}

export interface TavernRunListResult {
  items: TavernRun[];
}
