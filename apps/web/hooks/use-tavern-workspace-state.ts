"use client";

import type {
  PersonaProfile,
  TavernMessage,
  TavernRoomDetail,
  TavernRoomSummary,
  TavernRun,
  TavernRunRecoveryChain,
} from "@vibe-learner/shared";
import { useEffect, useMemo, useRef, useState } from "react";

import { type SceneLibraryItemPayload } from "../lib/api";
import {
  authoritativeFacilitatedRecovery,
  hasActiveTavernRun,
  latestTavernMessage,
  projectParticipantStates,
  tavernRoomSummaryButtons,
} from "../lib/tavern-workspace-state";

import type { BusyAction, MutationOperation } from "../lib/tavern-workspace-ports";

export function useTavernWorkspaceState() {
  const [rooms, setRooms] = useState<TavernRoomSummary[]>([]);
  const [nextRoomCursor, setNextRoomCursor] = useState<string | null>(null);
  const [loadingMoreRooms, setLoadingMoreRooms] = useState(false);
  const [roomPageError, setRoomPageError] = useState("");
  const [roomHistoryTruncated, setRoomHistoryTruncated] = useState(false);
  const [personas, setPersonas] = useState<PersonaProfile[]>([]);
  const [scenes, setScenes] = useState<SceneLibraryItemPayload[]>([]);
  const [detail, setDetail] = useState<TavernRoomDetail | null>(null);
  const [messages, setMessages] = useState<TavernMessage[]>([]);
  const [runs, setRuns] = useState<TavernRun[]>([]);
  const [recoveryChains, setRecoveryChains] = useState<TavernRunRecoveryChain[]>([]);
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
  const activeRoomIdRef = useRef("");
  const requestedRoomIdRef = useRef("");
  const olderLoadRoomRef = useRef<string | null>(null);
  const mutationOperationRef = useRef<MutationOperation | null>(null);
  const mutationOperationVersionRef = useRef(0);
  const resumeRunRef = useRef("");
  const foregroundRunRef = useRef("");
  const foregroundOperationIdRef = useRef<number | null>(null);
  const runPollVersionRef = useRef(0);
  const resumeAttemptsRef = useRef(new Map<string, number>());
  const detailRef = useRef<TavernRoomDetail | null>(null);
  const runsRef = useRef<TavernRun[]>([]);
  const messagesRef = useRef<TavernMessage[]>([]);
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
  const activeRoom = detail?.room ?? null;
  const roomIsActive = activeRoom?.status === "active";
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
    detailRef.current = detail;
  }, [detail]);

  useEffect(() => {
    runsRef.current = runs;
  }, [runs]);

  useEffect(() => {
    messagesRef.current = messages;
  }, [messages]);

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
    setDetail,
    messages,
    setMessages,
    runs,
    setRuns,
    recoveryChains,
    setRecoveryChains,
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
    activeRoomIdRef,
    requestedRoomIdRef,
    olderLoadRoomRef,
    mutationOperationRef,
    mutationOperationVersionRef,
    resumeRunRef,
    foregroundRunRef,
    foregroundOperationIdRef,
    runPollVersionRef,
    resumeAttemptsRef,
    detailRef,
    runsRef,
    messagesRef,
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
