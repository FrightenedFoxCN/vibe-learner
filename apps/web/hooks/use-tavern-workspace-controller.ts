"use client";
import { useCallback } from "react";
import {
  defaultTavernWorkspacePorts,
  type TavernWorkspacePorts,
} from "../lib/tavern-workspace-ports";
import { useTavernMutations } from "./use-tavern-mutations";
import { useTavernRoomQueries } from "./use-tavern-room-queries";
import { useTavernRunRecovery } from "./use-tavern-run-recovery";
import { useTavernWorkspaceState } from "./use-tavern-workspace-state";

export function useTavernWorkspaceController(
  ports: TavernWorkspacePorts = defaultTavernWorkspacePorts,
) {
  const state = useTavernWorkspaceState();
  const queries = useTavernRoomQueries(state, ports);
  useTavernRunRecovery(state, ports, queries);
  const mutations = useTavernMutations(state, ports, queries);
  const { setTargetPersonaIds, setVisibleError } = state;
  const handleTargetToggle = useCallback((personaId: string) => {
    setTargetPersonaIds((current) => {
      if (current.includes(personaId)) {
        return current.filter((id) => id !== personaId);
      }
      if (current.length >= 4) {
        setVisibleError(
          "一次多人互动最多选择 4 位角色。你可以在下一轮更换目标。",
        );
        return current;
      }
      setVisibleError("");
      return [...current, personaId];
    });
  }, []);

  const {
    rooms,
    nextRoomCursor,
    loadingMoreRooms,
    roomPageError,
    roomHistoryTruncated,
    personas,
    scenes,
    detail,
    messages,
    runs,
    recoveryChains,
    targetPersonaIds,
    generatingPersonaIds,
    showSetup,
    setShowSetup,
    busyAction,
    loadingOlder,
    notice,
    visibleError,
    rawError,
    activeRoom,
    roomIsActive,
    roomBusy,
    mutationBusy,
    runPending,
    latestMessage,
    retryableRuns,
    facilitatedRecovery,
    participantStates,
    roomButtons,
  } = state;
  const { openRoom, refreshRoom, loadMoreRooms, handleLoadOlder } = queries;
  return {
    rooms,
    nextRoomCursor,
    loadingMoreRooms,
    roomPageError,
    roomHistoryTruncated,
    personas,
    scenes,
    detail,
    messages,
    runs,
    recoveryChains,
    targetPersonaIds,
    generatingPersonaIds,
    showSetup,
    setShowSetup,
    busyAction,
    loadingOlder,
    notice,
    visibleError,
    rawError,
    activeRoom,
    roomIsActive,
    roomBusy,
    mutationBusy,
    runPending,
    latestMessage,
    retryableRuns,
    facilitatedRecovery,
    participantStates,
    roomButtons,
    openRoom,
    refreshRoom,
    loadMoreRooms,
    handleLoadOlder,
    ...mutations,
    handleTargetToggle,
    storage: ports.storage,
  };
}
