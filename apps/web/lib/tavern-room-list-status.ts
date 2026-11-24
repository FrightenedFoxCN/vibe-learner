export type TavernRoomListStatus =
  "loading" | "failed" | "ready" | "refreshing" | "stale";

export function advanceTavernRoomListStatus(
  current: TavernRoomListStatus,
  event: "start" | "success" | "failure",
): TavernRoomListStatus {
  if (event === "success") return "ready";
  const hasLoaded =
    current === "ready" || current === "refreshing" || current === "stale";
  if (event === "start") return hasLoaded ? "refreshing" : "loading";
  return hasLoaded ? "stale" : "failed";
}

export function tavernRoomListPresentation(
  status: TavernRoomListStatus,
  count: number,
) {
  const hasLoaded = status === "ready" || status === "refreshing" || status === "stale";
  return {
    showCount: hasLoaded || count > 0,
    showEmpty: hasLoaded && count === 0,
    loadingFirstPage: status === "loading",
    firstPageError:
      status === "failed"
        ? "房间历史暂时无法载入。"
        : status === "stale"
          ? "房间历史刷新失败；当前列表已保留。"
          : "",
  };
}
