import assert from "node:assert/strict";
import test from "node:test";
import {
  diagnosticBufferEvictions,
  diagnosticSnapshot,
  emitDiagnostic,
  flushDiagnostics,
  subscribeDiagnosticBufferEvictions,
} from "../lib/diagnostics.ts";

test("offline buffer evictions are live and are not mixed with server drops", async (t) => {
  const emptyContext = {
    client_instance_id: null,
    page_view_id: null,
    flow_id: null,
    action_id: null,
  };
  const fields = {
    request_id: null,
    duration_ms: null,
    status_code: null,
    method: null,
  };
  const observed: number[] = [];
  const unsubscribe = subscribeDiagnosticBufferEvictions(() => {
    observed.push(diagnosticBufferEvictions());
  });
  t.after(unsubscribe);
  const mock = t.mock.method(globalThis, "fetch", async () => {
    throw new TypeError("synthetic offline transport");
  });
  for (let i = 0; i < 1000; i++) emitDiagnostic("page_entered", emptyContext, fields);
  assert.equal(diagnosticBufferEvictions(), 0);
  await flushDiagnostics("https://diagnostics.invalid");
  assert.equal(diagnosticSnapshot().pending, 1000);
  emitDiagnostic("page_entered", emptyContext, fields);
  assert.deepEqual(observed, [1]);
  assert.equal(diagnosticSnapshot().pending, 1000);
  mock.mock.mockImplementation(async () => Response.json({ accepted: 93, dropped: 7 }));
  await flushDiagnostics("https://diagnostics.invalid");
  assert.equal(diagnosticSnapshot().pending, 900);
  assert.equal(diagnosticSnapshot().dropped, 8);
  assert.equal(diagnosticBufferEvictions(), 1);
  assert.deepEqual(observed, [1]);
});
