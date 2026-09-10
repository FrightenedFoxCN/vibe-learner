import assert from "node:assert/strict";
import { test } from "node:test";
import { buildSettingsDebugSnapshot } from "../components/settings/settings-debug-snapshot.ts";

const secret = "PRIVATE_SETTINGS_SENTINEL";
function fixture() {
  return {
    settings: {
      planProvider: "litellm", showDebugInfo: true,
      openaiApiKey: secret, openaiPlanApiKey: secret, openaiChatApiKey: secret, openaiSettingApiKey: secret,
      openaiApiKeyConfigured: true, openaiBaseUrl: `https://user:${secret}@example.invalid/${secret}`,
      openaiPlanModel: secret, openaiChatModel: secret, openaiPlanFallbackModel: secret,
      updatedAt: secret, futureSecretField: secret, openaiTimeoutSeconds: 30
    },
    loading: false, loadError: secret, saveError: secret, lastSavedAt: secret, savePhase: "error",
    numericDrafts: { openaiTimeoutSeconds: secret },
    desktopSecurity: { enabled: true, vaultState: "unlocked", busy: false, error: secret, startupError: secret, vaultPath: secret },
    probeState: Object.fromEntries(["global", "plan", "setting", "chat"].map(scope => [scope, {
      loading: false, available: true, models: [secret], capabilities: { [secret]: { note: secret } },
      featureReadiness: { plan: { status: "ready", model: secret, note: secret, code: secret, parameterAdjustments: [secret] } },
      error: secret, endpointKey: `https://example.invalid::${secret}`, lastCheckedAt: secret, sharedFromScope: null,
      futureSecretField: secret
    }]))
  };
}

test("Settings debug only exposes reviewed state, never credentials, endpoints, drafts or provider/error text", () => {
  const state = fixture();
  const original = JSON.stringify(state);
  const snapshot = buildSettingsDebugSnapshot(state);
  const serialized = JSON.stringify(snapshot);
  assert.ok(!serialized.includes(secret));
  for (const forbidden of ["endpointKey", "vaultPath", "futureSecretField", "parameterAdjustments", "https://"]) {
    assert.ok(!serialized.includes(forbidden), forbidden);
  }
  assert.equal(snapshot.error, "设置加载失败；设置保存失败");
  assert.equal(snapshot.details[0].value.keysConfigured.global, true);
  assert.deepEqual(snapshot.details[1].value.openaiTimeoutSeconds, { committed: 30, draftValid: false, hasDraft: true });
  assert.equal(snapshot.details[2].value.plan.modelCount, 1);
  assert.equal(snapshot.details[2].value.plan.features.plan, "ready");
  assert.equal(JSON.stringify(state), original);
});

test("unknown enum values and malformed numeric settings cannot echo input text", () => {
  const state = fixture();
  state.savePhase = secret;
  state.settings.planProvider = secret;
  state.settings.openaiTimeoutSeconds = secret;
  state.desktopSecurity.vaultState = secret;
  state.probeState.global.sharedFromScope = secret;
  state.probeState.global.featureReadiness.plan.status = secret;
  assert.ok(!JSON.stringify(buildSettingsDebugSnapshot(state)).includes(secret));
  state.settings = null;
  assert.equal(buildSettingsDebugSnapshot(state).details[0].value, null);
});
