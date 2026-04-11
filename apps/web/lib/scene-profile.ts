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
      selectedLayerId?: unknown;
    };
    const sceneLayers = Array.isArray(payload.sceneLayers) ? payload.sceneLayers : [];
    if (!sceneLayers.length) {
      return undefined;
    }

    const selectedLayerId = typeof payload.selectedLayerId === "string" ? payload.selectedLayerId : "";
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
    const summary = String(selectedLayer?.summary ?? "") || `场景路径：${selectedPath.join(" > ")}`;
    const sceneId = String(selectedLayer?.id ?? "scene-default");

    return {
      sceneId,
      title,
      summary,
      tags,
      selectedPath,
      focusObjectNames: focusObjects,
    };
  } catch {
    return undefined;
  }
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
