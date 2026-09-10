import { readFileSync } from "node:fs";
import { classifyDiagnostic } from "../../../packages/shared/src/diagnostic.ts";
import assert from "node:assert/strict";
import test from "node:test";
import { diagnosticContext, diagnosticFetch, diagnosticSnapshot, emitDiagnostic, flushDiagnostics, registerDiagnosticPage } from "../lib/diagnostics.ts";

test("old page cleanup cannot erase the replacement view", () => {
  const old = registerDiagnosticPage();
  const next = registerDiagnosticPage();
  old.dispose();
  assert.equal(diagnosticContext().page_view_id, next.id);
  next.dispose();
});

test("headers and body completion remain separate and share diagnostic identity", async () => {
  const original = globalThis.fetch;
  let finish!: () => void;
  globalThis.fetch = async (_input, init) => {
    assert.ok(new Headers(init?.headers).get("X-Debug-Action-Id"));
    return new Response(new ReadableStream({ start(controller) {
      controller.enqueue(new TextEncoder().encode("payload"));
      finish = () => controller.close();
    } }), { headers: { "X-Request-ID": "server_request" } });
  };
  try {
    const context = diagnosticContext("persona_flow");
    const response = await diagnosticFetch("http://service/personas?secret=hidden", undefined, context);
    const related = () => diagnosticSnapshot().events.filter(event => event.action_id === context.action_id);
    assert.deepEqual(related().map(event => event.name), ["request_started", "response_headers"]);
    finish();
    assert.equal(await response.text(), "payload");
    assert.equal(related().at(-1)?.name, "request_finished");
    assert.equal(related().at(-1)?.request_id, "server_request");
    assert.ok(!JSON.stringify(related()).includes("secret"));
  } finally { globalThis.fetch = original; }
});

test("offline uploads retain identities; buffers stay bounded and report losses", async () => {
  const original = globalThis.fetch;
  const fields = { request_id: null, duration_ms: null, status_code: null, method: null };
  for (let i = 0; i < 1100; i++) emitDiagnostic("request_started", diagnosticContext(), fields);
  assert.equal(diagnosticSnapshot().events.length, 1000);
  assert.equal(diagnosticSnapshot().pending, 1000);
  assert.ok(diagnosticSnapshot().dropped >= 100);
  const batches: string[] = [];
  globalThis.fetch = async (_input, init) => {
    batches.push(String(init?.body));
    if (batches.length === 1) throw new Error("offline");
    return Response.json({ accepted: 100, dropped: 0 });
  };
  try {
    await flushDiagnostics("http://service");
    await flushDiagnostics("http://service");
    assert.equal(batches[0], batches[1]);
    assert.equal(diagnosticSnapshot().pending, 900);
  } finally { globalThis.fetch = original; }
});

test("shared diagnostic classification stays aligned and distinguishes HTTP failure", () => {
  const cases = JSON.parse(readFileSync(new URL("../../../packages/shared/fixtures/diagnostics/event-classification-v1.json", import.meta.url), "utf8"));
  for (const item of cases) assert.deepEqual(classifyDiagnostic(item.name, item.status_code), item.classification);
  assert.equal(classifyDiagnostic("request_finished", 200).outcome, "completed");
  assert.equal(classifyDiagnostic("request_finished", 503).outcome, "failed");
});
