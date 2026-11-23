import {
  diagnosticDecode,
  DiagnosticContext as DiagnosticContext,
} from "../diagnostics";
import {
  decodeDeletedIdentity,
  decodeReusableSceneNode,
  decodeReusableSceneNodeList,
  decodeSceneLibraryItem,
  decodeSceneLibraryList,
  decodeSceneSetupState,
  decodeSceneTreeGenerateResult,
} from "../persona-scene-decode";

import { AI_BASE_URL, request, readJson } from "./_shared";
import { serializeSceneTree } from "./scene-serialize";

export interface SceneTreeGenerateResult {
  mode: "keywords" | "long_text";
  usedModel: string;
  usedWebSearch: boolean;
  sceneName: string;
  sceneSummary: string;
  selectedLayerId: string;
  sceneLayers: import("@vibe-learner/shared").SceneTreeNode[];
  modelRecoveries?: import("@vibe-learner/shared").ModelRecovery[];
}

export interface SceneSetupStatePayload {
  revision: number;
  updatedAt: string;
  sceneName: string;
  sceneSummary: string;
  sceneLayers: import("@vibe-learner/shared").SceneTreeNode[];
  selectedLayerId: string;
  collapsedLayerIds: string[];
  sceneProfile?: import("@vibe-learner/shared").SceneProfile;
}

export interface SceneLibraryItemPayload {
  sceneId: string;
  revision: number;
  createdAt: string;
  updatedAt: string;
  sceneName: string;
  sceneSummary: string;
  sceneLayers: import("@vibe-learner/shared").SceneTreeNode[];
  selectedLayerId: string;
  collapsedLayerIds: string[];
  sceneProfile?: import("@vibe-learner/shared").SceneProfile;
}

export interface ReusableSceneNodePayload {
  nodeId: string;
  nodeType: "layer" | "object";
  title: string;
  summary: string;
  tags: string[];
  reuseId: string;
  reuseHint: string;
  sourceSceneId: string;
  sourceSceneName: string;
  layerNode?: import("@vibe-learner/shared").SceneTreeNode;
  objectNode?: import("@vibe-learner/shared").SceneObjectSnapshot;
  createdAt: string;
  updatedAt: string;
}

export async function generateSceneTree(
  input: {
    mode: "keywords" | "long_text";
    inputText: string;
    layerCount?: number | null;
  },
  context?: DiagnosticContext,
): Promise<SceneTreeGenerateResult> {
  const requestBody: Record<string, unknown> = {
    mode: input.mode,
    input_text: input.inputText,
  };
  if (typeof input.layerCount === "number" && Number.isFinite(input.layerCount)) {
    requestBody.layer_count = input.layerCount;
  }
  const diagnosticResponse = await request(
    `${AI_BASE_URL()}/scene-setup/generate`,
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
    decodeSceneTreeGenerateResult(payload, { expectedMode: input.mode }),
  );
}

export async function getSceneSetupState(): Promise<SceneSetupStatePayload> {
  const diagnosticResponse = await request(`${AI_BASE_URL()}/scene-setup`);
  const payload = await readJson<unknown>(diagnosticResponse);
  return diagnosticDecode(diagnosticResponse, () => decodeSceneSetupState(payload));
}

export async function updateSceneSetupState(input: {
  expectedRevision: number;
  sceneLayers: unknown[];
  selectedLayerId: string;
  collapsedLayerIds: string[];
  sceneName?: string;
  sceneSummary?: string;
}): Promise<SceneSetupStatePayload> {
  const diagnosticResponse = await request(`${AI_BASE_URL()}/scene-setup`, {
    method: "PUT",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      contract_version: "scene-committed-save-v1",
      expected_revision: input.expectedRevision,
      scene_name: input.sceneName ?? "",
      scene_summary: input.sceneSummary ?? "",
      scene_layers: serializeSceneTree(
        input.sceneLayers as import("@vibe-learner/shared").SceneTreeNode[],
      ),
      selected_layer_id: input.selectedLayerId,
      collapsed_layer_ids: input.collapsedLayerIds,
    }),
  });
  const payload = await readJson<unknown>(diagnosticResponse);
  return diagnosticDecode(diagnosticResponse, () =>
    decodeSceneSetupState(payload, {
      expectedRevision: input.expectedRevision + 1,
    }),
  );
}

export async function listSceneLibrary(): Promise<SceneLibraryItemPayload[]> {
  const diagnosticResponse = await request(`${AI_BASE_URL()}/scene-library`);
  const payload = await readJson<unknown>(diagnosticResponse);
  return diagnosticDecode(diagnosticResponse, () => decodeSceneLibraryList(payload));
}

export async function getSceneLibraryItem(
  sceneId: string,
): Promise<SceneLibraryItemPayload> {
  const diagnosticResponse = await request(`${AI_BASE_URL()}/scene-library/${sceneId}`);
  const payload = await readJson<unknown>(diagnosticResponse);
  return diagnosticDecode(diagnosticResponse, () =>
    decodeSceneLibraryItem(payload, { expectedSceneId: sceneId }),
  );
}

export async function createSceneLibraryItem(
  input: {
    sceneName: string;
    sceneSummary: string;
    sceneLayers: unknown[];
    selectedLayerId: string;
    collapsedLayerIds: string[];
  },
  context?: DiagnosticContext,
): Promise<SceneLibraryItemPayload> {
  const diagnosticResponse = await request(
    `${AI_BASE_URL()}/scene-library`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        contract_version: "scene-committed-save-v1",
        expected_revision: 0,
        scene_name: input.sceneName,
        scene_summary: input.sceneSummary,
        scene_layers: serializeSceneTree(
          input.sceneLayers as import("@vibe-learner/shared").SceneTreeNode[],
        ),
        selected_layer_id: input.selectedLayerId,
        collapsed_layer_ids: input.collapsedLayerIds,
      }),
    },
    context,
  );
  const payload = await readJson<unknown>(diagnosticResponse);
  return diagnosticDecode(diagnosticResponse, () =>
    decodeSceneLibraryItem(payload, { expectedRevision: 1 }),
  );
}

export async function updateSceneLibraryItem(
  sceneId: string,
  input: {
    expectedRevision: number;
    sceneName: string;
    sceneSummary: string;
    sceneLayers: unknown[];
    selectedLayerId: string;
    collapsedLayerIds: string[];
  },
  context?: DiagnosticContext,
): Promise<SceneLibraryItemPayload> {
  const diagnosticResponse = await request(
    `${AI_BASE_URL()}/scene-library/${sceneId}`,
    {
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        contract_version: "scene-committed-save-v1",
        expected_revision: input.expectedRevision,
        scene_name: input.sceneName,
        scene_summary: input.sceneSummary,
        scene_layers: serializeSceneTree(
          input.sceneLayers as import("@vibe-learner/shared").SceneTreeNode[],
        ),
        selected_layer_id: input.selectedLayerId,
        collapsed_layer_ids: input.collapsedLayerIds,
      }),
    },
    context,
  );
  const payload = await readJson<unknown>(diagnosticResponse);
  return diagnosticDecode(diagnosticResponse, () =>
    decodeSceneLibraryItem(payload, {
      expectedSceneId: sceneId,
      expectedRevision: input.expectedRevision + 1,
    }),
  );
}

export async function deleteSceneLibraryItem(
  sceneId: string,
): Promise<{ deletedSceneId: string }> {
  const diagnosticResponse = await request(
    `${AI_BASE_URL()}/scene-library/${sceneId}`,
    {
      method: "DELETE",
    },
  );
  const payload = await readJson<unknown>(diagnosticResponse);
  return {
    deletedSceneId: diagnosticDecode(diagnosticResponse, () =>
      decodeDeletedIdentity(payload, {
        wireField: "deleted_scene_id",
        expectedId: sceneId,
        path: "scene_library_delete",
      }),
    ),
  };
}

export async function listReusableSceneNodes(): Promise<ReusableSceneNodePayload[]> {
  const diagnosticResponse = await request(`${AI_BASE_URL()}/reusable-scene-nodes`);
  const payload = await readJson<unknown>(diagnosticResponse);
  return diagnosticDecode(diagnosticResponse, () =>
    decodeReusableSceneNodeList(payload),
  );
}

export async function createReusableSceneNode(input: {
  nodeType: "layer" | "object";
  title: string;
  summary?: string;
  tags?: string[];
  reuseId?: string;
  reuseHint?: string;
  sourceSceneId?: string;
  sourceSceneName?: string;
  layerNode?: import("@vibe-learner/shared").SceneTreeNode | null;
  objectNode?: import("@vibe-learner/shared").SceneObjectSnapshot | null;
}): Promise<ReusableSceneNodePayload> {
  const diagnosticResponse = await request(`${AI_BASE_URL()}/reusable-scene-nodes`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      node_type: input.nodeType,
      title: input.title,
      summary: input.summary ?? "",
      tags: input.tags ?? [],
      reuse_id: input.reuseId ?? "",
      reuse_hint: input.reuseHint ?? "",
      source_scene_id: input.sourceSceneId ?? "",
      source_scene_name: input.sourceSceneName ?? "",
      layer_node: input.layerNode ? serializeSceneTree([input.layerNode])[0] : null,
      object_node: input.objectNode
        ? {
            id: input.objectNode.id,
            name: input.objectNode.name,
            description: input.objectNode.description,
            interaction: input.objectNode.interaction,
            tags: input.objectNode.tags,
            reuse_id: input.objectNode.reuseId,
            reuse_hint: input.objectNode.reuseHint,
          }
        : null,
    }),
  });
  const payload = await readJson<unknown>(diagnosticResponse);
  return diagnosticDecode(diagnosticResponse, () => decodeReusableSceneNode(payload));
}

export async function deleteReusableSceneNode(
  nodeId: string,
): Promise<{ deletedReusableSceneNodeId: string }> {
  const diagnosticResponse = await request(
    `${AI_BASE_URL()}/reusable-scene-nodes/${nodeId}`,
    {
      method: "DELETE",
    },
  );
  const payload = await readJson<unknown>(diagnosticResponse);
  return {
    deletedReusableSceneNodeId: diagnosticDecode(diagnosticResponse, () =>
      decodeDeletedIdentity(payload, {
        wireField: "deleted_reusable_scene_node_id",
        expectedId: nodeId,
        path: "reusable_scene_node_delete",
      }),
    ),
  };
}
