import type { TavernRun } from "@vibe-learner/shared";

export async function confirmTavernCancellation(input: {
  runId: string;
  cancel: () => Promise<TavernRun | undefined>;
  readRuns: () => Promise<TavernRun[] | undefined>;
  isCurrent: () => boolean;
  onCancelError: (error: unknown) => void;
}): Promise<TavernRun | undefined> {
  const matches = (run: TavernRun) =>
    run.id === input.runId && run.status === "canceled";
  let direct: TavernRun | undefined;
  try {
    direct = await input.cancel();
  } catch (error) {
    if (input.isCurrent()) input.onCancelError(error);
  }
  if (!input.isCurrent()) return;
  const runs = await input.readRuns();
  if (!input.isCurrent()) return;
  return runs?.find(matches) ?? (direct && matches(direct) ? direct : undefined);
}
