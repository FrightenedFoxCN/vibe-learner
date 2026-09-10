import { dom } from "./support/dom.js";
import assert from "node:assert/strict";
import { after, test } from "node:test";
import { importJsonDraft } from "../lib/bounded-json-import.ts";
import { diagnosticSnapshot, registerDiagnosticPage } from "../lib/diagnostics.ts";
import { normalizeImportedPersonaConfig } from "../lib/persona-draft.ts";
import { parseSceneImportPayload } from "../lib/scene-editor-model.ts";

after(() => dom.window.close());
const file = value => ({ size: 100, text: async () => JSON.stringify(value) });
const cases = [
  ["persona", normalizeImportedPersonaConfig, { name: "PRIVATE_IMPORT", systemPrompt: "PRIVATE_PROMPT", slots: [] }],
  ["scene", value => parseSceneImportPayload(value, true), { sceneName: "PRIVATE_IMPORT", sceneLayers: [{ title: "PRIVATE_LAYER", children: [] }] }]
];
for (const [kind, decode, valid] of cases) {
  test(`${kind} imports distinguish read success from domain validation and draft application`, async () => {
    let applied;
    assert.equal(await importJsonDraft(file(valid), kind, decode, value => { applied = value; return true; }), true);
    assert.ok(applied);
    let invalidApplied = false;
    await assert.rejects(importJsonDraft(file(null), kind, decode, () => { invalidApplied = true; return true; }));
    assert.equal(invalidApplied, false);
    const records = diagnosticSnapshot().events.filter(e => e.action_name === `json_import_${kind}_draft`);
    assert.deepEqual(records.map(e => e.name), ["action_started", "action_finished", "action_started", "action_failed"]);
    for (const parent of records.filter(e => e.name === "action_started")) {
      const children = diagnosticSnapshot().events.filter(e => e.parent_span_id === parent.span_id);
      assert.deepEqual(children.map(e => e.name), ["action_started", "action_finished"]);
      assert.ok(children.every(e => e.action_id === parent.action_id && e.flow_id === parent.flow_id));
    }
    assert.ok(!JSON.stringify(diagnosticSnapshot()).includes("PRIVATE"));
  });
}

test("a superseded import is cancelled on its original page and does not apply its draft", async () => {
  const page = registerDiagnosticPage('/scene-setup');
  let resolve;
  let current = true;
  let applied = false;
  const pending = importJsonDraft({ size: 10, text: () => new Promise(r => { resolve = r; }) }, "scene",
    value => parseSceneImportPayload(value, true), () => { if (!current) return false; applied = true; return true; });
  current = false;
  const replacement = registerDiagnosticPage('/settings');
  page.dispose();
  resolve(JSON.stringify(cases[1][2]));
  assert.equal(await pending, false);
  assert.equal(applied, false);
  const end = diagnosticSnapshot().events.at(-1);
  assert.equal(end.name, "action_cancelled");
  assert.equal(end.page_view_id, page.id);
  assert.equal(end.action_name, "json_import_scene_draft");
  replacement.dispose();
});
