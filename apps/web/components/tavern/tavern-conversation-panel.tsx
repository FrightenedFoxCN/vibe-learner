import type {
  TavernMessage,
  TavernParticipant,
  TavernRoomDetail,
} from "@vibe-learner/shared";
import { useEffect, useLayoutEffect, useMemo, useRef } from "react";
import { MaterialIcon } from "../ui/material-icon";
import { RichTextMessage } from "../ui/rich-text-message";
import { formatShortTime } from "./tavern-format";

export function TavernConversationPanel({
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
  const loadedMessageCount = messages.length;
  const firstSequence = messages[0]?.sequence;
  const latestSequence = messages[loadedMessageCount - 1]?.sequence ?? 0;
  const names = useMemo(
    () =>
      new Map(
        participants.map((participant) => [
          participant.personaId,
          participant.displayName || "未命名角色",
        ]),
      ),
    [participants],
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
    if (
      anchor &&
      scrollBox &&
      firstSequence !== undefined &&
      firstSequence < anchor.firstSequence
    ) {
      const anchorElement = scrollBox.querySelector<HTMLElement>(
        `[data-tavern-sequence="${anchor.firstSequence}"]`,
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
  }, [loadedMessageCount, firstSequence]);

  const loadOlder = async () => {
    const scrollBox = scrollRef.current;
    const firstSequence = messages[0]?.sequence ?? 0;
    const firstMessage = scrollBox?.querySelector<HTMLElement>(
      `[data-tavern-sequence="${firstSequence}"]`,
    );
    const viewportOffset =
      firstMessage && scrollBox
        ? firstMessage.getBoundingClientRect().top -
          scrollBox.getBoundingClientRect().top
        : 0;
    pendingOlderAnchorRef.current = scrollBox
      ? {
          height: scrollBox.scrollHeight,
          top: scrollBox.scrollTop,
          firstSequence,
          viewportOffset,
        }
      : null;
    if (!(await onLoadOlder())) pendingOlderAnchorRef.current = null;
  };

  return (
    <section
      className="tavern-panel tavern-conversation-panel"
      aria-labelledby="tavern-conversation-title"
    >
      <div className="tavern-panel-heading conversation-heading">
        <h2 id="tavern-conversation-title">对话记录</h2>
        <span className="tavern-count">
          {messages.length}/{messageCount}
        </span>
      </div>
      <p className="sr-only" aria-live="polite">
        {loadingOlder
          ? "正在载入更早消息"
          : latestSequence
            ? `最新消息序号 ${latestSequence}`
            : ""}
      </p>
      <div
        className="tavern-transcript"
        ref={scrollRef}
        aria-label="酒馆对话记录"
        aria-busy={loading || loadingOlder}
      >
        {hasOlder ? (
          <button
            type="button"
            className="tavern-load-older"
            onClick={() => void loadOlder()}
            disabled={loadingOlder || olderDisabled}
          >
            {loadingOlder ? "载入中…" : "载入更早消息"}
          </button>
        ) : messages.length ? (
          <p className="tavern-history-start">已到达对话起点</p>
        ) : null}

        {loading && !messages.length ? (
          <div className="tavern-empty-state">
            <MaterialIcon name="hourglass_top" size={24} />
            <p>正在恢复最近对话…</p>
          </div>
        ) : !room ? (
          <div className="tavern-empty-state">
            <MaterialIcon name="forum" size={28} />
            <p>先创建或打开一个酒馆，然后开始对话。</p>
          </div>
        ) : !messages.length ? (
          <div className="tavern-empty-state">
            <MaterialIcon name="forum" size={28} />
            <p>这里还很安静。选择角色并发送第一句话。</p>
          </div>
        ) : (
          messages.map((message) => (
            <article
              key={message.id}
              className={`tavern-message ${message.authorKind}`}
              data-tavern-sequence={message.sequence}
            >
              <div className="tavern-message-meta">
                <strong>{messageAuthorLabel(message)}</strong>
                <time dateTime={message.createdAt}>
                  #{message.sequence} · {formatShortTime(message.createdAt)}
                </time>
              </div>
              <div className="tavern-message-body">
                <RichTextMessage content={message.content} />
                {message.action ? (
                  <p className="tavern-message-action">动作：{message.action}</p>
                ) : null}
                {message.addressedParticipantIds.length ? (
                  <p className="tavern-message-addressed">
                    回应给{" "}
                    {message.addressedParticipantIds
                      .map((id) => names.get(id) || "房间角色")
                      .join("、")}
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

function messageAuthorLabel(message: TavernMessage): string {
  if (message.authorKind === "persona") return message.personaName || "房间角色";
  if (message.authorKind === "user") return "你";
  if (message.authorKind === "director") return "导演引导";
  return "系统";
}
