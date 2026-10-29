"use client";
import { Profiler, useState, useRef, useEffect, useMemo } from "react";
import { useTavernWorkspaceController } from "../hooks/use-tavern-workspace-controller";
import {
  defaultTavernWorkspacePorts,
  type TavernWorkspacePorts,
} from "../lib/tavern-workspace-ports";
import {
  TavernHeader,
  TavernSessionPanel,
  TavernSetupPanel,
  TavernConversationPanel,
  ParticipantRoster,
  InteractionComposer,
  ReliabilityDetails,
} from "./tavern-workspace-panels";
import { AsyncFeedback } from "./async-feedback";
import { usePageDebugSnapshot } from "./page-debug-context";
import { TopNav } from "./top-nav";

export function TavernWorkspace({
  ports = defaultTavernWorkspacePorts,
}: { ports?: TavernWorkspacePorts } = {}) {
  const {
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
    handleCreateRoom,
    handleArchiveToggle,
    handleTurn,
    handleCancelRun,
    handleRetry,
    handleTargetToggle,
    storage,
    openRoom,
    refreshRoom,
    loadMoreRooms,
    handleLoadOlder,
  } = useTavernWorkspaceController(ports);
  const [setupFocusRequest, setSetupFocusRequest] = useState(0);
  const setupTitleRef = useRef<HTMLInputElement>(null);
  const feedbackAction = useRef<Element | null>(null);
  useEffect(() => {
    if (!showSetup || setupFocusRequest === 0) return;
    const frame = window.requestAnimationFrame(() => {
      setupTitleRef.current?.scrollIntoView({
        behavior: "smooth",
        block: "center",
      });
      setupTitleRef.current?.focus({ preventScroll: true });
    });
    return () => window.cancelAnimationFrame(frame);
  }, [setupFocusRequest, showSetup]);

  const debugSnapshot = useMemo(
    () => ({
      title: "Tavern Workspace 调试面板",
      subtitle: "原始房间、消息、run 与 Harness evidence 仅在调试层查看。",
      error: rawError,
      summary: [
        { label: "房间", value: activeRoom?.title || "-" },
        { label: "Revision", value: String(activeRoom?.revision ?? 0) },
        {
          label: "Last sequence",
          value: String(activeRoom?.lastSequence ?? 0),
        },
        { label: "已载入消息", value: String(messages.length) },
        { label: "最近 runs", value: String(runs.length) },
      ],
      details: [
        { title: "当前房间", value: detail },
        { title: "已载入消息", value: messages },
        { title: "最近 runs / traces", value: runs },
      ],
    }),
    [activeRoom, detail, messages, rawError, runs],
  );
  usePageDebugSnapshot(debugSnapshot);

  const sessionPanel = (
    <TavernSessionPanel
      rooms={roomButtons}
      activeRoomId={activeRoom?.id ?? ""}
      busy={busyAction !== null}
      hasMore={nextRoomCursor !== null}
      loadingMore={loadingMoreRooms}
      historyTruncated={roomHistoryTruncated}
      pageError={roomPageError}
      onOpen={(roomId) => void openRoom(roomId)}
      onLoadMore={() => void loadMoreRooms()}
    />
  );

  return (
    <main
      className="with-app-nav tavern-page"
      onClickCapture={(event) => {
        feedbackAction.current = (event.target as Element).closest(
          "button, input, select",
        );
      }}
    >
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

      <AsyncFeedback
        actionRef={feedbackAction}
        pending={busyAction !== null}
        error={visibleError}
        message=""
      />

      <div
        className={`tavern-workspace-grid ${activeRoom ? "has-room" : "empty-room"}`}
      >
        <div className="tavern-left-rail">
          {process.env.NEXT_PUBLIC_TAVERN_ROOM_PROFILING === "1" ? (
            <Profiler
              id="TavernSessionPanel"
              onRender={(
                id,
                phase,
                actualDuration,
                baseDuration,
                startTime,
                commitTime,
              ) => {
                const target = window as Window & {
                  __tavernRoomProfileSamples?: unknown[];
                };
                const samples = (target.__tavernRoomProfileSamples ??= []);
                samples.push({
                  id,
                  phase,
                  actualDuration,
                  baseDuration,
                  startTime,
                  commitTime,
                  roomIds: roomButtons.map((room) => room.id),
                  loadingMore: loadingMoreRooms,
                });
                if (samples.length > 2000)
                  samples.splice(0, samples.length - 2000);
              }}
            >
              {sessionPanel}
            </Profiler>
          ) : (
            sessionPanel
          )}
          {showSetup ? (
            <TavernSetupPanel
              storage={storage}
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
              storage={storage}
              key={activeRoom.id}
              roomId={activeRoom.id}
              roomAvailable
              roomActive={Boolean(roomIsActive)}
              participants={detail?.participants ?? []}
              selectedIds={targetPersonaIds}
              latestMessage={latestMessage}
              recovery={facilitatedRecovery}
              busy={
                busyAction === "turn" ||
                busyAction === "retry" ||
                busyAction === "cancel" ||
                runPending ||
                loadingOlder
              }
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
              disabled={
                !roomIsActive || mutationBusy || runPending || loadingOlder
              }
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
