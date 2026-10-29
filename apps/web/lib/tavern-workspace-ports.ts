import type { DiagnosticContext } from "./diagnostics";
import {
  createTavernRoom,
  cancelTavernRun,
  getTavernRoom,
  getTavernRunRecovery,
  listTavernRooms,
  listTavernRuns,
  retryTavernRun,
  resumeTavernRun,
  runTavernTurn,
  updateTavernRoom,
} from "./data/tavern";
import { listPersonas } from "./data/personas";
import { listSceneLibrary } from "./data/scenes";
import {
  readActiveTavernRoomId,
  readTavernCreationDraft,
  readTavernRoomDraft,
  rememberActiveTavernRoomId,
  writeTavernCreationDraft,
  writeTavernRoomDraft,
  makeTavernRequestKey,
} from "./tavern-workspace-state";

const api = {
  createTavernRoom,
  cancelTavernRun,
  getTavernRoom,
  getTavernRunRecovery,
  listPersonas,
  listSceneLibrary,
  listTavernRooms,
  listTavernRuns,
  retryTavernRun,
  resumeTavernRun,
  runTavernTurn,
  updateTavernRoom,
};
const storage = {
  readActiveTavernRoomId,
  readTavernCreationDraft,
  readTavernRoomDraft,
  rememberActiveTavernRoomId,
  writeTavernCreationDraft,
  writeTavernRoomDraft,
};

export type TavernApiPort = typeof api;
export type TavernStoragePort = typeof storage;
export interface TavernClockPort {
  setTimeout(callback: () => void, delay: number): number;
  clearTimeout(handle: number): void;
  setInterval(callback: () => void, delay: number): number;
  clearInterval(handle: number): void;
}
export interface TavernWorkspacePorts {
  api: TavernApiPort;
  storage: TavernStoragePort;
  clock: TavernClockPort;
  makeRequestKey: typeof makeTavernRequestKey;
}
export type TavernRoomQueryPorts = Pick<
  TavernWorkspacePorts,
  "storage" | "makeRequestKey"
> & {
  api: Pick<
    TavernApiPort,
    | "getTavernRoom"
    | "getTavernRunRecovery"
    | "listTavernRooms"
    | "listTavernRuns"
    | "listPersonas"
    | "listSceneLibrary"
  >;
};
export type TavernRecoveryPorts = Pick<TavernWorkspacePorts, "clock"> & {
  api: Pick<TavernApiPort, "listTavernRuns" | "resumeTavernRun">;
};
export type TavernMutationPorts = Pick<
  TavernWorkspacePorts,
  "storage" | "makeRequestKey"
> & {
  api: Pick<
    TavernApiPort,
    | "createTavernRoom"
    | "cancelTavernRun"
    | "retryTavernRun"
    | "runTavernTurn"
    | "updateTavernRoom"
  >;
};

export type BusyAction =
  | "bootstrap"
  | "room"
  | "create"
  | "archive"
  | "turn"
  | "retry"
  | "cancel"
  | null;
export type MutationAction = Exclude<BusyAction, "bootstrap" | "room" | null>;
export interface MutationOperation {
  diagnostic: DiagnosticContext;
  id: number;
  action: MutationAction;
  roomId: string;
}

export const defaultTavernWorkspacePorts: TavernWorkspacePorts = {
  api,
  storage,
  makeRequestKey: makeTavernRequestKey,
  clock: {
    setTimeout: (callback, delay) => window.setTimeout(callback, delay),
    clearTimeout: (handle) => window.clearTimeout(handle),
    setInterval: (callback, delay) => window.setInterval(callback, delay),
    clearInterval: (handle) => window.clearInterval(handle),
  },
};
