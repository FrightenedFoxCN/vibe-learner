"use client";

import type { TavernTurnResult } from "@vibe-learner/shared";
import { useCallback, useEffect, useState } from "react";

import {
  createDiagnosticId,
  diagnosticContext,
  type DiagnosticContext,
} from "../lib/diagnostics";
import { RUN_STATUS_LABELS } from "../lib/tavern-copy";
import {
  hasActiveTavernRun,
  isTavernRoomStateAtLeast,
  mergeTavernRoomPages,
  reconcileTavernCreationDraftPersonas,
  TAVERN_PAGE_SIZE,
  TAVERN_ROOM_PAGE_SIZE,
  TAVERN_ROOM_SUMMARY_LIMIT,
} from "../lib/tavern-workspace-state";

import { recordError } from "../lib/tavern-client-errors";
import {
  advanceTavernRoomListStatus,
  type TavernRoomListStatus,
} from "../lib/tavern-room-list-status";
import { readTavernRoomSnapshot } from "../lib/tavern-room-read";
import { refreshTavernTranscript } from "../lib/tavern-transcript-refresh";
import type { TavernRoomQueryPorts } from "../lib/tavern-workspace-ports";
import type { TavernWorkspaceState } from "./use-tavern-workspace-state";

export function useTavernRoomQueries(
  state: TavernWorkspaceState,
  ports: TavernRoomQueryPorts,
) {
  const {
    setRooms,
    nextRoomCursor,
    setNextRoomCursor,
    setLoadingMoreRooms,
    setRoomPageError,
    setRoomHistoryTruncated,
    setPersonas,
    setScenes,
    detail,
    messages,
    readRoomSnapshot,
    publishRoomSnapshot,
    setTargetPersonaIds,
    setGeneratingPersonaIds,
    setShowSetup,
    setBusyAction,
    setLoadingOlder,
    setNotice,
    setVisibleError,
    setRawError,
    roomLoadVersion,
    roomRefreshVersion,
    recoveryVersionRef,
    mountedRef,
    requestedRoomIdRef,
    olderLoadRoomRef,
    mutationOperationRef,
    mutationOperationVersionRef,
    foregroundRunRef,
    foregroundOperationIdRef,
    roomsRef,
    roomPageVersionRef,
    loadingRoomCursorRef,
    activeRoom,
    runPending,
  } = state;
  const {
    getTavernRoom,
    getTavernRunRecovery,
    listPersonas,
    listSceneLibrary,
    listTavernRooms,
    listTavernRuns,
  } = ports.api;
  const {
    readActiveTavernRoomId,
    readTavernCreationDraft,
    readTavernRoomDraft,
    rememberActiveTavernRoomId,
    writeTavernCreationDraft,
    writeTavernRoomDraft,
  } = ports.storage;
  const { makeRequestKey } = ports;
  const [roomListStatus, setRoomListStatus] = useState<TavernRoomListStatus>("loading");
  const openRoom = useCallback(
    async (roomId: string) => {
      if (!mountedRef.current) return false;
      const loadVersion = ++roomLoadVersion.current;
      roomRefreshVersion.current += 1;
      requestedRoomIdRef.current = roomId;
      const ownsLoad = () =>
        mountedRef.current &&
        loadVersion === roomLoadVersion.current &&
        requestedRoomIdRef.current === roomId;
      recoveryVersionRef.current += 1;
      mutationOperationRef.current = null;
      mutationOperationVersionRef.current += 1;
      foregroundOperationIdRef.current = null;
      foregroundRunRef.current = "";
      olderLoadRoomRef.current = null;
      setLoadingOlder(false);
      setGeneratingPersonaIds([]);
      setBusyAction("room");
      setVisibleError("");
      setRawError("");
      setNotice("正在恢复最近对话…");
      const diagnostic = diagnosticContext(createDiagnosticId());
      try {
        const snapshot = await readTavernRoomSnapshot({
          detail: getTavernRoom(
            { roomId, tail: true, limit: TAVERN_PAGE_SIZE },
            diagnostic,
          ),
          runs: listTavernRuns(roomId, 50, diagnostic),
          recovery: getTavernRunRecovery(roomId, 50, diagnostic),
        });
        const { detail: nextDetail, recovery: nextRecoveryChains } = snapshot;
        const nextRuns = snapshot.runs ?? [];
        if (!ownsLoad() || nextDetail.room.id !== roomId) return false;
        const roomDraft = readTavernRoomDraft(roomId);
        const draftRun = roomDraft.pendingTurn
          ? nextRuns.find((run) => run.idempotencyKey === roomDraft.pendingTurn?.key)
          : undefined;
        const participantIds = new Set(
          nextDetail.participants.map((item) => item.personaId),
        );
        const restoredTargetIds =
          roomDraft.pendingTurn?.targetPersonaIds
            .filter((id) => participantIds.has(id))
            .slice(0, 4) ?? [];
        if (draftRun) writeTavernRoomDraft(roomId, { message: "", guidance: "" });
        if (
          !publishRoomSnapshot({
            kind: "open",
            detail: nextDetail,
            runs: snapshot.runs,
            recovery: nextRecoveryChains,
          })
        )
          return false;
        if (snapshot.reliabilityErrors.length)
          setRawError(snapshot.reliabilityErrors.join("；"));
        setTargetPersonaIds(
          restoredTargetIds.length
            ? restoredTargetIds
            : nextDetail.participants[0]
              ? [nextDetail.participants[0].personaId]
              : [],
        );
        setShowSetup(false);
        setNotice(
          nextDetail.room.status === "archived"
            ? "已打开归档房间（只读）"
            : hasActiveTavernRun(nextRuns)
              ? "检测到尚未完成的互动"
              : "酒馆已就绪",
        );
        rememberActiveTavernRoomId(roomId);
        return true;
      } catch (error) {
        if (!ownsLoad()) return false;
        recordError(
          error,
          "无法打开这个酒馆，请稍后重试。",
          setVisibleError,
          setRawError,
        );
        setNotice("恢复失败");
        requestedRoomIdRef.current = readRoomSnapshot()?.detail.room.id ?? "";
        return false;
      } finally {
        if (mountedRef.current && loadVersion === roomLoadVersion.current) {
          setBusyAction(null);
        }
      }
    },
    [
      getTavernRoom,
      getTavernRunRecovery,
      listTavernRuns,
      readTavernRoomDraft,
      rememberActiveTavernRoomId,
      writeTavernRoomDraft,
      readRoomSnapshot,
      publishRoomSnapshot,
      foregroundOperationIdRef,
      foregroundRunRef,
      mountedRef,
      mutationOperationRef,
      mutationOperationVersionRef,
      olderLoadRoomRef,
      recoveryVersionRef,
      requestedRoomIdRef,
      roomLoadVersion,
      roomRefreshVersion,
      setBusyAction,
      setGeneratingPersonaIds,
      setLoadingOlder,
      setNotice,
      setRawError,
      setShowSetup,
      setTargetPersonaIds,
      setVisibleError,
    ],
  );

  const updateRooms = useCallback(
    async (context?: DiagnosticContext) => {
      if (!mountedRef.current) return;
      const pageVersion = ++roomPageVersionRef.current;
      loadingRoomCursorRef.current = null;
      setLoadingMoreRooms(false);
      setRoomPageError("");
      setRoomListStatus((current) => advanceTavernRoomListStatus(current, "start"));
      try {
        const page = await listTavernRooms({ limit: TAVERN_ROOM_PAGE_SIZE }, context);
        if (!mountedRef.current || pageVersion !== roomPageVersionRef.current) return;
        loadingRoomCursorRef.current = null;
        setLoadingMoreRooms(false);
        roomsRef.current = page.items;
        setRooms(page.items);
        setNextRoomCursor(page.nextCursor);
        setRoomHistoryTruncated(false);
        setRoomPageError("");
        setRoomListStatus("ready");
        return page;
      } catch (error) {
        if (!mountedRef.current || pageVersion !== roomPageVersionRef.current) return;
        setRawError(String(error));
        setRoomListStatus((current) => advanceTavernRoomListStatus(current, "failure"));
      }
    },
    [
      listTavernRooms,
      loadingRoomCursorRef,
      mountedRef,
      roomPageVersionRef,
      roomsRef,
      setLoadingMoreRooms,
      setNextRoomCursor,
      setRawError,
      setRoomHistoryTruncated,
      setRoomPageError,
      setRooms,
    ],
  );

  const refreshRoom = useCallback(
    async (
      context = diagnosticContext(createDiagnosticId()),
      { recoveryRead = false } = {},
    ) => {
      if (!mountedRef.current || !activeRoom?.id) {
        return;
      }
      const roomId = activeRoom.id;
      const refreshVersion = ++roomRefreshVersion.current;
      const recoveryVersion = ++recoveryVersionRef.current;
      const roomListRead = recoveryRead ? null : updateRooms(context);
      try {
        const snapshot = await readTavernRoomSnapshot({
          detail: getTavernRoom(
            { roomId, tail: true, limit: TAVERN_PAGE_SIZE },
            context,
          ),
          runs: listTavernRuns(roomId, 50, context),
          recovery: getTavernRunRecovery(roomId, 50, context),
        });
        const {
          detail: nextDetail,
          runs: nextRuns,
          recovery: nextRecoveryChains,
        } = snapshot;
        const isCurrent = () =>
          mountedRef.current &&
          readRoomSnapshot()?.detail.room.id === roomId &&
          requestedRoomIdRef.current === roomId &&
          refreshVersion === roomRefreshVersion.current;
        if (!isCurrent()) return;
        const currentDetail = readRoomSnapshot()?.detail;
        if (
          currentDetail?.room.id !== roomId ||
          !isTavernRoomStateAtLeast(nextDetail.room, currentDetail.room)
        )
          return;
        const transcript = await refreshTavernTranscript(
          currentDetail,
          nextDetail,
          (afterSequence, limit) =>
            getTavernRoom({ roomId, afterSequence, limit }, context),
        );
        if (!isCurrent()) return;
        const ownsRecovery = recoveryVersion === recoveryVersionRef.current;
        const published = publishRoomSnapshot({
          kind: "refresh",
          detail: nextDetail,
          initial: currentDetail,
          transcript,
          runs: nextRuns,
          recovery: nextRecoveryChains,
          ownsRecovery,
        });
        if (!published) return;
        if (ownsRecovery && snapshot.reliabilityErrors.length)
          setRawError(snapshot.reliabilityErrors.join("；"));
        const latestRun = published.runs[0];
        setNotice(
          nextDetail.room.status === "archived"
            ? "已同步归档房间"
            : latestRun?.status === "pending"
              ? "检测到尚未完成的互动"
              : latestRun
                ? `已同步 · ${RUN_STATUS_LABELS[latestRun.status]}`
                : "酒馆已就绪",
        );
        return { detail: published.detail, runs: nextRuns ? published.runs : [] };
      } catch (error) {
        if (
          readRoomSnapshot()?.detail.room.id === roomId &&
          requestedRoomIdRef.current === roomId &&
          refreshVersion === roomRefreshVersion.current
        ) {
          if (recoveryRead) {
            setRawError(String(error));
          } else {
            recordError(
              error,
              "刷新失败，当前内容仍保留在页面上。",
              setVisibleError,
              setRawError,
            );
          }
        }
        return null;
      } finally {
        await roomListRead;
      }
    },
    [
      activeRoom?.id,
      getTavernRoom,
      getTavernRunRecovery,
      listTavernRuns,
      readRoomSnapshot,
      publishRoomSnapshot,
      mountedRef,
      recoveryVersionRef,
      requestedRoomIdRef,
      roomRefreshVersion,
      setNotice,
      setRawError,
      setVisibleError,
      updateRooms,
    ],
  );

  useEffect(() => {
    let canceled = false;
    async function bootstrap() {
      setBusyAction("bootstrap");
      try {
        const [roomsResult, personasResult, scenesResult] = await Promise.allSettled([
          updateRooms(),
          listPersonas(),
          listSceneLibrary(),
        ]);
        if (canceled) return;
        const nextRoomPage =
          roomsResult.status === "fulfilled" ? roomsResult.value : null;
        const nextRooms = nextRoomPage?.items ?? [];
        const nextPersonas =
          personasResult.status === "fulfilled" ? personasResult.value : [];
        const nextScenes =
          scenesResult.status === "fulfilled" ? scenesResult.value : [];
        if (personasResult.status === "fulfilled") {
          const savedCreationDraft = readTavernCreationDraft();
          const reconciledCreationDraft = reconcileTavernCreationDraftPersonas(
            savedCreationDraft,
            nextPersonas.map((persona) => persona.id),
            makeRequestKey("room"),
          );
          if (reconciledCreationDraft !== savedCreationDraft) {
            writeTavernCreationDraft(reconciledCreationDraft);
          }
        }
        setPersonas(nextPersonas);
        setScenes(nextScenes);
        const failures = [personasResult, scenesResult]
          .filter((result) => result.status === "rejected")
          .map((result) => String((result as PromiseRejectedResult).reason));
        const storedRoomId = readActiveTavernRoomId();
        const preferredRoom =
          nextRooms.find((room) => room.status === "active") ?? nextRooms[0];
        const restoredStoredRoom = storedRoomId ? await openRoom(storedRoomId) : false;
        if (canceled) return;
        if (restoredStoredRoom || preferredRoom) {
          if (!restoredStoredRoom && preferredRoom) {
            await openRoom(preferredRoom.id);
          }
          if (canceled) return;
          if (failures.length) {
            setRawError(failures.join("；"));
            setVisibleError("部分酒馆资料暂时无法载入；已恢复的房间仍可继续使用。");
          }
        } else {
          if (failures.length) {
            setRawError(failures.join("；"));
            setVisibleError("部分酒馆资料暂时无法载入；可用功能仍可继续使用。");
          }
          setShowSetup(true);
          setNotice(
            failures.length ? "部分资料载入失败" : "创建一个酒馆，开始自由对话",
          );
          setBusyAction(null);
        }
      } catch (error) {
        if (canceled) return;
        recordError(
          error,
          "酒馆资料载入失败，请检查 AI 服务连接。",
          setVisibleError,
          setRawError,
        );
        setNotice("载入失败");
        setShowSetup(true);
        setBusyAction(null);
      }
    }
    void bootstrap();
    return () => {
      canceled = true;
      roomLoadVersion.current += 1;
      roomRefreshVersion.current += 1;
      roomPageVersionRef.current += 1;
      recoveryVersionRef.current += 1;
      loadingRoomCursorRef.current = null;
      requestedRoomIdRef.current = "";
      mutationOperationRef.current = null;
      mutationOperationVersionRef.current += 1;
      foregroundOperationIdRef.current = null;
    };
  }, [
    openRoom,
    updateRooms,
    listPersonas,
    listSceneLibrary,
    readTavernCreationDraft,
    writeTavernCreationDraft,
    readActiveTavernRoomId,
    makeRequestKey,
    setBusyAction,
    roomPageVersionRef,
    loadingRoomCursorRef,
    setPersonas,
    setScenes,
    setRawError,
    setVisibleError,
    setShowSetup,
    setNotice,
    roomLoadVersion,
    roomRefreshVersion,
    recoveryVersionRef,
    requestedRoomIdRef,
    mutationOperationRef,
    mutationOperationVersionRef,
    foregroundOperationIdRef,
  ]);

  const loadMoreRooms = useCallback(async () => {
    const cursor = nextRoomCursor;
    if (!cursor || loadingRoomCursorRef.current === cursor) return;
    const pageVersion = roomPageVersionRef.current;
    loadingRoomCursorRef.current = cursor;
    setLoadingMoreRooms(true);
    setRoomPageError("");
    try {
      const page = await listTavernRooms({
        limit: TAVERN_ROOM_PAGE_SIZE,
        cursor,
      });
      if (
        pageVersion !== roomPageVersionRef.current ||
        loadingRoomCursorRef.current !== cursor
      )
        return;
      const currentRoomIds = new Set(roomsRef.current.map((room) => room.id));
      const uniqueIncomingCount = page.items.filter(
        (room) => !currentRoomIds.has(room.id),
      ).length;
      const fetchedSummaryCount = roomsRef.current.length + uniqueIncomingCount;
      const merged = mergeTavernRoomPages(roomsRef.current, page.items);
      const reachedLimit =
        fetchedSummaryCount > TAVERN_ROOM_SUMMARY_LIMIT ||
        (merged.length >= TAVERN_ROOM_SUMMARY_LIMIT && page.nextCursor !== null);
      roomsRef.current = merged;
      setRooms(merged);
      setNextRoomCursor(reachedLimit ? null : page.nextCursor);
      setRoomHistoryTruncated(reachedLimit);
    } catch (error) {
      if (
        pageVersion === roomPageVersionRef.current &&
        loadingRoomCursorRef.current === cursor
      ) {
        setRawError(String(error));
        setRoomPageError("更多房间未载入；可以重试。当前列表没有变化。");
      }
    } finally {
      if (
        pageVersion === roomPageVersionRef.current &&
        loadingRoomCursorRef.current === cursor
      ) {
        loadingRoomCursorRef.current = null;
        setLoadingMoreRooms(false);
      }
    }
  }, [
    nextRoomCursor,
    listTavernRooms,
    loadingRoomCursorRef,
    roomPageVersionRef,
    setLoadingMoreRooms,
    setRoomPageError,
    roomsRef,
    setRooms,
    setNextRoomCursor,
    setRoomHistoryTruncated,
    setRawError,
  ]);

  const updateRunRecovery = useCallback(
    async (roomId: string, context?: DiagnosticContext) => {
      const loadVersion = roomLoadVersion.current;
      const recoveryVersion = ++recoveryVersionRef.current;
      const isCurrent = () =>
        mountedRef.current &&
        loadVersion === roomLoadVersion.current &&
        recoveryVersion === recoveryVersionRef.current &&
        readRoomSnapshot()?.detail.room.id === roomId &&
        requestedRoomIdRef.current === roomId;
      try {
        const nextChains = await getTavernRunRecovery(roomId, 50, context);
        if (isCurrent()) {
          publishRoomSnapshot({ kind: "recovery", roomId, chains: nextChains });
        }
      } catch (error) {
        if (isCurrent()) setRawError(String(error));
      }
    },
    [
      getTavernRunRecovery,
      readRoomSnapshot,
      publishRoomSnapshot,
      mountedRef,
      recoveryVersionRef,
      requestedRoomIdRef,
      roomLoadVersion,
      setRawError,
    ],
  );

  const syncTurnResult = useCallback(
    (result: TavernTurnResult) => {
      if (
        readRoomSnapshot()?.detail.room.id !== result.roomState.id ||
        requestedRoomIdRef.current !== result.roomState.id
      ) {
        return false;
      }
      if (!publishRoomSnapshot({ kind: "turn", result })) return false;
      roomRefreshVersion.current += 1;
      recoveryVersionRef.current += 1;
      return true;
    },
    [
      recoveryVersionRef,
      requestedRoomIdRef,
      roomRefreshVersion,
      readRoomSnapshot,
      publishRoomSnapshot,
    ],
  );

  const recoverCurrentRoom = useCallback(
    async (context?: DiagnosticContext) => {
      await refreshRoom(context);
    },
    [refreshRoom],
  );

  const handleLoadOlder = useCallback(async () => {
    if (
      !activeRoom ||
      detail?.nextBeforeSequence == null ||
      mutationOperationRef.current ||
      runPending
    )
      return false;
    const roomId = activeRoom.id;
    const loadVersion = roomLoadVersion.current;
    const ownsPage = () =>
      mountedRef.current &&
      loadVersion === roomLoadVersion.current &&
      readRoomSnapshot()?.detail.room.id === roomId &&
      requestedRoomIdRef.current === roomId &&
      olderLoadRoomRef.current === roomId;
    const requestedBefore = detail.nextBeforeSequence;
    const firstLoadedSequence = messages[0]?.sequence ?? Number.POSITIVE_INFINITY;
    if (olderLoadRoomRef.current) return false;
    olderLoadRoomRef.current = roomId;
    setLoadingOlder(true);
    setVisibleError("");
    try {
      const previous = await getTavernRoom({
        roomId,
        beforeSequence: requestedBefore,
        limit: TAVERN_PAGE_SIZE,
      });
      if (!ownsPage()) return false;
      if (
        !publishRoomSnapshot({
          kind: "older",
          roomId,
          requestedBefore,
          detail: previous,
        })
      )
        return false;
      return previous.messages.some(
        (message) => message.sequence < firstLoadedSequence,
      );
    } catch (error) {
      if (
        ownsPage() &&
        readRoomSnapshot()?.detail?.nextBeforeSequence === requestedBefore
      ) {
        recordError(error, "更早的消息暂时无法载入。", setVisibleError, setRawError);
      }
      return false;
    } finally {
      if (ownsPage()) {
        olderLoadRoomRef.current = null;
        setLoadingOlder(false);
      }
    }
  }, [
    activeRoom,
    detail?.nextBeforeSequence,
    messages,
    runPending,
    getTavernRoom,
    readRoomSnapshot,
    publishRoomSnapshot,
    mutationOperationRef,
    roomLoadVersion,
    olderLoadRoomRef,
    setLoadingOlder,
    setVisibleError,
    mountedRef,
    requestedRoomIdRef,
    setRawError,
  ]);

  return {
    roomListStatus,
    openRoom,
    refreshRoom,
    updateRooms,
    loadMoreRooms,
    updateRunRecovery,
    syncTurnResult,
    recoverCurrentRoom,
    handleLoadOlder,
  };
}
export type TavernRoomQueries = ReturnType<typeof useTavernRoomQueries>;
