import { classifyDiagnostic } from "../../../packages/shared/src/diagnostic.ts";
import type { DiagnosticEventV1, DiagnosticPagePath } from "@vibe-learner/shared";

export type DiagnosticContext = Pick<DiagnosticEventV1, "client_instance_id" | "page_view_id" | "flow_id" | "action_id"> & { page_path?: DiagnosticPagePath | null; local_span_id?: string | null };
const CAPACITY = 1000;
let clientId: string | null = null;
let page: { owner: symbol; id: string; path: DiagnosticPagePath | null } | null = null;
let events: DiagnosticEventV1[] = [];
let pending: DiagnosticEventV1[] = [];
let dropped = 0;
let uploading = false;
const responseContexts = new WeakMap<Response, { context: DiagnosticContext; method: DiagnosticEventV1["method"] }>();

export function diagnosticDecode<T>(response: Response, decode: () => T): T {
  const started = performance.now();
  try { return decode(); }
  catch (error) {
    recordDecodeFailure(response, performance.now() - started);
    throw error;
  }
}

export function recordDecodeFailure(response: Response, duration: number) {
  try {
    const captured = responseContexts.get(response);
    if (!captured) return;
    emitDiagnostic("decode_failed", captured.context, {
      request_id: response.headers.get("X-Request-ID"), status_code: response.status,
      method: captured.method, duration_ms: duration,
    });
  } catch { /* Telemetry never replaces the original decoder error. */ }
}


export function createDiagnosticId(): string | null {
  try { return crypto.randomUUID(); } catch { return null; }
}

const PAGE_PATHS = new Set<string>(["/", "/plan", "/study", "/persona-spectrum", "/scene-setup", "/tavern", "/settings", "/sensory-tools", "/model-usage"]);
function reviewedPagePath(path: unknown): DiagnosticPagePath | null {
  return typeof path === "string" && PAGE_PATHS.has(path) ? path as DiagnosticPagePath : null;
}

export function registerDiagnosticPage(pathname?: string) {
  const registration = { owner: Symbol("page-view"), id: createDiagnosticId() ?? "", path: reviewedPagePath(pathname) };
  page = registration;
  const context = diagnosticContext();
  const started = performance.now();
  let disposed = false;
  const fields = { request_id: null, status_code: null, method: null };
  if (registration.id) emitDiagnostic("page_entered", context, { ...fields, duration_ms: null });
  return { id: registration.id, dispose: () => {
    if (disposed) return;
    disposed = true;
    if (registration.id) emitDiagnostic("page_left", context, { ...fields, duration_ms: performance.now() - started });
    if (page?.owner === registration.owner) page = null;
  } };
}

export function diagnosticContext(flowId: string | null = null): DiagnosticContext {
  clientId ??= createDiagnosticId();
  return { client_instance_id: clientId, page_view_id: page?.id || null, page_path: page?.path ?? null, flow_id: flowId,
    action_id: createDiagnosticId() };
}

export function diagnosticSnapshot() {
  return { events: [...events], dropped, pending: pending.length };
}

export function emitDiagnostic(name: DiagnosticEventV1["name"], context: DiagnosticContext,
  fields: Pick<DiagnosticEventV1, "request_id" | "duration_ms" | "status_code" | "method"> & Partial<Pick<DiagnosticEventV1, "action_name" | "span_id" | "parent_span_id">>) {
  const eventId = createDiagnosticId();
  if (!eventId) { dropped += 1; return; }
  // Explicit projection: no URLs, bodies, exception strings or arbitrary object spreads.
  const event: DiagnosticEventV1 = {
    schema_version: "diagnostic-event-v1", event_id: eventId, source: "browser", name,
    ...classifyDiagnostic(name, fields.status_code),
    action_name: fields.action_name ?? null, span_id: fields.span_id ?? null, parent_span_id: fields.parent_span_id ?? null,
    timestamp: new Date().toISOString(), route: null, page_path: reviewedPagePath(context.page_path),
    client_instance_id: context.client_instance_id, page_view_id: context.page_view_id,
    flow_id: context.flow_id, action_id: context.action_id,
    request_id: fields.request_id, duration_ms: fields.duration_ms,
    status_code: fields.status_code, method: fields.method,
  };
  events.push(event);
  if (events.length > CAPACITY) events.shift();
  pending.push(event);
  if (pending.length > CAPACITY) { pending.shift(); dropped += 1; }
}

export async function flushDiagnostics(baseUrl: string) {
  if (uploading || pending.length === 0) return;
  uploading = true;
  const batch = pending.slice(0, 100);
  try {
    // Direct transport prevents recursive diagnostics. Retry retains event identities.
    const response = await fetch(`${baseUrl}/diagnostics/events`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ events: batch }), signal: AbortSignal.timeout(5000),
    });
    if (response.ok) {
      const result: unknown = await response.json();
      if (!result || typeof result !== "object" || !("dropped" in result) ||
          typeof result.dropped !== "number" || !Number.isInteger(result.dropped) || result.dropped < 0) return;
      dropped += result.dropped;
      const ids = new Set(batch.map(event => event.event_id));
      pending = pending.filter(event => !ids.has(event.event_id));
    }
  } catch { /* Offline diagnostics never change the business result. */ }
  finally { uploading = false; }
}

export async function diagnosticFetch(input: string, init?: RequestInit, context = diagnosticContext()): Promise<Response> {
  const method = (init?.method ?? "GET").toUpperCase();
  const safeMethod = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"].includes(method)
    ? method as DiagnosticEventV1["method"] : null;
  const started = performance.now();
  let requestId: string | null = null;
  let status: number | null = null;
  const emit = (name: DiagnosticEventV1["name"]) => emitDiagnostic(name, context, {
    request_id: requestId, method: safeMethod, status_code: status,
    duration_ms: name === "request_started" ? null : performance.now() - started,
  });
  const headers = new Headers(init?.headers);
  for (const key of ["client_instance_id", "page_view_id", "flow_id", "action_id"] as const) {
    const value = context[key];
    if (value) headers.set(`X-Debug-${key.replaceAll("_", "-")}`, value);
  }
  emit("request_started");
  try {
    const response = await fetch(input, { ...init, headers });
    requestId = response.headers.get("X-Request-ID");
    status = response.status;
    emit("response_headers");
    if (!response.body) { emit("request_finished"); responseContexts.set(response, { context: { ...context }, method: safeMethod }); return response; }
    const reader = response.body.getReader();
    let terminal = false;
    const finish = (name: DiagnosticEventV1["name"]) => { if (!terminal) { terminal = true; emit(name); } };
    const body = new ReadableStream<Uint8Array>({
      async pull(controller) {
        try {
          const result = await reader.read();
          if (result.done) { finish("request_finished"); controller.close(); }
          else controller.enqueue(result.value);
        } catch (error) {
          finish(init?.signal?.aborted ? "request_cancelled" : "request_failed");
          controller.error(error);
        }
      },
      async cancel(reason) { finish("request_cancelled"); await reader.cancel(reason); },
    });
    const wrapped = new Response(body, { status: response.status, statusText: response.statusText, headers: response.headers });
    responseContexts.set(wrapped, { context: { ...context }, method: safeMethod });
    return wrapped;
  } catch (error) {
    emit(init?.signal?.aborted ? "request_cancelled" : "request_failed");
    throw error;
  }
}
