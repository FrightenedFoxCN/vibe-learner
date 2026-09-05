import type {
  ModelRecovery,
  PersonaCard,
  PersonaCardGenerationMode,
  PersonaProfile,
  PersonaSlot,
  SceneObjectSnapshot,
  SceneProfile,
  SceneTreeNode,
  HarnessTraceV3,
} from "@vibe-learner/shared";

import { StrictResponseDecoder } from "./strict-response-decode.ts";
import { decodeHarnessTraceV3 } from "./harness-trace-decode.ts";

const PERSONA_SOURCES = ["builtin", "user"] as const;
const PERSONA_CARD_SOURCES = [
  "manual",
  "generated_keywords",
  "generated_text",
] as const;
const GENERATION_MODES = ["keywords", "long_text"] as const;
const SCENE_NODE_TYPES = ["layer", "object"] as const;
const MODEL_RECOVERY_SCHEMA_VERSIONS = ["model-recovery-v1"] as const;
const SCENE_TREE_GENERATE_RESPONSE_VERSION = "scene-tree-generate-response-v1";
const SCENE_MAX_DEPTH = 8;
const SCENE_MAX_LAYER_COUNT = 64;
const SCENE_MAX_OBJECT_COUNT = 128;
const SCENE_MAX_TEXT_BUDGET = 60_000;

export class PersonaSceneDecodeError extends Error {
  readonly code = "persona_scene_response_decode_error";
  readonly path: string;
  readonly reason: string;

  constructor(path: string, reason: string) {
    super(`${reason} at ${path}`);
    this.name = "PersonaSceneDecodeError";
    this.path = path;
    this.reason = reason;
  }
}

const decoder = new StrictResponseDecoder((path, reason) => {
  throw new PersonaSceneDecodeError(path, reason);
});

export interface DecodedPersonaAssets {
  personaId: string;
  renderer: string;
  assetManifest: Record<string, unknown>;
}

export interface DecodedPersonaCardGenerateResult {
  mode: PersonaCardGenerationMode;
  usedModel: string;
  usedWebSearch: boolean;
  summary: string;
  relationship: string;
  learnerAddress: string;
  items: PersonaCard[];
  modelRecoveries: ModelRecovery[];
  harnessTrace: HarnessTraceV3;
}

export interface DecodedPersonaSettingAssistOutput {
  slots: PersonaSlot[];
  systemPromptSuggestion: string;
  modelRecoveries: ModelRecovery[];
  harnessTrace: HarnessTraceV3;
}

export interface DecodedPersonaSlotAssistOutput {
  slot: PersonaSlot;
  modelRecoveries: ModelRecovery[];
  harnessTrace: HarnessTraceV3;
}

export interface DecodedSceneTreeGenerateResult {
  mode: "keywords" | "long_text";
  usedModel: string;
  usedWebSearch: boolean;
  sceneName: string;
  sceneSummary: string;
  selectedLayerId: string;
  sceneLayers: SceneTreeNode[];
  modelRecoveries: ModelRecovery[];
  harnessTrace: HarnessTraceV3;
}

function decodeWave4HarnessTrace(
  value: Record<string, unknown>,
  path: string,
  workflow: "persona" | "scene",
  stage: "persona_generation" | "scene_generation",
): HarnessTraceV3 {
  const trace = decodeHarnessTraceV3(
    decoder.field(value, "harness_trace", path),
    `${path}.harness_trace`,
    (tracePath, reason) => { throw new PersonaSceneDecodeError(tracePath, reason); },
  );
  decoder.equal(trace.workflow, workflow, `${path}.harness_trace.workflow`);
  decoder.equal(trace.stage, stage, `${path}.harness_trace.stage`);
  return trace;
}

export interface DecodedSceneSetupState {
  revision: number;
  updatedAt: string;
  sceneName: string;
  sceneSummary: string;
  sceneLayers: SceneTreeNode[];
  selectedLayerId: string;
  collapsedLayerIds: string[];
  sceneProfile?: SceneProfile;
}

export interface DecodedSceneLibraryItem extends DecodedSceneSetupState {
  sceneId: string;
  createdAt: string;
}

export interface DecodedReusableSceneNode {
  nodeId: string;
  nodeType: "layer" | "object";
  title: string;
  summary: string;
  tags: string[];
  reuseId: string;
  reuseHint: string;
  sourceSceneId: string;
  sourceSceneName: string;
  layerNode?: SceneTreeNode;
  objectNode?: SceneObjectSnapshot;
  createdAt: string;
  updatedAt: string;
}

function boundedString(
  raw: unknown,
  path: string,
  options: { allowEmpty?: boolean; maximum?: number } = {},
): string {
  const value = decoder.string(raw, path, options.allowEmpty ?? false);
  const maximum = options.maximum ?? Number.MAX_SAFE_INTEGER;
  if (value.length > maximum) {
    throw new PersonaSceneDecodeError(path, `string_length_exceeds_${maximum}`);
  }
  return value;
}

function decodeModelRecovery(raw: unknown, path: string): ModelRecovery {
  const value = decoder.record(raw, path);
  let schemaVersion: "model-recovery-v1" | undefined;
  if (Object.prototype.hasOwnProperty.call(value, "schema_version")) {
    schemaVersion = decoder.enumeration(
      decoder.field(value, "schema_version", path),
      MODEL_RECOVERY_SCHEMA_VERSIONS,
      `${path}.schema_version`,
    );
  }
  return {
    ...(schemaVersion === undefined ? {} : { schemaVersion }),
    recoveryId: decoder.string(
      decoder.field(value, "recovery_id", path),
      `${path}.recovery_id`,
    ),
    category: decoder.string(decoder.field(value, "category", path), `${path}.category`),
    reason: decoder.string(decoder.field(value, "reason", path), `${path}.reason`),
    strategy: decoder.string(decoder.field(value, "strategy", path), `${path}.strategy`),
    attempts: decoder.integer(decoder.field(value, "attempts", path), `${path}.attempts`, 1),
    note: decoder.string(decoder.field(value, "note", path), `${path}.note`, true),
    createdAt: decoder.string(
      decoder.field(value, "created_at", path),
      `${path}.created_at`,
    ),
  };
}

function decodeModelRecoveries(raw: unknown, path: string): ModelRecovery[] {
  const recoveries = decoder.array(raw, path, decodeModelRecovery);
  decoder.unique(recoveries.map((item) => item.recoveryId), `${path}.recovery_id`);
  return recoveries;
}

function decodePersonaSlot(raw: unknown, path: string): PersonaSlot {
  const value = decoder.record(raw, path);
  return {
    kind: decoder.string(decoder.field(value, "kind", path), `${path}.kind`),
    label: decoder.string(decoder.field(value, "label", path), `${path}.label`, true),
    content: decoder.string(decoder.field(value, "content", path), `${path}.content`, true),
    weight: decoder.finiteNumber(
      decoder.field(value, "weight", path),
      `${path}.weight`,
      0,
      100,
    ),
    locked: decoder.boolean(decoder.field(value, "locked", path), `${path}.locked`),
    sortOrder: decoder.integer(
      decoder.field(value, "sort_order", path),
      `${path}.sort_order`,
      0,
    ),
  };
}

export function decodePersonaProfile(
  raw: unknown,
  options: {
    expectedPersonaId?: string;
    expectedSource?: "builtin" | "user";
    path?: string;
  } = {},
): PersonaProfile {
  const path = options.path ?? "persona";
  const value = decoder.record(raw, path);
  const persona: PersonaProfile = {
    id: decoder.string(decoder.field(value, "id", path), `${path}.id`),
    revision: decoder.integer(
      decoder.field(value, "revision", path),
      `${path}.revision`,
      0,
    ),
    name: decoder.string(decoder.field(value, "name", path), `${path}.name`, true),
    source: decoder.enumeration(
      decoder.field(value, "source", path),
      PERSONA_SOURCES,
      `${path}.source`,
    ),
    summary: decoder.string(decoder.field(value, "summary", path), `${path}.summary`, true),
    relationship: decoder.string(
      decoder.field(value, "relationship", path),
      `${path}.relationship`,
      true,
    ),
    learnerAddress: decoder.string(
      decoder.field(value, "learner_address", path),
      `${path}.learner_address`,
      true,
    ),
    systemPrompt: decoder.string(
      decoder.field(value, "system_prompt", path),
      `${path}.system_prompt`,
      true,
    ),
    referenceHints: decoder.stringArray(
      decoder.field(value, "reference_hints", path),
      `${path}.reference_hints`,
    ),
    slots: decoder.array(
      decoder.field(value, "slots", path),
      `${path}.slots`,
      decodePersonaSlot,
    ),
    availableEmotions: decoder.stringArray(
      decoder.field(value, "available_emotions", path),
      `${path}.available_emotions`,
    ),
    availableActions: decoder.stringArray(
      decoder.field(value, "available_actions", path),
      `${path}.available_actions`,
    ),
    defaultSpeechStyle: decoder.string(
      decoder.field(value, "default_speech_style", path),
      `${path}.default_speech_style`,
    ),
  };
  if (options.expectedPersonaId !== undefined) {
    decoder.equal(persona.id, options.expectedPersonaId, `${path}.id`);
  }
  if (options.expectedSource !== undefined) {
    decoder.equal(persona.source, options.expectedSource, `${path}.source`);
  }
  return persona;
}

export function decodePersonaList(raw: unknown, path = "persona_list"): PersonaProfile[] {
  const value = decoder.record(raw, path);
  const items = decoder.array(
    decoder.field(value, "items", path),
    `${path}.items`,
    (item, itemPath) => decodePersonaProfile(item, { path: itemPath }),
  );
  decoder.unique(items.map((item) => item.id), `${path}.items.id`);
  return items;
}

export function decodePersonaAssets(
  raw: unknown,
  expectedPersonaId: string,
  path = "persona_assets",
): DecodedPersonaAssets {
  const value = decoder.record(raw, path);
  const personaId = decoder.string(
    decoder.field(value, "persona_id", path),
    `${path}.persona_id`,
  );
  decoder.equal(personaId, expectedPersonaId, `${path}.persona_id`);
  return {
    personaId,
    renderer: decoder.string(decoder.field(value, "renderer", path), `${path}.renderer`),
    assetManifest: decoder.record(
      decoder.field(value, "asset_manifest", path),
      `${path}.asset_manifest`,
    ),
  };
}

function decodePersonaCard(
  raw: unknown,
  path: string,
  expectedSource?: PersonaCard["source"],
): PersonaCard {
  const value = decoder.record(raw, path);
  const card: PersonaCard = {
    id: decoder.string(decoder.field(value, "id", path), `${path}.id`),
    title: decoder.string(decoder.field(value, "title", path), `${path}.title`, true),
    kind: decoder.string(decoder.field(value, "kind", path), `${path}.kind`),
    label: decoder.string(decoder.field(value, "label", path), `${path}.label`, true),
    content: decoder.string(decoder.field(value, "content", path), `${path}.content`, true),
    tags: decoder.stringArray(decoder.field(value, "tags", path), `${path}.tags`),
    searchKeywords: decoder.string(
      decoder.field(value, "search_keywords", path),
      `${path}.search_keywords`,
      true,
    ),
    source: decoder.enumeration(
      decoder.field(value, "source", path),
      PERSONA_CARD_SOURCES,
      `${path}.source`,
    ),
    sourceNote: decoder.string(
      decoder.field(value, "source_note", path),
      `${path}.source_note`,
      true,
    ),
    createdAt: decoder.string(decoder.field(value, "created_at", path), `${path}.created_at`),
    updatedAt: decoder.string(decoder.field(value, "updated_at", path), `${path}.updated_at`),
  };
  if (expectedSource !== undefined) {
    decoder.equal(card.source, expectedSource, `${path}.source`);
  }
  return card;
}

export function decodePersonaCardList(
  raw: unknown,
  path = "persona_card_list",
): PersonaCard[] {
  const value = decoder.record(raw, path);
  const items = decoder.array(
    decoder.field(value, "items", path),
    `${path}.items`,
    (item, itemPath) => decodePersonaCard(item, itemPath),
  );
  decoder.unique(items.map((item) => item.id), `${path}.items.id`);
  return items;
}

export function decodePersonaCardGenerateResult(
  raw: unknown,
  options: { expectedMode: PersonaCardGenerationMode; path?: string },
): DecodedPersonaCardGenerateResult {
  const path = options.path ?? "persona_card_generate";
  const value = decoder.record(raw, path);
  const mode = decoder.enumeration(
    decoder.field(value, "mode", path),
    GENERATION_MODES,
    `${path}.mode`,
  );
  decoder.equal(mode, options.expectedMode, `${path}.mode`);
  const expectedSource = mode === "keywords" ? "generated_keywords" : "generated_text";
  const items = decoder.array(
    decoder.field(value, "items", path),
    `${path}.items`,
    (item, itemPath) => decodePersonaCard(item, itemPath, expectedSource),
  );
  decoder.unique(items.map((item) => item.id), `${path}.items.id`);
  return {
    mode,
    usedModel: decoder.string(
      decoder.field(value, "used_model", path),
      `${path}.used_model`,
      true,
    ),
    usedWebSearch: decoder.boolean(
      decoder.field(value, "used_web_search", path),
      `${path}.used_web_search`,
    ),
    summary: decoder.string(decoder.field(value, "summary", path), `${path}.summary`, true),
    relationship: decoder.string(
      decoder.field(value, "relationship", path),
      `${path}.relationship`,
      true,
    ),
    learnerAddress: decoder.string(
      decoder.field(value, "learner_address", path),
      `${path}.learner_address`,
      true,
    ),
    items,
    modelRecoveries: decodeModelRecoveries(
      decoder.field(value, "model_recoveries", path),
      `${path}.model_recoveries`,
    ),
    harnessTrace: decodeWave4HarnessTrace(value, path, "persona", "persona_generation"),
  };
}

export function decodePersonaSettingAssistOutput(
  raw: unknown,
  path = "persona_setting_assist",
): DecodedPersonaSettingAssistOutput {
  const value = decoder.record(raw, path);
  return {
    slots: decoder.array(
      decoder.field(value, "slots", path),
      `${path}.slots`,
      decodePersonaSlot,
    ),
    systemPromptSuggestion: decoder.string(
      decoder.field(value, "system_prompt_suggestion", path),
      `${path}.system_prompt_suggestion`,
    ),
    modelRecoveries: decodeModelRecoveries(
      decoder.field(value, "model_recoveries", path),
      `${path}.model_recoveries`,
    ),
    harnessTrace: decodeWave4HarnessTrace(value, path, "persona", "persona_generation"),
  };
}

export function decodePersonaSlotAssistOutput(
  raw: unknown,
  expectedSlot: PersonaSlot,
  path = "persona_slot_assist",
): DecodedPersonaSlotAssistOutput {
  const value = decoder.record(raw, path);
  const slot = decodePersonaSlot(
    decoder.field(value, "slot", path),
    `${path}.slot`,
  );
  decoder.equal(slot.kind, expectedSlot.kind, `${path}.slot.kind`);
  return {
    slot,
    modelRecoveries: decodeModelRecoveries(
      decoder.field(value, "model_recoveries", path),
      `${path}.model_recoveries`,
    ),
    harnessTrace: decodeWave4HarnessTrace(value, path, "persona", "persona_generation"),
  };
}

interface SceneDecodeState {
  ids: Set<string>;
  layerCount: number;
  objectCount: number;
  textBudget: number;
}

function createSceneDecodeState(initialTextBudget = 0): SceneDecodeState {
  return {
    ids: new Set(),
    layerCount: 0,
    objectCount: 0,
    textBudget: initialTextBudget,
  };
}

function registerSceneIdentity(
  state: SceneDecodeState,
  id: string,
  path: string,
): void {
  if (state.ids.has(id)) {
    throw new PersonaSceneDecodeError(`${path}.id`, "duplicate_scene_identity");
  }
  state.ids.add(id);
}

function decodeSceneObject(
  raw: unknown,
  path: string,
  state: SceneDecodeState,
): SceneObjectSnapshot {
  const value = decoder.record(raw, path);
  const object: SceneObjectSnapshot = {
    id: boundedString(decoder.field(value, "id", path), `${path}.id`, { maximum: 64 }),
    name: boundedString(decoder.field(value, "name", path), `${path}.name`, { maximum: 500 }),
    description: boundedString(
      decoder.field(value, "description", path),
      `${path}.description`,
      { maximum: 4000 },
    ),
    interaction: boundedString(
      decoder.field(value, "interaction", path),
      `${path}.interaction`,
      { maximum: 4000 },
    ),
    tags: boundedString(decoder.field(value, "tags", path), `${path}.tags`, {
      allowEmpty: true,
      maximum: 1000,
    }),
    reuseId: boundedString(
      decoder.field(value, "reuse_id", path),
      `${path}.reuse_id`,
      { maximum: 64 },
    ),
    reuseHint: boundedString(
      decoder.field(value, "reuse_hint", path),
      `${path}.reuse_hint`,
      { allowEmpty: true, maximum: 1000 },
    ),
  };
  registerSceneIdentity(state, object.id, path);
  state.objectCount += 1;
  if (state.objectCount > SCENE_MAX_OBJECT_COUNT) {
    throw new PersonaSceneDecodeError(path, "scene_object_budget_exceeded");
  }
  state.textBudget +=
    object.name.length +
    object.description.length +
    object.interaction.length +
    object.tags.length +
    object.reuseHint.length;
  return object;
}

function decodeSceneNode(
  raw: unknown,
  path: string,
  state: SceneDecodeState,
  depth: number,
): SceneTreeNode {
  if (depth > SCENE_MAX_DEPTH) {
    throw new PersonaSceneDecodeError(path, "scene_depth_budget_exceeded");
  }
  const value = decoder.record(raw, path);
  const id = boundedString(decoder.field(value, "id", path), `${path}.id`, { maximum: 64 });
  const reuseId = boundedString(
    decoder.field(value, "reuse_id", path),
    `${path}.reuse_id`,
    { maximum: 64 },
  );
  registerSceneIdentity(state, id, path);
  state.layerCount += 1;
  if (state.layerCount > SCENE_MAX_LAYER_COUNT) {
    throw new PersonaSceneDecodeError(path, "scene_layer_budget_exceeded");
  }
  const node: SceneTreeNode = {
    id,
    title: boundedString(decoder.field(value, "title", path), `${path}.title`, {
      maximum: 500,
    }),
    scopeLabel: boundedString(
      decoder.field(value, "scope_label", path),
      `${path}.scope_label`,
      { maximum: 500 },
    ),
    summary: boundedString(decoder.field(value, "summary", path), `${path}.summary`, {
      maximum: 4000,
    }),
    atmosphere: boundedString(
      decoder.field(value, "atmosphere", path),
      `${path}.atmosphere`,
      { maximum: 4000 },
    ),
    rules: boundedString(decoder.field(value, "rules", path), `${path}.rules`, {
      maximum: 4000,
    }),
    entrance: boundedString(decoder.field(value, "entrance", path), `${path}.entrance`, {
      maximum: 4000,
    }),
    tags: boundedString(decoder.field(value, "tags", path), `${path}.tags`, {
      allowEmpty: true,
      maximum: 1000,
    }),
    reuseId,
    reuseHint: boundedString(
      decoder.field(value, "reuse_hint", path),
      `${path}.reuse_hint`,
      { allowEmpty: true, maximum: 1000 },
    ),
    objects: decoder.array(
      decoder.field(value, "objects", path),
      `${path}.objects`,
      (item, itemPath) => decodeSceneObject(item, itemPath, state),
    ),
    children: [],
  };
  if (node.objects.length > 16) {
    throw new PersonaSceneDecodeError(`${path}.objects`, "scene_object_child_budget_exceeded");
  }
  const rawChildren = decoder.field(value, "children", path);
  const children = decoder.array(rawChildren, `${path}.children`, (item, itemPath) =>
    decodeSceneNode(item, itemPath, state, depth + 1),
  );
  if (children.length > 8) {
    throw new PersonaSceneDecodeError(`${path}.children`, "scene_layer_child_budget_exceeded");
  }
  node.children = children;
  state.textBudget +=
    node.title.length +
    node.scopeLabel.length +
    node.summary.length +
    node.atmosphere.length +
    node.rules.length +
    node.entrance.length +
    node.tags.length +
    node.reuseHint.length;
  return node;
}

function decodeSceneTree(
  raw: unknown,
  path: string,
  options: { allowEmpty?: boolean; sceneName?: string; sceneSummary?: string } = {},
): SceneTreeNode[] {
  const state = createSceneDecodeState(
    (options.sceneName?.length ?? 0) + (options.sceneSummary?.length ?? 0),
  );
  const tree = decoder.array(raw, path, (item, itemPath) =>
    decodeSceneNode(item, itemPath, state, 1),
  );
  if (tree.length > 8) {
    throw new PersonaSceneDecodeError(path, "scene_root_layer_budget_exceeded");
  }
  if (!options.allowEmpty && tree.length === 0) {
    throw new PersonaSceneDecodeError(path, "expected_non_empty_scene_tree");
  }
  if (state.textBudget > SCENE_MAX_TEXT_BUDGET) {
    throw new PersonaSceneDecodeError(path, "scene_text_budget_exceeded");
  }
  return tree;
}

function findSceneLayer(
  tree: SceneTreeNode[],
  id: string,
  parentPath: string[] = [],
): { node: SceneTreeNode; titlePath: string[] } | undefined {
  for (const node of tree) {
    const titlePath = [...parentPath, node.title];
    if (node.id === id) return { node, titlePath };
    const child = findSceneLayer(node.children, id, titlePath);
    if (child) return child;
  }
  return undefined;
}

function sceneLayerIds(tree: SceneTreeNode[]): string[] {
  const result: string[] = [];
  const visit = (nodes: SceneTreeNode[]) => {
    for (const node of nodes) {
      result.push(node.id);
      visit(node.children);
    }
  };
  visit(tree);
  return result;
}

function selectedLayerTags(tags: string): string[] {
  return [...new Set(tags.replaceAll("，", ",").split(",").map((item) => item.trim()).filter(Boolean))];
}

function arraysEqual(left: readonly string[], right: readonly string[]): boolean {
  return left.length === right.length && left.every((value, index) => value === right[index]);
}

function sceneObjectsEqual(
  left: readonly SceneObjectSnapshot[],
  right: readonly SceneObjectSnapshot[],
): boolean {
  return left.length === right.length && left.every((item, index) => {
    const other = right[index];
    return other !== undefined &&
      item.id === other.id &&
      item.name === other.name &&
      item.description === other.description &&
      item.interaction === other.interaction &&
      item.tags === other.tags &&
      item.reuseId === other.reuseId &&
      item.reuseHint === other.reuseHint;
  });
}

function sceneTreesEqual(left: readonly SceneTreeNode[], right: readonly SceneTreeNode[]): boolean {
  return left.length === right.length && left.every((item, index) => {
    const other = right[index];
    return other !== undefined &&
      item.id === other.id &&
      item.title === other.title &&
      item.scopeLabel === other.scopeLabel &&
      item.summary === other.summary &&
      item.atmosphere === other.atmosphere &&
      item.rules === other.rules &&
      item.entrance === other.entrance &&
      item.tags === other.tags &&
      item.reuseId === other.reuseId &&
      item.reuseHint === other.reuseHint &&
      sceneObjectsEqual(item.objects, other.objects) &&
      sceneTreesEqual(item.children, other.children);
  });
}

export function decodeSceneProfile(raw: unknown, path = "scene_profile"): SceneProfile {
  const value = decoder.record(raw, path);
  const sceneName = boundedString(
    decoder.field(value, "scene_name", path),
    `${path}.scene_name`,
    { maximum: 500 },
  );
  const summary = boundedString(decoder.field(value, "summary", path), `${path}.summary`, {
    maximum: 4000,
  });
  const sceneTree = decodeSceneTree(
    decoder.field(value, "scene_tree", path),
    `${path}.scene_tree`,
    { sceneName, sceneSummary: summary },
  );
  const sceneId = boundedString(
    decoder.field(value, "scene_id", path),
    `${path}.scene_id`,
    { maximum: 64 },
  );
  const selected = findSceneLayer(sceneTree, sceneId);
  if (!selected) {
    throw new PersonaSceneDecodeError(`${path}.scene_id`, "selected_scene_layer_missing");
  }
  const title = boundedString(decoder.field(value, "title", path), `${path}.title`, {
    maximum: 500,
  });
  decoder.equal(title, selected.node.title, `${path}.title`);
  const tags = decoder.stringArray(decoder.field(value, "tags", path), `${path}.tags`);
  if (!arraysEqual(tags, selectedLayerTags(selected.node.tags))) {
    throw new PersonaSceneDecodeError(`${path}.tags`, "scene_profile_tags_mismatch");
  }
  const selectedPath = decoder.stringArray(
    decoder.field(value, "selected_path", path),
    `${path}.selected_path`,
  );
  if (!arraysEqual(selectedPath, selected.titlePath)) {
    throw new PersonaSceneDecodeError(`${path}.selected_path`, "scene_profile_path_mismatch");
  }
  const focusObjectNames = decoder.stringArray(
    decoder.field(value, "focus_object_names", path),
    `${path}.focus_object_names`,
  );
  const expectedFocusObjectNames = selected.node.objects.slice(0, 4).map((item) => item.name);
  if (!arraysEqual(focusObjectNames, expectedFocusObjectNames)) {
    throw new PersonaSceneDecodeError(
      `${path}.focus_object_names`,
      "scene_profile_focus_objects_mismatch",
    );
  }
  return {
    sceneName,
    sceneId,
    title,
    summary,
    tags,
    selectedPath,
    focusObjectNames,
    sceneTree,
  };
}

function validateSceneStateProjection(input: {
  path: string;
  revision: number;
  sceneName: string;
  sceneSummary: string;
  sceneLayers: SceneTreeNode[];
  selectedLayerId: string;
  collapsedLayerIds: string[];
  sceneProfile?: SceneProfile;
  allowEmpty: boolean;
}): void {
  const {
    path,
    revision,
    sceneName,
    sceneSummary,
    sceneLayers,
    selectedLayerId,
    collapsedLayerIds,
    sceneProfile,
    allowEmpty,
  } = input;
  if (sceneLayers.length === 0) {
    if (
      !allowEmpty ||
      revision !== 0 ||
      sceneName !== "" ||
      sceneSummary !== "" ||
      selectedLayerId !== "" ||
      collapsedLayerIds.length !== 0 ||
      sceneProfile !== undefined
    ) {
      throw new PersonaSceneDecodeError(path, "invalid_empty_scene_state");
    }
    return;
  }
  if (!sceneName || !sceneSummary || !selectedLayerId) {
    throw new PersonaSceneDecodeError(path, "scene_committed_content_required");
  }
  const selected = findSceneLayer(sceneLayers, selectedLayerId);
  if (!selected) {
    throw new PersonaSceneDecodeError(`${path}.selected_layer_id`, "selected_scene_layer_missing");
  }
  decoder.unique(collapsedLayerIds, `${path}.collapsed_layer_ids`);
  const layerIds = new Set(sceneLayerIds(sceneLayers));
  for (const [index, id] of collapsedLayerIds.entries()) {
    if (!layerIds.has(id)) {
      throw new PersonaSceneDecodeError(
        `${path}.collapsed_layer_ids[${index}]`,
        "collapsed_scene_layer_missing",
      );
    }
  }
  if (!sceneProfile) {
    throw new PersonaSceneDecodeError(`${path}.scene_profile`, "committed_scene_profile_required");
  }
  decoder.equal(sceneProfile.sceneId, selectedLayerId, `${path}.scene_profile.scene_id`);
  decoder.equal(sceneProfile.sceneName, sceneName, `${path}.scene_profile.scene_name`);
  decoder.equal(sceneProfile.summary, sceneSummary, `${path}.scene_profile.summary`);
  if (!sceneTreesEqual(sceneProfile.sceneTree, sceneLayers)) {
    throw new PersonaSceneDecodeError(
      `${path}.scene_profile.scene_tree`,
      "scene_profile_tree_mismatch",
    );
  }
}

function decodeNullableSceneProfile(raw: unknown, path: string): SceneProfile | undefined {
  return decoder.nullable(raw, path, decodeSceneProfile) ?? undefined;
}

export function decodeSceneTreeGenerateResult(
  raw: unknown,
  options: { expectedMode: "keywords" | "long_text"; path?: string },
): DecodedSceneTreeGenerateResult {
  const path = options.path ?? "scene_tree_generate";
  const value = decoder.record(raw, path);
  const contractVersion = decoder.string(
    decoder.field(value, "contract_version", path),
    `${path}.contract_version`,
  );
  decoder.equal(
    contractVersion,
    SCENE_TREE_GENERATE_RESPONSE_VERSION,
    `${path}.contract_version`,
  );
  const mode = decoder.enumeration(
    decoder.field(value, "mode", path),
    GENERATION_MODES,
    `${path}.mode`,
  );
  decoder.equal(mode, options.expectedMode, `${path}.mode`);
  const sceneName = boundedString(
    decoder.field(value, "scene_name", path),
    `${path}.scene_name`,
    { maximum: 500 },
  );
  const sceneSummary = boundedString(
    decoder.field(value, "scene_summary", path),
    `${path}.scene_summary`,
    { maximum: 4000 },
  );
  const sceneLayers = decodeSceneTree(
    decoder.field(value, "scene_layers", path),
    `${path}.scene_layers`,
    { sceneName, sceneSummary },
  );
  const selectedLayerId = decoder.string(
    decoder.field(value, "selected_layer_id", path),
    `${path}.selected_layer_id`,
  );
  if (!findSceneLayer(sceneLayers, selectedLayerId)) {
    throw new PersonaSceneDecodeError(
      `${path}.selected_layer_id`,
      "selected_scene_layer_missing",
    );
  }
  return {
    mode,
    usedModel: decoder.string(
      decoder.field(value, "used_model", path),
      `${path}.used_model`,
      true,
    ),
    usedWebSearch: decoder.boolean(
      decoder.field(value, "used_web_search", path),
      `${path}.used_web_search`,
    ),
    sceneName,
    sceneSummary,
    selectedLayerId,
    sceneLayers,
    modelRecoveries: decodeModelRecoveries(
      decoder.field(value, "model_recoveries", path),
      `${path}.model_recoveries`,
    ),
    harnessTrace: decodeWave4HarnessTrace(value, path, "scene", "scene_generation"),
  };
}

export function decodeSceneSetupState(
  raw: unknown,
  options: { expectedRevision?: number; path?: string } = {},
): DecodedSceneSetupState {
  const path = options.path ?? "scene_setup";
  const value = decoder.record(raw, path);
  const configId = decoder.string(
    decoder.field(value, "config_id", path),
    `${path}.config_id`,
  );
  decoder.equal(configId, "default", `${path}.config_id`);
  const revision = decoder.integer(decoder.field(value, "revision", path), `${path}.revision`);
  if (options.expectedRevision !== undefined) {
    decoder.equal(revision, options.expectedRevision, `${path}.revision`);
  }
  const sceneName = boundedString(
    decoder.field(value, "scene_name", path),
    `${path}.scene_name`,
    { allowEmpty: true, maximum: 500 },
  );
  const sceneSummary = boundedString(
    decoder.field(value, "scene_summary", path),
    `${path}.scene_summary`,
    { allowEmpty: true, maximum: 4000 },
  );
  const sceneLayers = decodeSceneTree(
    decoder.field(value, "scene_layers", path),
    `${path}.scene_layers`,
    { allowEmpty: true, sceneName, sceneSummary },
  );
  const selectedLayerId = decoder.string(
    decoder.field(value, "selected_layer_id", path),
    `${path}.selected_layer_id`,
    true,
  );
  const collapsedLayerIds = decoder.stringArray(
    decoder.field(value, "collapsed_layer_ids", path),
    `${path}.collapsed_layer_ids`,
  );
  const sceneProfile = decodeNullableSceneProfile(
    decoder.field(value, "scene_profile", path),
    `${path}.scene_profile`,
  );
  validateSceneStateProjection({
    path,
    revision,
    sceneName,
    sceneSummary,
    sceneLayers,
    selectedLayerId,
    collapsedLayerIds,
    sceneProfile,
    allowEmpty: true,
  });
  return {
    revision,
    updatedAt: decoder.string(
      decoder.field(value, "updated_at", path),
      `${path}.updated_at`,
    ),
    sceneName,
    sceneSummary,
    sceneLayers,
    selectedLayerId,
    collapsedLayerIds,
    ...(sceneProfile ? { sceneProfile } : {}),
  };
}

export function decodeSceneLibraryItem(
  raw: unknown,
  options: { expectedSceneId?: string; expectedRevision?: number; path?: string } = {},
): DecodedSceneLibraryItem {
  const path = options.path ?? "scene_library_item";
  const value = decoder.record(raw, path);
  const sceneId = decoder.string(
    decoder.field(value, "scene_id", path),
    `${path}.scene_id`,
  );
  if (options.expectedSceneId !== undefined) {
    decoder.equal(sceneId, options.expectedSceneId, `${path}.scene_id`);
  }
  const configId = decoder.string(
    decoder.field(value, "config_id", path),
    `${path}.config_id`,
  );
  decoder.equal(configId, sceneId, `${path}.config_id`);
  const revision = decoder.integer(
    decoder.field(value, "revision", path),
    `${path}.revision`,
    1,
  );
  if (options.expectedRevision !== undefined) {
    decoder.equal(revision, options.expectedRevision, `${path}.revision`);
  }
  const sceneName = boundedString(
    decoder.field(value, "scene_name", path),
    `${path}.scene_name`,
    { maximum: 500 },
  );
  const sceneSummary = boundedString(
    decoder.field(value, "scene_summary", path),
    `${path}.scene_summary`,
    { maximum: 4000 },
  );
  const sceneLayers = decodeSceneTree(
    decoder.field(value, "scene_layers", path),
    `${path}.scene_layers`,
    { sceneName, sceneSummary },
  );
  const selectedLayerId = decoder.string(
    decoder.field(value, "selected_layer_id", path),
    `${path}.selected_layer_id`,
  );
  const collapsedLayerIds = decoder.stringArray(
    decoder.field(value, "collapsed_layer_ids", path),
    `${path}.collapsed_layer_ids`,
  );
  const sceneProfile = decodeNullableSceneProfile(
    decoder.field(value, "scene_profile", path),
    `${path}.scene_profile`,
  );
  validateSceneStateProjection({
    path,
    revision,
    sceneName,
    sceneSummary,
    sceneLayers,
    selectedLayerId,
    collapsedLayerIds,
    sceneProfile,
    allowEmpty: false,
  });
  return {
    sceneId,
    revision,
    createdAt: decoder.string(
      decoder.field(value, "created_at", path),
      `${path}.created_at`,
    ),
    updatedAt: decoder.string(
      decoder.field(value, "updated_at", path),
      `${path}.updated_at`,
    ),
    sceneName,
    sceneSummary,
    sceneLayers,
    selectedLayerId,
    collapsedLayerIds,
    ...(sceneProfile ? { sceneProfile } : {}),
  };
}

export function decodeSceneLibraryList(
  raw: unknown,
  path = "scene_library_list",
): DecodedSceneLibraryItem[] {
  const value = decoder.record(raw, path);
  const items = decoder.array(
    decoder.field(value, "items", path),
    `${path}.items`,
    (item, itemPath) => decodeSceneLibraryItem(item, { path: itemPath }),
  );
  decoder.unique(items.map((item) => item.sceneId), `${path}.items.scene_id`);
  return items;
}

export function decodeReusableSceneNode(
  raw: unknown,
  path = "reusable_scene_node",
): DecodedReusableSceneNode {
  const value = decoder.record(raw, path);
  const nodeType = decoder.enumeration(
    decoder.field(value, "node_type", path),
    SCENE_NODE_TYPES,
    `${path}.node_type`,
  );
  const rawLayerNode = decoder.field(value, "layer_node", path);
  const rawObjectNode = decoder.field(value, "object_node", path);
  let layerNode: SceneTreeNode | undefined;
  let objectNode: SceneObjectSnapshot | undefined;
  if (nodeType === "layer") {
    if (rawLayerNode === null || rawObjectNode !== null) {
      throw new PersonaSceneDecodeError(path, "reusable_scene_node_variant_mismatch");
    }
    const state = createSceneDecodeState();
    layerNode = decodeSceneNode(rawLayerNode, `${path}.layer_node`, state, 1);
    if (state.textBudget > SCENE_MAX_TEXT_BUDGET) {
      throw new PersonaSceneDecodeError(`${path}.layer_node`, "scene_text_budget_exceeded");
    }
  } else {
    if (rawObjectNode === null || rawLayerNode !== null) {
      throw new PersonaSceneDecodeError(path, "reusable_scene_node_variant_mismatch");
    }
    objectNode = decodeSceneObject(
      rawObjectNode,
      `${path}.object_node`,
      createSceneDecodeState(),
    );
  }
  const title = decoder.string(decoder.field(value, "title", path), `${path}.title`);
  const summary = decoder.string(
    decoder.field(value, "summary", path),
    `${path}.summary`,
    true,
  );
  const reuseId = decoder.string(
    decoder.field(value, "reuse_id", path),
    `${path}.reuse_id`,
    true,
  );
  const reuseHint = decoder.string(
    decoder.field(value, "reuse_hint", path),
    `${path}.reuse_hint`,
    true,
  );
  return {
    nodeId: decoder.string(decoder.field(value, "node_id", path), `${path}.node_id`),
    nodeType,
    title,
    summary,
    tags: decoder.stringArray(decoder.field(value, "tags", path), `${path}.tags`),
    reuseId,
    reuseHint,
    sourceSceneId: decoder.string(
      decoder.field(value, "source_scene_id", path),
      `${path}.source_scene_id`,
      true,
    ),
    sourceSceneName: decoder.string(
      decoder.field(value, "source_scene_name", path),
      `${path}.source_scene_name`,
      true,
    ),
    ...(layerNode ? { layerNode } : {}),
    ...(objectNode ? { objectNode } : {}),
    createdAt: decoder.string(decoder.field(value, "created_at", path), `${path}.created_at`),
    updatedAt: decoder.string(decoder.field(value, "updated_at", path), `${path}.updated_at`),
  };
}

export function decodeReusableSceneNodeList(
  raw: unknown,
  path = "reusable_scene_node_list",
): DecodedReusableSceneNode[] {
  const value = decoder.record(raw, path);
  const items = decoder.array(
    decoder.field(value, "items", path),
    `${path}.items`,
    decodeReusableSceneNode,
  );
  decoder.unique(items.map((item) => item.nodeId), `${path}.items.node_id`);
  return items;
}

export function decodeDeletedIdentity(
  raw: unknown,
  options: { wireField: string; expectedId: string; path: string },
): string {
  const value = decoder.record(raw, options.path);
  const deletedId = decoder.string(
    decoder.field(value, options.wireField, options.path),
    `${options.path}.${options.wireField}`,
  );
  decoder.equal(deletedId, options.expectedId, `${options.path}.${options.wireField}`);
  return deletedId;
}
