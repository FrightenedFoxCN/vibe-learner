import {
  CHARACTER_ACTIONS,
  CHARACTER_EMOTIONS,
} from "@vibe-learner/shared/character";
import type {
  CharacterAction,
  CharacterEmotion,
  CreatePersonaInput,
  PersonaProfile,
  PersonaSlot,
  SpeechStyle,
} from "@vibe-learner/shared";

export interface PersonaDraft {
  name: string;
  summary: string;
  relationship: string;
  learnerAddress: string;
  systemPrompt: string;
  referenceHints: string[];
  slots: PersonaSlot[];
  availableEmotionsText: string;
  availableActionsText: string;
  defaultSpeechStyle: SpeechStyle;
}

export const EMPTY_PERSONA_DRAFT: PersonaDraft = {
  name: "",
  summary: "",
  relationship: "",
  learnerAddress: "",
  systemPrompt: "",
  referenceHints: [],
  slots: [],
  availableEmotionsText: CHARACTER_EMOTIONS.join(", "),
  availableActionsText: CHARACTER_ACTIONS.join(", "),
  defaultSpeechStyle: "warm",
};

export function clampPersonaWeight(value: number): number {
  const normalized = Number.isFinite(value) ? Math.round(value) : 50;
  return Math.max(0, Math.min(100, normalized));
}

export function personaToDraft(persona: PersonaProfile): PersonaDraft {
  return {
    name: persona.name,
    summary: persona.summary,
    relationship: persona.relationship,
    learnerAddress: persona.learnerAddress,
    systemPrompt: persona.systemPrompt,
    referenceHints: persona.referenceHints ?? [],
    slots: (persona.slots ?? []).map((slot, index) => ({
      ...slot,
      weight: slot.weight ?? 50,
      locked: slot.locked ?? false,
      sortOrder: slot.sortOrder ?? index * 10,
    })),
    availableEmotionsText: persona.availableEmotions.join(", "),
    availableActionsText: persona.availableActions.join(", "),
    defaultSpeechStyle: persona.defaultSpeechStyle,
  };
}

export function draftToCreatePersonaInput(draft: PersonaDraft): CreatePersonaInput {
  return {
    name: draft.name.trim(),
    summary: draft.summary.trim(),
    relationship: draft.relationship.trim(),
    learnerAddress: draft.learnerAddress.trim(),
    systemPrompt: draft.systemPrompt.trim(),
    referenceHints: mergeReferenceHints([], draft.referenceHints),
    slots: [...draft.slots]
      .sort((left, right) => {
        const leftOrder = left.sortOrder ?? 0;
        const rightOrder = right.sortOrder ?? 0;
        if (leftOrder !== rightOrder) {
          return leftOrder - rightOrder;
        }
        return (right.weight ?? 50) - (left.weight ?? 50);
      })
      .map((slot, index) => ({
        ...slot,
        kind: slot.kind.trim() || "custom",
        label: slot.label.trim(),
        content: slot.content.trim(),
        weight: clampPersonaWeight(Number(slot.weight ?? 50)),
        locked: slot.locked ?? false,
        sortOrder: index * 10,
      })),
    availableEmotions: coercePersonaEmotions(draft.availableEmotionsText),
    availableActions: coercePersonaActions(draft.availableActionsText),
    defaultSpeechStyle: draft.defaultSpeechStyle,
  };
}

export function createPersonaInputToDraft(snapshot: CreatePersonaInput): PersonaDraft {
  return {
    name: snapshot.name,
    summary: snapshot.summary,
    relationship: snapshot.relationship,
    learnerAddress: snapshot.learnerAddress,
    systemPrompt: snapshot.systemPrompt,
    referenceHints: mergeReferenceHints([], snapshot.referenceHints ?? []),
    slots: (snapshot.slots ?? []).map((slot, index) => ({
      ...slot,
      weight: clampPersonaWeight(Number(slot.weight ?? 50)),
      locked: slot.locked ?? false,
      sortOrder: slot.sortOrder ?? index * 10,
    })),
    availableEmotionsText: (snapshot.availableEmotions ?? CHARACTER_EMOTIONS).join(", "),
    availableActionsText: (snapshot.availableActions ?? CHARACTER_ACTIONS).join(", "),
    defaultSpeechStyle: snapshot.defaultSpeechStyle ?? "warm",
  };
}

export function personaDraftFingerprint(draft: PersonaDraft): string {
  return JSON.stringify(draftToCreatePersonaInput(draft));
}

export function duplicatePersonaDraft(draft: PersonaDraft): PersonaDraft {
  const baseName = draft.name.trim() || "未命名人格";
  return {
    ...createPersonaInputToDraft(draftToCreatePersonaInput(draft)),
    name: `${baseName} 副本`,
  };
}

export function mergePersonaAssistSlots(
  currentSlots: PersonaSlot[],
  suggestedSlots: PersonaSlot[],
): PersonaSlot[] {
  const unusedSuggestions = suggestedSlots.map((slot, index) => ({ slot, index, used: false }));
  const merged = currentSlots.map((current, currentIndex) => {
    const exact = unusedSuggestions.find((candidate) => (
      !candidate.used &&
      candidate.slot.kind === current.kind &&
      candidate.slot.label.trim() === current.label.trim()
    ));
    const sameKind = exact ?? unusedSuggestions.find((candidate) => (
      !candidate.used && candidate.slot.kind === current.kind
    ));
    if (sameKind) {
      sameKind.used = true;
    }
    if (current.locked || !sameKind) {
      return {
        ...current,
        weight: current.weight ?? 50,
        locked: current.locked ?? false,
        sortOrder: current.sortOrder ?? currentIndex * 10,
      };
    }
    return {
      ...sameKind.slot,
      weight: current.weight ?? sameKind.slot.weight ?? 50,
      locked: false,
      sortOrder: current.sortOrder ?? sameKind.slot.sortOrder ?? currentIndex * 10,
    };
  });

  for (const candidate of unusedSuggestions) {
    if (!candidate.used) {
      merged.push({
        ...candidate.slot,
        weight: candidate.slot.weight ?? 50,
        locked: candidate.slot.locked ?? false,
        sortOrder: merged.length * 10,
      });
    }
  }
  return merged.map((slot, index) => ({ ...slot, sortOrder: index * 10 }));
}

export function clearPersonaDraftForGeneratedBackfill(draft: PersonaDraft): PersonaDraft {
  return {
    ...draft,
    summary: "",
    relationship: "",
    learnerAddress: "",
    referenceHints: [],
    slots: [],
  };
}

export function mergeReferenceHints(base: string[], incoming: string[]): string[] {
  const seen = new Set<string>();
  const result: string[] = [];
  for (const rawValue of [...base, ...incoming]) {
    const value = rawValue.trim();
    const key = value.toLowerCase();
    if (!value || seen.has(key)) {
      continue;
    }
    seen.add(key);
    result.push(value);
  }
  return result;
}

export function normalizeImportedPersonaConfig(parsed: Record<string, unknown>): CreatePersonaInput {
  const name = requireStringAlias(parsed, ["name"], "name", false).trim();
  if (!name) {
    throw new Error("缺少名称字段（name）");
  }
  const systemPrompt = requireStringAlias(
    parsed,
    ["systemPrompt", "system_prompt"],
    "systemPrompt",
    false,
  ).trim();
  const slots = parseImportedSlots(parsed.slots);
  const referenceHints = parseOptionalStringArrayAlias(
    parsed,
    ["referenceHints", "reference_hints"],
    "referenceHints",
  );
  const availableEmotions = parseOptionalStringArrayAlias(
    parsed,
    ["availableEmotions", "available_emotions"],
    "availableEmotions",
  );
  const availableActions = parseOptionalStringArrayAlias(
    parsed,
    ["availableActions", "available_actions"],
    "availableActions",
  );
  const speechStyle = requireStringAlias(
    parsed,
    ["defaultSpeechStyle", "default_speech_style"],
    "defaultSpeechStyle",
    true,
    "warm",
  ).trim();
  if (!speechStyle) {
    throw new Error("defaultSpeechStyle 不能为空");
  }

  return {
    name,
    summary: requireStringAlias(parsed, ["summary"], "summary", true).trim(),
    relationship: requireStringAlias(
      parsed,
      ["relationship", "relation"],
      "relationship",
      true,
    ).trim(),
    learnerAddress: requireStringAlias(
      parsed,
      ["learnerAddress", "learner_address", "address"],
      "learnerAddress",
      true,
    ).trim(),
    systemPrompt,
    referenceHints,
    slots,
    availableEmotions: availableEmotions?.length ? availableEmotions : undefined,
    availableActions: availableActions?.length ? availableActions : undefined,
    defaultSpeechStyle: speechStyle,
  };
}

function parseImportedSlots(raw: unknown): PersonaSlot[] {
  if (raw === undefined) {
    return [];
  }
  if (!Array.isArray(raw)) {
    throw new Error("slots 必须是数组");
  }
  return raw.map((rawSlot, index) => {
    if (!rawSlot || typeof rawSlot !== "object" || Array.isArray(rawSlot)) {
      throw new Error(`slots[${index}] 必须是对象`);
    }
    const slot = rawSlot as Record<string, unknown>;
    const kind = requireStringAlias(slot, ["kind"], `slots[${index}].kind`, true, "custom").trim();
    if (!kind) {
      throw new Error(`slots[${index}].kind 不能为空`);
    }
    const weight = parseFiniteNumberAlias(slot, ["weight"], `slots[${index}].weight`, 50);
    if (weight < 0 || weight > 100) {
      throw new Error(`slots[${index}].weight 必须在 0–100 之间`);
    }
    const sortOrder = parseFiniteNumberAlias(
      slot,
      ["sortOrder", "sort_order"],
      `slots[${index}].sortOrder`,
      index * 10,
    );
    if (!Number.isInteger(sortOrder) || sortOrder < 0) {
      throw new Error(`slots[${index}].sortOrder 必须是非负整数`);
    }
    const lockedRaw = readAlias(slot, ["locked"]);
    if (lockedRaw !== undefined && typeof lockedRaw !== "boolean") {
      throw new Error(`slots[${index}].locked 必须是布尔值`);
    }
    return {
      kind,
      label: requireStringAlias(slot, ["label"], `slots[${index}].label`, true, kind).trim(),
      content: requireStringAlias(slot, ["content"], `slots[${index}].content`, true).trim(),
      weight,
      locked: lockedRaw ?? false,
      sortOrder,
    };
  });
}

function parseOptionalStringArrayAlias(
  record: Record<string, unknown>,
  aliases: string[],
  path: string,
): string[] | undefined {
  const raw = readAlias(record, aliases);
  if (raw === undefined) {
    return undefined;
  }
  if (!Array.isArray(raw) || raw.some((item) => typeof item !== "string")) {
    throw new Error(`${path} 必须是字符串数组`);
  }
  return mergeReferenceHints([], raw as string[]);
}

function parseFiniteNumberAlias(
  record: Record<string, unknown>,
  aliases: string[],
  path: string,
  fallback: number,
): number {
  const raw = readAlias(record, aliases);
  if (raw === undefined) {
    return fallback;
  }
  if (typeof raw !== "number" || !Number.isFinite(raw)) {
    throw new Error(`${path} 必须是有限数字`);
  }
  return raw;
}

function requireStringAlias(
  record: Record<string, unknown>,
  aliases: string[],
  path: string,
  optional: boolean,
  fallback = "",
): string {
  const raw = readAlias(record, aliases);
  if (raw === undefined && optional) {
    return fallback;
  }
  if (typeof raw !== "string") {
    throw new Error(`${path} 必须是字符串`);
  }
  return raw;
}

function readAlias(record: Record<string, unknown>, aliases: string[]): unknown {
  for (const alias of aliases) {
    if (Object.prototype.hasOwnProperty.call(record, alias)) {
      return record[alias];
    }
  }
  return undefined;
}

function splitCsv(value: string): string[] {
  return value.split(/[,，\n]/).map((item) => item.trim()).filter(Boolean);
}

function coercePersonaEmotions(value: string): CharacterEmotion[] {
  return dedupeCsvValues(splitCsv(value));
}

function coercePersonaActions(value: string): CharacterAction[] {
  return dedupeCsvValues(splitCsv(value));
}

function dedupeCsvValues<T extends string>(values: T[]): T[] {
  const seen = new Set<string>();
  const result: T[] = [];
  for (const value of values) {
    const key = value.toLowerCase();
    if (!seen.has(key)) {
      seen.add(key);
      result.push(value);
    }
  }
  return result;
}
