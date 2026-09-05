import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  decodeDeletedIdentity,
  decodePersonaAssets,
  decodePersonaCardGenerateResult,
  decodePersonaCardList,
  decodePersonaList,
  decodePersonaProfile,
  decodePersonaSettingAssistOutput,
  decodePersonaSlotAssistOutput,
  decodeReusableSceneNode,
  decodeReusableSceneNodeList,
  decodeSceneLibraryItem,
  decodeSceneLibraryList,
  decodeSceneProfile,
  decodeSceneSetupState,
  decodeSceneTreeGenerateResult,
  PersonaSceneDecodeError,
} from "../lib/persona-scene-decode.ts";

const personaSpectrumSource = readFileSync(
  new URL("../app/persona-spectrum/page.tsx", import.meta.url),
  "utf8",
);

function wireSlot(overrides: Record<string, unknown> = {}) {
  return {
    kind: "custom-tone",
    label: "Tone",
    content: "Patient and precise",
    weight: 1,
    locked: false,
    sort_order: 0,
    ...overrides,
  };
}

function wirePersona(overrides: Record<string, unknown> = {}) {
  return {
    id: "persona-1",
    revision: 0,
    name: "Mentor",
    source: "user",
    summary: "A mentor",
    relationship: "Teacher",
    learner_address: "Learner",
    system_prompt: "Stay grounded",
    reference_hints: ["reference"],
    slots: [wireSlot(), wireSlot({ kind: "custom-second", sort_order: 0 })],
    available_emotions: ["calm", "custom-focus"],
    available_actions: ["idle"],
    default_speech_style: "warm",
    ...overrides,
  };
}

function wireCard(overrides: Record<string, unknown> = {}) {
  return {
    id: "card-1",
    title: "Card",
    kind: "custom-tone",
    label: "Tone",
    content: "Patient",
    tags: ["teaching"],
    search_keywords: "mentor",
    source: "manual",
    source_note: "",
    created_at: "2026-08-24T00:00:00Z",
    updated_at: "2026-08-24T00:00:00Z",
    ...overrides,
  };
}

function wireRecovery(overrides: Record<string, unknown> = {}) {
  return {
    schema_version: "model-recovery-v1",
    recovery_id: "recovery-1",
    category: "schema",
    reason: "malformed",
    strategy: "repair",
    attempts: 1,
    note: "",
    created_at: "2026-08-24T00:00:00Z",
    ...overrides,
  };
}

function wireHarnessTrace(
  workflow: "persona" | "scene",
  stage: "persona_generation" | "scene_generation",
  overrides: Record<string, unknown> = {},
) {
  const operationId = "harness-operation-bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb";
  const artifactType = workflow === "persona" ? "persona_snapshot" : "scene_snapshot";
  const inputContract = workflow === "persona"
    ? { name: "PersonaGenerationInputManifest", version: "persona-generation-input-manifest-v1" }
    : { name: "SceneGenerationInputManifest", version: "scene-generation-input-manifest-v1" };
  const artifactContract = workflow === "persona"
    ? { name: "PersonaGenerationProtectedInput", version: "persona-generation-protected-input-v1" }
    : { name: "SceneGenerationProtectedInput", version: "scene-generation-protected-input-v1" };
  const promptContract = workflow === "persona"
    ? { name: "PersonaGenerationPrompt", version: "persona-generation-prompt-v1" }
    : { name: "SceneGenerationPrompt", version: "scene-generation-prompt-v1" };
  const policyContract = workflow === "persona"
    ? { name: "PersonaGenerationHarnessPolicy", version: "persona-generation-harness-v1" }
    : { name: "SceneGenerationHarnessPolicy", version: "scene-generation-harness-v1" };
  const traceContract = workflow === "persona"
    ? { name: "PersonaGenerationProposal", version: "persona-generation-proposal-v1" }
    : { name: "SceneTreeProposal", version: "scene-tree-proposal-v1" };
  const componentContract = workflow === "persona"
    ? { name: "persona_compiler", version: "persona-compiler-v1" }
    : { name: "scene_compiler", version: "scene-compiler-v1" };
  const outputDigest = "a".repeat(64);
  return {
    trace_schema_version: "harness-trace-v3",
    trace_id: "harness-trace-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    operation_id: operationId,
    parent_trace_id: null,
    workflow,
    stage,
    status: "passed",
    contract: traceContract,
    context: {
      context_contract: { name: "HarnessContextEnvelopeV3", version: "harness-context-v3" },
      workflow,
      stage,
      operation_id: operationId,
      input_contract: inputContract,
      subject_refs: [{ resource_type: "frontend_request", resource_id: `${workflow}-request-1`, revision: null }],
      component_versions: [componentContract],
      snapshot_refs: [{
        artifact_type: artifactType,
        artifact_id: `${workflow}-snapshot-1`,
        contract: artifactContract,
        digest_algorithm: "sha256",
        payload_digest: "b".repeat(64),
      }],
      digest_algorithm: "sha256",
      digest_contract: { name: "HarnessContextManifestDigest", version: "harness-context-manifest-digest-v1" },
      input_digest: "c".repeat(64),
      context_digest: "d".repeat(64),
      policy_contract: policyContract,
      prompt_contract: promptContract,
    },
    output_digest: outputDigest,
    checks: [{ name: "proposal_schema_and_invariants", status: "passed", code: "proposal_valid", message: "Proposal is valid." }],
    attempt_records: [
      { attempt_id: "harness-attempt-cccccccccccccccccccccccccccccccc", attempt_index: 1, phase: "generate", status: "passed", output_digest: outputDigest, error_code: "", duration_ms: 1 },
      { attempt_id: "harness-attempt-dddddddddddddddddddddddddddddddd", attempt_index: 2, phase: "decode", status: "passed", output_digest: outputDigest, error_code: "", duration_ms: 1 },
      { attempt_id: "harness-attempt-eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee", attempt_index: 3, phase: "validate", status: "passed", output_digest: outputDigest, error_code: "", duration_ms: 1 },
    ],
    recovery_strategy: "none",
    error_code: "",
    duration_ms: 1,
    commit_evidence: {
      status: "not_applicable",
      effect_batch_id: null,
      payload_contract: null,
      digest_algorithm: null,
      digest_scope: null,
      attempted_resource_refs: [],
      committed_resources: [],
      payload_digest: null,
      committed_at: null,
      rollback_reason_code: "",
      rolled_back_at: null,
    },
    started_at: "2026-08-24T00:00:00Z",
    completed_at: "2026-08-24T00:00:01Z",
    ...overrides,
  };
}

function wireObject(index = 1, overrides: Record<string, unknown> = {}) {
  return {
    id: `object-${index}`,
    name: `Object ${index}`,
    description: "A useful object",
    interaction: "Inspect it",
    tags: "focus",
    reuse_id: `object-reuse-${index}`,
    reuse_hint: "",
    ...overrides,
  };
}

function wireLayer(
  index = 1,
  overrides: Record<string, unknown> = {},
): Record<string, unknown> {
  return {
    id: `layer-${index}`,
    title: `Layer ${index}`,
    scope_label: "Area",
    summary: "A learning area",
    atmosphere: "Quiet",
    rules: "Stay focused",
    entrance: "Open door",
    tags: "quiet，study,quiet",
    reuse_id: `layer-reuse-${index}`,
    reuse_hint: "",
    objects: index === 1 ? [wireObject()] : [],
    children: [],
    ...overrides,
  };
}

function wireProfile(
  layer = wireLayer(),
  overrides: Record<string, unknown> = {},
) {
  const layerRecord = layer as Record<string, unknown>;
  const objects = layerRecord.objects as Array<Record<string, unknown>>;
  return {
    scene_name: "Night Library",
    scene_id: String(layerRecord.id),
    title: String(layerRecord.title),
    summary: "A quiet study scene",
    tags: ["quiet", "study"],
    selected_path: [String(layerRecord.title)],
    focus_object_names: objects.slice(0, 4).map((item) => String(item.name)),
    scene_tree: [layer],
    ...overrides,
  };
}

function wireSetup(overrides: Record<string, unknown> = {}) {
  const layer = wireLayer();
  return {
    config_id: "default",
    revision: 1,
    updated_at: "2026-08-24T00:00:00Z",
    scene_name: "Night Library",
    scene_summary: "A quiet study scene",
    scene_layers: [layer],
    selected_layer_id: "layer-1",
    collapsed_layer_ids: [],
    scene_profile: wireProfile(layer),
    ...overrides,
  };
}

function wireLibrary(overrides: Record<string, unknown> = {}) {
  return {
    ...wireSetup(),
    config_id: "scene-1",
    scene_id: "scene-1",
    revision: 2,
    created_at: "2026-08-23T00:00:00Z",
    ...overrides,
  };
}

function wireSceneGenerate(overrides: Record<string, unknown> = {}) {
  return {
    contract_version: "scene-tree-generate-response-v1",
    mode: "keywords",
    used_model: "mock-setting",
    used_web_search: false,
    scene_name: "Night Library",
    scene_summary: "A quiet study scene",
    selected_layer_id: "layer-1",
    scene_layers: [wireLayer()],
    model_recoveries: [wireRecovery()],
    harness_trace: wireHarnessTrace("scene", "scene_generation"),
    ...overrides,
  };
}

function nestedLayers(depth: number): Record<string, unknown> {
  const layer = wireLayer(depth, { objects: [] });
  if (depth > 1) {
    layer.children = [nestedLayers(depth - 1)];
  }
  return layer;
}

test("Persona decoder accepts custom slot vocabulary and duplicate sort orders", () => {
  const persona = decodePersonaProfile(wirePersona(), {
    expectedPersonaId: "persona-1",
    expectedSource: "user",
  });
  assert.equal(persona.slots[0]?.kind, "custom-tone");
  assert.equal(persona.slots[1]?.sortOrder, 0);
  assert.deepEqual(decodePersonaList({ items: [wirePersona()] }), [persona]);
});

test("Persona decoder rejects coercion, illegal source, URL drift, and non-finite slots", () => {
  const missingRevision = wirePersona() as Record<string, unknown>;
  delete missingRevision.revision;
  for (const attack of [
    missingRevision,
    wirePersona({ revision: "0" }),
    wirePersona({ revision: -1 }),
    wirePersona({ revision: 1.5 }),
    wirePersona({ source: "generated" }),
    wirePersona({ relationship: null }),
    wirePersona({ available_actions: "idle" }),
    wirePersona({ slots: [wireSlot({ weight: Number.POSITIVE_INFINITY })] }),
    wirePersona({ slots: [wireSlot({ weight: 101 })] }),
    wirePersona({ slots: [wireSlot({ locked: 1 })] }),
  ]) {
    assert.throws(() => decodePersonaProfile(attack), PersonaSceneDecodeError);
  }
  assert.throws(
    () => decodePersonaProfile(wirePersona(), { expectedPersonaId: "persona-other" }),
    (error: unknown) =>
      error instanceof PersonaSceneDecodeError && error.path === "persona.id",
  );
});

test("Persona card envelopes reject duplicate IDs and illegal source values", () => {
  assert.equal(decodePersonaCardList({ items: [wireCard()] })[0]?.source, "manual");
  assert.throws(
    () => decodePersonaCardList({ items: [wireCard(), wireCard()] }),
    PersonaSceneDecodeError,
  );
  assert.throws(
    () => decodePersonaCardList({ items: [wireCard({ source: "model" })] }),
    PersonaSceneDecodeError,
  );
  assert.throws(
    () => decodePersonaCardList({ items: [wireCard({ tags: [1] })] }),
    PersonaSceneDecodeError,
  );
});

test("Persona generation binds mode, generated source, booleans, and recovery schema", () => {
  const payload = {
    mode: "keywords",
    used_model: "mock-setting",
    used_web_search: false,
    summary: "Summary",
    relationship: "Teacher",
    learner_address: "Learner",
    items: [wireCard({ source: "generated_keywords" })],
    model_recoveries: [wireRecovery()],
    harness_trace: wireHarnessTrace("persona", "persona_generation"),
  };
  assert.equal(
    decodePersonaCardGenerateResult(payload, { expectedMode: "keywords" }).items[0]?.source,
    "generated_keywords",
  );
  for (const attack of [
    { ...payload, mode: "long_text" },
    { ...payload, used_web_search: 0 },
    { ...payload, items: [wireCard({ source: "generated_text" })] },
    { ...payload, model_recoveries: [wireRecovery({ schema_version: "harness-trace-v3" })] },
  ]) {
    assert.throws(
      () => decodePersonaCardGenerateResult(attack, { expectedMode: "keywords" }),
      PersonaSceneDecodeError,
    );
  }
});

test("Persona count UI states exact 1-24 semantics", () => {
  assert.match(personaSpectrumSource, />精确卡片数量（可选）</);
  assert.match(personaSpectrumSource, /min=\{1\}/);
  assert.match(personaSpectrumSource, /max=\{24\}/);
  assert.match(personaSpectrumSource, /parsedCount > 24/);
  assert.match(personaSpectrumSource, /填写后精确生成 1–24 张/);
});

test("Persona assist decoders require typed slots and preserve assisted slot identity", () => {
  const setting = decodePersonaSettingAssistOutput({
    slots: [wireSlot()],
    system_prompt_suggestion: "Suggestion",
    model_recoveries: [],
    harness_trace: wireHarnessTrace("persona", "persona_generation"),
  });
  assert.equal(setting.slots[0]?.weight, 1);
  const slot = decodePersonaSlotAssistOutput(
    {
      slot: wireSlot({ content: "Rewritten" }),
      model_recoveries: [],
      harness_trace: wireHarnessTrace("persona", "persona_generation"),
    },
    { kind: "custom-tone", label: "Tone", content: "Before", weight: 1, locked: false, sortOrder: 0 },
  );
  assert.equal(slot.slot.content, "Rewritten");
  assert.throws(
    () => decodePersonaSlotAssistOutput(
      {
        slot: wireSlot({ kind: "other" }),
        model_recoveries: [],
        harness_trace: wireHarnessTrace("persona", "persona_generation"),
      },
      { kind: "custom-tone", label: "Tone", content: "Before", locked: false, sortOrder: 0 },
    ),
    PersonaSceneDecodeError,
  );
  assert.throws(
    () => decodePersonaSettingAssistOutput({
      slots: [wireSlot()],
      system_prompt_suggestion: "",
      model_recoveries: [],
      harness_trace: wireHarnessTrace("persona", "persona_generation"),
    }),
    PersonaSceneDecodeError,
  );
});

test("Persona assets and delete projections bind the URL identity", () => {
  assert.equal(
    decodePersonaAssets(
      { persona_id: "persona-1", renderer: "placeholder", asset_manifest: {} },
      "persona-1",
    ).personaId,
    "persona-1",
  );
  assert.equal(
    decodeDeletedIdentity(
      { deleted_scene_id: "scene-1" },
      { wireField: "deleted_scene_id", expectedId: "scene-1", path: "delete" },
    ),
    "scene-1",
  );
  assert.throws(
    () => decodeDeletedIdentity(
      { deleted_scene_id: "scene-other" },
      { wireField: "deleted_scene_id", expectedId: "scene-1", path: "delete" },
    ),
    PersonaSceneDecodeError,
  );
});

test("Scene generation accepts a coherent committed projection", () => {
  const result = decodeSceneTreeGenerateResult(wireSceneGenerate(), {
    expectedMode: "keywords",
  });
  assert.equal(result.sceneLayers[0]?.objects[0]?.id, "object-1");
  assert.equal(result.modelRecoveries[0]?.schemaVersion, "model-recovery-v1");
});

test("Scene generation rejects contract, mode, selection, depth, child, and identity attacks", () => {
  const duplicateIdentity = wireLayer(2, {
    id: "object-1",
    reuse_id: "layer-reuse-2",
    objects: [],
  });
  const tooManyChildren = Array.from({ length: 9 }, (_, index) =>
    wireLayer(index + 2, { objects: [] }),
  );
  for (const attack of [
    wireSceneGenerate({ contract_version: "scene-tree-generate-response-v2" }),
    wireSceneGenerate({ mode: "long_text" }),
    wireSceneGenerate({ selected_layer_id: "missing" }),
    wireSceneGenerate({ scene_layers: [nestedLayers(9)] }),
    wireSceneGenerate({ scene_layers: [wireLayer(1, { children: tooManyChildren })] }),
    wireSceneGenerate({ scene_layers: [wireLayer(), duplicateIdentity] }),
  ]) {
    assert.throws(
      () => decodeSceneTreeGenerateResult(attack, { expectedMode: "keywords" }),
      PersonaSceneDecodeError,
    );
  }
  const sharedReuse = wireSceneGenerate({
    scene_layers: [
      wireLayer(),
      wireLayer(2, { reuse_id: "object-reuse-1", objects: [] }),
    ],
  });
  assert.equal(
    decodeSceneTreeGenerateResult(sharedReuse, { expectedMode: "keywords" }).sceneLayers.length,
    2,
  );
});

test("Wave 4 decoders fail closed on malformed nested v3 Harness evidence", () => {
  const attacks = [
    wireSceneGenerate({
      harness_trace: wireHarnessTrace("scene", "scene_generation", {
        contract: 42,
      }),
    }),
    wireSceneGenerate({
      harness_trace: wireHarnessTrace("scene", "scene_generation", {
        output_digest: "not-a-digest",
      }),
    }),
    wireSceneGenerate({
      harness_trace: wireHarnessTrace("scene", "scene_generation", {
        started_at: "yesterday",
      }),
    }),
  ];
  for (const attack of attacks) {
    assert.throws(
      () => decodeSceneTreeGenerateResult(attack, { expectedMode: "keywords" }),
      PersonaSceneDecodeError,
    );
  }
});

test("Scene Setup accepts only the exact empty initial state or a coherent committed state", () => {
  const empty = decodeSceneSetupState({
    config_id: "default",
    revision: 0,
    updated_at: "2026-08-24T00:00:00Z",
    scene_name: "",
    scene_summary: "",
    scene_layers: [],
    selected_layer_id: "",
    collapsed_layer_ids: [],
    scene_profile: null,
  });
  assert.equal(empty.sceneProfile, undefined);
  assert.equal(decodeSceneSetupState(wireSetup(), { expectedRevision: 1 }).revision, 1);
  for (const attack of [
    { ...wireSetup(), config_id: "other" },
    { ...wireSetup(), revision: "1" },
    { ...wireSetup(), collapsed_layer_ids: ["missing"] },
    { ...wireSetup(), scene_profile: null },
    {
      config_id: "default",
      revision: 1,
      updated_at: "2026-08-24T00:00:00Z",
      scene_name: "",
      scene_summary: "",
      scene_layers: [],
      selected_layer_id: "",
      collapsed_layer_ids: [],
      scene_profile: null,
    },
  ]) {
    assert.throws(() => decodeSceneSetupState(attack), PersonaSceneDecodeError);
  }
});

test("Scene Profile binds title path, tags, focus objects, and committed tree", () => {
  assert.deepEqual(decodeSceneProfile(wireProfile()).selectedPath, ["Layer 1"]);
  for (const attack of [
    wireProfile(wireLayer(), { scene_id: "missing" }),
    wireProfile(wireLayer(), { title: "Forged" }),
    wireProfile(wireLayer(), { selected_path: ["layer-1"] }),
    wireProfile(wireLayer(), { tags: ["quiet"] }),
    wireProfile(wireLayer(), { focus_object_names: [] }),
  ]) {
    assert.throws(() => decodeSceneProfile(attack), PersonaSceneDecodeError);
  }
  const state = wireSetup();
  const profile = state.scene_profile as Record<string, unknown>;
  assert.throws(
    () => decodeSceneSetupState({
      ...state,
      scene_profile: { ...profile, summary: "Different" },
    }),
    PersonaSceneDecodeError,
  );
  assert.throws(
    () => decodeSceneSetupState({
      ...state,
      scene_profile: { ...profile, scene_tree: [wireLayer(9)] },
    }),
    PersonaSceneDecodeError,
  );
});

test("Scene Library binds config, URL, revision, profile, and list identity", () => {
  assert.equal(
    decodeSceneLibraryItem(wireLibrary(), {
      expectedSceneId: "scene-1",
      expectedRevision: 2,
    }).sceneId,
    "scene-1",
  );
  assert.equal(decodeSceneLibraryList({ items: [wireLibrary()] }).length, 1);
  for (const attack of [
    wireLibrary({ config_id: "scene-other" }),
    wireLibrary({ revision: 0 }),
    wireLibrary({ scene_id: "scene-other" }),
  ]) {
    assert.throws(
      () => decodeSceneLibraryItem(attack, { expectedSceneId: "scene-1" }),
      PersonaSceneDecodeError,
    );
  }
  assert.throws(
    () => decodeSceneLibraryList({ items: [wireLibrary(), wireLibrary()] }),
    PersonaSceneDecodeError,
  );
});

test("Reusable Scene Node decoder enforces the discriminated node projection", () => {
  const layer = wireLayer();
  const reusable = {
    node_id: "scene-node-1",
    node_type: "layer",
    title: "Layer 1 template",
    summary: "Reusable library metadata",
    tags: ["quiet"],
    reuse_id: "layer-reuse-1",
    reuse_hint: "",
    source_scene_id: "layer-1",
    source_scene_name: "Night Library",
    layer_node: layer,
    object_node: null,
    created_at: "2026-08-24T00:00:00Z",
    updated_at: "2026-08-24T00:00:00Z",
  };
  assert.equal(decodeReusableSceneNode(reusable).layerNode?.id, "layer-1");
  assert.equal(decodeReusableSceneNodeList({ items: [reusable] }).length, 1);
  for (const attack of [
    { ...reusable, node_type: "other" },
    { ...reusable, object_node: wireObject() },
    { ...reusable, layer_node: null },
  ]) {
    assert.throws(() => decodeReusableSceneNode(attack), PersonaSceneDecodeError);
  }
  assert.throws(
    () => decodeReusableSceneNodeList({ items: [reusable, reusable] }),
    PersonaSceneDecodeError,
  );
});
