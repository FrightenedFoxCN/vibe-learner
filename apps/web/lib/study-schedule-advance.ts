export interface StudyScheduleSelection {
  planId: string;
  scheduleId: string;
}

export function resolveStudyScheduleSelection<T extends { id: string; unitId: string }>(
  planId: string,
  options: readonly T[],
  selection: StudyScheduleSelection,
  sessionUnitId?: string,
): T | null {
  return (
    (planId && selection.planId === planId
      ? options.find((item) => item.id === selection.scheduleId)
      : undefined) ??
    (sessionUnitId
      ? options.find((item) => item.unitId === sessionUnitId)
      : undefined) ??
    options[0] ??
    null
  );
}

export interface StudyScheduleAdvance {
  planId: string;
  currentId: string;
  nextId: string;
}

interface ScheduleAdvanceActions {
  update: (input: {
    planId: string;
    scheduleIds: string[];
    status: "completed" | "in_progress";
  }) => Promise<boolean>;
  isCurrent: () => boolean;
  navigate: (nextId: string) => Promise<void>;
  onPartial: (advance: StudyScheduleAdvance | null) => void;
}

export async function advanceStudySchedule(
  advance: StudyScheduleAdvance,
  { update, isCurrent, navigate, onPartial }: ScheduleAdvanceActions,
  currentAlreadyCompleted = false,
): Promise<void> {
  const { planId, currentId, nextId } = advance;
  if (!isCurrent()) return;
  if (
    !currentAlreadyCompleted &&
    !(await update({ planId, scheduleIds: [currentId], status: "completed" }))
  )
    return;
  if (!isCurrent() || !nextId) return;

  const started = await update({
    planId,
    scheduleIds: [nextId],
    status: "in_progress",
  });
  if (!isCurrent()) return;
  onPartial(started ? null : advance);
  if (started) await navigate(nextId);
}
