import type { DiagnosticEventV1 } from "@vibe-learner/shared";
import { diagnosticContext, emitDiagnostic, createDiagnosticId, type DiagnosticContext } from "./diagnostics.ts";

export type DiagnosticActionName = NonNullable<DiagnosticEventV1["action_name"]>;

/** Explicitly captured context survives navigation; no process-global async action. */
export async function observeLocalAction<T>(name: DiagnosticActionName, run: (context: DiagnosticContext) => Promise<T>,
  options: { context?: DiagnosticContext; cancelled?: (result: T) => boolean } = {}): Promise<T> {
  const context = options.context ?? diagnosticContext(createDiagnosticId());
  const span = createDiagnosticId();
  const started = performance.now();
  const emit = (event: "action_started" | "action_finished" | "action_failed" | "action_cancelled") => {
    try {
      emitDiagnostic(event, context, { request_id: null, status_code: null, method: null,
        duration_ms: event === "action_started" ? null : performance.now() - started,
        action_name: name, span_id: span, parent_span_id: context.local_span_id ?? null });
    } catch { /* Diagnostic failure cannot change the action's result. */ }
  };
  emit("action_started");
  try {
    const result = await run({ ...context, local_span_id: span });
    emit(options.cancelled?.(result) ? "action_cancelled" : "action_finished");
    return result;
  } catch (error) {
    emit("action_failed");
    throw error;
  }
}
