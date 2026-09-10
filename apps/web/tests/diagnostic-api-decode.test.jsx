import { dom } from "./support/dom.js";
import assert from "node:assert/strict";
import { after, test } from "node:test";
import { listPersonas, listDocuments, listLearningPlans, listSceneLibrary, getStudySession, listTavernRooms, runTavernTurn, processDocumentStream, createLearningPlanStream } from "../lib/api.ts";
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
