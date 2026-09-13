import assert from "node:assert/strict";
import test from "node:test";

import type { RuntimeCapabilitySignal, RuntimeSettings } from "@vibe-learner/shared";
import { formatCapabilityDecisionNote, resolveProbeConflictScopes } from "../components/settings/settings-utils.ts";

function settings(overrides: Record<string, unknown> = {}): RuntimeSettings {
  return {
    openaiApiKey: "shared-key", openaiBaseUrl: "https://shared.example/v1",
    openaiPlanApiKey: "", openaiPlanBaseUrl: "",
    openaiSettingApiKey: "setting-key", openaiSettingBaseUrl: "https://setting.example/v1",
    openaiChatApiKey: "", openaiChatBaseUrl: "", ...overrides,
  } as unknown as RuntimeSettings;
}

test("Settings probes lock only scopes sharing the effective endpoint and credential", () => {
  assert.deepEqual(resolveProbeConflictScopes(settings(), "plan"), ["global", "plan", "chat"]);
  assert.deepEqual(resolveProbeConflictScopes(settings(), "setting"), ["setting"]);
  assert.deepEqual(resolveProbeConflictScopes(settings({ openaiPlanApiKey: "plan-key" }), "plan"), ["plan"]);
  assert.deepEqual(resolveProbeConflictScopes(settings({ openaiApiKey: "", openaiPlanApiKey: "" }), "plan"), ["plan"]);
});

test("unknown capability copy preserves manual choice and warns about request failure", () => {
  const unknown = { status: "unknown", source: "unavailable", note: "" } as RuntimeCapabilitySignal;
  const note = formatCapabilityDecisionNote(unknown);
  assert.match(note, /不代表支持或不支持/);
  assert.match(note, /手工决定/);
  assert.match(note, /请求失败/);
  assert.equal(
    formatCapabilityDecisionNote({ ...unknown, note: "Provider did not disclose metadata." }),
    "Provider did not disclose metadata.",
  );
  assert.equal(formatCapabilityDecisionNote({ status: "supported", source: "metadata", note: "" }), "");
});
