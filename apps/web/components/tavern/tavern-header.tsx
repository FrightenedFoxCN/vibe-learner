import type { TavernRoomDetail } from "@vibe-learner/shared";
import { MaterialIcon } from "../ui/material-icon";
import { ProviderTruth } from "../ui/provider-truth";

export function TavernHeader({
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
        <p className="tavern-header-status" role="status" aria-live="polite">
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
          {busy ? "处理中 · " : ""}
          {notice}
          {room ? ` · revision ${room.revision}` : ""}
          <ProviderTruth scope="tavern" />
        </p>
      </div>
      <div className="tavern-header-actions">
        {room ? (
          <>
            <button
              type="button"
              className="tavern-button secondary"
              onClick={onRefresh}
              disabled={busy}
            >
              <MaterialIcon name="refresh" size={16} />
              刷新
            </button>
            <button
              type="button"
              className="tavern-button secondary"
              onClick={onArchiveToggle}
              disabled={busy || runPending}
            >
              {room.status === "active" ? "归档" : "恢复使用"}
            </button>
          </>
        ) : null}
        <button
          type="button"
          className="tavern-button primary"
          onClick={onCreate}
          disabled={busy}
        >
          <MaterialIcon name="add" size={16} />
          新建酒馆
        </button>
      </div>
    </header>
  );
}
