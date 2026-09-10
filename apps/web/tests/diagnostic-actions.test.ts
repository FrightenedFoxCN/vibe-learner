import assert from "node:assert/strict";
import test from "node:test";
import { observeLocalAction } from "../lib/diagnostic-actions.ts";
import { diagnosticSnapshot, registerDiagnosticPage } from "../lib/diagnostics.ts";
import { readBoundedJsonImport, JSON_IMPORT_MAX_BYTES } from "../lib/bounded-json-import.ts";
import { SettingsSaveCoordinator } from "../lib/settings-save-coordinator.ts";

const named = (name: string) => diagnosticSnapshot().events.filter(event => event.action_name === name);

test("JSON import records read completion and size/parse rejection without content", async () => {
  const payload = { password: "PRIVATE_JSON_SENTINEL" };
  assert.deepEqual(await readBoundedJsonImport({ size: 8, text: async () => JSON.stringify(payload) }, "persona"), payload);
  assert.equal(named("json_import_read_persona").at(-1)?.name, "action_finished");
  let read = false;
  await assert.rejects(readBoundedJsonImport({ size: JSON_IMPORT_MAX_BYTES + 1, text: async () => { read = true; return ""; } }, "scene"));
  assert.equal(read, false);
  assert.equal(named("json_import_read_scene").at(-1)?.name, "action_failed");
  await assert.rejects(readBoundedJsonImport({ size: 10, text: async () => "PRIVATE_PARSE_SENTINEL" }, "scene"));
  assert.ok(!JSON.stringify(diagnosticSnapshot()).includes("PRIVATE"));
});

test("export cancellation and Vault failure preserve original result and exception", async () => {
  const result = await observeLocalAction("json_export_handoff", async () => false, { cancelled: saved => !saved });
  assert.equal(result, false);
  assert.equal(named("json_export_handoff").at(-1)?.name, "action_cancelled");
  const error = new Error("PRIVATE_PASSWORD_SENTINEL");
  await assert.rejects(observeLocalAction("vault_unlock", async () => { throw error; }), value => value === error);
  assert.equal(named("vault_unlock").at(-1)?.name, "action_failed");
  assert.ok(!JSON.stringify(diagnosticSnapshot()).includes("PRIVATE_PASSWORD_SENTINEL"));
});

test("Settings draining keeps captured context while the current page changes", async () => {
  const firstPage = registerDiagnosticPage();
  let finish!: (value: { key: string }) => void;
  let submittedContext: any;
  let notify!: () => void;
  const saved = new Promise<void>(resolve => { notify = resolve; });
  const coordinator = new SettingsSaveCoordinator({
    serialize: (value: { key: string }) => value.key,
    persist: (_value, context) => { submittedContext = context; return new Promise(resolve => { finish = resolve; }); },
    saved: () => notify(), status: () => {},
  }, 0, { schedule: () => 1, cancel: () => {} });
  coordinator.edit({ key: "PRIVATE_SETTINGS_SENTINEL" });
  coordinator.flush();
  const next = registerDiagnosticPage();
  firstPage.dispose();
  finish({ key: "PRIVATE_SETTINGS_SENTINEL" });
  await saved;
  const events = named("settings_save").filter(event => event.action_id === submittedContext.action_id);
  assert.deepEqual(events.map(event => event.name), ["action_started", "action_finished"]);
  assert.ok(events.every(event => event.page_view_id === firstPage.id));
  assert.equal(events[0].span_id, events[1].span_id);
  assert.ok(!JSON.stringify(events).includes("PRIVATE_SETTINGS_SENTINEL"));
  next.dispose();
});

test("diagnostic ID allocation failure cannot block a local action", async () => {
  const original = Object.getOwnPropertyDescriptor(globalThis, "crypto");
  Object.defineProperty(globalThis, "crypto", { configurable: true, value: { randomUUID() { throw new Error("diagnostic entropy failure"); } } });
  try {
    assert.equal(await observeLocalAction("vault_lock", async () => "business-completed"), "business-completed");
    assert.ok(diagnosticSnapshot().dropped > 0);
  } finally {
    if (original) Object.defineProperty(globalThis, "crypto", original);
  }
});

test("Settings and nested Vault spans share action but retain parentage", async () => {
  await observeLocalAction("settings_save", context => observeLocalAction("vault_save_secrets", async () => "saved", { context }));
  const parent = named("settings_save").at(-1)!;
  const child = named("vault_save_secrets").at(-1)!;
  assert.equal(child.action_id, parent.action_id);
  assert.equal(child.parent_span_id, parent.span_id);
  assert.notEqual(child.span_id, parent.span_id);
});
