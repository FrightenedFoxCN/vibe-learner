"use client";

import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type FormEvent,
  type KeyboardEvent,
  type RefObject,
} from "react";
import type {
  PersonaProfile,
  TavernMessage,
  TavernParticipant,
  TavernRoomDetail,
  TavernRoomSummary,
  TavernRun,
  TavernRunRecoveryChain,
  TavernTurnResult,
} from "@vibe-learner/shared";

import {
  createTavernRoom,
  cancelTavernRun,
  decodeTavernHttpError,
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
  type SceneLibraryItemPayload,
} from "../lib/api";
import { AppLink } from "../lib/app-navigation";
import { ProviderTruth } from "./provider-truth";
import {
  hasActiveTavernRun,
  authoritativeFacilitatedRecovery,
  isTavernRoomStateAtLeast,
  latestTavernMessage,
  makeTavernRequestKey,
  mergeTavernMessages,
  projectParticipantStates,
  reconcileTavernRuns,
  readActiveTavernRoomId,
  readTavernCreationDraft,
  readTavernRoomDraft,
  rememberActiveTavernRoomId,
  writeTavernCreationDraft,
  writeTavernRoomDraft,
  TAVERN_PAGE_SIZE,
  type TavernParticipantGenerationState,
} from "../lib/tavern-workspace-state";
import { MaterialIcon } from "./material-icon";
import { usePageDebugSnapshot } from "./page-debug-context";
import { RichTextMessage } from "./rich-text-message";
import { TopNav } from "./top-nav";

type BusyAction = "bootstrap" | "room" | "create" | "archive" | "turn" | "retry" | "cancel" | null;
type MutationAction = Exclude<BusyAction, "bootstrap" | "room" | null>;

interface MutationOperation {
  id: number;
  action: MutationAction;
  roomId: string;
}

const RUN_STATUS_LABELS: Record<TavernRun["status"], string> = {
  pending: "等待生成",
  completed: "已完成",
  partial: "部分角色已回应",
  failed: "本轮未完成",
  canceled: "已取消",
};

const STEP_STATUS_LABELS: Record<TavernParticipantGenerationState, string> = {
  idle: "就绪",
  pending: "等待发言",
  generating: "正在生成",
  completed: "已回应",
  failed: "回应未完成",
  blocked: "等待前序恢复",
  canceled: "已取消",
  previous_completed: "上一轮已回应",
  previous_failed: "上一轮未完成",
  previous_blocked: "上一轮待恢复",
  previous_canceled: "上一轮已取消",
};

export function TavernWorkspace() {
  const [rooms, setRooms] = useState<TavernRoomSummary[]>([]);
  const [personas, setPersonas] = useState<PersonaProfile[]>([]);
  const [scenes, setScenes] = useState<SceneLibraryItemPayload[]>([]);
  const [detail, setDetail] = useState<TavernRoomDetail | null>(null);
  const [messages, setMessages] = useState<TavernMessage[]>([]);
  const [runs, setRuns] = useState<TavernRun[]>([]);
  const [recoveryChains, setRecoveryChains] = useState<TavernRunRecoveryChain[]>([]);
  const [targetPersonaIds, setTargetPersonaIds] = useState<string[]>([]);
  const [generatingPersonaIds, setGeneratingPersonaIds] = useState<string[]>([]);
  const [showSetup, setShowSetup] = useState(false);
  const [setupFocusRequest, setSetupFocusRequest] = useState(0);
  const [busyAction, setBusyAction] = useState<BusyAction>("bootstrap");
  const [loadingOlder, setLoadingOlder] = useState(false);
  const [notice, setNotice] = useState("正在载入酒馆记录…");
  const [visibleError, setVisibleError] = useState("");
  const [rawError, setRawError] = useState("");
  const roomLoadVersion = useRef(0);
  const roomRefreshVersion = useRef(0);
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
  const setupTitleRef = useRef<HTMLInputElement>(null);

  const activeRoom = detail?.room ?? null;
  const roomIsActive = activeRoom?.status === "active";
  const roomBusy = busyAction === "room" || busyAction === "bootstrap";
  const mutationBusy = busyAction !== null && !roomBusy;
  const runPending = hasActiveTavernRun(runs);
  const latestMessage = latestTavernMessage(messages);
  const retryableRuns = useMemo(
    () => recoveryChains
      .filter((chain) => chain.recoveryAction === "retry_leaf")
      .map((chain) => chain.leafRun),
    [recoveryChains]
  );
  const facilitatedRecovery = useMemo(
    () => authoritativeFacilitatedRecovery(recoveryChains),
    [recoveryChains]
  );
  const participantStates = useMemo(
    () => projectParticipantStates(
      detail?.participants ?? [],
      runs,
      generatingPersonaIds
    ),
    [detail?.participants, generatingPersonaIds, runs]
  );

  useEffect(() => {
    if (!showSetup || setupFocusRequest === 0) return;
    const frame = window.requestAnimationFrame(() => {
      setupTitleRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
      setupTitleRef.current?.focus({ preventScroll: true });
    });
    return () => window.cancelAnimationFrame(frame);
  }, [setupFocusRequest, showSetup]);

  useEffect(() => {
    detailRef.current = detail;
  }, [detail]);

  useEffect(() => {
    runsRef.current = runs;
  }, [runs]);

  useEffect(() => {
    messagesRef.current = messages;
  }, [messages]);

  const beginMutation = useCallback(
    (action: MutationAction, roomId: string, replaceCurrent = false): MutationOperation | null => {
      if (olderLoadRoomRef.current || (mutationOperationRef.current && !replaceCurrent)) return null;
      const operation = {
        id: ++mutationOperationVersionRef.current,
        action,
        roomId,
      };
      mutationOperationRef.current = operation;
      return operation;
    },
    []
  );

  const operationIsCurrent = useCallback((operation: MutationOperation): boolean => {
    return mutationOperationRef.current?.id === operation.id;
  }, []);

  const finishMutation = useCallback((operation: MutationOperation): boolean => {
    if (!operationIsCurrent(operation)) return false;
    mutationOperationRef.current = null;
    setBusyAction((current) => current === operation.action ? null : current);
    return true;
  }, [operationIsCurrent]);

  const releaseForegroundOperation = useCallback((operation: MutationOperation) => {
    if (foregroundOperationIdRef.current !== operation.id) return;
    foregroundOperationIdRef.current = null;
    foregroundRunRef.current = "";
  }, []);

  const openRoom = useCallback(async (roomId: string) => {
    const loadVersion = ++roomLoadVersion.current;
    roomRefreshVersion.current += 1;
    requestedRoomIdRef.current = roomId;
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
    try {
      const [nextDetail, nextRuns, nextRecoveryChains] = await Promise.all([
        getTavernRoom({ roomId, tail: true, limit: TAVERN_PAGE_SIZE }),
        listTavernRuns(roomId),
        getTavernRunRecovery(roomId),
      ]);
      if (loadVersion !== roomLoadVersion.current) {
        return;
      }
      activeRoomIdRef.current = roomId;
      requestedRoomIdRef.current = roomId;
      const roomDraft = readTavernRoomDraft(roomId);
      const draftRun = roomDraft.pendingTurn
        ? nextRuns.find((run) => run.idempotencyKey === roomDraft.pendingTurn?.key)
        : undefined;
      const participantIds = new Set(nextDetail.participants.map((item) => item.personaId));
      const restoredTargetIds = roomDraft.pendingTurn?.targetPersonaIds
        .filter((id) => participantIds.has(id))
        .slice(0, 4) ?? [];
      if (draftRun) writeTavernRoomDraft(roomId, { message: "", guidance: "" });
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
            : []
      );
      setShowSetup(false);
      setNotice(
        nextDetail.room.status === "archived"
          ? "已打开归档房间（只读）"
          : hasActiveTavernRun(nextRuns)
            ? "检测到正在执行的互动，正在自动恢复"
            : "酒馆已就绪"
      );
      rememberActiveTavernRoomId(roomId);
    } catch (error) {
      if (loadVersion !== roomLoadVersion.current) {
        return;
      }
      recordError(error, "无法打开这个酒馆，请稍后重试。", setVisibleError, setRawError);
      setNotice("恢复失败");
      requestedRoomIdRef.current = activeRoomIdRef.current;
    } finally {
      if (loadVersion === roomLoadVersion.current) {
        setBusyAction(null);
      }
    }
  }, []);

  const refreshRoom = useCallback(async () => {
    if (!activeRoom?.id) {
      return;
    }
    const roomId = activeRoom.id;
    const refreshVersion = ++roomRefreshVersion.current;
    try {
      const [nextDetail, nextRuns, nextRecoveryChains, nextRooms] = await Promise.all([
        getTavernRoom({ roomId, tail: true, limit: TAVERN_PAGE_SIZE }),
        listTavernRuns(roomId),
        getTavernRunRecovery(roomId),
        listTavernRooms(),
      ]);
      if (
        activeRoomIdRef.current !== roomId ||
        requestedRoomIdRef.current !== roomId ||
        refreshVersion !== roomRefreshVersion.current
      ) {
        return;
      }
      const currentDetail = detailRef.current;
      if (currentDetail?.room.id !== roomId) return;
      const refreshedDetail = {
        ...nextDetail,
        nextBeforeSequence: currentDetail.nextBeforeSequence,
      };
      const nextMessages = mergeTavernMessages(messagesRef.current, nextDetail.messages);
      const reconciledRuns = reconcileTavernRuns(runsRef.current, nextRuns);
      detailRef.current = refreshedDetail;
      runsRef.current = reconciledRuns;
      setDetail(refreshedDetail);
      messagesRef.current = nextMessages;
      setMessages(nextMessages);
      setRuns(reconciledRuns);
      setRecoveryChains(nextRecoveryChains);
      setRooms(nextRooms);
      const latestRun = reconciledRuns[0];
      setNotice(
        nextDetail.room.status === "archived"
          ? "已同步归档房间"
          : latestRun?.status === "pending"
            ? "检测到正在执行的互动，正在自动恢复"
            : latestRun
              ? `已同步 · ${RUN_STATUS_LABELS[latestRun.status]}`
              : "酒馆已就绪"
      );
      return { detail: nextDetail, runs: reconciledRuns };
    } catch (error) {
      if (
        activeRoomIdRef.current === roomId &&
        requestedRoomIdRef.current === roomId &&
        refreshVersion === roomRefreshVersion.current
      ) {
        recordError(error, "刷新失败，当前内容仍保留在页面上。", setVisibleError, setRawError);
      }
      return null;
    }
  }, [activeRoom?.id]);

  useEffect(() => {
    let canceled = false;
    async function bootstrap() {
      setBusyAction("bootstrap");
      try {
        const [roomsResult, personasResult, scenesResult] = await Promise.allSettled([
          listTavernRooms(),
          listPersonas(),
          listSceneLibrary(),
        ]);
        if (canceled) return;
        const nextRooms = roomsResult.status === "fulfilled" ? roomsResult.value : [];
        const nextPersonas = personasResult.status === "fulfilled" ? personasResult.value : [];
        const nextScenes = scenesResult.status === "fulfilled" ? scenesResult.value : [];
        setRooms(nextRooms);
        setPersonas(nextPersonas);
        setScenes(nextScenes);
        const failures = [roomsResult, personasResult, scenesResult]
          .filter((result) => result.status === "rejected")
          .map((result) => String((result as PromiseRejectedResult).reason));
        const storedRoomId = readActiveTavernRoomId();
        const preferredRoom =
          nextRooms.find((room) => room.id === storedRoomId) ??
          nextRooms.find((room) => room.status === "active") ??
          nextRooms[0];
        if (preferredRoom) {
          await openRoom(preferredRoom.id);
          if (failures.length) {
            setRawError(failures.join("；"));
            setVisibleError("部分酒馆资料暂时无法载入；已恢复的房间仍可继续使用。");
          }
        } else {
          if (failures.length) {
            setRawError(failures.join("；"));
            setVisibleError(
              failures.length === 3
                ? friendlyTavernError(failures[0], "酒馆资料载入失败，请检查 AI 服务连接。")
                : "部分酒馆资料暂时无法载入；可用功能仍可继续使用。"
            );
          }
          setShowSetup(true);
          setNotice(failures.length ? "部分资料载入失败" : "创建一个酒馆，开始自由对话");
          setBusyAction(null);
        }
      } catch (error) {
        if (canceled) return;
        recordError(error, "酒馆资料载入失败，请检查 AI 服务连接。", setVisibleError, setRawError);
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
      requestedRoomIdRef.current = "";
      mutationOperationRef.current = null;
      mutationOperationVersionRef.current += 1;
      foregroundOperationIdRef.current = null;
    };
  }, [openRoom]);

  useEffect(() => {
    const participantIds = new Set((detail?.participants ?? []).map((item) => item.personaId));
    setTargetPersonaIds((current) => {
      const valid = current.filter((id) => participantIds.has(id)).slice(0, 4);
      if (valid.length) return valid;
      return detail?.participants[0] ? [detail.participants[0].personaId] : [];
    });
  }, [detail?.room.id, detail?.participants]);

  const updateRooms = useCallback(async () => {
    try {
      setRooms(await listTavernRooms());
    } catch (error) {
      setRawError(String(error));
    }
  }, []);

  const updateRunRecovery = useCallback(async (roomId: string) => {
    try {
      const nextChains = await getTavernRunRecovery(roomId);
      if (
        activeRoomIdRef.current === roomId &&
        requestedRoomIdRef.current === roomId
      ) {
        setRecoveryChains(nextChains);
      }
    } catch (error) {
      setRawError(String(error));
    }
  }, []);

  const syncTurnResult = useCallback((result: TavernTurnResult) => {
    if (
      activeRoomIdRef.current !== result.roomState.id ||
      requestedRoomIdRef.current !== result.roomState.id
    ) {
      return false;
    }
    const currentDetail = detailRef.current;
    if (!currentDetail || currentDetail.room.id !== result.roomState.id) return false;
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
      (
        currentRun &&
        currentRun.status !== "pending" &&
        currentRun.status !== result.run.status
      )
    ) return false;
    const appended = [
      ...(result.inputMessage ? [result.inputMessage] : []),
      ...result.generatedMessages,
    ];
    const nextMessages = mergeTavernMessages(messagesRef.current, appended);
    messagesRef.current = nextMessages;
    setMessages(nextMessages);
    const nextRuns = [result.run, ...runsRef.current.filter((run) => run.id !== result.run.id)];
    const nextDetail = {
      ...currentDetail,
      room: {
        ...currentDetail.room,
        status: result.roomState.status,
        revision: result.roomState.revision,
        lastSequence: result.roomState.lastSequence,
        updatedAt: result.roomState.updatedAt,
      },
      messageCount: Math.max(currentDetail.messageCount, result.roomState.lastSequence),
    };
    runsRef.current = nextRuns;
    detailRef.current = nextDetail;
    setRuns(nextRuns);
    setDetail(nextDetail);
    return true;
  }, []);

  const recoverCurrentRoom = useCallback(async () => {
    await refreshRoom();
  }, [refreshRoom]);

  const resumePendingRun = useCallback(async (run: TavernRun) => {
    const roomId = run.roomId;
    if (
      !roomId ||
      resumeRunRef.current === run.id ||
      activeRoomIdRef.current !== roomId ||
      requestedRoomIdRef.current !== roomId
    ) {
      return;
    }
    resumeRunRef.current = run.id;
    try {
      const result = await resumeTavernRun(roomId, run.id);
      if (
        activeRoomIdRef.current !== roomId ||
        requestedRoomIdRef.current !== roomId
      ) return;
      syncTurnResult(result);
      resumeAttemptsRef.current.delete(run.id);
      setNotice(result.run.status === "completed" ? "中断的互动已恢复" : RUN_STATUS_LABELS[result.run.status]);
      setVisibleError("");
    } catch (error) {
      if (decodeTavernHttpError(error)?.code === "tavern_run_in_progress") {
        resumeAttemptsRef.current.set(
          run.id,
          Math.min(3, (resumeAttemptsRef.current.get(run.id) ?? 0) + 1)
        );
      } else if (
        activeRoomIdRef.current === roomId &&
        requestedRoomIdRef.current === roomId
      ) {
        recordError(error, "自动恢复暂时失败；页面会继续保留已提交消息。", setVisibleError, setRawError);
      }
    } finally {
      if (resumeRunRef.current === run.id) resumeRunRef.current = "";
      if (
        activeRoomIdRef.current === roomId &&
        requestedRoomIdRef.current === roomId
      ) await refreshRoom();
    }
  }, [refreshRoom, syncTurnResult]);

  useEffect(() => {
    const pendingRun = runs.find((run) => run.status === "pending");
    if (!activeRoom || !pendingRun || pendingRun.id === foregroundRunRef.current) return;
    const attempt = resumeAttemptsRef.current.get(pendingRun.id) ?? 0;
    const timer = window.setTimeout(
      () => void resumePendingRun(pendingRun),
      Math.min(10000, 2500 * (2 ** attempt))
    );
    return () => window.clearTimeout(timer);
  }, [activeRoom, resumePendingRun, runs]);

  useEffect(() => {
    if (!activeRoom || (busyAction !== "turn" && busyAction !== "retry")) return;
    const roomId = activeRoom.id;
    const operationId = foregroundOperationIdRef.current;
    if (operationId === null) return;
    let disposed = false;
    const discoverPendingRun = async () => {
      const pollVersion = ++runPollVersionRef.current;
      try {
        const nextRuns = await listTavernRuns(roomId);
        if (
          disposed ||
          pollVersion !== runPollVersionRef.current ||
          foregroundOperationIdRef.current !== operationId ||
          mutationOperationRef.current?.id !== operationId ||
          activeRoomIdRef.current !== roomId ||
          requestedRoomIdRef.current !== roomId
        ) return;
        const reconciledRuns = reconcileTavernRuns(runsRef.current, nextRuns);
        const pending = reconciledRuns.find((run) => run.status === "pending");
        if (pending) foregroundRunRef.current = pending.id;
        runsRef.current = reconciledRuns;
        setRuns(reconciledRuns);
      } catch (error) {
        if (
          !disposed &&
          activeRoomIdRef.current === roomId &&
          requestedRoomIdRef.current === roomId
        ) setRawError(String(error));
      }
    };
    void discoverPendingRun();
    const timer = window.setInterval(() => void discoverPendingRun(), 900);
    return () => {
      disposed = true;
      runPollVersionRef.current += 1;
      window.clearInterval(timer);
    };
  }, [activeRoom, busyAction]);

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
      const sceneProfile = scenes.find((scene) => scene.sceneId === input.sceneId)?.sceneProfile;
      const savedCreation = readTavernCreationDraft();
      const sameCreation = savedCreation &&
        savedCreation.title === input.title &&
        savedCreation.sceneId === input.sceneId &&
        savedCreation.openingPrompt === input.openingPrompt &&
        savedCreation.personaIds.join("\u0000") === input.personaIds.join("\u0000");
      const creationDraft = sameCreation
        ? savedCreation
        : {
            ...input,
            key: makeTavernRequestKey("room"),
          };
      writeTavernCreationDraft(creationDraft);
      setBusyAction("create");
      setVisibleError("");
      setRawError("");
      setNotice("正在创建酒馆…");
      try {
        const created = await createTavernRoom({
          title: input.title,
          personaIds: input.personaIds,
          sceneProfile,
          openingPrompt: input.openingPrompt,
          idempotencyKey: creationDraft.key,
        });
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
        setTargetPersonaIds(created.participants[0] ? [created.participants[0].personaId] : []);
        setShowSetup(false);
        setNotice("酒馆已创建，可以开始对话");
        rememberActiveTavernRoomId(created.room.id);
        writeTavernCreationDraft(null);
        await updateRooms();
      } catch (error) {
        if (!operationIsCurrent(operation)) return;
        recordError(error, "创建失败，请检查标题、人格与服务连接。", setVisibleError, setRawError);
        setNotice("创建失败");
      } finally {
        finishMutation(operation);
      }
    },
    [beginMutation, finishMutation, operationIsCurrent, scenes, updateRooms]
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
      const updated = await updateTavernRoom(roomId, {
        status: nextStatus,
        expectedRoomRevision: activeRoom.revision,
      });
      if (
        !operationIsCurrent(operation) ||
        activeRoomIdRef.current !== roomId ||
        requestedRoomIdRef.current !== roomId
      ) return;
      const currentDetail = detailRef.current;
      if (
        !currentDetail ||
        currentDetail.room.id !== roomId ||
        !isTavernRoomStateAtLeast(updated.room, currentDetail.room)
      ) return;
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
      setNotice(nextStatus === "archived" ? "酒馆已归档，历史仍可阅读" : "酒馆已恢复使用");
      await updateRooms();
    } catch (error) {
      if (!operationIsCurrent(operation)) return;
      recordError(error, "房间状态未更新；页面将重新同步最新版本。", setVisibleError, setRawError);
      await recoverCurrentRoom();
    } finally {
      finishMutation(operation);
    }
  }, [activeRoom, beginMutation, finishMutation, operationIsCurrent, recoverCurrentRoom, runPending, updateRooms]);

  const handleTurn = useCallback(
    async (input: { kind: "user_message"; content: string } | { kind: "continue"; anchorMessageId: string }, guidance: string) => {
      if (
        !activeRoom ||
        !roomIsActive ||
        targetPersonaIds.length < 1 ||
        runPending
      ) return false;
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
      setNotice(targetPersonaIds.length === 1 ? "角色正在回应…" : "角色将按名册顺序依次回应…");
      const savedDraft = readTavernRoomDraft(roomId);
      const sameTargetSet = savedDraft.pendingTurn
        ? [...savedDraft.pendingTurn.targetPersonaIds].sort().join("\u0000")
          === [...targetPersonaIds].sort().join("\u0000")
        : false;
      const matchingPending = input.kind === "user_message"
        && savedDraft.pendingTurn?.content === input.content
        && savedDraft.pendingTurn.guidance === guidance
        && sameTargetSet
          ? savedDraft.pendingTurn
          : undefined;
      const requestKey = matchingPending?.key ?? makeTavernRequestKey("turn");
      const expectedRoomRevision = matchingPending?.expectedRoomRevision ?? activeRoom.revision;
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
        const result = await runTavernTurn(roomId, {
          input,
          mode: targetPersonaIds.length === 1 ? "direct" : "facilitated",
          targetPersonaIds,
          guidance,
          idempotencyKey: requestKey,
          expectedRoomRevision,
        });
        if (
          !operationIsCurrent(operation) ||
          activeRoomIdRef.current !== roomId ||
          requestedRoomIdRef.current !== roomId
        ) return false;
        if (!syncTurnResult(result)) return false;
        if (input.kind === "user_message" && result.inputMessage) {
          writeTavernRoomDraft(roomId, { message: "", guidance: "" });
        }
        setNotice(
          result.run.status === "completed"
            ? "本轮互动已完成"
            : RUN_STATUS_LABELS[result.run.status]
        );
        if (result.run.status === "partial" || result.run.status === "failed") {
          setVisibleError(
            result.run.status === "partial"
              ? "部分角色回应未完成；已保存的回应不会重复生成，可在下方仅恢复未完成角色。"
              : "本轮角色回应未完成；服务端已保存失败证据，可从恢复入口再次尝试。"
          );
        }
        await Promise.all([updateRooms(), updateRunRecovery(roomId)]);
        return result.inputMessage !== null || input.kind === "continue";
      } catch (error) {
        if (!operationIsCurrent(operation)) return false;
        const recovered = await refreshRoom();
        if (!operationIsCurrent(operation)) return false;
        const recoveredRun = recovered?.runs.find((run) => run.idempotencyKey === requestKey);
        if (recoveredRun && input.kind === "user_message") {
          writeTavernRoomDraft(roomId, { message: "", guidance: "" });
        }
        if (recoveredRun?.status === "canceled") {
          setVisibleError("");
          setNotice("已取消接收本轮结果");
        } else {
          recordError(error, "本轮未完整返回；已尝试恢复服务端保存的消息与可靠性记录。", setVisibleError, setRawError);
          setNotice(recoveredRun ? RUN_STATUS_LABELS[recoveredRun.status] : "本轮状态仍待确认");
        }
        return Boolean(recoveredRun);
      } finally {
        releaseForegroundOperation(operation);
        if (finishMutation(operation)) setGeneratingPersonaIds([]);
      }
    },
    [activeRoom, beginMutation, finishMutation, operationIsCurrent, refreshRoom, releaseForegroundOperation, roomIsActive, runPending, syncTurnResult, targetPersonaIds, updateRooms, updateRunRecovery]
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
      const result = await cancelTavernRun(roomId, pendingRun.id);
      if (
        !operationIsCurrent(operation) ||
        activeRoomIdRef.current !== roomId ||
        requestedRoomIdRef.current !== roomId
      ) return false;
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
        const recovered = await refreshRoom();
        const recoveredRun = recovered?.runs.find((run) => run.id === pendingRun.id);
        if (recoveredRun?.status === "canceled") {
          cancelConfirmed = true;
          writeTavernRoomDraft(roomId, { message: "", guidance: "" });
          setGeneratingPersonaIds([]);
          setVisibleError("");
        } else if (!canceled) {
          setVisibleError(
            "取消响应未能确认；已重新同步服务器状态，请按当前状态决定是否重试。"
          );
        }
        releaseForegroundOperation(operation);
        if (finishMutation(operation) && cancelConfirmed) {
          setNotice("已取消接收本轮结果；已发出的模型请求可能仍运行到超时");
        }
      }
    }
  }, [activeRoom, beginMutation, busyAction, finishMutation, operationIsCurrent, refreshRoom, releaseForegroundOperation, runs, syncTurnResult]);

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
          .map((step) => step.personaId)
      );
      setBusyAction("retry");
      setVisibleError("");
      setRawError("");
      setNotice("仅重试尚未完成的角色…");
      try {
        const result = await retryTavernRun(activeRoom.id, run.id, {
          idempotencyKey: makeTavernRequestKey("retry"),
          expectedRoomRevision: activeRoom.revision,
        });
        if (
          !operationIsCurrent(operation) ||
          activeRoomIdRef.current !== operation.roomId ||
          requestedRoomIdRef.current !== operation.roomId
        ) return;
        if (!syncTurnResult(result)) return;
        setNotice(result.run.status === "completed" ? "剩余角色已完成回应" : RUN_STATUS_LABELS[result.run.status]);
        if (result.run.status === "partial" || result.run.status === "failed") {
          setVisibleError("恢复运行仍有角色未完成；已完成回应不会重复生成，可继续恢复当前叶节点。");
        }
        await Promise.all([updateRooms(), updateRunRecovery(operation.roomId)]);
      } catch (error) {
        if (!operationIsCurrent(operation)) return;
        recordError(error, "重试未完整返回；已重新同步已保存的结果。", setVisibleError, setRawError);
        await recoverCurrentRoom();
      } finally {
        releaseForegroundOperation(operation);
        if (finishMutation(operation)) setGeneratingPersonaIds([]);
      }
    },
    [activeRoom, beginMutation, finishMutation, operationIsCurrent, recoverCurrentRoom, releaseForegroundOperation, roomIsActive, runPending, syncTurnResult, updateRooms, updateRunRecovery]
  );

  const handleLoadOlder = useCallback(async () => {
    if (
      !activeRoom ||
      detail?.nextBeforeSequence == null ||
      mutationOperationRef.current ||
      runPending
    ) return false;
    const roomId = activeRoom.id;
    const firstLoadedSequence = messages[0]?.sequence ?? Number.POSITIVE_INFINITY;
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
      if (
        activeRoomIdRef.current !== roomId ||
        requestedRoomIdRef.current !== roomId ||
        olderLoadRoomRef.current !== roomId
      ) return false;
      const nextMessages = mergeTavernMessages(messagesRef.current, previous.messages);
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
      return previous.messages.some((message) => message.sequence < firstLoadedSequence);
    } catch (error) {
      if (olderLoadRoomRef.current === roomId) {
        recordError(error, "更早的消息暂时无法载入。", setVisibleError, setRawError);
      }
      return false;
    } finally {
      if (olderLoadRoomRef.current === roomId) {
        olderLoadRoomRef.current = null;
        setLoadingOlder(false);
      }
    }
  }, [activeRoom, detail?.nextBeforeSequence, messages, runPending]);

  const handleTargetToggle = useCallback((personaId: string) => {
    setTargetPersonaIds((current) => {
      if (current.includes(personaId)) {
        return current.filter((id) => id !== personaId);
      }
      if (current.length >= 4) {
        setVisibleError("一次多人互动最多选择 4 位角色。你可以在下一轮更换目标。");
        return current;
      }
      setVisibleError("");
      return [...current, personaId];
    });
  }, []);

  const debugSnapshot = useMemo(
    () => ({
      title: "Tavern Workspace 调试面板",
      subtitle: "原始房间、消息、run 与 Harness evidence 仅在调试层查看。",
      error: rawError,
      summary: [
        { label: "房间", value: activeRoom?.title || "-" },
        { label: "Revision", value: String(activeRoom?.revision ?? 0) },
        { label: "Last sequence", value: String(activeRoom?.lastSequence ?? 0) },
        { label: "已载入消息", value: String(messages.length) },
        { label: "最近 runs", value: String(runs.length) },
      ],
      details: [
        { title: "当前房间", value: detail },
        { title: "已载入消息", value: messages },
        { title: "最近 runs / traces", value: runs },
      ],
    }),
    [activeRoom, detail, messages, rawError, runs]
  );
  usePageDebugSnapshot(debugSnapshot);

  return (
    <main className="with-app-nav tavern-page">
      <TopNav currentPath="/tavern" />

      <TavernHeader
        room={activeRoom}
        notice={notice}
        busy={roomBusy || mutationBusy || loadingOlder}
        runPending={runPending}
        onCreate={() => {
          setShowSetup(true);
          setSetupFocusRequest((current) => current + 1);
        }}
        onRefresh={() => void refreshRoom()}
        onArchiveToggle={() => void handleArchiveToggle()}
      />

      <ProviderTruth scope="tavern" />

      {visibleError ? (
        <div className="tavern-alert" role="alert">
          {visibleError}
        </div>
      ) : null}

      <div className={`tavern-workspace-grid ${activeRoom ? "has-room" : "empty-room"}`}>
        <div className="tavern-left-rail">
          <TavernSessionPanel
            rooms={rooms}
            activeRoomId={activeRoom?.id ?? ""}
            busy={busyAction !== null}
            onOpen={(roomId) => void openRoom(roomId)}
          />
          {showSetup ? (
            <TavernSetupPanel
              personas={personas}
              scenes={scenes}
              busy={busyAction === "create"}
              titleInputRef={setupTitleRef}
              onCancel={activeRoom ? () => setShowSetup(false) : undefined}
              onCreate={handleCreateRoom}
            />
          ) : null}
        </div>

        {activeRoom ? (
          <div className="tavern-right-rail">
            <InteractionComposer
              key={activeRoom.id}
              roomId={activeRoom.id}
              roomAvailable
              roomActive={Boolean(roomIsActive)}
              participants={detail?.participants ?? []}
              selectedIds={targetPersonaIds}
              latestMessage={latestMessage}
              recovery={facilitatedRecovery}
              busy={busyAction === "turn" || busyAction === "retry" || busyAction === "cancel" || runPending || loadingOlder}
              recoveryBusy={mutationBusy || runPending || loadingOlder}
              retrying={busyAction === "retry"}
              canCancel={runPending}
              canceling={busyAction === "cancel"}
              onTurn={handleTurn}
              onCancel={handleCancelRun}
              onRetry={(run) => void handleRetry(run)}
            />
            <ParticipantRoster
              states={participantStates}
              selectedIds={targetPersonaIds}
              disabled={!roomIsActive || mutationBusy || runPending || loadingOlder}
              onToggle={handleTargetToggle}
            />
            <ReliabilityDetails
              runs={runs}
              retryableRuns={retryableRuns}
              recoveryChains={recoveryChains}
              participants={detail?.participants ?? []}
              roomActive={Boolean(roomIsActive)}
              busy={mutationBusy || runPending || loadingOlder}
              onRetry={(run) => void handleRetry(run)}
            />
          </div>
        ) : null}

        <TavernConversationPanel
          key={activeRoom?.id ?? "empty-room"}
          room={activeRoom}
          participants={detail?.participants ?? []}
          messages={messages}
          messageCount={detail?.messageCount ?? 0}
          hasOlder={detail?.nextBeforeSequence != null}
          loading={roomBusy}
          loadingOlder={loadingOlder}
          olderDisabled={roomBusy || mutationBusy || runPending}
          onLoadOlder={handleLoadOlder}
        />
      </div>
    </main>
  );
}

function TavernHeader({
  room,
  notice,
  busy,
  runPending,
  onCreate,
  onRefresh,
  onArchiveToggle,
}: {
  room: TavernRoomDetail["room"] | null;
  notice: string;
  busy: boolean;
  runPending: boolean;
  onCreate: () => void;
  onRefresh: () => void;
  onArchiveToggle: () => void;
}) {
  return (
    <header className="tavern-header">
      <div>
        <p className="tavern-eyebrow">Tavern Workspace</p>
        <h1>{room?.title || "角色酒馆"}</h1>
        <p className="tavern-header-status" aria-live="polite">
          <span
            className={
              !room
                ? "tavern-status-dot empty"
                : room.status === "archived"
                  ? "tavern-status-dot archived"
                  : "tavern-status-dot"
            }
            aria-hidden="true"
          />
          {busy ? "处理中 · " : ""}{notice}
          {room ? ` · revision ${room.revision}` : ""}
        </p>
      </div>
      <div className="tavern-header-actions">
        {room ? (
          <>
            <button type="button" className="tavern-button secondary" onClick={onRefresh} disabled={busy}>
              <MaterialIcon name="refresh" size={16} />刷新
            </button>
            <button type="button" className="tavern-button secondary" onClick={onArchiveToggle} disabled={busy || runPending}>
              {room.status === "active" ? "归档" : "恢复使用"}
            </button>
          </>
        ) : null}
        <button type="button" className="tavern-button primary" onClick={onCreate} disabled={busy}>
          <MaterialIcon name="add" size={16} />新建酒馆
        </button>
      </div>
    </header>
  );
}

function TavernSessionPanel({
  rooms,
  activeRoomId,
  busy,
  onOpen,
}: {
  rooms: TavernRoomSummary[];
  activeRoomId: string;
  busy: boolean;
  onOpen: (roomId: string) => void;
}) {
  return (
    <section className="tavern-panel tavern-session-panel" aria-labelledby="tavern-session-title">
      <div className="tavern-panel-heading">
        <div>
          <p className="tavern-kicker">Tavern Session Panel</p>
          <h2 id="tavern-session-title">最近酒馆</h2>
        </div>
        <span className="tavern-count">{rooms.length}</span>
      </div>
      {rooms.length ? (
        <div className="tavern-room-list">
          {rooms.map((room) => (
            <button
              type="button"
              key={room.id}
              className={`tavern-room-item${room.id === activeRoomId ? " active" : ""}`}
              onClick={() => onOpen(room.id)}
              disabled={busy}
              aria-pressed={room.id === activeRoomId}
            >
              <span className="tavern-room-item-title">{room.title}</span>
              <span className="tavern-room-item-meta">
                {room.participantNames.map((name) => name || "未命名角色").join(" · ") || "无角色"}
              </span>
              <span className="tavern-room-item-meta">
                {room.messageCount} 条消息 · {room.status === "archived" ? "已归档" : formatShortTime(room.updatedAt)}
              </span>
            </button>
          ))}
        </div>
      ) : (
        <p className="tavern-empty-copy">还没有房间。选择 1–6 位人格即可创建。</p>
      )}
    </section>
  );
}

function TavernSetupPanel({
  personas,
  scenes,
  busy,
  titleInputRef,
  onCancel,
  onCreate,
}: {
  personas: PersonaProfile[];
  scenes: SceneLibraryItemPayload[];
  busy: boolean;
  titleInputRef: RefObject<HTMLInputElement | null>;
  onCancel?: () => void;
  onCreate: (input: { title: string; personaIds: string[]; sceneId: string; openingPrompt: string }) => Promise<void>;
}) {
  const initialCreationDraft = readTavernCreationDraft();
  const [title, setTitle] = useState(initialCreationDraft?.title ?? "新酒馆");
  const [selectedIds, setSelectedIds] = useState(initialCreationDraft?.personaIds ?? []);
  const [sceneId, setSceneId] = useState(initialCreationDraft?.sceneId ?? "");
  const [openingPrompt, setOpeningPrompt] = useState(initialCreationDraft?.openingPrompt ?? "");
  const [validation, setValidation] = useState("");
  const usableScenes = scenes.filter((scene) => Boolean(scene.sceneProfile));

  const togglePersona = (personaId: string) => {
    setSelectedIds((current) => {
      if (current.includes(personaId)) return current.filter((id) => id !== personaId);
      if (current.length >= 6) {
        setValidation("每个酒馆最多加入 6 位人格。");
        return current;
      }
      setValidation("");
      return [...current, personaId];
    });
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!title.trim()) {
      setValidation("请填写酒馆标题。");
      return;
    }
    if (selectedIds.length < 1 || selectedIds.length > 6) {
      setValidation("请选择 1–6 位人格角色。");
      return;
    }
    setValidation("");
    await onCreate({
      title: title.trim(),
      personaIds: selectedIds,
      sceneId,
      openingPrompt: openingPrompt.trim(),
    });
  };

  return (
    <section className="tavern-panel tavern-setup-panel" aria-labelledby="tavern-setup-title">
      <div className="tavern-panel-heading">
        <div>
          <p className="tavern-kicker">Tavern Setup Panel</p>
          <h2 id="tavern-setup-title">创建房间</h2>
        </div>
        {onCancel ? <button type="button" className="tavern-text-button" onClick={onCancel}>收起</button> : null}
      </div>
      <form
        className="tavern-setup-form"
        onSubmit={(event) => void submit(event)}
        aria-busy={busy}
        aria-describedby={validation ? "tavern-setup-error" : undefined}
      >
        <label>
          <span>标题</span>
          <input ref={titleInputRef} value={title} onChange={(event) => setTitle(event.target.value)} maxLength={80} disabled={busy} />
        </label>
        <fieldset>
          <legend>人格角色 <span>{selectedIds.length}/6</span></legend>
          {personas.length ? (
            <div className="tavern-persona-options">
              {personas.map((persona) => (
                <label key={persona.id} className={selectedIds.includes(persona.id) ? "selected" : ""}>
                  <input
                    type="checkbox"
                    checked={selectedIds.includes(persona.id)}
                    onChange={() => togglePersona(persona.id)}
                    disabled={busy}
                  />
                  <span><strong>{persona.name || "未命名角色"}</strong><small>{persona.relationship || persona.summary}</small></span>
                </label>
              ))}
            </div>
          ) : (
            <p className="tavern-empty-copy">人格库为空。先前往 <AppLink path="/persona-spectrum" className="tavern-inline-link">人格色谱</AppLink> 创建角色。</p>
          )}
        </fieldset>
        <label>
          <span>场景（可选）</span>
          <select value={sceneId} onChange={(event) => setSceneId(event.target.value)} disabled={busy}>
            <option value="">不使用场景</option>
            {usableScenes.map((scene) => (
              <option key={scene.sceneId} value={scene.sceneId}>{scene.sceneName || scene.sceneProfile?.title}</option>
            ))}
          </select>
        </label>
        <label>
          <span>开场白（可选）</span>
          <textarea
            value={openingPrompt}
            onChange={(event) => setOpeningPrompt(event.target.value)}
            maxLength={2000}
            rows={3}
            placeholder="描述初始情境；它会作为可见的导演消息保存。"
            disabled={busy}
          />
        </label>
        {validation ? <p id="tavern-setup-error" className="tavern-field-error" role="alert">{validation}</p> : null}
        <button type="submit" className="tavern-button primary full" disabled={busy || !personas.length}>
          {busy ? "正在创建…" : "创建并进入"}
        </button>
      </form>
    </section>
  );
}

function TavernConversationPanel({
  room,
  participants,
  messages,
  messageCount,
  hasOlder,
  loading,
  loadingOlder,
  olderDisabled,
  onLoadOlder,
}: {
  room: TavernRoomDetail["room"] | null;
  participants: TavernParticipant[];
  messages: TavernMessage[];
  messageCount: number;
  hasOlder: boolean;
  loading: boolean;
  loadingOlder: boolean;
  olderDisabled: boolean;
  onLoadOlder: () => Promise<boolean>;
}) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const pendingOlderAnchorRef = useRef<{
    height: number;
    top: number;
    firstSequence: number;
    viewportOffset: number;
  } | null>(null);
  const previousLatestSequence = useRef(0);
  const latestSequence = messages[messages.length - 1]?.sequence ?? 0;
  const names = useMemo(
    () => new Map(participants.map((participant) => [
      participant.personaId,
      participant.displayName || "未命名角色",
    ])),
    [participants]
  );

  useEffect(() => {
    if (latestSequence > previousLatestSequence.current) {
      if (pendingOlderAnchorRef.current) return;
      const scrollBox = scrollRef.current;
      if (scrollBox) scrollBox.scrollTop = scrollBox.scrollHeight;
      previousLatestSequence.current = latestSequence;
    }
  }, [latestSequence]);

  useLayoutEffect(() => {
    const anchor = pendingOlderAnchorRef.current;
    const scrollBox = scrollRef.current;
    const firstSequence = messages[0]?.sequence;
    if (
      anchor &&
      scrollBox &&
      firstSequence !== undefined &&
      firstSequence < anchor.firstSequence
    ) {
      const anchorElement = scrollBox.querySelector<HTMLElement>(
        `[data-tavern-sequence="${anchor.firstSequence}"]`
      );
      const priorBehavior = scrollBox.style.scrollBehavior;
      scrollBox.style.scrollBehavior = "auto";
      if (anchorElement) {
        const currentViewportOffset =
          anchorElement.getBoundingClientRect().top -
          scrollBox.getBoundingClientRect().top;
        scrollBox.scrollTop += currentViewportOffset - anchor.viewportOffset;
      } else {
        scrollBox.scrollTop = anchor.top + scrollBox.scrollHeight - anchor.height;
      }
      scrollBox.style.scrollBehavior = priorBehavior;
      pendingOlderAnchorRef.current = null;
    }
  }, [messages.length, messages[0]?.sequence]);

  const loadOlder = async () => {
    const scrollBox = scrollRef.current;
    const firstSequence = messages[0]?.sequence ?? 0;
    const firstMessage = scrollBox?.querySelector<HTMLElement>(
      `[data-tavern-sequence="${firstSequence}"]`
    );
    const viewportOffset = firstMessage && scrollBox
      ? firstMessage.getBoundingClientRect().top - scrollBox.getBoundingClientRect().top
      : 0;
    pendingOlderAnchorRef.current = scrollBox
      ? {
          height: scrollBox.scrollHeight,
          top: scrollBox.scrollTop,
          firstSequence,
          viewportOffset,
        }
      : null;
    if (!await onLoadOlder()) pendingOlderAnchorRef.current = null;
  };

  return (
    <section className="tavern-panel tavern-conversation-panel" aria-labelledby="tavern-conversation-title">
      <div className="tavern-panel-heading conversation-heading">
        <div>
          <p className="tavern-kicker">Tavern Conversation Panel</p>
          <h2 id="tavern-conversation-title">对话记录</h2>
        </div>
        <span className="tavern-count">{messages.length}/{messageCount}</span>
      </div>
      <p className="sr-only" aria-live="polite">
        {loadingOlder ? "正在载入更早消息" : latestSequence ? `最新消息序号 ${latestSequence}` : ""}
      </p>
      <div
        className="tavern-transcript"
        ref={scrollRef}
        aria-label="酒馆对话记录"
        aria-busy={loading || loadingOlder}
      >
        {hasOlder ? (
          <button type="button" className="tavern-load-older" onClick={() => void loadOlder()} disabled={loadingOlder || olderDisabled}>
            {loadingOlder ? "载入中…" : "载入更早消息"}
          </button>
        ) : messages.length ? <p className="tavern-history-start">已到达对话起点</p> : null}

        {loading && !messages.length ? (
          <div className="tavern-empty-state"><MaterialIcon name="hourglass_top" size={24} /><p>正在恢复最近对话…</p></div>
        ) : !room ? (
          <div className="tavern-empty-state"><MaterialIcon name="forum" size={28} /><p>先创建或打开一个酒馆，然后开始对话。</p></div>
        ) : !messages.length ? (
          <div className="tavern-empty-state"><MaterialIcon name="forum" size={28} /><p>这里还很安静。选择角色并发送第一句话。</p></div>
        ) : (
          messages.map((message) => (
            <article
              key={message.id}
              className={`tavern-message ${message.authorKind}`}
              data-tavern-sequence={message.sequence}
            >
              <div className="tavern-message-meta">
                <strong>{messageAuthorLabel(message)}</strong>
                <time dateTime={message.createdAt}>#{message.sequence} · {formatShortTime(message.createdAt)}</time>
              </div>
              <div className="tavern-message-body">
                <RichTextMessage content={message.content} />
                {message.action ? <p className="tavern-message-action">动作：{message.action}</p> : null}
                {message.addressedParticipantIds.length ? (
                  <p className="tavern-message-addressed">
                    回应给 {message.addressedParticipantIds.map((id) => names.get(id) || "房间角色").join("、")}
                  </p>
                ) : null}
              </div>
            </article>
          ))
        )}
      </div>
    </section>
  );
}

function ParticipantRoster({
  states,
  selectedIds,
  disabled,
  onToggle,
}: {
  states: ReturnType<typeof projectParticipantStates>;
  selectedIds: string[];
  disabled: boolean;
  onToggle: (personaId: string) => void;
}) {
  return (
    <section className="tavern-panel participant-roster" aria-labelledby="participant-roster-title">
      <div className="tavern-panel-heading">
        <div>
          <p className="tavern-kicker">Participant Roster</p>
          <h2 id="participant-roster-title">角色与目标</h2>
        </div>
        <span className="tavern-count">{selectedIds.length} 已选</span>
      </div>
      {states.length ? (
        <div className="tavern-roster-list">
          {states.map(({ participant, state }) => {
            const selected = selectedIds.includes(participant.personaId);
            const displayName = participant.displayName || "未命名角色";
            const stateLabel = selected && state === "idle"
              ? "本轮目标"
              : STEP_STATUS_LABELS[state];
            return (
              <label key={participant.personaId} className={`tavern-roster-item${selected ? " selected" : ""}`}>
                <input
                  type="checkbox"
                  checked={selected}
                  disabled={disabled}
                  onChange={() => onToggle(participant.personaId)}
                />
                <span className="tavern-avatar" aria-hidden="true">{displayName.slice(0, 1)}</span>
                <span className="tavern-roster-copy">
                  <strong>{displayName}</strong>
                  <small className={`state-${state}`}>{stateLabel}</small>
                </span>
              </label>
            );
          })}
        </div>
      ) : <p className="tavern-empty-copy">打开房间后在这里选择本轮发言角色。</p>}
      <p className="tavern-panel-footnote">选 1 位为单聊；选 2–4 位时，服务器按名册顺序引导讨论。</p>
    </section>
  );
}

function InteractionComposer({
  roomId,
  roomAvailable,
  roomActive,
  participants,
  selectedIds,
  latestMessage,
  recovery,
  busy,
  recoveryBusy,
  retrying,
  canCancel,
  canceling,
  onTurn,
  onCancel,
  onRetry,
}: {
  roomId: string;
  roomAvailable: boolean;
  roomActive: boolean;
  participants: TavernParticipant[];
  selectedIds: string[];
  latestMessage: TavernMessage | null;
  recovery: ReturnType<typeof authoritativeFacilitatedRecovery>;
  busy: boolean;
  recoveryBusy: boolean;
  retrying: boolean;
  canCancel: boolean;
  canceling: boolean;
  onTurn: (
    input: { kind: "user_message"; content: string } | { kind: "continue"; anchorMessageId: string },
    guidance: string
  ) => Promise<boolean>;
  onCancel: () => Promise<boolean>;
  onRetry: (run: TavernRun) => void;
}) {
  const initialDraft = readTavernRoomDraft(roomId);
  const [message, setMessage] = useState(initialDraft.message);
  const [guidance, setGuidance] = useState(initialDraft.guidance);
  const composingRef = useRef(false);
  const suppressCompositionEnterRef = useRef(false);
  const namesById = useMemo(
    () => new Map(participants.map((participant) => [
      participant.personaId,
      participant.displayName || "未命名角色",
    ])),
    [participants]
  );
  const recipientNames = [...participants]
    .sort((left, right) => left.displayOrder - right.displayOrder)
    .filter((participant) => selectedIds.includes(participant.personaId))
    .map((participant) => namesById.get(participant.personaId))
    .filter(Boolean);
  const unfinishedNames = recovery?.unfinishedPersonaIds
    .map((personaId) => namesById.get(personaId) || "房间角色") ?? [];
  const showRecovery = Boolean(roomActive && recovery && (!canCancel || retrying));
  const canRun = roomActive && selectedIds.length >= 1 && selectedIds.length <= 4 && !busy;

  useEffect(() => {
    const current = readTavernRoomDraft(roomId);
    writeTavernRoomDraft(roomId, {
      message,
      guidance,
      pendingTurn: current.pendingTurn,
    });
  }, [guidance, message, roomId]);

  const sendMessage = async () => {
    const content = message.trim();
    if (!content || !canRun) return;
    const completed = await onTurn({ kind: "user_message", content }, guidance.trim());
    if (completed) {
      setMessage("");
      setGuidance("");
    }
  };

  const continueConversation = async () => {
    if (!latestMessage || !canRun) return;
    const completed = await onTurn({ kind: "continue", anchorMessageId: latestMessage.id }, guidance.trim());
    if (completed) setGuidance("");
  };

  const cancelConversation = async () => {
    if (!canCancel || canceling) return;
    if (await onCancel()) {
      setMessage("");
      setGuidance("");
    }
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key !== "Enter" || event.shiftKey) return;
    if (
      composingRef.current ||
      event.nativeEvent.isComposing ||
      event.nativeEvent.keyCode === 229 ||
      suppressCompositionEnterRef.current
    ) {
      suppressCompositionEnterRef.current = false;
      return;
    }
    event.preventDefault();
    void sendMessage();
  };

  return (
    <section className="tavern-panel interaction-composer" aria-labelledby="interaction-composer-title">
      <div className="tavern-panel-heading">
        <div>
          <p className="tavern-kicker">Interaction Composer</p>
          <h2 id="interaction-composer-title">发起互动</h2>
        </div>
      </div>
      <p className="tavern-recipient-preview">
        {recipientNames.length ? `本轮回应：${recipientNames.join(" → ")}` : "请先选择至少一位角色"}
      </p>
      {showRecovery && recovery ? (
        <div className="tavern-recovery-callout" role="status" aria-live="polite">
          <div>
            <strong>
              {recovery.chainStatus === "recovered"
                ? "上次未完成的多人互动已由重试恢复"
                : "上次多人互动还有角色未回应"}
            </strong>
            {recovery.chainStatus === "recovered" ? (
              <p>{recovery.completedCount}/{recovery.totalCount} 位已完成回应，旧的部分结果不会再次暴露为可重试操作。</p>
            ) : (
              <p>
                {recovery.completedCount}/{recovery.totalCount} 位已回应；
                {unfinishedNames.join("、")} 尚未完成。已保存的回应不会重复生成。
              </p>
            )}
          </div>
          {recovery.chainStatus === "recoverable" ? (
            <button
              type="button"
              className="tavern-button secondary full"
              onClick={() => onRetry(recovery.run)}
              disabled={recoveryBusy || !roomActive}
            >
              {retrying ? "正在重试未完成角色…" : "仅重试未完成角色"}
            </button>
          ) : null}
        </div>
      ) : null}
      <label className="tavern-composer-label">
        <span>你的消息</span>
        <textarea
          value={message}
          onChange={(event) => setMessage(event.target.value)}
          onKeyDown={handleKeyDown}
          onCompositionStart={() => {
            composingRef.current = true;
            suppressCompositionEnterRef.current = false;
          }}
          onCompositionEnd={() => {
            composingRef.current = false;
            suppressCompositionEnterRef.current = true;
            window.setTimeout(() => {
              suppressCompositionEnterRef.current = false;
            }, 0);
          }}
          disabled={!roomActive || busy}
          maxLength={4000}
          rows={4}
          placeholder={
            roomActive
              ? "输入消息。Enter 发送，Shift + Enter 换行。"
              : roomAvailable
                ? "归档房间为只读状态。"
                : "请先创建或打开一个酒馆。"
          }
        />
      </label>
      <label className="tavern-composer-label">
        <span>下一轮引导（可选，不会显示在对话中）</span>
        <textarea
          value={guidance}
          onChange={(event) => setGuidance(event.target.value)}
          disabled={!roomActive || busy}
          maxLength={1000}
          rows={2}
          placeholder="例如：让角色互相回应，但保留各自立场。"
        />
      </label>
      <div className="tavern-composer-actions">
        <button type="button" className="tavern-button primary" onClick={() => void sendMessage()} disabled={!canRun || !message.trim()}>
          <MaterialIcon name="send" size={16} />{busy ? "生成中…" : "发送并回应"}
        </button>
        <button type="button" className="tavern-button secondary" onClick={() => void continueConversation()} disabled={!canRun || !latestMessage}>
          继续角色互动
        </button>
        {canCancel ? (
          <button
            type="button"
            className="tavern-button danger"
            onClick={() => void cancelConversation()}
            disabled={canceling}
          >
            <MaterialIcon name="close" size={16} />
            {canceling ? "正在取消…" : "取消接收结果"}
          </button>
        ) : null}
      </div>
      {busy ? <p className="tavern-panel-footnote" role="status">请求已交给服务器。取消会立即拒收结果，但已发出的模型请求可能运行到超时。</p> : null}
    </section>
  );
}

function ReliabilityDetails({
  runs,
  retryableRuns,
  recoveryChains,
  participants,
  roomActive,
  busy,
  onRetry,
}: {
  runs: TavernRun[];
  retryableRuns: TavernRun[];
  recoveryChains: TavernRunRecoveryChain[];
  participants: TavernParticipant[];
  roomActive: boolean;
  busy: boolean;
  onRetry: (run: TavernRun) => void;
}) {
  const retryableIds = new Set(retryableRuns.map((run) => run.id));
  const recoveredRootIds = new Set(
    recoveryChains
      .filter((chain) => chain.chainStatus === "recovered")
      .map((chain) => chain.rootRunId)
  );
  const names = new Map(participants.map((participant) => [
    participant.personaId,
    participant.displayName || "未命名角色",
  ]));
  return (
    <details className="tavern-panel reliability-details">
      <summary>
        <span><span className="tavern-kicker">Reliability Details</span><strong>可靠性摘要</strong></span>
        <span className="tavern-count" aria-label={`${retryableRuns.length} 个待恢复项`}>
          待恢复 {retryableRuns.length}
        </span>
      </summary>
      <div className="tavern-reliability-content">
        <p className="tavern-panel-footnote">这里只显示可读恢复摘要；完整 Harness trace 可在全局调试层查看。</p>
        {runs.length ? runs.slice(0, 12).map((run) => {
          const repairCount = [
            ...run.harnessTrace,
            ...run.speakerSteps.flatMap((step) => step.harnessTrace ? [step.harnessTrace] : []),
          ].filter((trace) => trace.status === "repaired").length;
          return (
            <div className="tavern-run-summary" key={run.id}>
              <div className="tavern-run-title-row">
                <strong>{RUN_STATUS_LABELS[run.status]}</strong>
                <span>{run.mode === "direct" ? "单角色" : "多人引导"} · {formatShortTime(run.createdAt)}</span>
              </div>
              <ul>
                {run.speakerSteps.map((step) => (
                  <li key={`${run.id}-${step.stepIndex}`}>
                    <span>{names.get(step.personaId) || "房间角色"}</span>
                    <span>{step.status === "blocked" ? "因前序回应未完成而暂未执行" : STEP_STATUS_LABELS[step.status]}</span>
                  </li>
                ))}
              </ul>
              {repairCount ? <p className="tavern-repair-note">本轮有 {repairCount} 项输出经校验后自动修正。</p> : null}
              {retryableIds.has(run.id) ? (
                <button type="button" className="tavern-button secondary full" onClick={() => onRetry(run)} disabled={!roomActive || busy}>
                  仅重试未完成角色
                </button>
              ) : recoveredRootIds.has(run.id) ? (
                <p className="tavern-repair-note">该部分结果已由后续范围重试完整恢复。</p>
              ) : run.parentRunId ? (
                <p className="tavern-repair-note">这是一次范围受限的恢复运行。</p>
              ) : null}
            </div>
          );
        }) : <p className="tavern-empty-copy">发起互动后，这里会显示每位角色的生成与恢复结果。</p>}
      </div>
    </details>
  );
}

function messageAuthorLabel(message: TavernMessage): string {
  if (message.authorKind === "persona") return message.personaName || "房间角色";
  if (message.authorKind === "user") return "你";
  if (message.authorKind === "director") return "导演引导";
  return "系统";
}

function formatShortTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "刚刚";
  return new Intl.DateTimeFormat("zh-CN", {
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function recordError(
  error: unknown,
  fallback: string,
  setVisible: (value: string) => void,
  setRaw: (value: string) => void
) {
  const raw = error instanceof Error ? error.message : String(error);
  setRaw(raw);
  setVisible(friendlyTavernError(error, fallback));
}

function friendlyTavernError(error: unknown, fallback: string): string {
  const detail = decodeTavernHttpError(error);
  const code = detail?.code ?? "";
  if (code === "tavern_revision_conflict") return "房间刚刚发生了更新，已重新同步；请确认内容后重试。";
  if (code === "tavern_run_in_progress") return "这个房间已有一轮互动正在生成，请稍后刷新。";
  if (code === "tavern_continue_anchor_stale") return "对话已出现更新；请基于最新一条消息继续。";
  if (code === "tavern_retry_context_changed") return "房间内容或角色设定已变化，不能继续旧恢复任务。";
  if (code === "tavern_retry_already_created") return "这次未完成互动已经创建过恢复任务，已重新同步。";
  if (code === "tavern_room_not_active") return "这个房间已归档；恢复使用后才能继续互动。";
  if (code === "tavern_run_failed") return "部分角色回应未通过可靠性检查。已保存的消息不会丢失，可从恢复入口继续未完成角色。";
  const raw = error instanceof Error ? error.message : String(error);
  if (raw.includes("tavern_response_decode_error") || / at tavern\./.test(raw)) {
    return "服务器返回的数据未通过可靠性校验；页面已保留现有内容，请刷新恢复，若持续出现请查看调试详情。";
  }
  if (raw.includes("Cannot reach AI service")) return "无法连接 AI 服务，请检查服务是否已启动。";
  return fallback;
}
