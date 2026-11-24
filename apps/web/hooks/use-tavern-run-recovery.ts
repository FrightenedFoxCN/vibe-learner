"use client";

import { useCallback, useEffect, useState } from "react";

import { createDiagnosticId, diagnosticContext } from "../lib/diagnostics";
import { RUN_STATUS_LABELS } from "../lib/tavern-copy";

import {
  createTavernPendingRecoveryBudget,
  tavernAutomaticRecoveryDelay,
  type TavernPendingRecoveryProgress,
} from "../lib/tavern-pending-recovery";
import type { TavernRecoveryPorts } from "../lib/tavern-workspace-ports";
import type { TavernRoomQueries } from "./use-tavern-room-queries";
import type { TavernWorkspaceState } from "./use-tavern-workspace-state";

export function useTavernRunRecovery(
  state: TavernWorkspaceState,
  ports: TavernRecoveryPorts,
  queries: TavernRoomQueries,
) {
  const {
    mountedRef,
    roomLoadVersion,
    runs,
    publishRoomSnapshot,
    busyAction,
    loadingOlder,
    setNotice,
    setRawError,
    readRoomSnapshot,
    requestedRoomIdRef,
    mutationOperationRef,
    mutationOperationVersionRef,
    olderLoadRoomRef,
    foregroundRunRef,
    foregroundOperationIdRef,
    runPollVersionRef,
    activeRoom,
  } = state;
  const { listTavernRuns, resumeTavernRun } = ports.api;
  const { clock } = ports;
  const { refreshRoom, syncTurnResult } = queries;
  const [budget] = useState(createTavernPendingRecoveryBudget);
  const [progressByRun, setProgressByRun] = useState<
    ReadonlyMap<string, TavernPendingRecoveryProgress>
  >(() => new Map());
  const resumePendingRun = useCallback(
    async (roomId: string, runId: string, mode: "automatic" | "manual") => {
      const snapshot = readRoomSnapshot();
      if (
        !mountedRef.current ||
        mutationOperationRef.current !== null ||
        olderLoadRoomRef.current !== null ||
        snapshot?.detail.room.id !== roomId ||
        snapshot.detail.room.status !== "active" ||
        requestedRoomIdRef.current !== roomId ||
        runId === foregroundRunRef.current ||
        !snapshot.runs.some((run) => run.id === runId && run.status === "pending")
      )
        return;

      const progress = budget.begin(runId, mode);
      if (!progress) return;
      setProgressByRun((current) => new Map(current).set(runId, progress));
      const loadVersion = roomLoadVersion.current;
      const mutationVersion = mutationOperationVersionRef.current;
      const isCurrent = () =>
        mountedRef.current &&
        loadVersion === roomLoadVersion.current &&
        mutationVersion === mutationOperationVersionRef.current &&
        mutationOperationRef.current === null &&
        readRoomSnapshot()?.detail.room.id === roomId &&
        requestedRoomIdRef.current === roomId;
      const diagnostic = diagnosticContext(createDiagnosticId());
      try {
        const result = await resumeTavernRun(roomId, runId, diagnostic);
        if (!isCurrent()) return;
        if (result.run.id !== runId || result.run.roomId !== roomId) {
          throw new Error("Tavern resume response does not match the requested run");
        }
        if (syncTurnResult(result)) {
          setNotice(
            result.run.status === "completed"
              ? "中断的互动已恢复"
              : RUN_STATUS_LABELS[result.run.status],
          );
        }
      } catch (error) {
        if (isCurrent()) setRawError(String(error));
      } finally {
        try {
          // A failed transport can still have committed server-side. Read back
          // before deciding whether this same run remains eligible for recovery.
          if (isCurrent()) await refreshRoom(diagnostic, { recoveryRead: true });
        } finally {
          const finished = budget.finish(runId);
          if (mountedRef.current) {
            setProgressByRun((current) => new Map(current).set(runId, finished));
          }
        }
      }
    },
    [
      budget,
      refreshRoom,
      syncTurnResult,
      resumeTavernRun,
      mountedRef,
      mutationOperationRef,
      olderLoadRoomRef,
      foregroundRunRef,
      readRoomSnapshot,
      requestedRoomIdRef,
      roomLoadVersion,
      mutationOperationVersionRef,
      setNotice,
      setRawError,
    ],
  );

  const pendingRunId = runs.find((run) => run.status === "pending")?.id;
  const roomId = activeRoom?.status === "active" ? activeRoom.id : undefined;
  const recoveryProgress = pendingRunId ? progressByRun.get(pendingRunId) : undefined;
  const automaticDelay = tavernAutomaticRecoveryDelay(recoveryProgress);
  useEffect(() => {
    if (
      !roomId ||
      !pendingRunId ||
      busyAction !== null ||
      loadingOlder ||
      automaticDelay === null
    )
      return;
    const timer = clock.setTimeout(
      () => void resumePendingRun(roomId, pendingRunId, "automatic"),
      automaticDelay,
    );
    return () => clock.clearTimeout(timer);
  }, [
    roomId,
    pendingRunId,
    busyAction,
    loadingOlder,
    resumePendingRun,
    clock,
    automaticDelay,
    recoveryProgress,
  ]);

  const retryPendingRun = useCallback(() => {
    if (!roomId || !pendingRunId || busyAction !== null || loadingOlder) return;
    return resumePendingRun(roomId, pendingRunId, "manual");
  }, [roomId, pendingRunId, busyAction, loadingOlder, resumePendingRun]);

  useEffect(() => {
    if (!activeRoom || (busyAction !== "turn" && busyAction !== "retry")) return;
    const roomId = activeRoom.id;
    const operationId = foregroundOperationIdRef.current;
    if (operationId === null) return;
    const diagnostic = mutationOperationRef.current?.diagnostic;
    let disposed = false;
    let inFlight = false;
    const discoverPendingRun = async () => {
      if (
        disposed ||
        inFlight ||
        foregroundOperationIdRef.current !== operationId ||
        mutationOperationRef.current?.id !== operationId
      )
        return;
      inFlight = true;
      const pollVersion = ++runPollVersionRef.current;
      try {
        const nextRuns = await listTavernRuns(roomId, 50, diagnostic);
        if (
          disposed ||
          pollVersion !== runPollVersionRef.current ||
          foregroundOperationIdRef.current !== operationId ||
          mutationOperationRef.current?.id !== operationId ||
          readRoomSnapshot()?.detail.room.id !== roomId ||
          requestedRoomIdRef.current !== roomId
        )
          return;
        const published = publishRoomSnapshot({ kind: "poll", roomId, runs: nextRuns });
        const pending = published?.runs.find((run) => run.status === "pending");
        if (pending) foregroundRunRef.current = pending.id;
      } catch (error) {
        if (
          !disposed &&
          foregroundOperationIdRef.current === operationId &&
          mutationOperationRef.current?.id === operationId &&
          readRoomSnapshot()?.detail.room.id === roomId &&
          requestedRoomIdRef.current === roomId
        )
          setRawError(String(error));
      } finally {
        inFlight = false;
      }
    };
    void discoverPendingRun();
    const timer = clock.setInterval(() => void discoverPendingRun(), 900);
    return () => {
      disposed = true;
      runPollVersionRef.current += 1;
      clock.clearInterval(timer);
    };
  }, [
    activeRoom,
    busyAction,
    listTavernRuns,
    clock,
    foregroundOperationIdRef,
    mutationOperationRef,
    runPollVersionRef,
    readRoomSnapshot,
    requestedRoomIdRef,
    foregroundRunRef,
    publishRoomSnapshot,
    setRawError,
  ]);

  return { recoveryProgress: roomId ? recoveryProgress : undefined, retryPendingRun };
}
