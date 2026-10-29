import type { PlanningIntent } from "@vibe-learner/shared";
import { isOutputLanguagePreference } from "@vibe-learner/shared/output-language";

export const OUTPUT_LANGUAGE_OPTIONS = [
  ["auto", "自动"],
  ["zh-CN", "简体中文"],
  ["zh-TW", "繁體中文"],
  ["en", "English"],
  ["fr", "Français"],
  ["de", "Deutsch"],
  ["es", "Español"],
  ["ja", "日本語"],
  ["ko", "한국어"],
  ["pt", "Português"],
  ["it", "Italiano"],
  ["ru", "Русский"],
  ["ar", "العربية"],
] as const;

export function outputLanguageError(value: string): string {
  return isOutputLanguagePreference(value)
    ? ""
    : "请选择输出语言，或填写语言标签，例如 fr-CA。";
}

export function withOutputLanguage(
  intent: PlanningIntent | undefined,
  language: string,
): PlanningIntent | undefined {
  if (outputLanguageError(language)) throw new Error(outputLanguageError(language));
  if (language.toLowerCase() === "auto") return intent;
  return {
    schemaVersion: "planning-intent-v1",
    pdfPageRanges: { status: "unknown", value: null },
    outlineTargets: { status: "unknown", value: null },
    sessionCount: { status: "unknown", value: null },
    minutesPerSession: { status: "unknown", value: null },
    ...intent,
    outputLanguage: { status: "user_explicit", value: language },
  };
}
