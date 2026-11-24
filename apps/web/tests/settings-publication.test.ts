import assert from "node:assert/strict";
import test from "node:test";
import type { RuntimeSettings } from "@vibe-learner/shared";

import { resolveSettingsPublication } from "../components/settings/settings-publication.ts";
import {
  buildNumericDrafts,
  serializeSettings,
} from "../components/settings/settings-utils.ts";

const submitted: RuntimeSettings = {
  updatedAt: "2025-01-01T00:00:00Z",
  planProvider: "mock",
  openaiApiKey: "synthetic-vault-value",
  openaiApiKeyConfigured: true,
  openaiBaseUrl: "https://model.example.invalid/v1",
  openaiPlanApiKey: "",
  openaiPlanApiKeyConfigured: false,
  openaiPlanBaseUrl: "",
  openaiPlanModel: "synthetic plan model",
  openaiSettingApiKey: "",
  openaiSettingApiKeyConfigured: false,
  openaiSettingBaseUrl: "",
  openaiSettingModel: "synthetic setting model",
  openaiSettingWebSearchEnabled: false,
  openaiChatApiKey: "",
  openaiChatApiKeyConfigured: false,
  openaiChatBaseUrl: "",
  openaiChatModel: "synthetic chat model",
  openaiChatTemperature: 0.3,
  openaiSettingTemperature: 0.3,
  openaiSettingMaxTokens: 1024,
  openaiChatMaxTokens: 1024,
  openaiChatHistoryMessages: 10,
  openaiChatToolMaxRounds: 3,
  openaiEmbeddingModel: "synthetic embedding model",
  openaiChatModelMultimodal: false,
  openaiTimeoutSeconds: 60,
  openaiPlanModelMultimodal: false,
  openaiPlanFallbackModel: "",
  openaiPlanFallbackDisableTools: true,
  showDebugInfo: false,
};
const result: RuntimeSettings = {
  ...submitted,
  updatedAt: "2025-01-01T00:00:01Z",
  openaiTimeoutSeconds: 45,
  openaiChatTemperature: 0.4,
};
const submittedForm = {
  settings: submitted,
  numericDrafts: buildNumericDrafts(submitted),
};
const autosave = {
  kind: "autosave",
  submittedKey: serializeSettings(submitted),
  settings: result,
} as const;

test("matching autosave accepts the canonical result, without re-enqueuing the baseline", () => {
  assert.deepEqual(resolveSettingsPublication(submittedForm, autosave), {
    form: { settings: result, numericDrafts: buildNumericDrafts(result) },
    runtimeSettings: result,
    baseline: null,
    lastSavedAt: result.updatedAt,
  });
});

test("slow autosave publishes the durable result but does not overwrite newer settings", () => {
  const current = {
    ...submittedForm,
    settings: { ...submitted, openaiChatModel: "new input" },
  };
  const publication = resolveSettingsPublication(current, autosave);
  assert.equal(publication.form, current);
  assert.equal(publication.runtimeSettings, result);
  assert.equal(publication.lastSavedAt, result.updatedAt);
  assert.equal(publication.baseline, null);
});

test("an in-progress numeric edit survives the receipt for an otherwise matching settings snapshot", () => {
  const current = {
    ...submittedForm,
    numericDrafts: { ...submittedForm.numericDrafts, openaiChatTemperature: "0." },
  };
  const publication = resolveSettingsPublication(current, autosave);
  assert.equal(publication.form.settings, result);
  assert.equal(publication.form.numericDrafts.openaiChatTemperature, "0.");
  assert.equal(publication.form.numericDrafts.openaiTimeoutSeconds, "45");
  assert.equal(current.numericDrafts.openaiTimeoutSeconds, "60");
});

test("initial load uses the provider snapshot without publishing back to the provider", () => {
  const current = { ...submittedForm, settings: null };
  assert.deepEqual(
    resolveSettingsPublication(current, { kind: "initial", settings: result }),
    {
      form: { settings: result, numericDrafts: buildNumericDrafts(result) },
      runtimeSettings: null,
      baseline: result,
      lastSavedAt: result.updatedAt,
    },
  );
});

test("explicit Vault reset replaces editable settings and raw drafts with the readback", () => {
  const masked = { ...result, openaiApiKey: "", openaiApiKeyConfigured: false };
  const current = {
    ...submittedForm,
    settings: { ...submitted, openaiChatModel: "abandoned input" },
    numericDrafts: { ...submittedForm.numericDrafts, openaiChatTemperature: "0." },
  };
  assert.deepEqual(
    resolveSettingsPublication(current, { kind: "vault", settings: masked }),
    {
      form: { settings: masked, numericDrafts: buildNumericDrafts(masked) },
      runtimeSettings: masked,
      baseline: masked,
      lastSavedAt: masked.updatedAt,
    },
  );
});
