"use client";

import type { TavernRun } from "@vibe-learner/shared";
import { useCallback } from "react";

import { createDiagnosticId, diagnosticContext } from "../lib/diagnostics";
import { RUN_STATUS_LABELS, TAVERN_COPY } from "../lib/tavern-copy";
import {
  isTavernRoomStateAtLeast,
  mergeTavernMessages,
} from "../lib/tavern-workspace-state";

import { recordError } from "../lib/tavern-client-errors";
import type {
  MutationAction,
  MutationOperation,
  TavernMutationPorts,
} from "../lib/tavern-workspace-ports";
import type { TavernRoomQueries } from "./use-tavern-room-queries";
import type { TavernWorkspaceState } from "./use-tavern-workspace-state";

export function useTavernMutations(
  state: TavernWorkspaceState,
  ports: TavernMutationPorts,
  queries: TavernRoomQueries,
) {
  const {
    mountedRef,
    scenes,
    setDetail,
    setMessages,
    runs,
    setRuns,
    setRecoveryChains,
    targetPersonaIds,
    setTargetPersonaIds,
    setGeneratingPersonaIds,
    setShowSetup,
    busyAction,
    setBusyAction,
    setNotice,
    setVisibleError,
    setRawError,
    roomLoadVersion,
    roomRefreshVersion,
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
    activeRoom,
    roomIsActive,
    runPending,
  } = state;
  const {
    createTavernRoom,
    cancelTavernRun,
    retryTavernRun,
    runTavernTurn,
    updateTavernRoom,
  } = ports.api;
  const {
    readTavernCreationDraft,
    readTavernRoomDraft,
    rememberActiveTavernRoomId,
    writeTavernCreationDraft,
    writeTavernRoomDraft,
  } = ports.storage;
  const { makeRequestKey } = ports;
  const {
    refreshRoom,
    updateRooms,
    updateRunRecovery,
    syncTurnResult,
    recoverCurrentRoom,
  } = queries;
  const beginMutation = useCallback(
    (
      action: MutationAction,
      roomId: string,
      replaceCurrent = false,
    ): MutationOperation | null => {
      if (
        !mountedRef.current ||
        (action !== "create" &&
          (activeRoomIdRef.current !== roomId ||
            requestedRoomIdRef.current !== roomId)) ||
        olderLoadRoomRef.current ||
        (mutationOperationRef.current && !replaceCurrent)
      )
        return null;
      const operation = {
        diagnostic: diagnosticContext(
          replaceCurrent && mutationOperationRef.current?.roomId === roomId
            ? mutationOperationRef.current.diagnostic.flow_id
            : createDiagnosticId(),
        ),
        id: ++mutationOperationVersionRef.current,
        action,
        roomId,
      };
      mutationOperationRef.current = operation;
      return operation;
    },
    [],
  );

  const operationIsCurrent = useCallback(
    (operation: MutationOperation): boolean => {
      return mountedRef.current && mutationOperationRef.current?.id === operation.id;
    },
    [mountedRef, mutationOperationRef],
  );

  const finishMutation = useCallback(
    (operation: MutationOperation): boolean => {
      if (!operationIsCurrent(operation)) return false;
      mutationOperationRef.current = null;
      setBusyAction((current) => (current === operation.action ? null : current));
      return true;
    },
    [operationIsCurrent],
  );

  const releaseForegroundOperation = useCallback(
    (operation: MutationOperation) => {
      if (foregroundOperationIdRef.current !== operation.id) return;
      foregroundOperationIdRef.current = null;
      foregroundRunRef.current = "";
    },
    [foregroundOperationIdRef, foregroundRunRef],
  );

  const handleCreateRoom = useCallback(
    async (input: {
      title: string;
      personaIds: string[];
      sceneId: string;
      openingPrompt: string;
    }) => {
      const operation = beginMutation("create", "new-room");
      if (!operation) return;
      roomRefreshVersion.current += 1;
      const sceneProfile = scenes.find(
        (scene) => scene.sceneId === input.sceneId,
      )?.sceneProfile;
      const savedCreation = readTavernCreationDraft();
      const sameCreation =
        savedCreation &&
        savedCreation.title === input.title &&
        savedCreation.sceneId === input.sceneId &&
        savedCreation.openingPrompt === input.openingPrompt &&
        savedCreation.personaIds.join("\u0000") === input.personaIds.join("\u0000");
      const creationDraft = sameCreation
        ? savedCreation
        : {
            ...input,
            key: makeRequestKey("room"),
          };
      writeTavernCreationDraft(creationDraft);
      setBusyAction("create");
      setVisibleError("");
      setRawError("");
      setNotice("正在创建酒馆…");
      try {
        const created = await createTavernRoom(
          {
            title: input.title,
            personaIds: input.personaIds,
            sceneProfile,
            openingPrompt: input.openingPrompt,
            idempotencyKey: creationDraft.key,
          },
          operation.diagnostic,
        );
        if (!operationIsCurrent(operation)) return;
        activeRoomIdRef.current = created.room.id;
        requestedRoomIdRef.current = created.room.id;
        roomLoadVersion.current += 1;
        roomRefreshVersion.current += 1;
        const nextMessages = mergeTavernMessages([], created.messages);
        messagesRef.current = nextMessages;
        detailRef.current = created;
        runsRef.current = [];
        setDetail(created);
        setMessages(nextMessages);
        setRuns([]);
        setRecoveryChains([]);
        setTargetPersonaIds(
          created.participants[0] ? [created.participants[0].personaId] : [],
        );
        setShowSetup(false);
        setNotice("酒馆已创建，可以开始对话");
        rememberActiveTavernRoomId(created.room.id);
        writeTavernCreationDraft(null);
        await updateRooms(operation.diagnostic);
      } catch (error) {
        if (!operationIsCurrent(operation)) return;
        recordError(
          error,
          "创建失败，请检查标题、人格与服务连接。",
          setVisibleError,
          setRawError,
        );
        setNotice("创建失败");
      } finally {
        finishMutation(operation);
      }
    },
    [
      beginMutation,
      finishMutation,
      operationIsCurrent,
      scenes,
      updateRooms,
      createTavernRoom,
      readTavernCreationDraft,
      rememberActiveTavernRoomId,
      writeTavernCreationDraft,
      makeRequestKey,
    ],
  );

  const handleArchiveToggle = useCallback(async () => {
    if (!activeRoom || runPending) return;
    const operation = beginMutation("archive", activeRoom.id);
    if (!operation) return;
    roomRefreshVersion.current += 1;
    setBusyAction("archive");
    setVisibleError("");
    setRawError("");
    const nextStatus = activeRoom.status === "active" ? "archived" : "active";
    const roomId = activeRoom.id;
    try {
      const updated = await updateTavernRoom(
        roomId,
        {
          status: nextStatus,
          expectedRoomRevision: activeRoom.revision,
        },
        operation.diagnostic,
      );
      if (
        !operationIsCurrent(operation) ||
        activeRoomIdRef.current !== roomId ||
        requestedRoomIdRef.current !== roomId
      )
        return;
      const currentDetail = detailRef.current;
      if (
        !currentDetail ||
        currentDetail.room.id !== roomId ||
        !isTavernRoomStateAtLeast(updated.room, currentDetail.room)
      )
        return;
      const nextMessages = mergeTavernMessages(messagesRef.current, updated.messages);
      const updatedDetail = {
        ...currentDetail,
        room: updated.room,
        participants: updated.participants,
        messageCount: updated.messageCount,
      };
      detailRef.current = updatedDetail;
      messagesRef.current = nextMessages;
      setDetail(updatedDetail);
      setMessages(nextMessages);
      setNotice(
        nextStatus === "archived" ? "酒馆已归档，历史仍可阅读" : "酒馆已恢复使用",
      );
      await updateRooms(operation.diagnostic);
    } catch (error) {
      if (!operationIsCurrent(operation)) return;
      recordError(
        error,
        "房间状态未更新；页面将重新同步最新版本。",
        setVisibleError,
        setRawError,
      );
      await recoverCurrentRoom(operation.diagnostic);
    } finally {
      finishMutation(operation);
    }
  }, [
    activeRoom,
    beginMutation,
    finishMutation,
    operationIsCurrent,
    recoverCurrentRoom,
    runPending,
    updateRooms,
    updateTavernRoom,
  ]);

  const handleTurn = useCallback(
    async (
      input:
        | { kind: "user_message"; content: string }
        | { kind: "continue"; anchorMessageId: string },
      guidance: string,
    ) => {
      if (!activeRoom || !roomIsActive || targetPersonaIds.length < 1 || runPending)
        return false;
      if (targetPersonaIds.length > 4) {
        setVisibleError("每轮最多选择 4 位角色。房间可以保留更多角色供后续选择。");
        return false;
      }
      const roomId = activeRoom.id;
      const operation = beginMutation("turn", roomId);
      if (!operation) return false;
      foregroundOperationIdRef.current = operation.id;
      roomRefreshVersion.current += 1;
      setGeneratingPersonaIds(targetPersonaIds);
      setBusyAction("turn");
      setVisibleError("");
      setRawError("");
      setNotice(
        targetPersonaIds.length === 1 ? "角色正在回应…" : "角色将按名册顺序依次回应…",
      );
      const savedDraft = readTavernRoomDraft(roomId);
      const sameTargetSet = savedDraft.pendingTurn
        ? [...savedDraft.pendingTurn.targetPersonaIds].sort().join("\u0000") ===
          [...targetPersonaIds].sort().join("\u0000")
        : false;
      const matchingPending =
        input.kind === "user_message" &&
        savedDraft.pendingTurn?.content === input.content &&
        savedDraft.pendingTurn.guidance === guidance &&
        sameTargetSet
          ? savedDraft.pendingTurn
          : undefined;
      const requestKey = matchingPending?.key ?? makeRequestKey("turn");
      const expectedRoomRevision =
        matchingPending?.expectedRoomRevision ?? activeRoom.revision;
      if (input.kind === "user_message") {
        writeTavernRoomDraft(roomId, {
          message: input.content,
          guidance,
          pendingTurn: {
            key: requestKey,
            content: input.content,
            guidance,
            targetPersonaIds,
            expectedRoomRevision,
          },
        });
      }
      try {
        const result = await runTavernTurn(
          roomId,
          {
            input,
            mode: targetPersonaIds.length === 1 ? "direct" : "facilitated",
            targetPersonaIds,
            guidance,
            idempotencyKey: requestKey,
            expectedRoomRevision,
          },
          operation.diagnostic,
        );
        if (
          !operationIsCurrent(operation) ||
          activeRoomIdRef.current !== roomId ||
          requestedRoomIdRef.current !== roomId
        )
          return false;
        if (!syncTurnResult(result)) return false;
        if (result.run.status !== "pending") releaseForegroundOperation(operation);
        if (input.kind === "user_message" && result.inputMessage) {
          writeTavernRoomDraft(roomId, { message: "", guidance: "" });
        }
        setNotice(
          result.run.status === "completed"
            ? "本轮互动已完成"
            : RUN_STATUS_LABELS[result.run.status],
        );
        if (result.run.status === "partial" || result.run.status === "failed") {
          setVisibleError(
            result.run.status === "partial" ? TAVERN_COPY.partial : TAVERN_COPY.failed,
          );
        }
        await Promise.all([
          updateRooms(operation.diagnostic),
          updateRunRecovery(roomId, operation.diagnostic),
        ]);
        return result.inputMessage !== null || input.kind === "continue";
      } catch (error) {
        if (!operationIsCurrent(operation)) return false;
        releaseForegroundOperation(operation);
        const recovered = await refreshRoom(operation.diagnostic);
        if (!operationIsCurrent(operation)) return false;
        const recoveredRun = recovered?.runs.find(
          (run) => run.idempotencyKey === requestKey,
        );
        if (recoveredRun && input.kind === "user_message") {
          writeTavernRoomDraft(roomId, { message: "", guidance: "" });
        }
        if (recoveredRun?.status === "canceled") {
          setVisibleError("");
          setNotice("已取消接收本轮结果");
        } else {
          recordError(
            error,
            "本轮未完整返回；已尝试恢复服务端保存的消息与可靠性记录。",
            setVisibleError,
            setRawError,
          );
          setNotice(
            recoveredRun ? RUN_STATUS_LABELS[recoveredRun.status] : "本轮状态仍待确认",
          );
        }
        return Boolean(recoveredRun);
      } finally {
        releaseForegroundOperation(operation);
        if (finishMutation(operation)) setGeneratingPersonaIds([]);
      }
    },
    [
      activeRoom,
      beginMutation,
      finishMutation,
      operationIsCurrent,
      refreshRoom,
      releaseForegroundOperation,
      roomIsActive,
      runPending,
      syncTurnResult,
      targetPersonaIds,
      updateRooms,
      updateRunRecovery,
      runTavernTurn,
      readTavernRoomDraft,
      writeTavernRoomDraft,
      makeRequestKey,
    ],
  );

  const handleCancelRun = useCallback(async () => {
    const pendingRun = runs.find((run) => run.status === "pending");
    if (!activeRoom || !pendingRun || busyAction === "cancel") return false;
    const roomId = activeRoom.id;
    const operation = beginMutation("cancel", roomId, true);
    if (!operation) return false;
    foregroundOperationIdRef.current = operation.id;
    let canceled = false;
    let cancelConfirmed = false;
    setBusyAction("cancel");
    setNotice("正在取消接收本轮结果…");
    setVisibleError("");
    try {
      const result = await cancelTavernRun(roomId, pendingRun.id, operation.diagnostic);
      if (
        !operationIsCurrent(operation) ||
        activeRoomIdRef.current !== roomId ||
        requestedRoomIdRef.current !== roomId
      )
        return false;
      if (!syncTurnResult(result)) return false;
      writeTavernRoomDraft(roomId, { message: "", guidance: "" });
      setGeneratingPersonaIds([]);
      canceled = true;
      cancelConfirmed = true;
      return true;
    } catch (error) {
      if (!operationIsCurrent(operation)) return false;
      setRawError(String(error));
      return false;
    } finally {
      if (operationIsCurrent(operation)) {
        const recovered = await refreshRoom(operation.diagnostic);
        if (!operationIsCurrent(operation)) return false;
        const recoveredRun = recovered?.runs.find((run) => run.id === pendingRun.id);
        if (recoveredRun?.status === "canceled") {
          cancelConfirmed = true;
          writeTavernRoomDraft(roomId, { message: "", guidance: "" });
          setGeneratingPersonaIds([]);
          setVisibleError("");
        } else if (!canceled) {
          setVisibleError(TAVERN_COPY.cancelUnconfirmed);
        }
        releaseForegroundOperation(operation);
        if (finishMutation(operation) && cancelConfirmed) {
          setNotice(TAVERN_COPY.canceled);
        }
      }
    }
  }, [
    activeRoom,
    beginMutation,
    busyAction,
    finishMutation,
    operationIsCurrent,
    refreshRoom,
    releaseForegroundOperation,
    runs,
    syncTurnResult,
    cancelTavernRun,
    writeTavernRoomDraft,
  ]);

  const handleRetry = useCallback(
    async (run: TavernRun) => {
      if (!activeRoom || !roomIsActive || runPending) return;
      const operation = beginMutation("retry", activeRoom.id);
      if (!operation) return;
      foregroundOperationIdRef.current = operation.id;
      roomRefreshVersion.current += 1;
      setGeneratingPersonaIds(
        run.speakerSteps
          .filter((step) => step.status === "failed" || step.status === "blocked")
          .map((step) => step.personaId),
      );
      setBusyAction("retry");
      setVisibleError("");
      setRawError("");
      setNotice("仅重试尚未完成的角色…");
      try {
        const result = await retryTavernRun(
          activeRoom.id,
          run.id,
          {
            idempotencyKey: makeRequestKey("retry"),
            expectedRoomRevision: activeRoom.revision,
          },
          operation.diagnostic,
        );
        if (
          !operationIsCurrent(operation) ||
          activeRoomIdRef.current !== operation.roomId ||
          requestedRoomIdRef.current !== operation.roomId
        )
          return;
        if (!syncTurnResult(result)) return;
        if (result.run.status !== "pending") releaseForegroundOperation(operation);
        setNotice(
          result.run.status === "completed"
            ? "剩余角色已完成回应"
            : RUN_STATUS_LABELS[result.run.status],
        );
        if (result.run.status === "partial" || result.run.status === "failed") {
          setVisibleError(TAVERN_COPY.retryIncomplete);
        }
        await Promise.all([
          updateRooms(operation.diagnostic),
          updateRunRecovery(operation.roomId, operation.diagnostic),
        ]);
      } catch (error) {
        if (!operationIsCurrent(operation)) return;
        recordError(
          error,
          "重试未完整返回；已重新同步已保存的结果。",
          setVisibleError,
          setRawError,
        );
        releaseForegroundOperation(operation);
        await recoverCurrentRoom(operation.diagnostic);
      } finally {
        releaseForegroundOperation(operation);
        if (finishMutation(operation)) setGeneratingPersonaIds([]);
      }
    },
    [
      activeRoom,
      beginMutation,
      finishMutation,
      operationIsCurrent,
      recoverCurrentRoom,
      releaseForegroundOperation,
      roomIsActive,
      runPending,
      syncTurnResult,
      updateRooms,
      updateRunRecovery,
      retryTavernRun,
      makeRequestKey,
    ],
  );

  return {
    handleCreateRoom,
    handleArchiveToggle,
    handleTurn,
    handleCancelRun,
    handleRetry,
  };
}
