import type { SceneProfile } from "@vibe-learner/shared";

const SCENE_STORAGE_KEY = "vibe-learner.scene-setup.v1";

type RawSceneLayer = {
  id?: unknown;
  title?: unknown;
  summary?: unknown;
  objects?: unknown;
  children?: unknown;
};

type RawSceneObject = {
  name?: unknown;
  tags?: unknown;
};

type RawSceneTreeNode = {
  id?: unknown;
  title?: unknown;
  scopeLabel?: unknown;
  summary?: unknown;
  atmosphere?: unknown;
  rules?: unknown;
  entrance?: unknown;
  objects?: unknown;
  children?: unknown;
};

export function readSceneProfileFromLocalStorage(): SceneProfile | undefined {
  if (typeof globalThis.localStorage === "undefined") {
    return undefined;
  }
  try {
    const raw = globalThis.localStorage.getItem(SCENE_STORAGE_KEY);
    if (!raw) {
      return undefined;
    }
    const payload = JSON.parse(raw) as {
      sceneLayers?: unknown;
      scene_layers?: unknown;
      selectedLayerId?: unknown;
      selected_layer_id?: unknown;
      sceneName?: unknown;
      scene_name?: unknown;
      sceneSummary?: unknown;
      scene_summary?: unknown;
    };
    const sceneLayers = Array.isArray(payload.sceneLayers)
      ? payload.sceneLayers
      : Array.isArray(payload.scene_layers)
        ? payload.scene_layers
        : [];
    if (!sceneLayers.length) {
      return undefined;
    }

    const selectedLayerId = typeof payload.selectedLayerId === "string"
      ? payload.selectedLayerId
      : typeof payload.selected_layer_id === "string"
        ? payload.selected_layer_id
        : "";
    const selectedResult = findLayerById(sceneLayers as RawSceneLayer[], selectedLayerId);
    const selectedLayer = selectedResult?.layer ?? (sceneLayers[0] as RawSceneLayer);
    const selectedPath = selectedResult?.path ?? [String((sceneLayers[0] as RawSceneLayer)?.title ?? "学习场景")];

    const focusObjects = Array.isArray(selectedLayer?.objects)
      ? selectedLayer.objects.slice(0, 4).map((item) => String((item as RawSceneObject).name ?? "")).filter(Boolean)
      : [];
    const tags = Array.isArray(selectedLayer?.objects)
      ? selectedLayer.objects
          .flatMap((item) => String((item as RawSceneObject).tags ?? "").split(","))
          .map((item) => item.trim())
          .filter(Boolean)
          .slice(0, 8)
      : [];

    const title = String(selectedLayer?.title ?? selectedPath[selectedPath.length - 1] ?? "默认教室");
    const sceneSummary = typeof payload.sceneSummary === "string"
      ? payload.sceneSummary
      : typeof payload.scene_summary === "string"
        ? payload.scene_summary
        : "";
    const sceneId = String(selectedLayer?.id ?? "scene-default");
    const sceneName = typeof payload.sceneName === "string"
      ? payload.sceneName
      : typeof payload.scene_name === "string"
        ? payload.scene_name
        : "";

    return {
      sceneName,
      sceneId,
      title,
      summary: sceneSummary || `场景路径：${selectedPath.join(" > ")}`,
      tags,
      selectedPath,
      focusObjectNames: focusObjects,
      sceneTree: normalizeSceneTree(sceneLayers as RawSceneTreeNode[]),
    };
  } catch {
    return undefined;
  }
}

function normalizeSceneTree(nodes: RawSceneTreeNode[]): import("@vibe-learner/shared").SceneTreeNode[] {
  return nodes.map((node) => ({
    id: String(node.id ?? ""),
    title: String(node.title ?? "未命名层级"),
    scopeLabel: String(node.scopeLabel ?? "未定义范围"),
    summary: String(node.summary ?? ""),
    atmosphere: String(node.atmosphere ?? ""),
    rules: String(node.rules ?? ""),
    entrance: String(node.entrance ?? ""),
    objects: Array.isArray(node.objects)
      ? node.objects.map((item) => ({
          id: String((item as Record<string, unknown>).id ?? ""),
          name: String((item as Record<string, unknown>).name ?? ""),
          description: String((item as Record<string, unknown>).description ?? ""),
          interaction: String((item as Record<string, unknown>).interaction ?? ""),
          tags: String((item as Record<string, unknown>).tags ?? ""),
        }))
      : [],
    children: Array.isArray(node.children) ? normalizeSceneTree(node.children as RawSceneTreeNode[]) : [],
  }));
}

function findLayerById(
  layers: RawSceneLayer[],
  targetId: string,
  path: string[] = []
): { layer: RawSceneLayer; path: string[] } | null {
  for (const layer of layers) {
    const nextPath = [...path, String(layer.title ?? "未命名层级")];
    if (targetId && String(layer.id ?? "") === targetId) {
      return { layer, path: nextPath };
    }
    const children = Array.isArray(layer.children) ? (layer.children as RawSceneLayer[]) : [];
    const found = findLayerById(children, targetId, nextPath);
    if (found) {
      return found;
    }
  }
  return null;
}
