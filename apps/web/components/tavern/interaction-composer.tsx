import type { TavernMessage, TavernParticipant, TavernRun } from "@vibe-learner/shared";
import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { TAVERN_COPY } from "../../lib/tavern-copy";
import { authoritativeFacilitatedRecovery } from "../../lib/tavern-workspace-state";
import { MaterialIcon } from "../ui/material-icon";
import type { TavernStoragePort } from "../../lib/tavern-workspace-ports";

export function InteractionComposer({
  storage,
  roomId,
  roomAvailable,
  roomActive,
  participants,
  selectedIds,
  activeReplyIds = [],
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
  storage: TavernStoragePort;
  roomId: string;
  roomAvailable: boolean;
  roomActive: boolean;
  participants: TavernParticipant[];
  selectedIds: string[];
  activeReplyIds?: string[];
  latestMessage: TavernMessage | null;
  recovery: ReturnType<typeof authoritativeFacilitatedRecovery>;
  busy: boolean;
  recoveryBusy: boolean;
  retrying: boolean;
  canCancel: boolean;
  canceling: boolean;
  onTurn: (
    input:
      | { kind: "user_message"; content: string }
      | { kind: "continue"; anchorMessageId: string },
    guidance: string,
  ) => Promise<boolean>;
  // True means a confirmed cancel consumed this composer's submitted draft.
  onCancel: () => Promise<boolean>;
  onRetry: (run: TavernRun) => void;
}) {
  const initialDraft = storage.readTavernRoomDraft(roomId);
  const [message, setMessage] = useState(initialDraft.message);
  const [guidance, setGuidance] = useState(initialDraft.guidance);
  const [focusRequestVersion, setFocusRequestVersion] = useState(0);
  const composingRef = useRef(false);
  const suppressCompositionEnterRef = useRef(false);
  const messageInputRef = useRef<HTMLTextAreaElement>(null);
  const mountedRoomIdRef = useRef(roomId);
  const handledFocusRequestRef = useRef(0);
  const namesById = useMemo(
    () =>
      new Map(
        participants.map((participant) => [
          participant.personaId,
          participant.displayName || "未命名角色",
        ]),
      ),
    [participants],
  );
  const recipientNames = [...participants]
    .sort((left, right) => left.displayOrder - right.displayOrder)
    .filter((participant) =>
      (activeReplyIds.length ? activeReplyIds : selectedIds).includes(
        participant.personaId,
      ),
    )
    .map((participant) => namesById.get(participant.personaId))
    .filter(Boolean);
  const unfinishedNames =
    recovery?.unfinishedPersonaIds.map(
      (personaId) => namesById.get(personaId) || "房间角色",
    ) ?? [];
  const showRecovery = Boolean(roomActive && recovery && (!canCancel || retrying));
  const canRun =
    roomActive && selectedIds.length >= 1 && selectedIds.length <= 4 && !busy;

  useEffect(() => {
    const current = storage.readTavernRoomDraft(roomId);
    storage.writeTavernRoomDraft(roomId, {
      message,
      guidance,
      pendingTurn: current.pendingTurn,
    });
  }, [guidance, message, roomId, storage]);

  useEffect(() => {
    mountedRoomIdRef.current = roomId;
    return () => {
      mountedRoomIdRef.current = "";
    };
  }, [roomId]);

  useEffect(() => {
    if (
      focusRequestVersion === 0 ||
      handledFocusRequestRef.current >= focusRequestVersion
    )
      return;
    if (busy) return;
    if (!roomActive || message || guidance) {
      handledFocusRequestRef.current = focusRequestVersion;
      return;
    }
    const expectedRoomId = roomId;
    const frame = window.requestAnimationFrame(() => {
      if (
        mountedRoomIdRef.current !== expectedRoomId ||
        handledFocusRequestRef.current >= focusRequestVersion
      )
        return;
      handledFocusRequestRef.current = focusRequestVersion;
      const input = messageInputRef.current;
      if (!input || !input.isConnected || input.disabled) return;
      input.focus({ preventScroll: true });
    });
    return () => window.cancelAnimationFrame(frame);
  }, [busy, focusRequestVersion, guidance, message, roomActive, roomId]);

  const sendMessage = async () => {
    const content = message.trim();
    if (!content || !canRun) return;
    const completed = await onTurn({ kind: "user_message", content }, guidance.trim());
    if (completed) {
      setMessage("");
      setGuidance("");
      setFocusRequestVersion((current) => current + 1);
    }
  };

  const continueConversation = async () => {
    if (!latestMessage || !canRun) return;
    const completed = await onTurn(
      { kind: "continue", anchorMessageId: latestMessage.id },
      guidance.trim(),
    );
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
    <section
      className="tavern-panel interaction-composer"
      aria-labelledby="interaction-composer-title"
    >
      <div className="tavern-panel-heading">
        <h2 id="interaction-composer-title">发起互动</h2>
      </div>
      <p className="tavern-recipient-preview">
        {recipientNames.length
          ? `本轮回应：${recipientNames.join(" → ")}`
          : "请先选择至少一位角色"}
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
              <p>
                {recovery.completedCount}/{recovery.totalCount} {TAVERN_COPY.recovered}
              </p>
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
          ref={messageInputRef}
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
                ? TAVERN_COPY.archived
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
        <button
          type="button"
          className="tavern-button primary"
          onClick={() => void sendMessage()}
          disabled={!canRun || !message.trim()}
        >
          <MaterialIcon name="send" size={16} />
          {busy ? "生成中…" : "发送并回应"}
        </button>
        <button
          type="button"
          className="tavern-button secondary"
          onClick={() => void continueConversation()}
          disabled={!canRun || !latestMessage}
        >
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
      {busy ? (
        <p className="tavern-panel-footnote" role="status">
          请求已交给服务器。取消会拒收结果并尝试中断本地请求，上游计算和计费可能继续。
        </p>
      ) : null}
    </section>
  );
}
