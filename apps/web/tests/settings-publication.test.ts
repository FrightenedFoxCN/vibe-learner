import assert from "node:assert/strict";
import { setImmediate } from "node:timers/promises";
import test from "node:test";
import {
  NUMERIC_SETTING_CONFIGS,
  parseNumericSetting,
} from "../components/settings/settings-utils.ts";
import type { RuntimeSettings } from "@vibe-learner/shared";

import {
  resolveSettingsPublication,
  type SettingsForm,
} from "../components/settings/settings-publication.ts";
import { SettingsSaveCoordinator } from "../lib/settings-save-coordinator.ts";
import { SettingsWriteHandoff } from "../lib/settings-write-handoff.ts";
import {
  buildNumericDrafts,
  buildRuntimeSettingsPatch,
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

test("settings numeric input rejects blank, coercions, fractions for integers, and overflow", () => {
  const tokens = NUMERIC_SETTING_CONFIGS.openaiChatMaxTokens;
  const temperature = NUMERIC_SETTING_CONFIGS.openaiChatTemperature;
  for (const draft of [
    "",
    "  ",
    "NaN",
    "Infinity",
    "0x100",
    "1e2",
    "63",
    "16385",
    "99.2",
    "9007199254740993",
  ]) {
    assert.equal(parseNumericSetting(draft, tokens), null, draft);
  }
  assert.equal(parseNumericSetting("64", tokens), 64);
  assert.equal(parseNumericSetting("16384", tokens), 16384);
  assert.equal(parseNumericSetting("0", temperature), 0);
  assert.equal(parseNumericSetting(".35", temperature), 0.35);
  assert.equal(parseNumericSetting("2", temperature), 2);
  assert.equal(parseNumericSetting("2.01", temperature), null);
});

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

for (const desktop of [false, true]) {
  test(`quick remount waits for all outgoing receipts before editing another field (desktop: ${desktop})`, async () => {
    const handoff = new SettingsWriteHandoff();
    let confirmed = submitted;
    const persisted: ReturnType<typeof buildRuntimeSettingsPatch>[] = [];
    const receipts: ((settings: RuntimeSettings) => void)[] = [];
    const readiness: boolean[] = [];
    handoff.subscribe(() => readiness.push(handoff.isPending()));

    function mountEditor() {
      const baseline = handoff.readBaseline(() => confirmed);
      if (!baseline) return null;
      let form: SettingsForm = {
        settings: baseline,
        numericDrafts: buildNumericDrafts(baseline),
      };
      const coordinator = new SettingsSaveCoordinator<RuntimeSettings>(
        {
          serialize: serializeSettings,
          persist: (snapshot) => {
            persisted.push(
              buildRuntimeSettingsPatch(snapshot, { includeSecrets: !desktop }),
            );
            return new Promise((resolve) => receipts.push(resolve));
          },
          saved: (settings, submittedKey) => {
            const publication = resolveSettingsPublication(form, {
              kind: "autosave",
              settings,
              submittedKey,
            });
            form = publication.form;
            if (publication.runtimeSettings) confirmed = publication.runtimeSettings;
          },
          status: () => {},
        },
        900,
      );
      coordinator.acceptSaved(baseline);
      return {
        coordinator,
        edit(patch: Partial<RuntimeSettings>) {
          const settings = { ...(form.settings ?? baseline), ...patch };
          form = { ...form, settings };
          coordinator.edit(settings);
        },
        unmount() {
          const completion = coordinator.flush();
          if (completion) handoff.track(completion);
        },
      };
    }

    const oldEditor = mountEditor();
    assert.ok(oldEditor);
    oldEditor.edit({ openaiChatModel: "  first edit  " });
    void oldEditor.coordinator.flush();
    oldEditor.edit({ openaiChatModel: "  latest edit  " });
    oldEditor.unmount();
    assert.equal(mountEditor(), null);
    assert.equal(persisted.length, 1);
    assert.equal(confirmed, submitted);

    receipts[0]({ ...submitted, openaiChatModel: "first edit" });
    await setImmediate();
    assert.equal(mountEditor(), null, "the queued write still owns the handoff");
    assert.equal(persisted.length, 2);
    receipts[1]({ ...result, openaiChatModel: "latest edit" });
    await setImmediate();
    assert.deepEqual(readiness, [true, false]);

    const returningEditor = mountEditor();
    assert.ok(returningEditor);
    returningEditor.edit({ showDebugInfo: true });
    const save = returningEditor.coordinator.flush();
    assert.equal(persisted.length, 3);
    assert.equal(persisted[2].openaiChatModel, "latest edit");
    assert.equal(persisted[2].openaiTimeoutSeconds, result.openaiTimeoutSeconds);
    assert.equal(persisted[2].showDebugInfo, true);
    assert.equal(
      persisted[2].openaiApiKey,
      desktop ? undefined : submitted.openaiApiKey,
    );
    receipts[2]({ ...confirmed, showDebugInfo: true });
    await save;
    assert.equal(confirmed.openaiChatModel, "latest edit");
    assert.equal(confirmed.showDebugInfo, true);
  });
}

test("a rejected outgoing write still signals admission after a batched busy interval", async () => {
  const handoff = new SettingsWriteHandoff();
  const original = handoff.getSnapshot();
  let reject!: (error: Error) => void;
  const completion = new Promise<void>((_resolve, fail) => {
    reject = fail;
  });
  handoff.track(completion);
  assert.equal(
    handoff.readBaseline(() => submitted),
    null,
  );
  reject(new Error("synthetic missing receipt"));
  await setImmediate();
  assert.equal(handoff.getSnapshot().pending, false);
  assert.notEqual(handoff.getSnapshot(), original);
  assert.equal(
    handoff.readBaseline(() => submitted),
    submitted,
  );
});
