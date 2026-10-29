"use client";

import type { TavernRun } from "@vibe-learner/shared";
import { useCallback, useEffect } from "react";

import { decodeTavernHttpError } from "../lib/api";
import { createDiagnosticId, diagnosticContext } from "../lib/diagnostics";
import { RUN_STATUS_LABELS } from "../lib/tavern-copy";
import { reconcileTavernRuns } from "../lib/tavern-workspace-state";

import { recordError } from "../lib/tavern-client-errors";
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
    setRuns,
    busyAction,
    setNotice,
    setVisibleError,
    setRawError,
    activeRoomIdRef,
    requestedRoomIdRef,
    mutationOperationRef,
    mutationOperationVersionRef,
    resumeRunRef,
    foregroundRunRef,
    foregroundOperationIdRef,
    runPollVersionRef,
    resumeAttemptsRef,
    runsRef,
    activeRoom,
  } = state;
  const { listTavernRuns, resumeTavernRun } = ports.api;
  const { clock } = ports;
  const { refreshRoom, syncTurnResult } = queries;
  const resumePendingRun = useCallback(
    async (run: TavernRun) => {
      const roomId = run.roomId;
      if (
        !mountedRef.current ||
        mutationOperationRef.current !== null ||
        !roomId ||
        resumeRunRef.current === run.id ||
        activeRoomIdRef.current !== roomId ||
        requestedRoomIdRef.current !== roomId
      ) {
        return;
      }
      const loadVersion = roomLoadVersion.current;
      const mutationVersion = mutationOperationVersionRef.current;
      const isCurrent = () =>
        mountedRef.current &&
        loadVersion === roomLoadVersion.current &&
        mutationVersion === mutationOperationVersionRef.current &&
        mutationOperationRef.current === null &&
        activeRoomIdRef.current === roomId &&
        requestedRoomIdRef.current === roomId;
      resumeRunRef.current = run.id;
      const diagnostic = diagnosticContext(createDiagnosticId());
      try {
        const result = await resumeTavernRun(roomId, run.id, diagnostic);
        if (!isCurrent() || !syncTurnResult(result)) return;
        resumeAttemptsRef.current.delete(run.id);
        setNotice(
          result.run.status === "completed"
            ? "中断的互动已恢复"
            : RUN_STATUS_LABELS[result.run.status],
        );
        setVisibleError("");
      } catch (error) {
        if (!isCurrent()) return;
        if (decodeTavernHttpError(error)?.code === "tavern_run_in_progress") {
          resumeAttemptsRef.current.set(
            run.id,
            Math.min(3, (resumeAttemptsRef.current.get(run.id) ?? 0) + 1),
          );
        } else if (
          activeRoomIdRef.current === roomId &&
          requestedRoomIdRef.current === roomId
        ) {
          recordError(
            error,
            "自动恢复暂时失败；页面会继续保留已提交消息。",
            setVisibleError,
            setRawError,
          );
        }
      } finally {
        if (
          loadVersion === roomLoadVersion.current &&
          resumeRunRef.current === run.id
        )
          resumeRunRef.current = "";
        if (isCurrent()) await refreshRoom(diagnostic);
      }
    },
    [refreshRoom, syncTurnResult, resumeTavernRun],
  );

  useEffect(() => {
    const pendingRun = runs.find((run) => run.status === "pending");
    if (
      !activeRoom ||
      busyAction !== null ||
      mutationOperationRef.current !== null ||
      !pendingRun ||
      pendingRun.id === foregroundRunRef.current
    )
      return;
    const attempt = resumeAttemptsRef.current.get(pendingRun.id) ?? 0;
    const timer = clock.setTimeout(
      () => void resumePendingRun(pendingRun),
      Math.min(10000, 2500 * 2 ** attempt),
    );
    return () => clock.clearTimeout(timer);
  }, [activeRoom, busyAction, resumePendingRun, runs, clock]);

  useEffect(() => {
    if (!activeRoom || (busyAction !== "turn" && busyAction !== "retry"))
      return;
    const roomId = activeRoom.id;
    const operationId = foregroundOperationIdRef.current;
    if (operationId === null) return;
    const diagnostic = mutationOperationRef.current?.diagnostic;
    let disposed = false;
    let inFlight = false;
    const discoverPendingRun = async () => {
      if (disposed || inFlight) return;
      inFlight = true;
      const pollVersion = ++runPollVersionRef.current;
      try {
        const nextRuns = await listTavernRuns(roomId, 50, diagnostic);
        if (
          disposed ||
          pollVersion !== runPollVersionRef.current ||
          foregroundOperationIdRef.current !== operationId ||
          mutationOperationRef.current?.id !== operationId ||
          activeRoomIdRef.current !== roomId ||
          requestedRoomIdRef.current !== roomId
        )
          return;
        const reconciledRuns = reconcileTavernRuns(runsRef.current, nextRuns);
        const pending = reconciledRuns.find((run) => run.status === "pending");
        if (pending) foregroundRunRef.current = pending.id;
        runsRef.current = reconciledRuns;
        setRuns(reconciledRuns);
      } catch (error) {
        if (
          !disposed &&
          foregroundOperationIdRef.current === operationId &&
          mutationOperationRef.current?.id === operationId &&
          activeRoomIdRef.current === roomId &&
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
  }, [activeRoom, busyAction, listTavernRuns, clock]);
}
