import {
  diagnosticDecode,
  DiagnosticContext as DiagnosticContext,
} from "../diagnostics";
import type {
  CreatePersonaInput,
  CreatePersonaCardInput,
  PersonaCard,
  PersonaCardGenerationMode,
  PersonaProfile,
  UpdatePersonaInput,
} from "@vibe-learner/shared";
import {
  decodeDeletedIdentity,
  decodePersonaAssets,
  decodePersonaCardGenerateResult,
  decodePersonaCardList,
  decodePersonaList,
  decodePersonaProfile,
  decodePersonaSettingAssistOutput,
  decodePersonaSlotAssistOutput,
} from "../persona-scene-decode";

import {
  AI_BASE_URL,
  request,
  readJson,
  serializeSlot,
  serializePersonaCardInput,
  serializePersonaInput,
} from "./_shared";

export interface PersonaAssets {
  personaId: string;
  renderer: string;
  assetManifest: Record<string, unknown>;
}

export interface PersonaCardGenerateResult {
  mode: PersonaCardGenerationMode;
  usedModel: string;
  usedWebSearch: boolean;
  summary: string;
  relationship: string;
  learnerAddress: string;
  items: PersonaCard[];
  modelRecoveries?: import("@vibe-learner/shared").ModelRecovery[];
}

export interface PersonaSettingAssistInput {
  name: string;
  summary: string;
  slots: import("@vibe-learner/shared").PersonaSlot[];
  rewriteStrength: number;
}

export interface PersonaSettingAssistOutput {
  slots: import("@vibe-learner/shared").PersonaSlot[];
  systemPromptSuggestion: string;
  modelRecoveries?: import("@vibe-learner/shared").ModelRecovery[];
}

export interface PersonaSlotAssistInput {
  name: string;
  summary: string;
  slot: import("@vibe-learner/shared").PersonaSlot;
  rewriteStrength: number;
}

export interface PersonaSlotAssistOutput {
  slot: import("@vibe-learner/shared").PersonaSlot;
  modelRecoveries?: import("@vibe-learner/shared").ModelRecovery[];
}

export async function listPersonas(
  context?: DiagnosticContext,
): Promise<PersonaProfile[]> {
  const diagnosticResponse = await request(
    `${AI_BASE_URL()}/personas`,
    undefined,
    context,
  );
  const payload = await readJson<unknown>(diagnosticResponse);
  return diagnosticDecode(diagnosticResponse, () => decodePersonaList(payload));
}

export async function createPersona(
  input: CreatePersonaInput,
  context?: DiagnosticContext,
): Promise<PersonaProfile> {
  const diagnosticResponse = await request(
    `${AI_BASE_URL()}/personas`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(serializePersonaInput(input)),
    },
    context,
  );
  const payload = await readJson<unknown>(diagnosticResponse);
  return diagnosticDecode(diagnosticResponse, () =>
    decodePersonaProfile(payload, { expectedSource: "user" }),
  );
}

export async function updatePersona(
  personaId: string,
  input: UpdatePersonaInput,
  context?: DiagnosticContext,
): Promise<PersonaProfile> {
  const encodedPersonaId = encodeURIComponent(personaId);
  const diagnosticResponse = await request(
    `${AI_BASE_URL()}/personas/${encodedPersonaId}`,
    {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(serializePersonaInput(input)),
    },
    context,
  );
  const payload = await readJson<unknown>(diagnosticResponse);
  return diagnosticDecode(diagnosticResponse, () =>
    decodePersonaProfile(payload, {
      expectedPersonaId: personaId,
      expectedSource: "user",
    }),
  );
}

export async function deletePersona(
  personaId: string,
  expectedRevision: number,
): Promise<void> {
  const encodedPersonaId = encodeURIComponent(personaId);
  const diagnosticResponse = await request(
    `${AI_BASE_URL()}/personas/${encodedPersonaId}?expected_revision=${expectedRevision}`,
    {
      method: "DELETE",
    },
  );
  const payload = await readJson<unknown>(diagnosticResponse);
  diagnosticDecode(diagnosticResponse, () =>
    decodeDeletedIdentity(payload, {
      wireField: "deleted_persona_id",
      expectedId: personaId,
      path: "persona_delete",
    }),
  );
}

export async function getPersonaAssets(personaId: string): Promise<PersonaAssets> {
  const encodedPersonaId = encodeURIComponent(personaId);
  const diagnosticResponse = await request(
    `${AI_BASE_URL()}/personas/${encodedPersonaId}/assets`,
  );
  const payload = await readJson<unknown>(diagnosticResponse);
  return diagnosticDecode(diagnosticResponse, () =>
    decodePersonaAssets(payload, personaId),
  );
}

export async function listPersonaCards(): Promise<PersonaCard[]> {
  const diagnosticResponse = await request(`${AI_BASE_URL()}/persona-cards`);
  const payload = await readJson<unknown>(diagnosticResponse);
  return diagnosticDecode(diagnosticResponse, () => decodePersonaCardList(payload));
}

export async function createPersonaCardsBatch(
  items: CreatePersonaCardInput[],
): Promise<PersonaCard[]> {
  const diagnosticResponse = await request(`${AI_BASE_URL()}/persona-cards/batch`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      items: items.map(serializePersonaCardInput),
    }),
  });
  const payload = await readJson<unknown>(diagnosticResponse);
  return diagnosticDecode(diagnosticResponse, () =>
    decodePersonaCardList(payload, "persona_card_batch"),
  );
}

export async function deletePersonaCard(cardId: string): Promise<void> {
  const diagnosticResponse = await request(`${AI_BASE_URL()}/persona-cards/${cardId}`, {
    method: "DELETE",
  });
  const payload = await readJson<unknown>(diagnosticResponse);
  diagnosticDecode(diagnosticResponse, () =>
    decodeDeletedIdentity(payload, {
      wireField: "deleted_persona_card_id",
      expectedId: cardId,
      path: "persona_card_delete",
    }),
  );
}

export async function generatePersonaCards(
  input: {
    mode: PersonaCardGenerationMode;
    inputText: string;
    count?: number | null;
  },
  context?: DiagnosticContext,
): Promise<PersonaCardGenerateResult> {
  const requestBody: Record<string, unknown> = {
    mode: input.mode,
    input_text: input.inputText,
  };
  if (typeof input.count === "number" && Number.isFinite(input.count)) {
    requestBody.count = input.count;
  }
  const diagnosticResponse = await request(
    `${AI_BASE_URL()}/persona-cards/generate`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(requestBody),
    },
    context,
  );
  const payload = await readJson<unknown>(diagnosticResponse);
  return diagnosticDecode(diagnosticResponse, () =>
    decodePersonaCardGenerateResult(payload, { expectedMode: input.mode }),
  );
}

export async function assistPersonaSetting(
  input: PersonaSettingAssistInput,
): Promise<PersonaSettingAssistOutput> {
  const diagnosticResponse = await request(`${AI_BASE_URL()}/personas/assist-setting`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      name: input.name,
      summary: input.summary,
      slots: input.slots.map(serializeSlot),
      rewrite_strength: input.rewriteStrength,
    }),
  });
  const payload = await readJson<unknown>(diagnosticResponse);
  return diagnosticDecode(diagnosticResponse, () =>
    decodePersonaSettingAssistOutput(payload),
  );
}

export async function assistPersonaSlot(
  input: PersonaSlotAssistInput,
  context?: DiagnosticContext,
): Promise<PersonaSlotAssistOutput> {
  const diagnosticResponse = await request(
    `${AI_BASE_URL()}/personas/assist-slot`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        name: input.name,
        summary: input.summary,
        slot: serializeSlot(input.slot),
        rewrite_strength: input.rewriteStrength,
      }),
    },
    context,
  );
  const payload = await readJson<unknown>(diagnosticResponse);
  return diagnosticDecode(diagnosticResponse, () =>
    decodePersonaSlotAssistOutput(payload, input.slot),
  );
}
