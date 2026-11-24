import type {
  TavernRoomDetail,
  TavernRun,
  TavernRunRecoveryChain,
} from "@vibe-learner/shared";

export async function readTavernRoomSnapshot(requests: {
  detail: Promise<TavernRoomDetail>;
  runs: Promise<TavernRun[]>;
  recovery: Promise<TavernRunRecoveryChain[]>;
}) {
  const [detail, runs, recovery] = await Promise.allSettled([
    requests.detail,
    requests.runs,
    requests.recovery,
  ]);
  if (detail.status === "rejected") throw detail.reason;
  return {
    detail: detail.value,
    runs: runs.status === "fulfilled" ? runs.value : null,
    recovery: recovery.status === "fulfilled" ? recovery.value : null,
    reliabilityErrors: [runs, recovery].flatMap((result) =>
      result.status === "rejected" ? [String(result.reason)] : [],
    ),
  };
}

export function tavernReadNotice(runsKnown: boolean, recoveryKnown: boolean) {
  if (!runsKnown) return "互动状态暂未确认；已保存的对话仍可阅读，请刷新后再继续。";
  if (!recoveryKnown) return "恢复详情暂时无法载入；已保存的对话仍可阅读。";
  return "";
}
