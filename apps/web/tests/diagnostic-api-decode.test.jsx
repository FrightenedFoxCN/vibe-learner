import { dom } from "./support/dom.js";
import assert from "node:assert/strict";
import { after, test } from "node:test";
import { createStudyDiagnosticFlows } from "../lib/study-diagnostic-context.ts";
import { submitStudyQuestionAttempt, sendStudyMessage, getStudyChatOperation, listPersonas, listDocuments, listLearningPlans, listSceneLibrary, getStudySession, listTavernRooms, runTavernTurn, processDocumentStream, createLearningPlanStream } from "../lib/api.ts";
import { diagnosticContext, diagnosticDecode, diagnosticFetch, diagnosticSnapshot, registerDiagnosticPage } from "../lib/diagnostics.ts";

after(() => dom.window.close());
test("all domain API decoders log malformed scalar responses against the actual request", async () => {
  const original = globalThis.fetch;
  const page = registerDiagnosticPage("/plan");
  let index = 0;
  try {
    for (const invoke of [listPersonas, listDocuments, listLearningPlans, listSceneLibrary, () => getStudySession("session"), listTavernRooms]) {
      const id = `request_decode_${index++}`;
      globalThis.fetch = async () => Response.json(null, { headers: { "X-Request-ID": id } });
      await assert.rejects(invoke());
      const events = diagnosticSnapshot().events.filter(event => event.request_id === id);
      const failed = events.filter(event => event.name === "decode_failed");
      assert.equal(failed.length, 1);
      assert.equal(failed[0].page_view_id, page.id);
      assert.equal(failed[0].page_path, "/plan");
      assert.equal(failed[0].error_code, "decode_failure");
      assert.equal(events.find(event => event.name === "request_finished")?.outcome, "completed");
    }
  } finally { globalThis.fetch = original; page.dispose(); }
});

test("JSON syntax failures are separate from HTTP errors and body transport failures", async () => {
  const original = globalThis.fetch;
  try {
    globalThis.fetch = async () => new Response("PRIVATE_BODY", { headers: { "X-Request-ID": "invalid_json" } });
    await assert.rejects(listPersonas(), SyntaxError);
    assert.equal(diagnosticSnapshot().events.filter(event => event.request_id === "invalid_json" && event.name === "decode_failed").length, 1);
    globalThis.fetch = async () => new Response("PRIVATE_HTTP_ERROR", { status: 503, headers: { "X-Request-ID": "http_error" } });
    await assert.rejects(listPersonas());
    assert.equal(diagnosticSnapshot().events.filter(event => event.request_id === "http_error" && event.name === "decode_failed").length, 0);
    globalThis.fetch = async () => new Response(new ReadableStream({ start(controller) { controller.error(new Error("PRIVATE_NETWORK")); } }), { headers: { "X-Request-ID": "body_error" } });
    await assert.rejects(listPersonas());
    assert.equal(diagnosticSnapshot().events.filter(event => event.request_id === "body_error" && event.name === "decode_failed").length, 0);
    assert.ok(!JSON.stringify(diagnosticSnapshot()).includes("PRIVATE"));
  } finally { globalThis.fetch = original; }
});

test("response-owned decoding preserves error identity and captured context after navigation", async () => {
  const original = globalThis.fetch;
  const old = registerDiagnosticPage("/persona-spectrum");
  const context = diagnosticContext("flow");
  try {
    globalThis.fetch = async () => Response.json({}, { headers: { "X-Request-ID": "captured" } });
    const response = await diagnosticFetch("http://service/private", undefined, context);
    const next = registerDiagnosticPage("/study");
    old.dispose();
    const error = new Error("PRIVATE_DECODER_ERROR");
    assert.throws(() => diagnosticDecode(response, () => { throw error; }), thrown => thrown === error);
    const event = diagnosticSnapshot().events.find(event => event.name === "decode_failed" && event.request_id === "captured");
    assert.equal(event.action_id, context.action_id);
    assert.equal(event.page_view_id, old.id);
    assert.equal(event.page_path, "/persona-spectrum");
    assert.equal(diagnosticDecode(response, () => 42), 42);
    assert.ok(!JSON.stringify(diagnosticSnapshot()).includes("PRIVATE"));
    next.dispose();
  } finally { globalThis.fetch = original; old.dispose(); }
});


test("Tavern terminal replay keeps exact request and attributes decoder rejection to replay response", async () => {
  const original = globalThis.fetch;
  const calls = [];
  globalThis.fetch = async (url, init) => {
    calls.push({ url, body: init.body, method: init.method });
    return calls.length === 1
      ? Response.json({ detail: { code: "tavern_run_failed", run_id: "run-1", child_run_id: "", current_revision: 1, recovery_action: "replay_same_request" } }, { status: 502, headers: { "X-Request-ID": "replay_initial" } })
      : Response.json(null, { headers: { "X-Request-ID": "replay_readback" } });
  };
  try {
    await assert.rejects(runTavernTurn("room", { mode: "direct", input: { kind: "user_message", text: "PRIVATE_MESSAGE" }, targetPersonaIds: ["persona"], idempotencyKey: "stable-key", expectedRoomRevision: 0 }));
    assert.equal(calls.length, 2);
    assert.deepEqual(calls[0], calls[1]);
    assert.equal(diagnosticSnapshot().events.filter(event => event.name === "decode_failed" && event.request_id === "replay_initial").length, 0);
    assert.equal(diagnosticSnapshot().events.filter(event => event.name === "decode_failed" && event.request_id === "replay_readback").length, 1);
    assert.ok(!JSON.stringify(diagnosticSnapshot()).includes("PRIVATE"));
  } finally { globalThis.fetch = original; }
});


test("Document and Planning stream decoder failures retain request identity and redact event text", async () => {
  const original = globalThis.fetch;
  let index = 0;
  try {
    for (const invoke of [() => processDocumentStream("document", () => {}), () => createLearningPlanStream({ documentId: "document" }, () => {})]) {
      const requestId = `stream_decode_${index++}`;
      globalThis.fetch = async () => new Response("PRIVATE_INVALID_JSON\n", { headers: { "X-Request-ID": requestId } });
      await assert.rejects(invoke());
      assert.equal(diagnosticSnapshot().events.filter(event => event.name === "decode_failed" && event.request_id === requestId).length, 1);
    }
    assert.ok(!JSON.stringify(diagnosticSnapshot()).includes("PRIVATE"));
  } finally { globalThis.fetch = original; }
});


test("Study diagnostic flows survive reload, separate Session scope and expire without storing content", () => {
  let raw = null, clock = 1000, counter = 0;
  const storage = { read: () => raw, write: value => { raw = value; } };
  const flows = createStudyDiagnosticFlows(storage, () => clock, () => `flow-${++counter}`);
  const first = flows("session", "request");
  assert.equal(flows("session", "request").flow_id, first.flow_id);
  const reload = createStudyDiagnosticFlows(storage, () => clock, () => `flow-${++counter}`);
  assert.equal(reload("session", "request").flow_id, first.flow_id);
  assert.notEqual(reload("other-session", "request").flow_id, first.flow_id);
  clock += 8 * 24 * 60 * 60 * 1000;
  assert.notEqual(reload("session", "request").flow_id, first.flow_id);
  for (let i = 0; i < 200; i++) reload("session", `request-${i}`);
  assert.equal(JSON.parse(raw).length, 128);
  assert.ok(raw.length <= 64 * 1024);
  assert.ok(JSON.parse(raw).every(item => Object.keys(item).sort().join(",") === "clientRequestId,createdAt,flowId,sessionId"));
  const denied = createStudyDiagnosticFlows({ read() { throw Error("denied"); }, write() { throw Error("denied"); } });
  assert.equal(denied("s", "r").flow_id, denied("s", "r").flow_id);
  const malformed = createStudyDiagnosticFlows({ read: () => JSON.stringify([{ sessionId: "s", clientRequestId: "r", flowId: "bad", createdAt: clock, message: "PRIVATE" }]), write() {} }, () => clock, () => "clean");
  assert.equal(malformed("s", "r").flow_id, "clean");
  const unavailable = createStudyDiagnosticFlows(storage, () => clock, () => null);
  assert.equal(unavailable("new", "new").flow_id, null);
});

test("Study JSON/attachment sends and operation query keep flow with fresh request actions and pages", async () => {
  const original = globalThis.fetch, sent = [];
  const page = registerDiagnosticPage("/study");
  let replacement;
  try {
    globalThis.fetch = async (url, init) => { sent.push({ url, headers: new Headers(init.headers) }); return Response.json(null, { headers: { "X-Request-ID": `study-${sent.length}` } }); };
    const input = { sessionId: "diagnostic-session", clientRequestId: "diagnostic-chat", expectedSessionRevision: 1, message: "PRIVATE_MESSAGE" };
    await assert.rejects(sendStudyMessage(input));
    await assert.rejects(sendStudyMessage({ ...input, attachments: [new File(["PRIVATE_ATTACHMENT"], "private.txt")] }));
    replacement = registerDiagnosticPage("/study"); page.dispose();
    await assert.rejects(getStudyChatOperation(input));
    assert.equal(new Set(sent.map(item => item.headers.get("X-Debug-Flow-Id"))).size, 1);
    assert.ok(sent[0].headers.get("X-Debug-Flow-Id"));
    assert.equal(new Set(sent.map(item => item.headers.get("X-Debug-Action-Id"))).size, 3);
    assert.equal(sent[0].headers.get("X-Debug-Page-View-Id"), page.id);
    assert.equal(sent[2].headers.get("X-Debug-Page-View-Id"), replacement.id);
    assert.ok(sent[1].url.endsWith("chat-with-attachments"));
    const events = diagnosticSnapshot().events.filter(item => /^study-[123]$/.test(item.request_id || ""));
    assert.ok(!JSON.stringify(events).includes("PRIVATE"));
  } finally { globalThis.fetch = original; page.dispose(); replacement?.dispose(); }
});


test("question attempt and persisted Session read-back share context even when read-back decoding fails", async () => {
  const original = globalThis.fetch, calls = [], page = registerDiagnosticPage("/study");
  let replacement;
  try {
    globalThis.fetch = async (url, init) => {
      calls.push({ url, headers: new Headers(init.headers) });
      if (calls.length === 1) {
        replacement = registerDiagnosticPage("/plan"); page.dispose();
        return Response.json({ schema_version: "study-question-attempt-response-v1", attempt_id: "a", client_attempt_id: "ca", session_id: "s", turn_id: "t", submitted_answer: "PRIVATE_ANSWER", is_correct: true, feedback_text: "feedback", explanation: "PRIVATE_GRADING", before_revision: 1, committed_revision: 2, committed_at: "2026-09-10T00:00:00Z" }, { headers: { "X-Request-ID": "question-post" } });
      }
      return Response.json(null, { headers: { "X-Request-ID": "question-readback" } });
    };
    await assert.rejects(submitStudyQuestionAttempt({ sessionId: "s", turnId: "t", clientAttemptId: "ca", expectedSessionRevision: 1, submittedAnswer: "PRIVATE_ANSWER" }));
    assert.equal(calls.length, 2);
    for (const header of ["X-Debug-Flow-Id", "X-Debug-Action-Id", "X-Debug-Page-View-Id"]) {
      assert.ok(calls[0].headers.get(header));
      assert.equal(calls[0].headers.get(header), calls[1].headers.get(header));
    }
    const events = diagnosticSnapshot().events.filter(item => item.request_id?.startsWith("question-"));
    assert.ok(events.some(item => item.name === "decode_failed" && item.request_id === "question-readback"));
    assert.ok(!JSON.stringify(events).includes("PRIVATE"));
  } finally { globalThis.fetch = original; page.dispose(); replacement?.dispose(); }
});
