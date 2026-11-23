import type { TavernRoomSummary } from "@vibe-learner/shared";
import { MaterialIcon } from "../ui/material-icon";
import { formatShortTime } from "./tavern-format";

export function TavernSessionPanel({
  rooms,
  activeRoomId,
  busy,
  hasMore,
  loadingMore,
  historyTruncated,
  pageError,
  onOpen,
  onLoadMore,
}: {
  rooms: TavernRoomSummary[];
  activeRoomId: string;
  busy: boolean;
  hasMore: boolean;
  loadingMore: boolean;
  historyTruncated: boolean;
  pageError: string;
  onOpen: (roomId: string) => void;
  onLoadMore: () => void;
}) {
  return (
    <section
      className="tavern-panel tavern-session-panel"
      aria-labelledby="tavern-session-title"
    >
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
                {room.participantNames
                  .map((name) => name || "未命名角色")
                  .join(" · ") || "无角色"}
              </span>
              <span className="tavern-room-item-meta">
                {room.messageCount} 条消息 ·{" "}
                {room.status === "archived"
                  ? "已归档"
                  : formatShortTime(room.updatedAt)}
              </span>
            </button>
          ))}
        </div>
      ) : (
        <p className="tavern-empty-copy">还没有房间。选择 1–6 位人格即可创建。</p>
      )}
      <div className="tavern-room-page-status">
        {pageError ? <p role="alert">{pageError}</p> : null}
        {hasMore ? (
          <button
            type="button"
            className="tavern-button secondary tavern-room-more"
            onClick={onLoadMore}
            disabled={busy || loadingMore}
          >
            <MaterialIcon name="expand_more" size={16} />
            {loadingMore ? "正在载入…" : pageError ? "重试载入更多" : "载入更多房间"}
          </button>
        ) : rooms.length ? (
          <p>{historyTruncated ? "已显示最近 100 个房间" : "已显示全部房间"}</p>
        ) : null}
      </div>
    </section>
  );
}
