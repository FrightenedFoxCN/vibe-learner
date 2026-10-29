"use client";

import type { TavernTurnResult } from "@vibe-learner/shared";
import { useCallback, useEffect } from "react";

import {
  createDiagnosticId,
  diagnosticContext,
  type DiagnosticContext,
} from "../lib/diagnostics";
import { RUN_STATUS_LABELS } from "../lib/tavern-copy";
import {
  hasActiveTavernRun,
  isTavernRoomStateAtLeast,
  mergeTavernMessages,
  mergeTavernRoomPages,
  reconcileTavernCreationDraftPersonas,
  reconcileTavernRuns,
  TAVERN_PAGE_SIZE,
  TAVERN_ROOM_PAGE_SIZE,
  TAVERN_ROOM_SUMMARY_LIMIT,
} from "../lib/tavern-workspace-state";

import { friendlyTavernError, recordError } from "../lib/tavern-client-errors";
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
    setDetail,
    messages,
    setMessages,
    setRuns,
    setRecoveryChains,
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
    resumeRunRef,
    mountedRef,
    activeRoomIdRef,
    requestedRoomIdRef,
    olderLoadRoomRef,
    mutationOperationRef,
    mutationOperationVersionRef,
    foregroundRunRef,
    foregroundOperationIdRef,
    detailRef,
    runsRef,
    messagesRef,
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
  const openRoom = useCallback(
    async (roomId: string) => {
      if (!mountedRef.current) return false;
      const loadVersion = ++roomLoadVersion.current;
      roomRefreshVersion.current += 1;
      requestedRoomIdRef.current = roomId;
      recoveryVersionRef.current += 1;
      resumeRunRef.current = "";
      mutationOperationRef.current = null;
      mutationOperationVersionRef.current += 1;
      foregroundOperationIdRef.current = null;
      foregroundRunRef.current = "";
      olderLoadRoomRef.current = null;
      setLoadingOlder(false);
      setGeneratingPersonaIds([]);
      setRecoveryChains([]);
      setBusyAction("room");
      setVisibleError("");
      setRawError("");
      setNotice("正在恢复最近对话…");
      const diagnostic = diagnosticContext(createDiagnosticId());
      try {
        const [nextDetail, nextRuns, nextRecoveryChains] = await Promise.all([
          getTavernRoom(
            { roomId, tail: true, limit: TAVERN_PAGE_SIZE },
            diagnostic,
          ),
          listTavernRuns(roomId, 50, diagnostic),
          getTavernRunRecovery(roomId, 50, diagnostic),
        ]);
        if (loadVersion !== roomLoadVersion.current) {
          return;
        }
        activeRoomIdRef.current = roomId;
        requestedRoomIdRef.current = roomId;
        const roomDraft = readTavernRoomDraft(roomId);
        const draftRun = roomDraft.pendingTurn
          ? nextRuns.find(
              (run) => run.idempotencyKey === roomDraft.pendingTurn?.key,
            )
          : undefined;
        const participantIds = new Set(
          nextDetail.participants.map((item) => item.personaId),
        );
        const restoredTargetIds =
          roomDraft.pendingTurn?.targetPersonaIds
            .filter((id) => participantIds.has(id))
            .slice(0, 4) ?? [];
        if (draftRun)
          writeTavernRoomDraft(roomId, { message: "", guidance: "" });
        const nextMessages = mergeTavernMessages([], nextDetail.messages);
        messagesRef.current = nextMessages;
        detailRef.current = nextDetail;
        runsRef.current = nextRuns;
        setDetail(nextDetail);
        setMessages(nextMessages);
        setRuns(nextRuns);
        setRecoveryChains(nextRecoveryChains);
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
              ? "检测到正在执行的互动，正在自动恢复"
              : "酒馆已就绪",
        );
        rememberActiveTavernRoomId(roomId);
        return true;
      } catch (error) {
        if (loadVersion !== roomLoadVersion.current) {
          return false;
        }
        recordError(
          error,
          "无法打开这个酒馆，请稍后重试。",
          setVisibleError,
          setRawError,
        );
        setNotice("恢复失败");
        requestedRoomIdRef.current = activeRoomIdRef.current;
        return false;
      } finally {
        if (loadVersion === roomLoadVersion.current) {
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
    ],
  );

  const refreshRoom = useCallback(
    async (context = diagnosticContext(createDiagnosticId())) => {
      if (!mountedRef.current || !activeRoom?.id) {
        return;
      }
      const roomId = activeRoom.id;
      const refreshVersion = ++roomRefreshVersion.current;
      const recoveryVersion = ++recoveryVersionRef.current;
      const pageVersion = ++roomPageVersionRef.current;
      loadingRoomCursorRef.current = null;
      setLoadingMoreRooms(false);
      try {
        const [nextDetail, nextRuns, nextRecoveryChains, nextRoomPage] =
          await Promise.all([
            getTavernRoom(
              { roomId, tail: true, limit: TAVERN_PAGE_SIZE },
              context,
            ),
            listTavernRuns(roomId, 50, context),
            getTavernRunRecovery(roomId, 50, context),
            listTavernRooms({ limit: TAVERN_ROOM_PAGE_SIZE }, context),
          ]);
        if (
          activeRoomIdRef.current !== roomId ||
          requestedRoomIdRef.current !== roomId ||
          refreshVersion !== roomRefreshVersion.current
        ) {
          return;
        }
        const currentDetail = detailRef.current;
        if (
          currentDetail?.room.id !== roomId ||
          !isTavernRoomStateAtLeast(nextDetail.room, currentDetail.room)
        )
          return;
        const refreshedDetail = {
          ...nextDetail,
          nextBeforeSequence: currentDetail.nextBeforeSequence,
        };
        const nextMessages = mergeTavernMessages(
          messagesRef.current,
          nextDetail.messages,
        );
        const reconciledRuns = reconcileTavernRuns(runsRef.current, nextRuns);
        detailRef.current = refreshedDetail;
        runsRef.current = reconciledRuns;
        setDetail(refreshedDetail);
        messagesRef.current = nextMessages;
        setMessages(nextMessages);
        setRuns(reconciledRuns);
        if (recoveryVersion === recoveryVersionRef.current)
          setRecoveryChains(nextRecoveryChains);
        if (pageVersion === roomPageVersionRef.current) {
          loadingRoomCursorRef.current = null;
          setLoadingMoreRooms(false);
          roomsRef.current = nextRoomPage.items;
          setRooms(nextRoomPage.items);
          setNextRoomCursor(nextRoomPage.nextCursor);
          setRoomHistoryTruncated(false);
          setRoomPageError("");
        }
        const latestRun = reconciledRuns[0];
        setNotice(
          nextDetail.room.status === "archived"
            ? "已同步归档房间"
            : latestRun?.status === "pending"
              ? "检测到正在执行的互动，正在自动恢复"
              : latestRun
                ? `已同步 · ${RUN_STATUS_LABELS[latestRun.status]}`
                : "酒馆已就绪",
        );
        return { detail: nextDetail, runs: reconciledRuns };
      } catch (error) {
        if (
          activeRoomIdRef.current === roomId &&
          requestedRoomIdRef.current === roomId &&
          refreshVersion === roomRefreshVersion.current
        ) {
          recordError(
            error,
            "刷新失败，当前内容仍保留在页面上。",
            setVisibleError,
            setRawError,
          );
        }
        return null;
      }
    },
    [
      activeRoom?.id,
      getTavernRoom,
      getTavernRunRecovery,
      listTavernRooms,
      listTavernRuns,
    ],
  );

  useEffect(() => {
    let canceled = false;
    async function bootstrap() {
      setBusyAction("bootstrap");
      try {
        const [roomsResult, personasResult, scenesResult] =
          await Promise.allSettled([
            listTavernRooms({ limit: TAVERN_ROOM_PAGE_SIZE }),
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
        roomPageVersionRef.current += 1;
        loadingRoomCursorRef.current = null;
        setLoadingMoreRooms(false);
        roomsRef.current = nextRooms;
        setRooms(nextRooms);
        setNextRoomCursor(nextRoomPage?.nextCursor ?? null);
        setRoomHistoryTruncated(false);
        setRoomPageError(
          roomsResult.status === "rejected" ? "房间历史暂时无法载入。" : "",
        );
        setPersonas(nextPersonas);
        setScenes(nextScenes);
        const failures = [roomsResult, personasResult, scenesResult]
          .filter((result) => result.status === "rejected")
          .map((result) => String((result as PromiseRejectedResult).reason));
        const storedRoomId = readActiveTavernRoomId();
        const preferredRoom =
          nextRooms.find((room) => room.status === "active") ?? nextRooms[0];
        const restoredStoredRoom = storedRoomId
          ? await openRoom(storedRoomId)
          : false;
        if (canceled) return;
        if (restoredStoredRoom || preferredRoom) {
          if (!restoredStoredRoom && preferredRoom) {
            await openRoom(preferredRoom.id);
          }
          if (canceled) return;
          if (failures.length) {
            setRawError(failures.join("；"));
            setVisibleError(
              "部分酒馆资料暂时无法载入；已恢复的房间仍可继续使用。",
            );
          }
        } else {
          if (failures.length) {
            setRawError(failures.join("；"));
            setVisibleError(
              failures.length === 3
                ? friendlyTavernError(
                    failures[0],
                    "酒馆资料载入失败，请检查 AI 服务连接。",
                  )
                : "部分酒馆资料暂时无法载入；可用功能仍可继续使用。",
            );
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
    listTavernRooms,
    listPersonas,
    listSceneLibrary,
    readTavernCreationDraft,
    writeTavernCreationDraft,
    readActiveTavernRoomId,
    makeRequestKey,
  ]);

  const updateRooms = useCallback(
    async (context?: DiagnosticContext) => {
      if (!mountedRef.current) return;
      const pageVersion = ++roomPageVersionRef.current;
      loadingRoomCursorRef.current = null;
      setLoadingMoreRooms(false);
      try {
        const page = await listTavernRooms(
          { limit: TAVERN_ROOM_PAGE_SIZE },
          context,
        );
        if (!mountedRef.current || pageVersion !== roomPageVersionRef.current)
          return;
        loadingRoomCursorRef.current = null;
        setLoadingMoreRooms(false);
        roomsRef.current = page.items;
        setRooms(page.items);
        setNextRoomCursor(page.nextCursor);
        setRoomHistoryTruncated(false);
        setRoomPageError("");
      } catch (error) {
        if (!mountedRef.current || pageVersion !== roomPageVersionRef.current)
          return;
        setRawError(String(error));
        setRoomPageError("房间历史刷新失败；当前列表已保留。");
      }
    },
    [listTavernRooms],
  );

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
        (merged.length >= TAVERN_ROOM_SUMMARY_LIMIT &&
          page.nextCursor !== null);
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
  }, [nextRoomCursor, listTavernRooms]);

  const updateRunRecovery = useCallback(
    async (roomId: string, context?: DiagnosticContext) => {
      const loadVersion = roomLoadVersion.current;
      const recoveryVersion = ++recoveryVersionRef.current;
      const isCurrent = () =>
        mountedRef.current &&
        loadVersion === roomLoadVersion.current &&
        recoveryVersion === recoveryVersionRef.current &&
        activeRoomIdRef.current === roomId &&
        requestedRoomIdRef.current === roomId;
      try {
        const nextChains = await getTavernRunRecovery(roomId, 50, context);
        if (isCurrent()) {
          setRecoveryChains(nextChains);
        }
      } catch (error) {
        if (isCurrent()) setRawError(String(error));
      }
    },
    [getTavernRunRecovery],
  );

  const syncTurnResult = useCallback((result: TavernTurnResult) => {
    if (
      activeRoomIdRef.current !== result.roomState.id ||
      requestedRoomIdRef.current !== result.roomState.id
    ) {
      return false;
    }
    const currentDetail = detailRef.current;
    if (!currentDetail || currentDetail.room.id !== result.roomState.id)
      return false;
    const currentRoomState = currentDetail
      ? {
          id: currentDetail.room.id,
          status: currentDetail.room.status,
          revision: currentDetail.room.revision,
          lastSequence: currentDetail.room.lastSequence,
          updatedAt: currentDetail.room.updatedAt,
        }
      : null;
    const currentRun = runsRef.current.find((run) => run.id === result.run.id);
    if (
      !isTavernRoomStateAtLeast(result.roomState, currentRoomState) ||
      (currentRun &&
        currentRun.status !== "pending" &&
        currentRun.status !== result.run.status)
    )
      return false;
    roomRefreshVersion.current += 1;
    recoveryVersionRef.current += 1;
    const appended = [
      ...(result.inputMessage ? [result.inputMessage] : []),
      ...result.generatedMessages,
    ];
    const nextMessages = mergeTavernMessages(messagesRef.current, appended);
    messagesRef.current = nextMessages;
    setMessages(nextMessages);
    const nextRuns = [
      result.run,
      ...runsRef.current.filter((run) => run.id !== result.run.id),
    ];
    const nextDetail = {
      ...currentDetail,
      room: {
        ...currentDetail.room,
        status: result.roomState.status,
        revision: result.roomState.revision,
        lastSequence: result.roomState.lastSequence,
        updatedAt: result.roomState.updatedAt,
      },
      messageCount: Math.max(
        currentDetail.messageCount,
        result.roomState.lastSequence,
      ),
    };
    runsRef.current = nextRuns;
    detailRef.current = nextDetail;
    setRuns(nextRuns);
    setDetail(nextDetail);
    return true;
  }, []);

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
      activeRoomIdRef.current === roomId &&
      requestedRoomIdRef.current === roomId &&
      olderLoadRoomRef.current === roomId;
    const firstLoadedSequence =
      messages[0]?.sequence ?? Number.POSITIVE_INFINITY;
    if (olderLoadRoomRef.current) return false;
    olderLoadRoomRef.current = roomId;
    setLoadingOlder(true);
    setVisibleError("");
    try {
      const previous = await getTavernRoom({
        roomId,
        beforeSequence: detail.nextBeforeSequence,
        limit: TAVERN_PAGE_SIZE,
      });
      if (!ownsPage()) return false;
      const nextMessages = mergeTavernMessages(
        messagesRef.current,
        previous.messages,
      );
      const currentDetail = detailRef.current;
      if (!currentDetail || currentDetail.room.id !== roomId) return false;
      const nextDetail = {
        ...currentDetail,
        nextBeforeSequence: previous.nextBeforeSequence,
      };
      messagesRef.current = nextMessages;
      detailRef.current = nextDetail;
      setMessages(nextMessages);
      setDetail(nextDetail);
      return previous.messages.some(
        (message) => message.sequence < firstLoadedSequence,
      );
    } catch (error) {
      if (ownsPage()) {
        recordError(
          error,
          "更早的消息暂时无法载入。",
          setVisibleError,
          setRawError,
        );
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
  ]);

  return {
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
