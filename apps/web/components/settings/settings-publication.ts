import type { RuntimeSettings } from "@vibe-learner/shared";

import {
  buildNumericDrafts,
  serializeSettings,
  type NumericDraftState,
  type NumericSettingKey,
} from "./settings-utils.ts";

export interface SettingsForm {
  settings: RuntimeSettings | null;
  numericDrafts: NumericDraftState;
}

export type SettingsPublication =
  | { kind: "initial" | "vault"; settings: RuntimeSettings }
  | { kind: "autosave"; settings: RuntimeSettings; submittedKey: string };

export function resolveSettingsPublication(
  current: SettingsForm,
  publication: SettingsPublication,
) {
  const { settings: next } = publication;
  const effects = {
    runtimeSettings: publication.kind === "initial" ? null : next,
    baseline: publication.kind === "autosave" ? null : next,
    lastSavedAt: next.updatedAt,
  };
  if (publication.kind !== "autosave") {
    // Initial load and explicit Vault transitions replace the whole editor.
    return {
      ...effects,
      form: { settings: next, numericDrafts: buildNumericDrafts(next) },
    };
  }
  if (
    !current.settings ||
    serializeSettings(current.settings) !== publication.submittedKey
  ) {
    // A durable result is valid for the runtime even when the editor moved on.
    return { ...effects, form: current };
  }

  const numericDrafts = buildNumericDrafts(next);
  for (const key of Object.keys(numericDrafts) as NumericSettingKey[]) {
    // Numeric edits do not enter the submitted snapshot until blur.
    if (current.numericDrafts[key] !== String(current.settings[key])) {
      numericDrafts[key] = current.numericDrafts[key];
    }
  }
  return { ...effects, form: { settings: next, numericDrafts } };
}
