"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type { CSSProperties, MouseEvent as ReactMouseEvent, ReactNode, SetStateAction } from "react";
import type { ModelRecovery } from "@vibe-learner/shared";

import { MaterialIcon, type MaterialIconName } from "../../components/material-icon";
import { ModelFallbackNotice } from "../../components/model-fallback-notice";
import { ProviderTruth } from "../../components/provider-truth";
import {
  type SceneObject,
  type SceneLayer,
  type SceneImportPayload,
  LAYER_TEMPLATES,
  createSceneObject,
  createSceneLayer,
  cloneSceneObjectFromLibrary,
  cloneSceneLayerFromLibrary,
  INITIAL_SCENE,
  SCENE_STORAGE_KEY,
  SCENE_SIDEBAR_WIDTH,
  deriveSceneProfile,
  normalizeSceneTreeNodeForProfile,
  countSceneNodes,
  countSceneObjects,
  removeLayerTree,
  canDeleteLayerSafely,
  collectLayerIds,
  parseSceneImportPayload,
  updateLayerTree,
  findLayerById,
  findObjectById,
  findLayerPath,
  inferTemplateIndexFromLayer,
} from "../../lib/scene-editor-model";
import { useSceneGeneration } from "../../hooks/use-scene-generation";
import { readBoundedJsonImport } from "../../lib/bounded-json-import";
import { exportJson } from "../../lib/export-json";
import { TopNav } from "../../components/top-nav";
import { usePageDebugSnapshot } from "../../components/page-debug-context";
import { assistPersonaSlot } from "../../lib/data/personas";
import {
  createReusableSceneNode,
  createSceneLibraryItem,
  deleteReusableSceneNode,
  deleteSceneLibraryItem,
  listReusableSceneNodes,
  listSceneLibrary,
  type ReusableSceneNodePayload,
  type SceneLibraryItemPayload,
  updateSceneLibraryItem,
} from "../../lib/data/scenes";
import {
  applyAsyncResult,
  AsyncResultFence,
  type AsyncResultScope,
} from "../../lib/async-result-fence";

type RewriteUndoEntry =
  | {
      kind: "layer";
      key: string;
      label: string;
      layerId: string;
      field: "summary" | "atmosphere" | "rules" | "entrance";
      previousValue: string;
    }
  | {
      kind: "object";
      key: string;
      label: string;
      layerId: string;
      objectId: string;
      field: "description" | "interaction";
      previousValue: string;
    };

function formatDate(value: string) {
  if (!value) {
    return "未知时间";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit"
  });
}

export default function SceneSetupPage() {
  const [sceneLayers, setSceneLayers] = useState<SceneLayer[]>(INITIAL_SCENE);
  const [sceneName, setSceneName] = useState("示例场景");
  const [sceneSummary, setSceneSummary] = useState("从世界整体的学术框架出发，逐层建立观察者在微观教室中的完整感受。这个示例展示了如何从宏观规则层层推导到具体互动对象。");
  const [selectedLayerId, setSelectedLayerId] = useState(INITIAL_SCENE[0]?.id ?? "");
  const [collapsedLayerIds, setCollapsedLayerIds] = useState<string[]>([]);
  const [savedScenes, setSavedScenes] = useState<SceneLibraryItemPayload[]>([]);
  const [selectedSavedSceneId, setSelectedSavedSceneId] = useState("");
  const [rewriteStrength, setRewriteStrength] = useState(0.6);
  const [rewritePendingKey, setRewritePendingKey] = useState("");
  const [rewriteError, setRewriteError] = useState("");
  const [rewriteModelRecoveries, setRewriteModelRecoveries] = useState<ModelRecovery[]>([]);
  const [lastRewrite, setLastRewrite] = useState<RewriteUndoEntry | null>(null);
  const [pendingDeleteLayerId, setPendingDeleteLayerId] = useState("");
  const [sceneIoMessage, setSceneIoMessage] = useState("");
  const [reusableNodes, setReusableNodes] = useState<ReusableSceneNodePayload[]>([]);
  const [reusableSearchQuery, setReusableSearchQuery] = useState("");
  const [reusableActionPendingId, setReusableActionPendingId] = useState("");
  const [reusableMessage, setReusableMessage] = useState("");
  const [reusableError, setReusableError] = useState("");
  const {
    sceneKeywordInput,
    setSceneKeywordInput,
    sceneLongTextFile,
    setSceneLongTextFile,
    sceneGenerateMode,
    setSceneGenerateMode,
    sceneGenerateLayerCount,
    setSceneGenerateLayerCount,
    sceneGeneratePending,
    sceneGenerateError,
    sceneGenerateMessage,
    sceneGenerateModelRecoveries,
    generatedSceneCandidate,
    handleGenerateScene,
    resetSceneGeneration,
  } = useSceneGeneration(currentSceneAsyncScope);
  const importInputRef = useRef<HTMLInputElement | null>(null);
  const sceneDraftRevisionRef = useRef(0);
  const sceneSubjectIdRef = useRef("scene-editor:local");
  const selectedLayerIdRef = useRef(INITIAL_SCENE[0]?.id ?? "");
  const selectedObjectIdRef = useRef("");
  const activeSceneFieldTargetRef = useRef(
    `scene-layer:${INITIAL_SCENE[0]?.id ?? "none"}`,
  );
  const rewriteFenceRef = useRef(new AsyncResultFence());
  const sceneImportFenceRef = useRef(new AsyncResultFence());

  const [collapsedSidebarSections, setCollapsedSidebarSections] = useState<string[]>([]);
  const [collapsedNodeEditorSectionsByLayer, setCollapsedNodeEditorSectionsByLayer] = useState<Record<string, string[]>>({});
  const [selectedObjectId, setSelectedObjectId] = useState("");
  const [isCompactLayout, setIsCompactLayout] = useState(false);

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
    rewriteFenceRef.current.invalidate();
    setRewritePendingKey("");
    selectedLayerIdRef.current = layerId;
    selectedObjectIdRef.current = "";
    activeSceneFieldTargetRef.current = `scene-layer:${layerId || "none"}`;
    setSelectedObjectId("");
    setSelectedLayerId(layerId);
  }

  function selectSceneObject(objectId: string): void {
    rewriteFenceRef.current.invalidate();
    setRewritePendingKey("");
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
  const filteredReusableNodes = useMemo(() => {
    const query = reusableSearchQuery.trim().toLowerCase();
    if (!query) {
      return reusableNodes;
    }
    return reusableNodes.filter((item) => {
      const haystack = [
        item.title,
        item.summary,
        item.tags.join(","),
        item.reuseHint,
        item.sourceSceneName,
      ].join("\n").toLowerCase();
      return haystack.includes(query);
    });
  }, [reusableNodes, reusableSearchQuery]);
  const headerMessage = useMemo(() => {
    const io = sceneIoMessage.trim();
    const generate = sceneGenerateMessage.trim();
    const reusable = reusableMessage.trim();
    return io || generate || reusable;
  }, [reusableMessage, sceneGenerateMessage, sceneIoMessage]);
  const currentCollapsedNodeEditorSections = useMemo(
    () => (selectedLayerId ? (collapsedNodeEditorSectionsByLayer[selectedLayerId] ?? []) : []),
    [collapsedNodeEditorSectionsByLayer, selectedLayerId]
  );

  const pageNotice = useMemo(() => {
    if (rewritePendingKey) {
      return "AI 正在重写场景字段";
    }
    if (sceneGeneratePending === "keywords") {
      return "正在根据关键词生成场景树";
    }
    if (sceneGeneratePending === "long_text") {
      return "正在从长文本提取场景树";
    }
    if (reusableActionPendingId) {
      return "可复用节点库更新中";
    }
    if (pendingDeleteLayerId) {
      return "等待确认删除层级";
    }
    if (headerMessage) {
      return headerMessage;
    }
    if (selectedObjectTarget?.object.name) {
      return `当前编辑 · ${selectedObjectTarget.object.name}`;
    }
    if (selectedLayer?.title) {
      return `当前编辑 · ${selectedLayer.title}`;
    }
    return "从左侧层级结构中选择一个节点开始编辑";
  }, [headerMessage, pendingDeleteLayerId, reusableActionPendingId, rewritePendingKey, sceneGeneratePending, selectedLayer, selectedObjectTarget]);

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

  useEffect(() => {
    const syncLayout = () => {
      setIsCompactLayout(window.innerWidth < 1320);
    };
    syncLayout();
    window.addEventListener("resize", syncLayout);
    return () => window.removeEventListener("resize", syncLayout);
  }, []);

  useEffect(() => {
    if (!selectedLayerId) {
      return;
    }
    const editorId = `scene-node-editor-${selectedLayerId}`;
    const timer = window.setTimeout(() => {
      const nodeEditor = document.getElementById(editorId);
      nodeEditor?.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }, 40);
    return () => {
      window.clearTimeout(timer);
    };
  }, [selectedLayerId]);

  useEffect(() => {
    let active = true;
    const hydrateScene = async () => {
      try {
        const raw = globalThis.localStorage?.getItem(SCENE_STORAGE_KEY);
        if (!raw || !active) {
          return;
        }
        const parsed = JSON.parse(raw);
        const imported = parseSceneImportPayload(parsed);
        applySceneImport(imported, "已加载本地保存场景。");
      } catch {
        if (active) {
          setSceneIoMessage("本地保存内容解析失败，已忽略。");
        }
      }
    };

    void hydrateScene();
    return () => {
      active = false;
    };
  }, []);

  const debugSnapshot = useMemo(
    () => ({
      title: "场景页调试面板",
      subtitle: "查看场景树、生成结果和错误。",
      error: [rewriteError, sceneGenerateError, reusableError].filter(Boolean).join("；"),
      summary: [
        { label: "场景名称", value: sceneName || "-" },
        { label: "选中层级", value: selectedLayer?.title || selectedLayerId || "-" },
        { label: "已保存场景", value: String(savedScenes.length) },
        { label: "可复用节点", value: String(reusableNodes.length) },
        { label: "生成候选", value: generatedSceneCandidate ? "是" : "否" },
        { label: "AI 恢复记录", value: String(rewriteModelRecoveries.length + sceneGenerateModelRecoveries.length) }
      ],
      details: [
        { title: "场景快照预览", value: sceneProfilePreview },
        { title: "当前选中路径", value: selectedPath },
        { title: "生成候选场景", value: generatedSceneCandidate },
        { title: "已保存场景列表", value: savedScenes },
        { title: "可复用节点列表", value: reusableNodes.slice(0, 24) },
        { title: "场景生成恢复记录", value: sceneGenerateModelRecoveries },
        { title: "文本重写恢复记录", value: rewriteModelRecoveries }
      ]
    }),
    [
      generatedSceneCandidate,
      reusableError,
      reusableNodes,
      rewriteModelRecoveries,
      rewriteError,
      savedScenes,
      sceneGenerateModelRecoveries,
      sceneGenerateError,
      sceneName,
      sceneProfilePreview,
      selectedLayer,
      selectedLayerId,
      selectedPath
    ]
  );

  usePageDebugSnapshot(debugSnapshot);

  useEffect(() => {
    let active = true;
    const hydrateLibrary = async () => {
      try {
        const [items, reusableItems] = await Promise.all([
          listSceneLibrary(),
          listReusableSceneNodes(),
        ]);
        if (!active) {
          return;
        }
        setSavedScenes(items);
        setReusableNodes(reusableItems);
        setSelectedSavedSceneId((current) => current || items[0]?.sceneId || "");
      } catch {
        if (active) {
          setSavedScenes([]);
          setReusableNodes([]);
        }
      }
    };

    void hydrateLibrary();
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    const timer = globalThis.setTimeout(() => {
      const payload = {
        version: 1,
        savedAt: new Date().toISOString(),
        sceneName,
        sceneSummary,
        sceneLayers,
        selectedLayerId: sceneSelectionLayerId,
        collapsedLayerIds,
      };
      try {
        globalThis.localStorage?.setItem(SCENE_STORAGE_KEY, JSON.stringify(payload));
      } catch {
        // local fallback write best effort
      }
    }, 700);

    return () => {
      globalThis.clearTimeout(timer);
    };
  }, [sceneLayers, sceneName, sceneSummary, sceneSelectionLayerId, collapsedLayerIds]);

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
    rewriteFenceRef.current.invalidate();
    setRewritePendingKey("");
    resetSceneGeneration();
    setSceneLayers(imported.sceneLayers);
    setSceneName(String(imported.sceneName || ""));
    setSceneSummary(String(imported.sceneSummary || ""));
    setSelectedLayerId(nextSelectedLayerId);
    setSelectedObjectId("");
    setCollapsedLayerIds(imported.collapsedLayerIds.filter((id) => knownIds.has(id)));
    setSceneIoMessage(message);
  }

  function updateLayer(targetId: string, updater: (layer: SceneLayer) => SceneLayer) {
    updateSceneLayersState((current) => updateLayerTree(current, targetId, updater));
  }

  function parseTagList(text: string) {
    return text.split(",").map((item) => item.trim()).filter(Boolean);
  }

  async function saveLayerToReusableLibrary(layerId: string) {
    const targetLayer = findLayerById(sceneLayers, layerId);
    if (!targetLayer) {
      return;
    }
    setReusableError("");
    setReusableMessage("");
    setReusableActionPendingId(targetLayer.id);
    try {
      const created = await createReusableSceneNode({
        nodeType: "layer",
        title: targetLayer.title,
        summary: targetLayer.summary,
        tags: parseTagList(targetLayer.tags),
        reuseId: targetLayer.reuseId,
        reuseHint: targetLayer.reuseHint,
        sourceSceneId: sceneProfilePreview?.sceneId ?? "",
        sourceSceneName: sceneName.trim(),
        layerNode: normalizeSceneTreeNodeForProfile(targetLayer),
      });
      setReusableNodes((current) => [created, ...current]);
      setReusableMessage(`已将层级 "${targetLayer.title}" 加入可复用节点库。`);
    } catch (error) {
      setReusableError(String(error));
    } finally {
      setReusableActionPendingId("");
    }
  }

  async function saveObjectToReusableLibrary(object: SceneObject) {
    setReusableError("");
    setReusableMessage("");
    setReusableActionPendingId(object.id);
    try {
      const created = await createReusableSceneNode({
        nodeType: "object",
        title: object.name,
        summary: object.description,
        tags: parseTagList(object.tags),
        reuseId: object.reuseId,
        reuseHint: object.reuseHint,
        sourceSceneId: sceneProfilePreview?.sceneId ?? "",
        sourceSceneName: sceneName.trim(),
        objectNode: {
          id: object.id,
          name: object.name,
          description: object.description,
          interaction: object.interaction,
          tags: object.tags,
          reuseId: object.reuseId,
          reuseHint: object.reuseHint,
        },
      });
      setReusableNodes((current) => [created, ...current]);
      setReusableMessage(`已将物体 "${object.name}" 加入可复用节点库。`);
    } catch (error) {
      setReusableError(String(error));
    } finally {
      setReusableActionPendingId("");
    }
  }

  async function deleteReusableNode(nodeId: string) {
    setReusableError("");
    setReusableMessage("");
    setReusableActionPendingId(nodeId);
    try {
      await deleteReusableSceneNode(nodeId);
      setReusableNodes((current) => current.filter((item) => item.nodeId !== nodeId));
    } catch (error) {
      setReusableError(String(error));
    } finally {
      setReusableActionPendingId("");
    }
  }

  function insertReusableNode(item: ReusableSceneNodePayload) {
    if (!selectedLayer) {
      setReusableError("请先选择一个目标层级，再插入节点。");
      return;
    }
    setReusableError("");
    setReusableMessage("");
    const objectNode = item.objectNode;
    const layerNode = item.layerNode;
    if (item.nodeType === "object" && objectNode) {
      updateLayer(selectedLayer.id, (layer) => ({
        ...layer,
        objects: [
          ...layer.objects,
          cloneSceneObjectFromLibrary(objectNode),
        ],
      }));
      setReusableMessage(`已把物体 "${item.title}" 插入到 "${selectedLayer.title}"。`);
      return;
    }
    if (item.nodeType === "layer" && layerNode) {
      updateLayer(selectedLayer.id, (layer) => ({
        ...layer,
        children: [
          ...layer.children,
          cloneSceneLayerFromLibrary(layerNode),
        ],
      }));
      setCollapsedLayerIds((current) => current.filter((id) => id !== selectedLayer.id));
      setReusableMessage(`已把层级 "${item.title}" 作为 "${selectedLayer.title}" 的子层插入。`);
      return;
    }
    setReusableError("所选节点数据不完整，无法插入。");
  }

  function addChildLayer(parentId: string) {
    updateSceneLayersState((current) =>
      updateLayerTree(current, parentId, (layer) => ({
        ...layer,
        children: [
          ...layer.children,
          createSceneLayer(
            layer.children[0]
              ? inferTemplateIndexFromLayer(layer.children[0])
              : Math.min(inferTemplateIndexFromLayer(layer) + 1, LAYER_TEMPLATES.length - 1)
          )
        ]
      }))
    );
  }

  function addObject(layerId: string) {
    const newObject = createSceneObject();
    updateLayer(layerId, (layer) => ({
      ...layer,
      objects: [...layer.objects, newObject]
    }));
    selectSceneObject(newObject.id);
    const targetId = `scene-object-editor-${layerId}-${newObject.id}`;
    globalThis.setTimeout(() => {
      const target = document.getElementById(targetId);
      target?.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }, 80);
  }

  function updateObject(layerId: string, objectId: string, key: keyof SceneObject, value: string) {
    updateLayer(layerId, (layer) => ({
      ...layer,
      objects: layer.objects.map((object) =>
        object.id === objectId ? { ...object, [key]: value } : object
      )
    }));
  }

  function removeObject(layerId: string, objectId: string) {
    if (selectedObjectId === objectId) {
      selectSceneObject("");
    }
    updateLayer(layerId, (layer) => ({
      ...layer,
      objects: layer.objects.filter((object) => object.id !== objectId)
    }));
  }

  function removeLayer(layerId: string) {
    updateSceneLayersState((current) => {
      if (!canDeleteLayerSafely(current, layerId)) {
        return current;
      }
      return removeLayerTree(current, layerId);
    });
    setCollapsedLayerIds((current) => current.filter((id) => id !== layerId));
  }

  function requestDeleteLayer(layerId: string) {
    if (!canDeleteLayerSafely(sceneLayers, layerId)) {
      return;
    }
    setPendingDeleteLayerId(layerId);
  }

  function cancelDeleteLayer() {
    setPendingDeleteLayerId("");
  }

  function confirmDeleteLayer() {
    if (!pendingDeleteLayerId) {
      return;
    }
    if (!canDeleteLayerSafely(sceneLayers, pendingDeleteLayerId)) {
      setPendingDeleteLayerId("");
      return;
    }
    removeLayer(pendingDeleteLayerId);
    setPendingDeleteLayerId("");
  }

  function undoLastRewrite() {
    if (!lastRewrite || rewritePendingKey) {
      return;
    }
    if (lastRewrite.kind === "layer") {
      updateLayer(lastRewrite.layerId, (layer) => ({
        ...layer,
        [lastRewrite.field]: lastRewrite.previousValue
      }));
    } else {
      updateObject(lastRewrite.layerId, lastRewrite.objectId, lastRewrite.field, lastRewrite.previousValue);
    }
    setLastRewrite(null);
    setRewriteError("");
  }

  async function saveLibraryScene(mode: "upsert" | "create" = "upsert") {
    try {
      const trimmedSceneName = sceneName.trim();
      const trimmedSceneSummary = sceneSummary.trim();
      if (!trimmedSceneName || !trimmedSceneSummary) {
        setSceneIoMessage("请先填写场景名和 summary。");
        return;
      }
      const payload = {
        sceneName: trimmedSceneName,
        sceneSummary: trimmedSceneSummary,
        sceneLayers,
        selectedLayerId: sceneSelectionLayerId,
        collapsedLayerIds,
      };
      if (mode === "upsert" && selectedSavedSceneId) {
        const selectedSavedScene = savedScenes.find(
          (item) => item.sceneId === selectedSavedSceneId
        );
        if (!selectedSavedScene) {
          setSceneIoMessage("当前保存版本已不存在，请刷新场景库后重试。");
          return;
        }
        const updated = await updateSceneLibraryItem(selectedSavedSceneId, {
          ...payload,
          expectedRevision: selectedSavedScene.revision,
        });
        setSavedScenes((current) => current.map((item) => (item.sceneId === updated.sceneId ? updated : item)));
        setSceneIoMessage(`已更新已保存场景“${updated.sceneName}”。`);
        return;
      }
      const created = await createSceneLibraryItem(payload);
      setSavedScenes((current) => [created, ...current.filter((item) => item.sceneId !== created.sceneId)]);
      setSelectedSavedSceneId(created.sceneId);
      setSceneIoMessage(`已保存场景“${created.sceneName}”。`);
    } catch {
      setSceneIoMessage("保存到场景库失败，请稍后重试。");
    }
  }

  async function loadSavedScene(sceneId: string) {
    const target = savedScenes.find((item) => item.sceneId === sceneId);
    if (!target) {
      return;
    }
    try {
      const imported = parseSceneImportPayload({
        sceneName: target.sceneName,
        sceneSummary: target.sceneSummary,
        sceneLayers: target.sceneLayers,
        selectedLayerId: target.selectedLayerId,
        collapsedLayerIds: target.collapsedLayerIds,
      });
      applySceneImport(
        imported,
        `已载入场景“${target.sceneName}”。`,
        `scene-library:${target.sceneId}`,
      );
      setSelectedSavedSceneId(target.sceneId);
    } catch {
      setSceneIoMessage(`载入场景“${target.sceneName}”时数据格式异常。`);
    }
  }

  async function deleteSavedScene(sceneId: string) {
    const target = savedScenes.find((item) => item.sceneId === sceneId);
    if (!target) {
      return;
    }
    if (!globalThis.confirm(`确认删除已保存场景“${target.sceneName}”？`)) {
      return;
    }
    try {
      await deleteSceneLibraryItem(sceneId);
      setSavedScenes((current) => current.filter((item) => item.sceneId !== sceneId));
      if (selectedSavedSceneId === sceneId) {
        setSelectedSavedSceneId("");
      }
      setSceneIoMessage(`已删除场景“${target.sceneName}”。`);
    } catch {
      setSceneIoMessage("删除场景失败，请稍后重试。");
    }
  }

  async function exportScene() {
    try {
      const payload = {
        version: 1,
        exportedAt: new Date().toISOString(),
        sceneName,
        sceneSummary,
        sceneLayers,
        selectedLayerId: sceneSelectionLayerId,
        collapsedLayerIds,
      };
      const saved = await exportJson(`scene-setup-${new Date().toISOString().slice(0, 19).replace(/:/g, "-")}.json`, payload);
      setSceneIoMessage(saved ? "场景已导出为 JSON 文件。" : "已取消导出。");
    } catch {
      setSceneIoMessage("导出失败，请稍后重试。");
    }
  }

  function requestImportScene() {
    importInputRef.current?.click();
  }

  async function importSceneFromFile(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) {
      return;
    }
    const fieldTarget = "scene-file-import";
    const ticket = sceneImportFenceRef.current.begin(
        currentSceneAsyncScope(fieldTarget),
    );
    try {
      const parsed = await readBoundedJsonImport(file, "scene");
      const imported = parseSceneImportPayload(parsed, true);
      const decision = applyAsyncResult({
        fence: sceneImportFenceRef.current,
        ticket,
        currentScope: currentSceneAsyncScope(fieldTarget),
        value: imported,
        apply: (next) => applySceneImport(next, "场景导入成功。"),
      });
      if (decision !== "apply") {
        return;
      }
    } catch {
      if (
        sceneImportFenceRef.current.decide(
          ticket,
          currentSceneAsyncScope(fieldTarget),
        ) === "apply"
      ) {
        setSceneIoMessage("导入失败：文件格式不正确。");
      }
    } finally {
      sceneImportFenceRef.current.settle(ticket);
      event.target.value = "";
    }
  }

  function applyGeneratedSceneCandidateToEditor() {
    if (!generatedSceneCandidate) {
      return;
    }
    applySceneImport(generatedSceneCandidate, "已将生成场景树应用到当前编辑区。");
  }

  async function rewriteLayerField(layerId: string, field: "summary" | "atmosphere" | "rules" | "entrance", label: string) {
    const layer = findLayerById(sceneLayers, layerId);
    if (!layer) {
      return;
    }
    const sourceText = layer[field].trim();
    if (!sourceText) {
      setRewriteError("请先填写内容，再进行 AI 重写。");
      return;
    }

    const pendingKey = `${layerId}:${field}`;
    activeSceneFieldTargetRef.current = pendingKey;
    setRewriteError("");
    setRewriteModelRecoveries([]);
    setRewritePendingKey(pendingKey);
    const ticket = rewriteFenceRef.current.begin(currentSceneAsyncScope());
    try {
      const previousValue = layer[field];
      const result = await assistPersonaSlot({
        name: `场景层级 ${layer.title}`,
        summary: `${layer.scopeLabel}：${layer.summary}`,
        slot: {
          kind: "custom",
          label,
          content: layer[field],
          weight: 1,
          locked: false,
          sortOrder: 0
        },
        rewriteStrength: Number(rewriteStrength.toFixed(2))
      });
      if (rewriteFenceRef.current.decide(ticket, currentSceneAsyncScope()) !== "apply") {
        return;
      }
      updateLayer(layerId, (currentLayer) => ({
        ...currentLayer,
        [field]: result.slot.content
      }));
      setRewriteModelRecoveries(result.modelRecoveries ?? []);
      setLastRewrite({
        kind: "layer",
        key: pendingKey,
        label,
        layerId,
        field,
        previousValue
      });
    } catch (error) {
      if (rewriteFenceRef.current.decide(ticket, currentSceneAsyncScope()) === "apply") {
        setRewriteError(String(error));
      }
    } finally {
      if (rewriteFenceRef.current.settle(ticket)) {
        setRewritePendingKey("");
      }
    }
  }

  async function rewriteObjectField(layerId: string, objectId: string, field: "description" | "interaction", label: string) {
    const layer = findLayerById(sceneLayers, layerId);
    const object = layer?.objects.find((item) => item.id === objectId);
    if (!layer || !object) {
      return;
    }
    const sourceText = object[field].trim();
    if (!sourceText) {
      setRewriteError("请先填写内容，再进行 AI 重写。");
      return;
    }

    const pendingKey = `${layerId}:${objectId}:${field}`;
    activeSceneFieldTargetRef.current = pendingKey;
    setRewriteError("");
    setRewriteModelRecoveries([]);
    setRewritePendingKey(pendingKey);
    const ticket = rewriteFenceRef.current.begin(currentSceneAsyncScope());
    try {
      const previousValue = object[field];
      const result = await assistPersonaSlot({
        name: `场景物体 ${object.name}`,
        summary: `${layer.title} / ${object.name}`,
        slot: {
          kind: "custom",
          label,
          content: object[field],
          weight: 1,
          locked: false,
          sortOrder: 0
        },
        rewriteStrength: Number(rewriteStrength.toFixed(2))
      });
      if (rewriteFenceRef.current.decide(ticket, currentSceneAsyncScope()) !== "apply") {
        return;
      }
      updateObject(layerId, objectId, field, result.slot.content);
      setRewriteModelRecoveries(result.modelRecoveries ?? []);
      setLastRewrite({
        kind: "object",
        key: pendingKey,
        label,
        layerId,
        objectId,
        field,
        previousValue
      });
    } catch (error) {
      if (rewriteFenceRef.current.decide(ticket, currentSceneAsyncScope()) === "apply") {
        setRewriteError(String(error));
      }
    } finally {
      if (rewriteFenceRef.current.settle(ticket)) {
        setRewritePendingKey("");
      }
    }
  }

  function toggleSidebarSection(key: string) {
    setCollapsedSidebarSections((prev) =>
      prev.includes(key) ? prev.filter((k) => k !== key) : [...prev, key]
    );
  }

  function toggleNodeEditorSection(key: string) {
    const layerId = selectedLayerId;
    if (!layerId) {
      return;
    }
    setCollapsedNodeEditorSectionsByLayer((prev) => {
      const current = prev[layerId] ?? [];
      const next = current.includes(key)
        ? current.filter((k) => k !== key)
        : [...current, key];
      return {
        ...prev,
        [layerId]: next,
      };
    });
  }

  function toggleLayerEditor(layerId: string) {
    selectSceneLayer(selectedLayerIdRef.current === layerId ? "" : layerId);
  }

  function toggleObjectEditor(objectId: string) {
    selectSceneObject(selectedObjectIdRef.current === objectId ? "" : objectId);
  }

  function handleSelectLayer(layerId: string) {
    selectSceneLayer(layerId);
  }

  function renderSelectedLayerEditor(): ReactNode {
    if (!selectedLayer) {
      return <p style={styles.emptyState}>选择层级后在这里编辑。</p>;
    }

    return (
      <>
        <ModelFallbackNotice recoveries={rewriteModelRecoveries} />
        {rewriteError ? (
          <div style={styles.rewriteControlRow}>
            <span style={styles.errorText}>{rewriteError}</span>
          </div>
        ) : null}

        <div style={styles.editorSection}>
          <button type="button" style={styles.editorSectionHeader} onClick={() => toggleNodeEditorSection("basic")}> 
            <span style={styles.panelTitle}>基础设定</span>
            <span style={styles.sidebarToggleIcon}><MaterialIcon name={currentCollapsedNodeEditorSections.includes("basic") ? "chevron_right" : "expand_more"} size={16} /></span>
          </button>
          {!currentCollapsedNodeEditorSections.includes("basic") ? (
            <div style={styles.editorSectionBody}>
        <div style={styles.formGrid}>
          <label style={styles.fieldGroup}>
            <span style={styles.fieldLabel}>层级名称</span>
            <input
              style={styles.input}
              value={selectedLayer.title}
              onChange={(event) => updateLayer(selectedLayer.id, (layer) => ({ ...layer, title: event.target.value }))}
            />
          </label>

          <label style={styles.fieldGroup}>
            <span style={styles.fieldLabel}>层级作用</span>
            <input
              style={styles.input}
              value={selectedLayer.scopeLabel}
              onChange={(event) => updateLayer(selectedLayer.id, (layer) => ({ ...layer, scopeLabel: event.target.value }))}
            />
          </label>

          <label style={styles.fieldGroup}>
            <span style={styles.fieldLabel}>层级标签</span>
            <input
              style={styles.input}
              value={selectedLayer.tags}
              onChange={(event) => updateLayer(selectedLayer.id, (layer) => ({ ...layer, tags: event.target.value }))}
              placeholder="用逗号分隔"
            />
          </label>

          <label style={styles.fieldGroup}>
            <span style={styles.fieldLabelRow}>
              <span style={styles.fieldLabel}>层级总述</span>
              <RewriteStateButton
                actionKey={`${selectedLayer.id}:summary`}
                label="层级总述"
                pendingKey={rewritePendingKey}
                lastRewrite={lastRewrite}
                rewriteStrength={rewriteStrength}
                onRewriteStrengthChange={(value) => updateSceneGenerationInput(() => setRewriteStrength(value))}
                onRewrite={() => void rewriteLayerField(selectedLayer.id, "summary", "层级总述")}
                onUndo={undoLastRewrite}
              />
            </span>
            <textarea
              style={styles.textarea}
              value={selectedLayer.summary}
              onChange={(event) => updateLayer(selectedLayer.id, (layer) => ({ ...layer, summary: event.target.value }))}
            />
          </label>

          <label style={styles.fieldGroup}>
            <span style={styles.fieldLabelRow}>
              <span style={styles.fieldLabel}>氛围与感知</span>
              <RewriteStateButton
                actionKey={`${selectedLayer.id}:atmosphere`}
                label="氛围与感知"
                pendingKey={rewritePendingKey}
                lastRewrite={lastRewrite}
                rewriteStrength={rewriteStrength}
                onRewriteStrengthChange={(value) => updateSceneGenerationInput(() => setRewriteStrength(value))}
                onRewrite={() => void rewriteLayerField(selectedLayer.id, "atmosphere", "氛围与感知")}
                onUndo={undoLastRewrite}
              />
            </span>
            <textarea
              style={styles.textarea}
              value={selectedLayer.atmosphere}
              onChange={(event) => updateLayer(selectedLayer.id, (layer) => ({ ...layer, atmosphere: event.target.value }))}
            />
          </label>

          <label style={styles.fieldGroup}>
            <span style={styles.fieldLabelRow}>
              <span style={styles.fieldLabel}>进入方式 / 过渡</span>
              <RewriteStateButton
                actionKey={`${selectedLayer.id}:entrance`}
                label="进入方式 / 过渡"
                pendingKey={rewritePendingKey}
                lastRewrite={lastRewrite}
                rewriteStrength={rewriteStrength}
                onRewriteStrengthChange={(value) => updateSceneGenerationInput(() => setRewriteStrength(value))}
                onRewrite={() => void rewriteLayerField(selectedLayer.id, "entrance", "进入方式 / 过渡")}
                onUndo={undoLastRewrite}
              />
            </span>
            <textarea
              style={styles.textarea}
              value={selectedLayer.entrance}
              onChange={(event) => updateLayer(selectedLayer.id, (layer) => ({ ...layer, entrance: event.target.value }))}
            />
          </label>

          <label style={styles.fieldGroup}>
            <span style={styles.fieldLabelRow}>
              <span style={styles.fieldLabel}>层级规则</span>
              <RewriteStateButton
                actionKey={`${selectedLayer.id}:rules`}
                label="层级规则"
                pendingKey={rewritePendingKey}
                lastRewrite={lastRewrite}
                rewriteStrength={rewriteStrength}
                onRewriteStrengthChange={(value) => updateSceneGenerationInput(() => setRewriteStrength(value))}
                onRewrite={() => void rewriteLayerField(selectedLayer.id, "rules", "层级规则")}
                onUndo={undoLastRewrite}
              />
            </span>
            <textarea
              style={styles.textarea}
              value={selectedLayer.rules}
              onChange={(event) => updateLayer(selectedLayer.id, (layer) => ({ ...layer, rules: event.target.value }))}
            />
          </label>

        </div>
            </div>
          ) : null}
        </div>
      </>
    );
  }

  function renderObjectEditor(layerId: string, object: SceneObject): ReactNode {
    return (
      <>
        <ModelFallbackNotice recoveries={rewriteModelRecoveries} />
        {rewriteError ? (
          <div style={styles.rewriteControlRow}>
            <span style={styles.errorText}>{rewriteError}</span>
          </div>
        ) : null}

        <div style={styles.editorSection}>
          <div style={styles.editorSectionBody}>
            <div style={styles.formGrid}>
              <label style={styles.fieldGroup}>
                <span style={styles.fieldLabel}>物体名称</span>
                <input
                  style={styles.input}
                  value={object.name}
                  onChange={(event) => updateObject(layerId, object.id, "name", event.target.value)}
                />
              </label>

              <label style={styles.fieldGroup}>
                <span style={styles.fieldLabelRow}>
                  <span style={styles.fieldLabel}>外观 / 说明</span>
                  <RewriteStateButton
                    actionKey={`${layerId}:${object.id}:description`}
                    label="物体外观 / 说明"
                    pendingKey={rewritePendingKey}
                    lastRewrite={lastRewrite}
                    rewriteStrength={rewriteStrength}
                    onRewriteStrengthChange={(value) => updateSceneGenerationInput(() => setRewriteStrength(value))}
                    onRewrite={() => void rewriteObjectField(layerId, object.id, "description", "物体外观与说明")}
                    onUndo={undoLastRewrite}
                  />
                </span>
                <textarea
                  style={styles.textarea}
                  value={object.description}
                  onChange={(event) => updateObject(layerId, object.id, "description", event.target.value)}
                />
              </label>

              <label style={styles.fieldGroup}>
                <span style={styles.fieldLabelRow}>
                  <span style={styles.fieldLabel}>交互方式</span>
                  <RewriteStateButton
                    actionKey={`${layerId}:${object.id}:interaction`}
                    label="物体交互方式"
                    pendingKey={rewritePendingKey}
                    lastRewrite={lastRewrite}
                    rewriteStrength={rewriteStrength}
                    onRewriteStrengthChange={(value) => updateSceneGenerationInput(() => setRewriteStrength(value))}
                    onRewrite={() => void rewriteObjectField(layerId, object.id, "interaction", "物体交互方式")}
                    onUndo={undoLastRewrite}
                  />
                </span>
                <textarea
                  style={styles.textarea}
                  value={object.interaction}
                  onChange={(event) => updateObject(layerId, object.id, "interaction", event.target.value)}
                />
              </label>

              <label style={styles.fieldGroup}>
                <span style={styles.fieldLabel}>标签</span>
                <input
                  style={styles.input}
                  value={object.tags}
                  onChange={(event) => updateObject(layerId, object.id, "tags", event.target.value)}
                  placeholder="用逗号分隔"
                />
              </label>

            </div>
          </div>
        </div>
      </>
    );
  }

  return (
    <main className="with-app-nav" style={styles.page}>
      <TopNav currentPath="/scene-setup" />

      <div style={styles.heading}>
        <div style={styles.headingRow}>
          <h1 style={styles.pageTitle}>场景搭建</h1>
          <ProviderTruth scope="scene" />
          <div style={styles.notice}>{pageNotice}</div>
        </div>
      </div>

      <div
        style={{
          ...styles.workspaceShell,
          ...(isCompactLayout ? styles.workspaceShellCompact : null),
        }}
      >
        {/* ── Panel 1: Scene Tree + Node Editor ── */}
        <div
          style={{
            ...styles.panel,
            ...(isCompactLayout ? styles.panelCompact : null),
            flex: 1,
            minWidth: 0,
          }}
        >
          <div style={styles.panelHeader}>
            <span style={styles.panelTitle}>场景树与节点编辑器</span>
            <div style={styles.panelHeaderActions}>
              <button
                style={selectedSavedSceneId ? { ...styles.sidebarIconButton, ...styles.sidebarIconButtonPrimary } : styles.sidebarIconButton}
                type="button"
                onClick={() => void saveLibraryScene("upsert")}
                title={selectedSavedSceneId ? "更新已保存场景" : "保存到场景库"}
                aria-label={selectedSavedSceneId ? "更新已保存场景" : "保存到场景库"}
              >
                <MaterialIcon name="save" size={14} />
              </button>
              <button
                style={styles.sidebarIconButton}
                type="button"
                onClick={() => void saveLibraryScene("create")}
                title="另存为新场景"
                aria-label="另存为新场景"
              >
                <MaterialIcon name="library_add" size={14} />
              </button>
              <button
                style={styles.sidebarIconButton}
                type="button"
                onClick={requestImportScene}
                title="导入 JSON"
                aria-label="导入 JSON"
              >
                <MaterialIcon name="upload_file" size={14} />
              </button>
              <button
                style={styles.sidebarIconButton}
                type="button"
                onClick={exportScene}
                title="导出 JSON"
                aria-label="导出 JSON"
              >
                <MaterialIcon name="download" size={14} />
              </button>
            </div>
          </div>
          <div style={{ ...styles.panelBody, ...(isCompactLayout ? styles.panelBodyCompact : null) }}>
          <input
            ref={importInputRef}
            type="file"
            accept="application/json,.json"
            style={styles.hiddenInput}
            onChange={(event) => void importSceneFromFile(event)}
          />
          <div style={styles.treeStack}>
            {sceneLayers.map((layer, index) => (
              <SceneLayerCard
                key={layer.id}
                layer={layer}
                index={index}
                selectedLayerId={selectedLayerId}
                selectedObjectId={selectedObjectId}
                onSelect={handleSelectLayer}
                onToggleEditor={toggleLayerEditor}
                onAddChild={addChildLayer}
                onAddObject={addObject}
                onSaveToReusable={(layerId) => { void saveLayerToReusableLibrary(layerId); }}
                onSelectObject={toggleObjectEditor}
                onSaveObjectToReusable={(object) => { void saveObjectToReusableLibrary(object); }}
                onRemoveObject={removeObject}
                reusableActionPendingId={reusableActionPendingId}
                onRequestDelete={requestDeleteLayer}
                canDeleteLayerForId={(layerId) => canDeleteLayerSafely(sceneLayers, layerId)}
                editorContent={renderSelectedLayerEditor()}
                renderObjectEditor={renderObjectEditor}
              />
            ))}
          </div>
          </div>
        </div>

        {/* ── Panel 3: Sidebar ── */}
        <aside
          style={{
            ...styles.sidebarPane,
            ...(isCompactLayout ? styles.sidebarPaneCompact : null),
            width: isCompactLayout ? "100%" : SCENE_SIDEBAR_WIDTH,
            flexShrink: 0,
          }}
        >
          <div style={styles.sidebarSection}>
            <div style={styles.sidebarSectionStaticHeader}>
              <span style={styles.panelTitle}>当前场景</span>
              <span style={styles.sidebarSectionMeta}>
                {sceneNodeCount} 节点 · {sceneObjectCount} 物体
              </span>
            </div>
            <div style={{ ...styles.sidebarSectionBody, ...styles.sceneMetaSectionBody }}>
              <label style={styles.sceneNameLabel}>
                <span style={styles.fieldLabel}>场景名称</span>
                <input
                  style={styles.sceneNameInput}
                  value={sceneName}
                  onChange={(event) => updateSceneGenerationInput(() => setSceneName(event.target.value))}
                  placeholder="例如：高一物理-力学基础"
                />
              </label>
              <label style={styles.sceneSummaryLabel}>
                <span style={styles.fieldLabel}>场景摘要</span>
                <textarea
                  style={styles.sceneSummaryInput}
                  value={sceneSummary}
                  onChange={(event) => updateSceneGenerationInput(() => setSceneSummary(event.target.value))}
                  placeholder="用自己的话描述这个场景。"
                />
              </label>
            </div>
          </div>

          <div style={styles.sidebarSection}>
            <button type="button" style={styles.sidebarSectionHeader} onClick={() => toggleSidebarSection("generate")}>
              <span style={styles.panelTitle}>场景树生成器</span>
              <span style={styles.sidebarToggleIcon}><MaterialIcon name={collapsedSidebarSections.includes("generate") ? "chevron_right" : "expand_more"} size={16} /></span>
            </button>
            {!collapsedSidebarSections.includes("generate") ? (
              <div style={styles.sidebarSectionBody}>
                <label style={styles.fieldGroup}>
                  <span style={styles.fieldLabel}>层级偏好（可选）</span>
                  <input
                    style={styles.input}
                    type="number"
                    min={1}
                    step={1}
                    value={sceneGenerateLayerCount}
                    onChange={(event) => updateSceneGenerationInput(() => setSceneGenerateLayerCount(event.target.value))}
                    placeholder="留空表示不限"
                  />
                </label>
                <div style={styles.modeSwitchRow}>
                  <div style={styles.modeSwitch}>
                    <button
                      type="button"
                      style={sceneGenerateMode === "keywords" ? styles.modeSwitchButtonActive : styles.modeSwitchButton}
                      onClick={() => updateSceneGenerationInput(() => setSceneGenerateMode("keywords"))}
                    >
                      关键词搜索
                    </button>
                    <button
                      type="button"
                      style={sceneGenerateMode === "long_text" ? styles.modeSwitchButtonActive : styles.modeSwitchButton}
                      onClick={() => updateSceneGenerationInput(() => setSceneGenerateMode("long_text"))}
                    >
                      长文本提取
                    </button>
                  </div>
                  <button
                    style={styles.sidebarIconButton}
                    type="button"
                    disabled={sceneGeneratePending !== null}
                    onClick={() => void handleGenerateScene(sceneGenerateMode)}
                    title={
                      sceneGenerateMode === "keywords"
                        ? (sceneGeneratePending === "keywords" ? "生成中" : "根据关键词生成场景树")
                        : (sceneGeneratePending === "long_text" ? "提取中" : "根据长文本提取场景树")
                    }
                    aria-label={
                      sceneGenerateMode === "keywords"
                        ? (sceneGeneratePending === "keywords" ? "生成中" : "根据关键词生成场景树")
                        : (sceneGeneratePending === "long_text" ? "提取中" : "根据长文本提取场景树")
                    }
                  >
                    <MaterialIcon
                      name={
                        sceneGenerateMode === "keywords"
                          ? (sceneGeneratePending === "keywords" ? "hourglass_top" : "auto_awesome")
                          : (sceneGeneratePending === "long_text" ? "hourglass_top" : "description")
                      }
                      size={14}
                    />
                  </button>
                </div>
                {sceneGenerateMode === "keywords" ? (
                  <label key="keywords-mode" style={styles.fieldGroup}>
                    <input
                      style={styles.input}
                      value={sceneKeywordInput}
                      onChange={(event) => updateSceneGenerationInput(() => setSceneKeywordInput(event.target.value))}
                      placeholder="输入关键词，例如：赛博校园, 物理实验, 夜间自习, 钟楼广播"
                    />
                  </label>
                ) : (
                  <label key="long-text-mode" style={styles.fieldGroup}>
                    <input
                      type="file"
                      accept=".txt,.md,text/plain,text/markdown"
                      style={styles.fileInput}
                      onChange={(event) => updateSceneGenerationInput(() => setSceneLongTextFile(event.target.files?.[0] ?? null))}
                    />
                    {sceneLongTextFile ? <span style={styles.helperText}>{sceneLongTextFile.name}</span> : null}
                  </label>
                )}
                {sceneGenerateError ? <p style={styles.errorText}>{sceneGenerateError}</p> : null}
                {generatedSceneCandidate ? (
                  <div style={styles.generatedSceneCard}>
                    <strong style={styles.generatedSceneTitle}>{generatedSceneCandidate.sceneName}</strong>
                    <p style={styles.generatedSceneSummary}>{generatedSceneCandidate.sceneSummary}</p>
                    <p style={styles.generatedSceneMeta}>
                      {generatedSceneCandidate.mode === "keywords" ? "关键词生成" : "长文本提取"} ·
                      {generatedSceneCandidate.usedModel || "unknown"} ·
                      {countSceneNodes(generatedSceneCandidate.sceneLayers.map((layer) => normalizeSceneTreeNodeForProfile(layer)))} 节点
                    </p>
                    <div style={styles.sidebarActionRow}>
                      <button
                        style={styles.sidebarIconButton}
                        type="button"
                        onClick={applyGeneratedSceneCandidateToEditor}
                        title="应用到编辑区"
                        aria-label="应用到编辑区"
                      >
                        <MaterialIcon name="input" size={14} />
                      </button>
                    </div>
                  </div>
                ) : null}
              </div>
            ) : null}
          </div>

          <div style={styles.sidebarSection}>
            <button type="button" style={styles.sidebarSectionHeader} onClick={() => toggleSidebarSection("reuse")}>
              <span style={styles.panelTitle}>可复用节点库</span>
              <span style={styles.sidebarToggleIcon}><MaterialIcon name={collapsedSidebarSections.includes("reuse") ? "chevron_right" : "expand_more"} size={16} /></span>
            </button>
            {!collapsedSidebarSections.includes("reuse") ? (
              <div style={styles.sidebarSectionBody}>
                <label style={styles.fieldGroup}>
                  <span style={styles.fieldLabel}>搜索节点</span>
                  <input
                    style={styles.input}
                    value={reusableSearchQuery}
                    onChange={(event) => setReusableSearchQuery(event.target.value)}
                    placeholder="搜索标题、标签、复用说明"
                  />
                </label>
                {reusableError ? <p style={styles.errorText}>{reusableError}</p> : null}
                <div style={styles.reusableNodeList}>
                  {filteredReusableNodes.length ? filteredReusableNodes.map((item) => (
                    <article key={item.nodeId} style={styles.reusableNodeCard}>
                      <div style={styles.savedSceneTitleRow}>
                        <strong style={styles.savedSceneTitle}>{item.title}</strong>
                        <span style={styles.savedSceneMeta}>{item.nodeType === "layer" ? "层级" : "物体"}</span>
                      </div>
                      {item.summary ? <p style={styles.savedSceneSummary}>{item.summary}</p> : null}
                      <p style={styles.savedSceneMeta}>{item.reuseHint || "未填写复用说明"}</p>
                      <p style={styles.savedSceneMeta}>
                        {(item.tags.length ? item.tags.join(" · ") : "无标签")}
                        {item.sourceSceneName ? ` · 来自 ${item.sourceSceneName}` : ""}
                      </p>
                      <div style={styles.sidebarCardActions}>
                        <button
                          style={styles.sidebarIconButton}
                          type="button"
                          onClick={() => insertReusableNode(item)}
                          title="插入到当前层级"
                          aria-label="插入到当前层级"
                        >
                          <MaterialIcon name="input" size={14} />
                        </button>
                        <button
                          style={styles.sidebarIconButton}
                          type="button"
                          disabled={reusableActionPendingId === item.nodeId}
                          onClick={() => void deleteReusableNode(item.nodeId)}
                          title={reusableActionPendingId === item.nodeId ? "删除中" : "删除复用节点"}
                          aria-label={reusableActionPendingId === item.nodeId ? "删除中" : "删除复用节点"}
                        >
                          <MaterialIcon name={reusableActionPendingId === item.nodeId ? "hourglass_top" : "delete"} size={14} />
                        </button>
                      </div>
                    </article>
                  )) : (
                    <p style={styles.sidebarHint}>节点库还是空的。</p>
                  )}
                </div>
              </div>
            ) : null}
          </div>

          <div style={styles.sidebarSection}>
            <button type="button" style={styles.sidebarSectionHeader} onClick={() => toggleSidebarSection("saved")}>
              <span style={styles.panelTitle}>已保存场景</span>
              <span style={styles.sidebarToggleIcon}><MaterialIcon name={collapsedSidebarSections.includes("saved") ? "chevron_right" : "expand_more"} size={16} /></span>
            </button>
            {!collapsedSidebarSections.includes("saved") ? (
              <div style={styles.sidebarSectionBody}>
                {savedScenes.length ? (
                  <div style={styles.savedSceneList}>
                    {savedScenes.map((item) => {
                      const isSelected = selectedSavedSceneId === item.sceneId;
                      return (
                        <div key={item.sceneId} style={{ ...styles.savedSceneItem, ...(isSelected ? styles.savedSceneItemSelected : {}) }}>
                          <button
                            type="button"
                            style={styles.savedSceneBody}
                            onClick={() => setSelectedSavedSceneId(item.sceneId)}
                          >
                            <div style={styles.savedSceneTitleRow}>
                              <strong style={styles.savedSceneTitle}>{item.sceneName}</strong>
                              <span style={styles.savedSceneMeta}>{formatDate(item.updatedAt)}</span>
                            </div>
                            <p style={styles.savedSceneSummary}>{item.sceneSummary || "未填写 summary"}</p>
                            <p style={styles.savedSceneMeta}>{item.sceneProfile?.title ?? "未生成快照"} · {countSceneNodes(item.sceneProfile?.sceneTree ?? [])} 节点</p>
                          </button>
                          <div style={styles.sidebarCardActions}>
                            <button
                              style={styles.sidebarIconButton}
                              type="button"
                              onClick={() => void loadSavedScene(item.sceneId)}
                              title="载入场景"
                              aria-label="载入场景"
                            >
                              <MaterialIcon name="file_open" size={14} />
                            </button>
                            <button
                              style={isSelected ? { ...styles.sidebarIconButton, ...styles.sidebarIconButtonPrimary } : styles.sidebarIconButton}
                              type="button"
                              onClick={() => setSelectedSavedSceneId(item.sceneId)}
                              title={isSelected ? "当前更新目标" : "作为更新目标"}
                              aria-label={isSelected ? "当前更新目标" : "作为更新目标"}
                            >
                              <MaterialIcon name="check_circle" size={14} />
                            </button>
                            <button
                              style={styles.sidebarIconButton}
                              type="button"
                              onClick={() => void deleteSavedScene(item.sceneId)}
                              title="删除已保存场景"
                              aria-label="删除已保存场景"
                            >
                              <MaterialIcon name="delete" size={14} />
                            </button>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                ) : null}
              </div>
            ) : null}
          </div>
        </aside>
      </div>

      {pendingDeleteLayerId ? (
        <div style={styles.confirmOverlay} role="presentation">
          <div style={styles.confirmDialog} role="dialog" aria-modal="true" aria-label="删除层级确认">
            <h2 style={styles.confirmTitle}>确认删除层级？</h2>
            <p style={styles.confirmText}>
              即将删除“{findLayerById(sceneLayers, pendingDeleteLayerId)?.title ?? "当前层级"}”及其所有子层级与物体。此操作不可自动恢复。
            </p>
            <div style={styles.confirmActions}>
              <button type="button" style={styles.btnGhost} onClick={cancelDeleteLayer}>取消</button>
              <button type="button" style={styles.btnDanger} onClick={confirmDeleteLayer}>确认删除</button>
            </div>
          </div>
        </div>
      ) : null}

    </main>
  );
}

function SceneLayerCard({
  layer,
  index,
  selectedLayerId,
  selectedObjectId,
  onSelect,
  onToggleEditor,
  onAddChild,
  onAddObject,
  onSaveToReusable,
  onSelectObject,
  onSaveObjectToReusable,
  onRemoveObject,
  reusableActionPendingId,
  onRequestDelete,
  canDeleteLayerForId,
  editorContent,
  renderObjectEditor,
}: {
  layer: SceneLayer;
  index: number;
  selectedLayerId: string;
  selectedObjectId: string;
  onSelect: (layerId: string) => void;
  onToggleEditor: (layerId: string) => void;
  onAddChild: (layerId: string) => void;
  onAddObject: (layerId: string) => void;
  onSaveToReusable: (layerId: string) => void;
  onSelectObject: (objectId: string) => void;
  onSaveObjectToReusable: (object: SceneObject) => void;
  onRemoveObject: (layerId: string, objectId: string) => void;
  reusableActionPendingId: string;
  onRequestDelete: (layerId: string) => void;
  canDeleteLayerForId: (layerId: string) => boolean;
  editorContent: ReactNode;
  renderObjectEditor: (layerId: string, object: SceneObject) => ReactNode;
}) {
  const isSelected = layer.id === selectedLayerId;
  const isCollapsed = false;
  const hasChildren = layer.children.length > 0;
  const hasObjects = layer.objects.length > 0;
  const stopCardAction = (handler: () => void) => (event: ReactMouseEvent<HTMLButtonElement>) => {
    event.stopPropagation();
    handler();
  };
  return (
    <div style={styles.cardGroup}>
      <article
        style={{
          ...styles.layerCard,
          ...(isSelected ? styles.layerCardActive : null)
        }}
        onClick={() => onSelect(layer.id)}
      >
        <div style={styles.layerTopRow}>
          <div style={styles.layerIndexBadge}>{String(index + 1).padStart(2, "0")}</div>
          <div style={styles.layerHeadCopy}>
            <span style={styles.layerScope}>{layer.scopeLabel}</span>
            <h2 style={styles.layerTitle}>{layer.title}</h2>
          </div>
        </div>

        {!isSelected ? (
          <>
            <p style={styles.layerSummary}>{layer.summary}</p>

            <div style={styles.objectChipRow}>
              {layer.tags.split(",").map((tag) => tag.trim()).filter(Boolean).slice(0, 2).map((tag) => (
                <span key={`${layer.id}:${tag}`} style={styles.tagChip}>#{tag}</span>
              ))}
              {layer.objects.slice(0, 3).map((object) => (
                <span key={object.id} style={styles.objectChip}>{object.name}</span>
              ))}
              {layer.objects.length > 3 ? <span style={styles.objectChip}>+{layer.objects.length - 3}</span> : null}
            </div>
          </>
        ) : null}

        <div style={styles.cardActions}>
          <SceneIconButton icon="add_circle" label="添加子层" size="micro" variant="accent" onClick={stopCardAction(() => onAddChild(layer.id))} />
          <SceneIconButton icon="category" label="添加物体" size="micro" onClick={stopCardAction(() => onAddObject(layer.id))} />
          <SceneIconButton
            icon={reusableActionPendingId === layer.id ? "hourglass_top" : "create_new_folder"}
            label="加入节点库"
            size="micro"
            onClick={stopCardAction(() => onSaveToReusable(layer.id))}
            disabled={reusableActionPendingId === layer.id}
          />
          <SceneIconButton
            icon="delete"
            label="删除当前层级"
            size="micro"
            variant="danger"
            onClick={stopCardAction(() => onRequestDelete(layer.id))}
            disabled={!canDeleteLayerForId(layer.id)}
          />
          <SceneIconButton
            icon={isSelected ? "expand_more" : "chevron_right"}
            label={isSelected ? "收起节点编辑器" : "展开节点编辑器"}
            size="micro"
            onClick={stopCardAction(() => onToggleEditor(layer.id))}
          />
        </div>
      </article>

      {isSelected ? <div id={`scene-node-editor-${layer.id}`} style={styles.nodeInlineEditor}>{editorContent}</div> : null}

      {(hasObjects || hasChildren) && !isCollapsed ? (
        <div style={styles.childStack}>
          {layer.objects.map((object) => (
            <SceneObjectCard
              key={object.id}
              object={object}
              layerId={layer.id}
              selectedObjectId={selectedObjectId}
              onSelect={onSelectObject}
              onSaveToReusable={onSaveObjectToReusable}
              onRemove={onRemoveObject}
              reusableActionPendingId={reusableActionPendingId}
              editorContent={renderObjectEditor(layer.id, object)}
            />
          ))}
          {layer.children.map((child, childIndex) => (
            <SceneLayerCard
              key={child.id}
              layer={child}
              index={childIndex}
              selectedLayerId={selectedLayerId}
              selectedObjectId={selectedObjectId}
              onSelect={onSelect}
              onToggleEditor={onToggleEditor}
              onAddChild={onAddChild}
              onAddObject={onAddObject}
              onSaveToReusable={onSaveToReusable}
              onSelectObject={onSelectObject}
              onSaveObjectToReusable={onSaveObjectToReusable}
              onRemoveObject={onRemoveObject}
              reusableActionPendingId={reusableActionPendingId}
              onRequestDelete={onRequestDelete}
              canDeleteLayerForId={canDeleteLayerForId}
              editorContent={editorContent}
              renderObjectEditor={renderObjectEditor}
            />
          ))}
        </div>
      ) : null}
    </div>
  );
}

function SceneObjectCard({
  object,
  layerId,
  selectedObjectId,
  onSelect,
  onSaveToReusable,
  onRemove,
  reusableActionPendingId,
  editorContent,
}: {
  object: SceneObject;
  layerId: string;
  selectedObjectId: string;
  onSelect: (objectId: string) => void;
  onSaveToReusable: (object: SceneObject) => void;
  onRemove: (layerId: string, objectId: string) => void;
  reusableActionPendingId: string;
  editorContent: ReactNode;
}) {
  const isSelected = object.id === selectedObjectId;
  const stopCardAction = (handler: () => void) => (event: ReactMouseEvent<HTMLButtonElement>) => {
    event.stopPropagation();
    handler();
  };

  return (
    <div style={styles.cardGroup}>
      <article
        style={{
          ...styles.objectNodeCard,
          ...(isSelected ? styles.objectNodeCardActive : null),
        }}
        onClick={() => onSelect(object.id)}
      >
        <div style={styles.objectNodeTopRow}>
          <div style={styles.objectNodeBadge}>
            <MaterialIcon name="category" size={14} />
          </div>
          <div style={styles.layerHeadCopy}>
            <span style={styles.layerScope}>物体节点</span>
            <h3 style={styles.layerTitle}>{object.name}</h3>
          </div>
        </div>

        {!isSelected ? (
          <>
            <p style={styles.layerSummary}>
              {(object.description || object.interaction || "尚未填写细节").slice(0, 96)}
              {(object.description || object.interaction || "").length > 96 ? "..." : ""}
            </p>
            <div style={styles.objectChipRow}>
              {object.tags.split(",").map((tag) => tag.trim()).filter(Boolean).slice(0, 3).map((tag) => (
                <span key={`${object.id}:${tag}`} style={styles.tagChip}>#{tag}</span>
              ))}
            </div>
          </>
        ) : null}

        <div style={styles.cardActions}>
          <SceneIconButton
            icon={reusableActionPendingId === object.id ? "hourglass_top" : "create_new_folder"}
            label="加入节点库"
            size="micro"
            onClick={stopCardAction(() => onSaveToReusable(object))}
            disabled={reusableActionPendingId === object.id}
          />
          <SceneIconButton
            icon="delete"
            label="删除物体"
            size="micro"
            variant="danger"
            onClick={stopCardAction(() => onRemove(layerId, object.id))}
          />
          <SceneIconButton
            icon={isSelected ? "expand_more" : "chevron_right"}
            label={isSelected ? "收起物体编辑器" : "展开物体编辑器"}
            size="micro"
            onClick={stopCardAction(() => onSelect(object.id))}
          />
        </div>
      </article>

      {isSelected ? <div id={`scene-object-editor-${layerId}-${object.id}`} style={styles.nodeInlineEditor}>{editorContent}</div> : null}
    </div>
  );
}

function SceneIconButton({
  icon,
  label,
  onClick,
  disabled = false,
  variant = "default",
  size = "small",
}: {
  icon: MaterialIconName;
  label: string;
  onClick: (event: ReactMouseEvent<HTMLButtonElement>) => void;
  disabled?: boolean;
  variant?: "default" | "accent" | "danger";
  size?: "small" | "micro";
}) {
  const style = {
    ...(size === "micro" ? styles.iconButtonMicro : styles.iconButton),
    ...(variant === "accent"
      ? size === "micro"
        ? styles.iconButtonMicroAccent
        : styles.iconButtonAccent
      : variant === "danger"
        ? size === "micro"
          ? styles.iconButtonMicroDanger
          : styles.iconButtonDanger
        : {}),
  };
  return (
    <button type="button" aria-label={label} title={label} style={style} onClick={onClick} disabled={disabled}>
      <MaterialIcon name={icon} size={size === "micro" ? 14 : 16} />
    </button>
  );
}

function RewriteStateButton({
  actionKey,
  label,
  pendingKey,
  lastRewrite,
  rewriteStrength,
  onRewriteStrengthChange,
  onRewrite,
  onUndo,
}: {
  actionKey: string;
  label: string;
  pendingKey: string;
  lastRewrite: RewriteUndoEntry | null;
  rewriteStrength: number;
  onRewriteStrengthChange: (value: number) => void;
  onRewrite: () => void;
  onUndo: () => void;
}) {
  const [isStrengthOpen, setIsStrengthOpen] = useState(false);
  const strengthPopoverRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!isStrengthOpen) {
      return;
    }
    const handlePointerDown = (event: MouseEvent) => {
      if (!strengthPopoverRef.current?.contains(event.target as Node)) {
        setIsStrengthOpen(false);
      }
    };
    document.addEventListener("mousedown", handlePointerDown);
    return () => document.removeEventListener("mousedown", handlePointerDown);
  }, [isStrengthOpen]);

  const isPending = pendingKey === actionKey;
  const isUndo = !isPending && lastRewrite?.key === actionKey;
  const icon = isPending ? "hourglass_top" : isUndo ? "undo" : "auto_awesome";
  const buttonLabel = isPending
    ? "重写中"
    : isUndo
      ? `撤销重写：${lastRewrite?.label ?? label}`
      : `AI 重写${label}`;

  useEffect(() => {
    if (isPending) {
      setIsStrengthOpen(false);
    }
  }, [isPending]);

  return (
    <div style={styles.rewriteActionGroup}>
      <SceneIconButton
        icon={icon}
        label={buttonLabel}
        onClick={(event) => {
          event.stopPropagation();
          if (isPending) {
            return;
          }
          if (isUndo) {
            onUndo();
            return;
          }
          setIsStrengthOpen((current) => !current);
        }}
        disabled={Boolean(pendingKey)}
      />
      {(!isPending && !isUndo && isStrengthOpen) ? (
        <div ref={strengthPopoverRef} style={styles.rewritePopoverWrap}>
          <div style={styles.rewritePopover} onClick={(event) => event.stopPropagation()}>
            <div style={styles.rewritePopoverSection}>
              <span style={styles.rewritePopoverTitle}>重写强度</span>
              <span style={styles.rewritePopoverValue}>{(rewriteStrength * 100).toFixed(0)}%</span>
            </div>
            <input
              style={styles.rewriteSlider}
              type="range"
              min={0.05}
              max={1}
              step={0.05}
              value={rewriteStrength}
              onChange={(event) => onRewriteStrengthChange(Number(event.target.value))}
            />
            <p style={styles.rewritePopoverHint}>数值越高，AI 对原始设定的改写幅度越大。</p>
            <button
              type="button"
              style={styles.rewritePopoverButton}
              onClick={(event) => {
                event.stopPropagation();
                setIsStrengthOpen(false);
                onRewrite();
              }}
            >
              开始重写
            </button>
          </div>
        </div>
      ) : null}
    </div>
  );
}

const styles: Record<string, CSSProperties> = {
  // ── page shell ────────────────────────────────────────────
  page: {
    width: "100%",
    height: "100vh",
    boxSizing: "border-box",
    maxWidth: 1600,
    margin: "0 auto",
    padding: "0 28px 28px",
    overflow: "hidden",
    display: "flex",
    flexDirection: "column",
    gap: 0,
    background: "var(--bg)",
  },
  heading: {
    display: "grid",
    gap: 8,
    position: "sticky",
    top: 0,
    zIndex: 15,
    paddingTop: 20,
    marginBottom: 16,
    paddingBottom: 16,
    borderBottom: "1px solid color-mix(in srgb, var(--border) 76%, white)",
    background: "color-mix(in srgb, white 92%, var(--bg))",
  },
  headingRow: {
    display: "flex",
    alignItems: "center",
    gap: 12,
    flexWrap: "wrap",
  },
  notice: {
    width: "fit-content",
    maxWidth: "100%",
    minHeight: 24,
    padding: "0 8px",
    border: "none",
    background: "color-mix(in srgb, white 72%, var(--accent-soft))",
    color: "var(--ink-2)",
    fontSize: 12,
    lineHeight: 1,
    display: "inline-flex",
    alignItems: "center",
  },
  workspaceShell: {
    display: "flex",
    flex: 1,
    minHeight: 0,
    overflow: "hidden",
    gap: 14,
  },
  workspaceShellCompact: {
    flexDirection: "column",
    overflowY: "auto",
  },
  panel: {
    display: "flex",
    flexDirection: "column",
    overflow: "hidden",
    border: "1px solid var(--border)",
    background: "color-mix(in srgb, white 99%, var(--panel))",
    minHeight: 0,
  },
  panelCompact: {
    overflow: "visible",
  },
  resizer: {
    width: 4,
    flexShrink: 0,
    background: "var(--border)",
    cursor: "col-resize",
  },
  panelHeader: {
    position: "relative",
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 12,
    flexWrap: "wrap",
    minHeight: 40,
    padding: "10px 16px",
    borderBottom: "1px solid color-mix(in srgb, var(--border) 76%, white)",
    background: "transparent",
    flexShrink: 0,
  },
  panelHeaderActions: {
    display: "inline-flex",
    alignItems: "center",
    gap: 8,
    flexWrap: "wrap",
  },
  panelBody: {
    flex: 1,
    minHeight: 0,
    overflowY: "auto",
    padding: "16px 18px 18px",
    display: "grid",
    gap: 14,
    alignContent: "start",
  },
  panelBodyCompact: {
    overflow: "visible",
  },
  nodeInlineEditor: {
    marginTop: 6,
    paddingTop: 14,
    borderTop: "1px solid color-mix(in srgb, var(--border) 74%, white)",
    display: "grid",
    gap: 12,
    alignContent: "start",
  },
  editorSection: {
    border: "1px solid color-mix(in srgb, var(--border) 80%, white)",
    background: "color-mix(in srgb, white 99%, var(--panel))",
    display: "grid",
    gap: 0,
    overflow: "hidden",
  },
  editorSectionHeader: {
    width: "100%",
    border: "none",
    background: "transparent",
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    padding: "9px 10px",
    cursor: "pointer",
    textAlign: "left",
  },
  editorSectionBody: {
    padding: "0 10px 10px",
    display: "grid",
    gap: 10,
  },
  pageTitle: {
    margin: 0,
    fontSize: 20,
    fontWeight: 700,
    color: "var(--ink)",
    lineHeight: 1.2,
  },
  // ── sidebar fields ────────────────────────────────────────
  sceneNameLabel: { display: "grid", gap: 6 },
  sceneSummaryLabel: { display: "grid", gap: 6 },
  sceneNameInput: {
    width: "100%",
    border: "1px solid var(--border)",
    padding: "7px 10px",
    background: "var(--bg)",
    color: "var(--ink)",
    fontSize: 13,
    outline: "none",
  },
  sceneSummaryInput: {
    width: "100%",
    minHeight: 80,
    resize: "vertical",
    border: "1px solid var(--border)",
    padding: "7px 10px",
    background: "var(--bg)",
    color: "var(--ink)",
    fontSize: 13,
    lineHeight: 1.6,
    outline: "none",
  },
  sceneActionButtons: { display: "flex", flexWrap: "wrap", gap: 6 },
  // ── saved scenes ──────────────────────────────────────────
  savedSceneList: {
    display: "grid",
    gap: 6,
    alignContent: "start",
    alignItems: "start",
    justifyContent: "start",
    alignSelf: "start",
    width: "100%",
  },
  savedSceneItem: {
    display: "grid",
    gap: 6,
    padding: 10,
    border: "1px solid color-mix(in srgb, var(--border) 80%, white)",
    background: "color-mix(in srgb, white 96%, var(--panel))",
    width: "100%",
  },
  savedSceneItemSelected: {
    border: "1px solid var(--accent)",
    boxShadow: "0 0 0 1px var(--accent) inset",
  },
  savedSceneBody: {
    display: "grid",
    gap: 4,
    textAlign: "left",
    border: "none",
    background: "transparent",
    padding: 0,
    cursor: "pointer",
  },
  savedSceneTitleRow: {
    display: "flex",
    justifyContent: "space-between",
    gap: 10,
    alignItems: "baseline",
  },
  savedSceneTitle: { fontSize: 13, color: "var(--ink)" },
  savedSceneMeta: { fontSize: 11, color: "var(--muted)", margin: 0, lineHeight: 1.4 },
  savedSceneSummary: { margin: 0, fontSize: 12, lineHeight: 1.5, color: "var(--muted)" },
  savedSceneActions: { display: "flex", flexWrap: "wrap", gap: 4 },
  sidebarPane: {
    display: "flex",
    flexDirection: "column",
    gap: 10,
    minHeight: 0,
    overflowY: "auto",
  },
  sidebarPaneCompact: {
    overflow: "visible",
  },
  sidebarSection: {
    border: "1px solid var(--border)",
    background: "color-mix(in srgb, white 99%, var(--panel))",
    overflow: "hidden",
    flexShrink: 0,
  },
  sidebarSectionStaticHeader: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    gap: 12,
    padding: "10px 12px",
    borderBottom: "1px solid color-mix(in srgb, var(--border) 76%, white)",
  },
  sidebarSectionMeta: {
    fontSize: 11,
    color: "var(--muted)",
    whiteSpace: "nowrap",
  },
  sidebarSectionHeader: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    width: "100%",
    border: "none",
    background: "transparent",
    padding: "10px 12px",
    cursor: "pointer",
    textAlign: "left",
  },
  sidebarSectionBody: {
    padding: "0 12px 12px",
    display: "grid",
    gap: 8,
    alignContent: "start",
  },
  sceneMetaSectionBody: {
    paddingTop: 16,
  },
  sidebarFlatSection: {
    border: "1px solid var(--border)",
    background: "color-mix(in srgb, white 99%, var(--panel))",
    overflow: "hidden",
    flexShrink: 0,
  },
  sidebarFlatBody: {
    padding: "12px",
    display: "grid",
    gap: 8,
    alignContent: "start",
  },
  sidebarToggleIcon: { color: "var(--muted)", display: "inline-flex", alignItems: "center", justifyContent: "center" },
  sidebarHint: { margin: 0, fontSize: 12, color: "var(--muted)", lineHeight: 1.6 },
  sidebarStatusMsg: {
    margin: 0,
    padding: "8px 10px",
    fontSize: 12,
    color: "var(--muted)",
    border: "1px solid var(--border)",
    background: "color-mix(in srgb, white 96%, var(--panel))",
  },
  treePane: { padding: "16px 20px", display: "grid", gap: 14, alignContent: "start", overflowY: "auto" },
  editorPane: { borderLeft: "1px solid var(--border)", padding: "16px 20px", display: "grid", gap: 16, alignContent: "start", overflowY: "auto" },
  panelHead: { paddingBottom: 10, borderBottom: "1px solid var(--border)", display: "grid", gap: 3 },
  panelTitle: { fontSize: 10, fontWeight: 700, color: "var(--muted)", textTransform: "uppercase", letterSpacing: "0.12em" },
  hiddenInput: { display: "none" },
  treeStack: { display: "grid", gap: 8 },
  cardGroup: { display: "grid", gap: 6 },
  layerCard: {
    border: "none",
    background: "color-mix(in srgb, white 54%, var(--accent-soft))",
    padding: 12,
    display: "grid",
    gap: 8,
    cursor: "pointer",
  },
  layerCardActive: {
    background: "color-mix(in srgb, white 28%, var(--accent-soft))",
    boxShadow: "0 0 0 2px color-mix(in srgb, var(--accent) 24%, transparent) inset",
  },
  layerTopRow: { display: "flex", alignItems: "flex-start", gap: 8 },
  layerIndexBadge: { width: 22, height: 22, background: "var(--accent)", color: "#fff", display: "grid", placeItems: "center", fontSize: 10, fontWeight: 800, letterSpacing: "0.06em", flexShrink: 0 },
  layerHeadCopy: { display: "grid", gap: 2, minWidth: 0 },
  layerScope: { fontSize: 10, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.07em", color: "var(--muted)" },
  layerTitle: { margin: 0, fontSize: 13, fontWeight: 600, color: "var(--ink)", lineHeight: 1.2 },
  layerSummary: { margin: 0, fontSize: 12, lineHeight: 1.5, color: "var(--muted)" },
  layerReuseHint: { margin: 0, fontSize: 11, lineHeight: 1.5, color: "var(--ink)" },
  objectNodeCard: {
    borderWidth: 1,
    borderStyle: "solid",
    borderColor: "color-mix(in srgb, var(--border) 82%, white)",
    background: "color-mix(in srgb, white 98%, var(--panel))",
    padding: 12,
    display: "grid",
    gap: 8,
    cursor: "pointer",
  },
  objectNodeCardActive: {
    borderColor: "var(--accent)",
    boxShadow: "0 0 0 2px var(--accent-soft) inset",
  },
  objectNodeTopRow: { display: "flex", alignItems: "flex-start", gap: 8 },
  objectNodeBadge: {
    width: 22,
    height: 22,
    border: "1px solid color-mix(in srgb, var(--accent) 40%, var(--border))",
    background: "color-mix(in srgb, white 84%, var(--accent-soft))",
    color: "var(--accent)",
    display: "grid",
    placeItems: "center",
    flexShrink: 0,
  },
  objectChipRow: { display: "flex", flexWrap: "wrap", gap: 4 },
  tagChip: { padding: "2px 6px", border: "1px solid var(--accent-soft)", background: "var(--accent-soft)", fontSize: 10, color: "var(--accent)" },
  objectChip: { padding: "2px 6px", border: "1px solid var(--border)", background: "var(--bg)", fontSize: 10, color: "var(--muted)" },
  cardActions: { display: "flex", flexWrap: "wrap", gap: 4 },
  childStack: { paddingLeft: 12, borderLeft: "2px solid var(--border)", display: "grid", gap: 6 },
  pathChipRow: { display: "flex", flexWrap: "wrap", gap: 4 },
  pathChip: { padding: "2px 6px", background: "color-mix(in srgb, white 90%, var(--panel))", border: "1px solid var(--border)", fontSize: 11, color: "var(--muted)" },
  rewriteControlRow: { display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8, paddingBottom: 4, borderBottom: "1px solid var(--border)" },
  rewriteActionGroup: { display: "inline-flex", alignItems: "center", gap: 4, position: "relative" },
  rewritePopoverWrap: {
    position: "absolute",
    top: "calc(100% + 8px)",
    right: 0,
    zIndex: 20,
  },
  rewritePopover: {
    position: "relative",
    width: 220,
    display: "grid",
    gap: 10,
    padding: "12px 12px 10px",
    border: "1px solid color-mix(in srgb, var(--border) 76%, white)",
    background: "var(--panel)",
    boxShadow: "0 12px 28px rgba(13, 32, 40, 0.12)",
  },
  rewritePopoverSection: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 8,
  },
  rewritePopoverTitle: { fontSize: 12, fontWeight: 600, color: "var(--ink)" },
  rewritePopoverValue: { fontSize: 12, fontWeight: 600, color: "var(--ink)" },
  rewritePopoverHint: { margin: 0, fontSize: 12, lineHeight: 1.5, color: "var(--muted)" },
  rewritePopoverButton: {
    border: "none",
    height: 30,
    background: "var(--accent)",
    color: "white",
    fontSize: 12,
    fontWeight: 600,
    cursor: "pointer",
  },
  rewriteSlider: { width: "100%", flexShrink: 0 },
  formGrid: { display: "grid", gap: 12 },
  fieldGroup: { display: "grid", gap: 6 },
  compactField: { display: "grid", gap: 6, flex: 1 },
  fieldLabel: { fontSize: 11, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.07em", color: "var(--muted)" },
  fieldLabelRow: { display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8 },
  input: { width: "100%", height: 36, border: "1px solid var(--border)", background: "var(--panel)", padding: "0 10px", color: "var(--ink)", fontSize: 13, outline: "none" },
  textarea: { width: "100%", minHeight: 72, border: "1px solid var(--border)", background: "var(--panel)", padding: "8px 10px", color: "var(--ink)", fontSize: 13, lineHeight: 1.6, resize: "vertical", outline: "none" },
  helperText: { fontSize: 12, color: "var(--muted)" },
  emptyState: { margin: 0, padding: "20px 0", color: "var(--muted)", lineHeight: 1.7, fontSize: 13 },
  errorText: { fontSize: 12, color: "var(--danger, #b42318)", lineHeight: 1.5 },
  generatedSceneCard: { display: "grid", gap: 6, padding: 10, border: "1px solid color-mix(in srgb, var(--border) 80%, white)", background: "color-mix(in srgb, white 96%, var(--panel))" },
  generatedSceneTitle: { fontSize: 13, color: "var(--ink)" },
  generatedSceneSummary: { margin: 0, fontSize: 12, lineHeight: 1.5, color: "var(--muted)" },
  generatedSceneMeta: { margin: 0, fontSize: 11, lineHeight: 1.4, color: "var(--muted)" },
  reusableNodeList: { display: "grid", gap: 8, maxHeight: 320, overflowY: "auto" },
  reusableNodeCard: { display: "grid", gap: 6, padding: 10, border: "1px solid color-mix(in srgb, var(--border) 80%, white)", background: "color-mix(in srgb, white 96%, var(--panel))" },
  fileInput: {
    width: "100%",
    border: "1px solid var(--border)",
    background: "var(--panel)",
    color: "var(--ink)",
    padding: "6px 8px",
    fontSize: 12,
  },
  modeSwitchRow: {
    display: "flex",
    alignItems: "center",
    gap: 8,
    justifyContent: "space-between",
    flexWrap: "nowrap",
  },
  modeSwitch: {
    display: "inline-flex",
    border: "1px solid var(--border)",
    background: "color-mix(in srgb, white 88%, var(--panel))",
    minHeight: 28,
    minWidth: 0,
    flex: 1,
  },
  modeSwitchButton: {
    border: "none",
    background: "transparent",
    color: "var(--muted)",
    padding: "0 10px",
    fontSize: 12,
    cursor: "pointer",
    minHeight: 28,
    flex: 1,
  },
  modeSwitchButtonActive: {
    border: "none",
    background: "color-mix(in srgb, white 65%, var(--accent-soft))",
    color: "var(--ink)",
    fontWeight: 600,
    padding: "0 10px",
    fontSize: 12,
    cursor: "pointer",
    minHeight: 28,
    flex: 1,
  },
  btnPrimary: { border: "none", background: "var(--accent)", color: "white", height: 34, padding: "0 14px", fontWeight: 600, cursor: "pointer", fontSize: 13, flexShrink: 0, display: "inline-flex", alignItems: "center" },
  btnGhost: { border: "1px solid var(--border)", background: "transparent", color: "var(--ink)", height: 34, padding: "0 12px", cursor: "pointer", fontSize: 13, flexShrink: 0, display: "inline-flex", alignItems: "center" },
  btnDanger: { border: "none", background: "var(--danger, #b42318)", color: "white", height: 34, padding: "0 12px", cursor: "pointer", fontSize: 13, fontWeight: 600, display: "inline-flex", alignItems: "center" },
  sidebarActionRow: {
    display: "flex",
    gap: 4,
    alignItems: "center",
    justifyContent: "flex-end",
    flexWrap: "wrap",
  },
  sidebarCardActions: {
    display: "flex",
    gap: 4,
    alignItems: "center",
    justifyContent: "flex-end",
  },
  sidebarIconButton: {
    border: "1px solid color-mix(in srgb, var(--border) 76%, white)",
    width: 28,
    height: 28,
    padding: 0,
    background: "color-mix(in srgb, white 72%, var(--surface))",
    color: "var(--ink)",
    cursor: "pointer",
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
    flexShrink: 0,
  },
  sidebarIconButtonPrimary: {
    border: "none",
    background: "var(--accent)",
    color: "white",
  },
  iconButton: { borderWidth: 1, borderStyle: "solid", borderColor: "var(--border)", background: "var(--panel)", color: "var(--ink)", height: 28, minWidth: 28, padding: 0, cursor: "pointer", fontSize: 12, fontWeight: 700, display: "inline-flex", alignItems: "center", justifyContent: "center", flexShrink: 0 },
  iconButtonAccent: { borderColor: "color-mix(in srgb, var(--accent) 40%, var(--border))", background: "color-mix(in srgb, white 76%, var(--accent-soft))", color: "var(--accent)" },
  iconButtonDanger: { borderColor: "color-mix(in srgb, var(--danger, #b42318) 38%, var(--border))", background: "color-mix(in srgb, white 88%, var(--danger, #b42318))", color: "var(--danger, #b42318)" },
  iconButtonMicro: { borderWidth: 1, borderStyle: "solid", borderColor: "var(--border)", background: "transparent", color: "var(--muted)", height: 22, minWidth: 22, padding: 0, fontSize: 11, cursor: "pointer", display: "inline-flex", alignItems: "center", justifyContent: "center", flexShrink: 0 },
  iconButtonMicroAccent: { borderColor: "color-mix(in srgb, var(--accent) 40%, var(--border))", color: "var(--accent)", background: "color-mix(in srgb, white 84%, var(--accent-soft))" },
  iconButtonMicroDanger: { borderColor: "color-mix(in srgb, var(--danger, #b42318) 38%, var(--border))", color: "var(--danger, #b42318)", background: "color-mix(in srgb, white 92%, var(--danger, #b42318))" },
  confirmOverlay: { position: "fixed", inset: 0, background: "rgba(15, 23, 42, 0.35)", display: "grid", placeItems: "center", zIndex: 30, padding: 16 },
  confirmDialog: { width: "min(480px, 100%)", background: "var(--bg)", border: "1px solid var(--border)", display: "grid", gap: 12, padding: 20, boxShadow: "0 14px 28px rgba(15, 23, 42, 0.12)" },
  confirmTitle: { margin: 0, fontSize: 15, fontWeight: 700, color: "var(--ink)" },
  confirmText: { margin: 0, fontSize: 13, lineHeight: 1.6, color: "var(--muted)" },
  confirmActions: { display: "flex", justifyContent: "flex-end", gap: 8 },
};
