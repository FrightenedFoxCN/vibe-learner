type TimeField = "since" | "until";

export type DiagnosticTimeRange =
  | { ok: true; since?: string; until?: string }
  | { ok: false; field: TimeField; message: string };

export function parseDiagnosticTimeRange(
  since: string,
  until: string,
): DiagnosticTimeRange {
  const start = since ? new Date(since) : undefined;
  const end = until ? new Date(until) : undefined;
  if (start && !Number.isFinite(start.getTime()))
    return { ok: false, field: "since", message: "请输入有效的开始时间。" };
  if (end && !Number.isFinite(end.getTime()))
    return { ok: false, field: "until", message: "请输入有效的结束时间。" };
  if (start && end && start.getTime() >= end.getTime())
    return { ok: false, field: "until", message: "结束时间必须晚于开始时间。" };
  return { ok: true, since: start?.toISOString(), until: end?.toISOString() };
}
