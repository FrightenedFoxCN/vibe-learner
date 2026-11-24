"use client";

import type { PersonaProfile, TavernRoomSummary } from "@vibe-learner/shared";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { type SceneLibraryItemPayload } from "../lib/data/scenes";
import {
  authoritativeFacilitatedRecovery,
  hasActiveTavernRun,
  latestTavernMessage,
  projectParticipantStates,
  tavernRoomSummaryButtons,
} from "../lib/tavern-workspace-state";

import { tavernReadNotice } from "../lib/tavern-room-read";
import {
  reduceTavernRoomSnapshot,
  type TavernRoomSnapshot,
  type TavernRoomSnapshotAction,
} from "../lib/tavern-room-snapshot";

import type { BusyAction, MutationOperation } from "../lib/tavern-workspace-ports";

const EMPTY_MESSAGES: TavernRoomSnapshot["detail"]["messages"] = [];
const EMPTY_RUNS: TavernRoomSnapshot["runs"] = [];
const EMPTY_RECOVERY: TavernRoomSnapshot["recoveryChains"] = [];

export function useTavernWorkspaceState() {
  const [rooms, setRooms] = useState<TavernRoomSummary[]>([]);
  const [nextRoomCursor, setNextRoomCursor] = useState<string | null>(null);
  const [loadingMoreRooms, setLoadingMoreRooms] = useState(false);
  const [roomPageError, setRoomPageError] = useState("");
  const [roomHistoryTruncated, setRoomHistoryTruncated] = useState(false);
  const [personas, setPersonas] = useState<PersonaProfile[]>([]);
  const [scenes, setScenes] = useState<SceneLibraryItemPayload[]>([]);
  const [snapshot, setSnapshot] = useState<TavernRoomSnapshot | null>(null);
  const snapshotRef = useRef<TavernRoomSnapshot | null>(null);
  const [targetPersonaIds, setTargetPersonaIds] = useState<string[]>([]);
  const [generatingPersonaIds, setGeneratingPersonaIds] = useState<string[]>([]);
  const [showSetup, setShowSetup] = useState(false);
  const [busyAction, setBusyAction] = useState<BusyAction>("bootstrap");
  const [loadingOlder, setLoadingOlder] = useState(false);
  const [notice, setNotice] = useState("正在载入酒馆记录…");
  const [visibleError, setVisibleError] = useState("");
  const [rawError, setRawError] = useState("");
  const roomLoadVersion = useRef(0);
  const roomRefreshVersion = useRef(0);
  const recoveryVersionRef = useRef(0);
  const requestedRoomIdRef = useRef("");
  const olderLoadRoomRef = useRef<string | null>(null);
  const mutationOperationRef = useRef<MutationOperation | null>(null);
  const mutationOperationVersionRef = useRef(0);
  const resumeRunRef = useRef("");
  const foregroundRunRef = useRef("");
  const foregroundOperationIdRef = useRef<number | null>(null);
  const runPollVersionRef = useRef(0);
  const resumeAttemptsRef = useRef(new Map<string, number>());
  const roomsRef = useRef<TavernRoomSummary[]>([]);
  const roomPageVersionRef = useRef(0);
  const loadingRoomCursorRef = useRef<string | null>(null);

  const mountedRef = useRef(true);
  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);
  const readRoomSnapshot = useCallback(() => snapshotRef.current, []);
  const publishRoomSnapshot = useCallback((action: TavernRoomSnapshotAction) => {
    if (!mountedRef.current) return null;
    const current = snapshotRef.current;
    const next = reduceTavernRoomSnapshot(current, action);
    if (!next || next === current) return null;
    // Async guards and React render state advance from the same projection.
    snapshotRef.current = next;
    setSnapshot(next);
    return next;
  }, []);
  const detail = snapshot?.detail ?? null;
  const messages = detail?.messages ?? EMPTY_MESSAGES;
  const runs = snapshot?.runs ?? EMPTY_RUNS;
  const recoveryChains = snapshot?.recoveryChains ?? EMPTY_RECOVERY;
  const activeRoom = detail?.room ?? null;
  const roomIsActive = activeRoom?.status === "active";
  const roomReadNotice = snapshot
    ? tavernReadNotice(snapshot.runsKnown, snapshot.recoveryKnown)
    : "";
  const roomRunsUnknown = snapshot !== null && !snapshot.runsKnown;
  const roomBusy = busyAction === "room" || busyAction === "bootstrap";
  const mutationBusy = busyAction !== null && !roomBusy;
  const runPending = hasActiveTavernRun(runs);
  const activeReplyPersonaIds = useMemo(
    () =>
      runs.find((run) => run.status === "pending")?.scheduledParticipantIds ??
      generatingPersonaIds,
    [runs, generatingPersonaIds],
  );
  const latestMessage = latestTavernMessage(messages);
  const retryableRuns = useMemo(
    () =>
      recoveryChains
        .filter((chain) => chain.recoveryAction === "retry_leaf")
        .map((chain) => chain.leafRun),
    [recoveryChains],
  );
  const facilitatedRecovery = useMemo(
    () => authoritativeFacilitatedRecovery(recoveryChains),
    [recoveryChains],
  );
  const participantStates = useMemo(
    () =>
      projectParticipantStates(detail?.participants ?? [], runs, generatingPersonaIds),
    [detail?.participants, generatingPersonaIds, runs],
  );
  const roomButtons = useMemo(
    () => tavernRoomSummaryButtons(rooms, detail),
    [detail, rooms],
  );

  useEffect(() => {
    roomsRef.current = rooms;
  }, [rooms]);

  useEffect(() => {
    const participantIds = new Set(
      (detail?.participants ?? []).map((item) => item.personaId),
    );
    setTargetPersonaIds((current) => {
      const valid = current.filter((id) => participantIds.has(id)).slice(0, 4);
      if (valid.length) return valid;
      return detail?.participants[0] ? [detail.participants[0].personaId] : [];
    });
  }, [detail?.room.id, detail?.participants]);

  return {
    rooms,
    setRooms,
    nextRoomCursor,
    setNextRoomCursor,
    loadingMoreRooms,
    setLoadingMoreRooms,
    roomPageError,
    setRoomPageError,
    roomHistoryTruncated,
    setRoomHistoryTruncated,
    personas,
    setPersonas,
    scenes,
    setScenes,
    detail,
    messages,
    runs,
    recoveryChains,
    readRoomSnapshot,
    publishRoomSnapshot,
    roomReadNotice,
    roomRunsUnknown,
    targetPersonaIds,
    setTargetPersonaIds,
    generatingPersonaIds,
    setGeneratingPersonaIds,
    showSetup,
    setShowSetup,
    busyAction,
    setBusyAction,
    loadingOlder,
    setLoadingOlder,
    notice,
    setNotice,
    visibleError,
    setVisibleError,
    rawError,
    setRawError,
    roomLoadVersion,
    roomRefreshVersion,
    recoveryVersionRef,
    requestedRoomIdRef,
    olderLoadRoomRef,
    mutationOperationRef,
    mutationOperationVersionRef,
    resumeRunRef,
    foregroundRunRef,
    foregroundOperationIdRef,
    runPollVersionRef,
    resumeAttemptsRef,
    roomsRef,
    roomPageVersionRef,
    loadingRoomCursorRef,
    mountedRef,
    activeRoom,
    roomIsActive,
    roomBusy,
    mutationBusy,
    runPending,
    latestMessage,
    retryableRuns,
    facilitatedRecovery,
    participantStates,
    activeReplyPersonaIds,
    roomButtons,
  };
}
export type TavernWorkspaceState = ReturnType<typeof useTavernWorkspaceState>;
