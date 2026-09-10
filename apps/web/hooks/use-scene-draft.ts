"use client";

import { useEffect, useMemo, useRef, useState, type SetStateAction } from "react";
import type { AsyncResultScope } from "../lib/async-result-fence";
import {
  INITIAL_SCENE,
  SCENE_STORAGE_KEY,
  collectLayerIds,
  findLayerById,
  findObjectById,
  findLayerPath,
  deriveSceneProfile,
  countSceneNodes,
  countSceneObjects,
  normalizeSceneTreeNodeForProfile,
  parseSceneImportPayload,
  type SceneLayer,
  type SceneImportPayload,
} from "../lib/scene-editor-model";

export interface SceneDraftStorage {
  read: () => unknown;
  write: (payload: SceneImportPayload & { version: number; savedAt: string }) => void;
}
export interface SceneDraftClock {
  schedule: (callback: () => void, delay: number) => unknown;
  cancel: (handle: unknown) => void;
}
const localStorage: SceneDraftStorage = {
  read: () => { const raw = globalThis.localStorage?.getItem(SCENE_STORAGE_KEY); return raw ? JSON.parse(raw) : null; },
  write: payload => globalThis.localStorage?.setItem(SCENE_STORAGE_KEY, JSON.stringify(payload)),
};
const clock: SceneDraftClock = {
  schedule: (callback, delay) => setTimeout(callback, delay),
  cancel: handle => clearTimeout(handle as ReturnType<typeof setTimeout>),
};

export function useSceneDraft({ onSelectionChange, onImported, onNotice }: {
  onSelectionChange: () => void;
  onImported: () => void;
  onNotice: (message: string) => void;
}, storage = localStorage, scheduler = clock) {
  const [sceneLayers, setSceneLayers] = useState<SceneLayer[]>(INITIAL_SCENE);
  const [sceneName, setSceneName] = useState("示例场景");
  const [sceneSummary, setSceneSummary] = useState("从世界整体的学术框架出发，逐层建立观察者在微观教室中的完整感受。这个示例展示了如何从宏观规则层层推导到具体互动对象。");
  const [selectedLayerId, setSelectedLayerId] = useState(INITIAL_SCENE[0]?.id ?? "");
  const [collapsedLayerIds, setCollapsedLayerIds] = useState<string[]>(() => collectLayerIds(INITIAL_SCENE).filter(id => !INITIAL_SCENE.some(layer => layer.id === id)));
  const [selectedObjectId, setSelectedObjectId] = useState("");
  const sceneDraftRevisionRef = useRef(0);
  const sceneSubjectIdRef = useRef("scene-editor:local");
  const selectedLayerIdRef = useRef(INITIAL_SCENE[0]?.id ?? "");
  const selectedObjectIdRef = useRef("");
  const activeSceneFieldTargetRef = useRef(
    `scene-layer:${INITIAL_SCENE[0]?.id ?? "none"}`,
  );
  function currentSceneAsyncScope(fieldTarget = activeSceneFieldTargetRef.current): AsyncResultScope {
    return {
      subjectId: sceneSubjectIdRef.current,
      draftRevision: sceneDraftRevisionRef.current,
      fieldTarget,
    };
  }

  function updateSceneLayersState(next: SetStateAction<SceneLayer[]>): void {
    sceneDraftRevisionRef.current += 1;
    setSceneLayers(next);
  }

  function updateSceneGenerationInput(update: () => void): void {
    sceneDraftRevisionRef.current += 1;
    update();
  }

  function selectSceneLayer(layerId: string): void {
    onSelectionChange();
    selectedLayerIdRef.current = layerId;
    selectedObjectIdRef.current = "";
    activeSceneFieldTargetRef.current = `scene-layer:${layerId || "none"}`;
    setSelectedObjectId("");
    setSelectedLayerId(layerId);
  }

  function selectSceneObject(objectId: string): void {
    onSelectionChange();
    selectedLayerIdRef.current = "";
    selectedObjectIdRef.current = objectId;
    activeSceneFieldTargetRef.current = `scene-object:${objectId || "none"}`;
    setSelectedLayerId("");
    setSelectedObjectId(objectId);
  }

  const selectedLayer = useMemo(() => findLayerById(sceneLayers, selectedLayerId), [sceneLayers, selectedLayerId]);
  const selectedObjectTarget = useMemo(
    () => (selectedObjectId ? findObjectById(sceneLayers, selectedObjectId) : null),
    [sceneLayers, selectedObjectId]
  );
  // Editor focus may be an object or collapsed; persisted scenes still need a layer.
  const sceneSelectionLayerId = selectedLayer?.id ?? selectedObjectTarget?.layer.id ?? sceneLayers[0]?.id ?? "";
  const selectedPath = useMemo(() => findLayerPath(sceneLayers, selectedLayerId), [sceneLayers, selectedLayerId]);
  const sceneProfilePreview = useMemo(
    () => deriveSceneProfile(sceneLayers, sceneSelectionLayerId, sceneName.trim(), sceneSummary.trim()),
    [sceneLayers, sceneSelectionLayerId, sceneName, sceneSummary]
  );
  const sceneNodeCount = useMemo(
    () => countSceneNodes(sceneLayers.map((layer) => normalizeSceneTreeNodeForProfile(layer))),
    [sceneLayers]
  );
  const sceneObjectCount = useMemo(() => countSceneObjects(sceneLayers), [sceneLayers]);
  useEffect(() => {
    if (selectedLayerId && !selectedLayer && sceneLayers[0]?.id) {
      selectSceneLayer(sceneLayers[0].id);
    }
  }, [sceneLayers, selectedLayer, selectedLayerId]);

  useEffect(() => {
    if (selectedObjectId && !selectedObjectTarget) {
      selectSceneObject("");
    }
  }, [selectedObjectId, selectedObjectTarget]);

  function applySceneImport(
    imported: SceneImportPayload,
    message: string,
    subjectId = "scene-editor:local",
  ) {
    const knownIds = new Set(collectLayerIds(imported.sceneLayers));
    const nextSelectedLayerId =
      imported.selectedLayerId && knownIds.has(imported.selectedLayerId)
        ? imported.selectedLayerId
        : imported.sceneLayers[0]?.id ?? "";
    sceneDraftRevisionRef.current += 1;
    sceneSubjectIdRef.current = subjectId;
    selectedLayerIdRef.current = nextSelectedLayerId;
    selectedObjectIdRef.current = "";
    activeSceneFieldTargetRef.current = `scene-layer:${nextSelectedLayerId || "none"}`;
    onSelectionChange();
    onImported();
    setSceneLayers(imported.sceneLayers);
    setSceneName(String(imported.sceneName || ""));
    setSceneSummary(String(imported.sceneSummary || ""));
    setSelectedLayerId(nextSelectedLayerId);
    setSelectedObjectId("");
    setCollapsedLayerIds(imported.collapsedLayerIds.filter((id) => knownIds.has(id)));
    onNotice(message);
  }

  function setSceneFieldTarget(target: string) { activeSceneFieldTargetRef.current = target; }
  function toggleLayerSelection(layerId: string) { selectSceneLayer(selectedLayerIdRef.current === layerId ? "" : layerId); }
  function toggleObjectSelection(objectId: string) { selectSceneObject(selectedObjectIdRef.current === objectId ? "" : objectId); }
  const [hydrated, setHydrated] = useState(false);
  const pendingRef = useRef<SceneImportPayload | null>(null);
  function flushDraft() {
    const pending = pendingRef.current;
    if (!pending) return;
    try {
      storage.write({ ...pending, version: 1, savedAt: new Date().toISOString() });
      pendingRef.current = null;
    } catch {
      // Local fallback is best effort; a later edit or pagehide can retry it.
    }
  }
  useEffect(() => {
    try {
      const raw = storage.read();
      if (raw) applySceneImport(parseSceneImportPayload(raw), "已加载本地保存场景。");
    } catch {
      onNotice("本地保存内容解析失败，已忽略。");
    }
    setHydrated(true);
    window.addEventListener("pagehide", flushDraft);
    return () => {
      window.removeEventListener("pagehide", flushDraft);
      flushDraft();
    };
  }, []);
  useEffect(() => {
    if (!hydrated) return;
    pendingRef.current = { sceneName, sceneSummary, sceneLayers, selectedLayerId: sceneSelectionLayerId, collapsedLayerIds };
    const timer = scheduler.schedule(flushDraft, 700);
    return () => scheduler.cancel(timer);
  }, [hydrated, sceneLayers, sceneName, sceneSummary, sceneSelectionLayerId, collapsedLayerIds]);
  return {
    sceneLayers,
    sceneName,
    setSceneName,
    sceneSummary,
    setSceneSummary,
    selectedLayerId,
    collapsedLayerIds,
    setCollapsedLayerIds,
    selectedObjectId,
    currentSceneAsyncScope,
    updateSceneLayersState,
    updateSceneGenerationInput,
    selectSceneLayer,
    selectSceneObject,
    selectedLayer,
    selectedObjectTarget,
    sceneSelectionLayerId,
    selectedPath,
    sceneProfilePreview,
    sceneNodeCount,
    sceneObjectCount,
    applySceneImport,
    setSceneFieldTarget,
    toggleLayerSelection,
    toggleObjectSelection,
  };
}
