const AUTO_RECOVERY_DELAYS_MS = [2500, 5000, 10000] as const;

type RecoveryMode = "automatic" | "manual";
export type TavernPendingRecoveryProgress = Readonly<{
  automaticAttempts: number;
  inFlight: boolean;
}>;

const INITIAL_PROGRESS: TavernPendingRecoveryProgress = {
  automaticAttempts: 0,
  inFlight: false,
};

export function tavernAutomaticRecoveryDelay(
  progress: TavernPendingRecoveryProgress = INITIAL_PROGRESS,
): number | null {
  if (progress.inFlight) return null;
  return AUTO_RECOVERY_DELAYS_MS[progress.automaticAttempts] ?? null;
}

export function createTavernPendingRecoveryBudget() {
  const perRun = new Map<string, TavernPendingRecoveryProgress>();
  return {
    begin(runId: string, mode: RecoveryMode) {
      const current = perRun.get(runId) ?? INITIAL_PROGRESS;
      if (
        current.inFlight ||
        (mode === "automatic" && tavernAutomaticRecoveryDelay(current) === null)
      )
        return null;
      // Charge at dispatch, independent of transport or server outcome. A room
      // switch, same-ID refresh, or manual request does not reset this budget.
      const progress = {
        automaticAttempts: current.automaticAttempts + (mode === "automatic" ? 1 : 0),
        inFlight: true,
      };
      perRun.set(runId, progress);
      return progress;
    },
    finish(runId: string) {
      const current = perRun.get(runId) ?? INITIAL_PROGRESS;
      const progress = { ...current, inFlight: false };
      perRun.set(runId, progress);
      return progress;
    },
  };
}
