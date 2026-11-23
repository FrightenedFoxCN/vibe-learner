"use client";

import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { useConfirm } from "../components/ui/confirm-provider";
import {
  type SceneObject,
  type SceneLayer,
  LAYER_TEMPLATES,
  createSceneObject,
  createSceneLayer,
  cloneSceneObjectFromLibrary,
  cloneSceneLayerFromLibrary,
  normalizeSceneTreeNodeForProfile,
  removeLayerTree,
  canDeleteLayerSafely,
  parseSceneImportPayload,
  updateLayerTree,
  findLayerById,
  inferTemplateIndexFromLayer,
} from "../lib/scene-editor-model";
import { useSceneLibrary } from "./use-scene-library";
import { useSceneDraft } from "./use-scene-draft";
import { useSceneGeneration } from "./use-scene-generation";
import { readBoundedJsonImport } from "../lib/bounded-json-import";
import { observeLocalAction } from "../lib/diagnostic-actions";
import { isApiHttpError } from "../lib/http-error";
import { exportJson } from "../lib/export-json";
import { usePageDebugSnapshot } from "../components/debug/page-debug-context";
import { useSceneRewrite } from "./use-scene-rewrite";
import { type ReusableSceneNodePayload } from "../lib/data/scenes";
import { applyAsyncResult, AsyncResultFence } from "../lib/async-result-fence";

export function useSceneWorkspaceController() {
  const confirm = useConfirm();
  const {
    savedScenes,
    reusableNodes,
    selectedSavedSceneId,
    getSceneBinding,
    bindScene,
    refreshSceneLibraryItem,
    createSceneLibraryItem,
    updateSceneLibraryItem,
    deleteSceneLibraryItem,
    createReusableSceneNode,
    deleteReusableSceneNode,
    libraryError,
    reusableActionPendingId,
    reusableMessage,
    reusableError,
    setReusableMessage,
    setReusableError,
    runReusableAction,
  } = useSceneLibrary();
  const pageHeadingRef = useRef<HTMLHeadingElement>(null);
  const deletedTrigger = useRef<HTMLElement | null>(null);
  const [sceneIoMessage, setSceneIoMessage] = useState("");
  const [sceneIoPendingCount, setSceneIoPendingCount] = useState(0);
  const [sceneIoError, setSceneIoError] = useState("");
  const sceneIoPending = sceneIoPendingCount > 0;
  function beginSceneIo() {
    setSceneIoError("");
    setSceneIoMessage("");
    setSceneIoPendingCount((count) => count + 1);
  }
  function finishSceneIo() {
    setSceneIoPendingCount((count) => Math.max(0, count - 1));
  }
  const [reusableSearchQuery, setReusableSearchQuery] = useState("");
  const {
    contentFingerprint,
    sceneStorageFailed,
    flushDraft,
    isSceneDraftDirty,
    markSaved,
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
    beginDiagnosticAction,
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
  } = useSceneDraft({
    onSelectionChange: () => invalidateRewrite(),
    onImported: () => {
      bindScene(null);
      resetSceneGeneration();
      resetRewrite();
    },
    onNotice: setSceneIoMessage,
  });
  useLayoutEffect(() => {
    const trigger = deletedTrigger.current;
    if (!trigger || trigger.isConnected) return;
    deletedTrigger.current = null;
    // The shared dialog may restore focus before the deletion removes the button.
    if (!document.activeElement || document.activeElement === document.body) {
      pageHeadingRef.current?.focus({ preventScroll: true });
    }
  }, [savedScenes, sceneLayers]);
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
  } = useSceneGeneration(currentSceneAsyncScope, undefined, beginDiagnosticAction);
  const {
    rewriteStrength,
    setRewriteStrength,
    rewritePendingKey,
    rewriteError,
    rewriteModelRecoveries,
    lastRewrite,
    undoLastRewrite,
    rewriteLayerField,
    rewriteObjectField,
    invalidateRewrite,
    resetRewrite,
  } = useSceneRewrite({
    beginDiagnosticAction,
    sceneLayers,
    currentSceneAsyncScope,
    setSceneFieldTarget,
    updateLayer,
    updateObject,
  });
  const importInputRef = useRef<HTMLInputElement | null>(null);
  const sceneImportFenceRef = useRef(new AsyncResultFence());
  useEffect(() => () => sceneImportFenceRef.current.invalidate(), []);
  const draftView = useRef({
    active: false,
    dirty: false,
    candidate: generatedSceneCandidate,
  });
  useLayoutEffect(() => {
    draftView.current = {
      active: true,
      dirty: isSceneDraftDirty,
      candidate: generatedSceneCandidate,
    };
    return () => {
      draftView.current.active = false;
    };
  }, [isSceneDraftDirty, generatedSceneCandidate]);

  async function confirmReplaceSceneDraft(action: string, trigger?: HTMLElement) {
    const before = currentSceneAsyncScope("scene-replacement");
    const approved =
      !draftView.current.dirty ||
      (await confirm({
        title: "替换当前场景草稿？",
        message: `${action}会丢弃当前场景草稿。可先另存为新场景或导出 JSON。`,
        confirmLabel: "替换草稿",
        danger: true,
        trigger,
        fallbackFocus: () => pageHeadingRef.current,
      }));
    const after = currentSceneAsyncScope("scene-replacement");
    return (
      approved &&
      draftView.current.active &&
      after.subjectId === before.subjectId &&
      after.draftRevision === before.draftRevision
    );
  }

  const [collapsedSidebarSections, setCollapsedSidebarSections] = useState<string[]>([
    "reuse",
    "saved",
  ]);
  const [collapsedNodeEditorSectionsByLayer, setCollapsedNodeEditorSectionsByLayer] =
    useState<Record<string, string[]>>({});
  const [isCompactLayout, setIsCompactLayout] = useState(false);

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
      ]
        .join("\n")
        .toLowerCase();
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
    () =>
      selectedLayerId
        ? (collapsedNodeEditorSectionsByLayer[selectedLayerId] ?? [])
        : [],
    [collapsedNodeEditorSectionsByLayer, selectedLayerId],
  );

  const pageNotice = useMemo(() => {
    if (sceneIoPending) {
      return "正在处理场景文件与场景库";
    }
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
  }, [
    sceneIoPending,
    headerMessage,
    reusableActionPendingId,
    rewritePendingKey,
    sceneGeneratePending,
    selectedLayer,
    selectedObjectTarget,
  ]);

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

  const debugSnapshot = useMemo(
    () => ({
      title: "场景页调试面板",
      subtitle: "查看场景树、生成结果和错误。",
      error: [
        sceneIoError,
        rewriteError,
        sceneGenerateError,
        reusableError,
        libraryError,
      ]
        .filter(Boolean)
        .join("；"),
      summary: [
        { label: "场景名称", value: sceneName || "-" },
        { label: "选中层级", value: selectedLayer?.title || selectedLayerId || "-" },
        { label: "已保存场景", value: String(savedScenes.length) },
        { label: "可复用节点", value: String(reusableNodes.length) },
        { label: "生成候选", value: generatedSceneCandidate ? "是" : "否" },
        {
          label: "AI 恢复记录",
          value: String(
            rewriteModelRecoveries.length + sceneGenerateModelRecoveries.length,
          ),
        },
      ],
      details: [
        { title: "场景快照预览", value: sceneProfilePreview },
        { title: "当前选中路径", value: selectedPath },
        { title: "生成候选场景", value: generatedSceneCandidate },
        { title: "已保存场景列表", value: savedScenes },
        { title: "可复用节点列表", value: reusableNodes.slice(0, 24) },
        { title: "场景生成恢复记录", value: sceneGenerateModelRecoveries },
        { title: "文本重写恢复记录", value: rewriteModelRecoveries },
      ],
    }),
    [
      generatedSceneCandidate,
      libraryError,
      reusableError,
      reusableNodes,
      rewriteModelRecoveries,
      rewriteError,
      savedScenes,
      sceneGenerateModelRecoveries,
      sceneGenerateError,
      sceneIoError,
      sceneName,
      sceneProfilePreview,
      selectedLayer,
      selectedLayerId,
      selectedPath,
    ],
  );

  usePageDebugSnapshot(debugSnapshot);

  function updateLayer(targetId: string, updater: (layer: SceneLayer) => SceneLayer) {
    updateSceneLayersState((current) => updateLayerTree(current, targetId, updater));
  }

  function parseTagList(text: string) {
    return text
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean);
  }

  async function saveLayerToReusableLibrary(layerId: string) {
    const targetLayer = findLayerById(sceneLayers, layerId);
    if (!targetLayer) {
      return;
    }
    await runReusableAction(
      targetLayer.id,
      `已将层级 "${targetLayer.title}" 加入可复用节点库。`,
      () =>
        createReusableSceneNode({
          nodeType: "layer",
          title: targetLayer.title,
          summary: targetLayer.summary,
          tags: parseTagList(targetLayer.tags),
          reuseId: targetLayer.reuseId,
          reuseHint: targetLayer.reuseHint,
          sourceSceneId: sceneProfilePreview?.sceneId ?? "",
          sourceSceneName: sceneName.trim(),
          layerNode: normalizeSceneTreeNodeForProfile(targetLayer),
        }),
    );
  }

  async function saveObjectToReusableLibrary(object: SceneObject) {
    await runReusableAction(
      object.id,
      `已将物体 "${object.name}" 加入可复用节点库。`,
      () =>
        createReusableSceneNode({
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
        }),
    );
  }

  async function deleteReusableNode(nodeId: string) {
    await runReusableAction(nodeId, "", () => deleteReusableSceneNode(nodeId));
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
        objects: [...layer.objects, cloneSceneObjectFromLibrary(objectNode)],
      }));
      setReusableMessage(`已把物体 "${item.title}" 插入到 "${selectedLayer.title}"。`);
      return;
    }
    if (item.nodeType === "layer" && layerNode) {
      updateLayer(selectedLayer.id, (layer) => ({
        ...layer,
        children: [...layer.children, cloneSceneLayerFromLibrary(layerNode)],
      }));
      setCollapsedLayerIds((current) =>
        current.filter((id) => id !== selectedLayer.id),
      );
      setReusableMessage(
        `已把层级 "${item.title}" 作为 "${selectedLayer.title}" 的子层插入。`,
      );
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
              : Math.min(
                  inferTemplateIndexFromLayer(layer) + 1,
                  LAYER_TEMPLATES.length - 1,
                ),
          ),
        ],
      })),
    );
  }

  function addObject(layerId: string) {
    const newObject = createSceneObject();
    updateLayer(layerId, (layer) => ({
      ...layer,
      objects: [...layer.objects, newObject],
    }));
    selectSceneObject(newObject.id);
    const targetId = `scene-object-editor-${layerId}-${newObject.id}`;
    globalThis.setTimeout(() => {
      const target = document.getElementById(targetId);
      target?.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }, 80);
  }

  function updateObject(
    layerId: string,
    objectId: string,
    key: keyof SceneObject,
    value: string,
  ) {
    updateLayer(layerId, (layer) => ({
      ...layer,
      objects: layer.objects.map((object) =>
        object.id === objectId ? { ...object, [key]: value } : object,
      ),
    }));
  }

  function removeObject(layerId: string, objectId: string) {
    if (selectedObjectId === objectId) {
      selectSceneObject("");
    }
    updateLayer(layerId, (layer) => ({
      ...layer,
      objects: layer.objects.filter((object) => object.id !== objectId),
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

  async function requestDeleteLayer(layerId: string, trigger: HTMLElement) {
    const layer = findLayerById(sceneLayers, layerId);
    if (!layer || !canDeleteLayerSafely(sceneLayers, layerId)) return;
    const captured = currentSceneAsyncScope();
    if (
      !(await confirm({
        title: "确认删除层级？",
        message: `即将删除“${layer.title || "当前层级"}”及其所有子层级与物体。此操作不可自动恢复。`,
        confirmLabel: "确认删除",
        danger: true,
        trigger,
        fallbackFocus: () => pageHeadingRef.current,
      }))
    )
      return;
    const current = currentSceneAsyncScope();
    if (
      current.subjectId !== captured.subjectId ||
      current.draftRevision !== captured.draftRevision
    ) {
      setSceneIoError("场景草稿已变化，请重新确认删除层级。");
      return;
    }
    deletedTrigger.current = trigger;
    removeLayer(layerId);
  }

  async function saveLibraryScene(mode: "upsert" | "create" = "upsert") {
    beginSceneIo();
    const boundScene = mode === "upsert" ? getSceneBinding() : null;
    try {
      const trimmedSceneName = sceneName.trim();
      const trimmedSceneSummary = sceneSummary.trim();
      if (!trimmedSceneName || !trimmedSceneSummary) {
        setSceneIoError("请先填写场景名称和场景摘要。");
        return;
      }
      const payload = {
        sceneName: trimmedSceneName,
        sceneSummary: trimmedSceneSummary,
        sceneLayers,
        selectedLayerId: sceneSelectionLayerId,
        collapsedLayerIds,
      };
      const diagnostic = beginDiagnosticAction();
      const draftScope = currentSceneAsyncScope("scene-save");
      const markSubmitted = () => {
        const current = currentSceneAsyncScope("scene-save");
        if (
          draftView.current.active &&
          current.subjectId === draftScope.subjectId &&
          current.draftRevision === draftScope.draftRevision
        )
          markSaved(contentFingerprint);
      };
      if (boundScene) {
        const updated = await updateSceneLibraryItem(
          boundScene.sceneId,
          {
            ...payload,
            expectedRevision: boundScene.revision,
          },
          diagnostic,
        );
        markSubmitted();
        setSceneIoMessage(`已更新已保存场景“${updated.sceneName}”。`);
        return;
      }
      const created = await createSceneLibraryItem(payload, diagnostic);
      markSubmitted();
      setSceneIoMessage(`已保存场景“${created.sceneName}”。`);
    } catch (error) {
      if (boundScene && isApiHttpError(error) && (error.status === 409 || error.status === 404)) {
        if (getSceneBinding() !== boundScene) return;
        try {
          const latest = await refreshSceneLibraryItem(boundScene.sceneId);
          if (latest && getSceneBinding() !== boundScene) return;
          setSceneIoError(latest
            ? "场景已在其他操作中更新，当前草稿仍在。可从场景库载入最新版本，或将草稿另存为新场景。"
            : "原场景已不存在，当前草稿仍在。可另存为新场景。");
        } catch {
          if (getSceneBinding() === boundScene)
            setSceneIoError("场景版本已变化，且未能读取最新版本。当前草稿仍在，可另存为新场景。");
        }
      } else {
        setSceneIoError("保存到场景库失败，请稍后重试。");
      }
    } finally {
      finishSceneIo();
    }
  }

  async function loadSavedScene(sceneId: string, trigger?: HTMLElement) {
    const target = savedScenes.find((item) => item.sceneId === sceneId);
    if (!target) {
      return;
    }
    beginSceneIo();
    try {
      const imported = parseSceneImportPayload({
        sceneName: target.sceneName,
        sceneSummary: target.sceneSummary,
        sceneLayers: target.sceneLayers,
        selectedLayerId: target.selectedLayerId,
        collapsedLayerIds: target.collapsedLayerIds,
      });
      if (!(await confirmReplaceSceneDraft("载入已保存场景", trigger))) return;
      applySceneImport(
        imported,
        `已载入场景“${target.sceneName}”。`,
        `scene-library:${target.sceneId}`,
        false,
        true,
      );
      bindScene(target);
    } catch {
      setSceneIoError(`载入场景“${target.sceneName}”时数据格式异常。`);
    } finally {
      finishSceneIo();
    }
  }

  async function deleteSavedScene(sceneId: string, trigger: HTMLElement) {
    const target = savedScenes.find((item) => item.sceneId === sceneId);
    if (!target) {
      return;
    }
    if (
      !(await confirm({
        title: "确认删除已保存场景？",
        message: `即将从场景库删除“${target.sceneName}”。此操作不可自动恢复。`,
        confirmLabel: "确认删除",
        danger: true,
        trigger,
        fallbackFocus: () => pageHeadingRef.current,
      }))
    )
      return;
    beginSceneIo();
    try {
      const deleted = await deleteSceneLibraryItem(sceneId, target.revision, () => {
        deletedTrigger.current = trigger;
      });
      if (!deleted) {
        setSceneIoError("已保存场景的版本已变化，请核对后重新确认删除。");
        return;
      }
      setSceneIoMessage(`已删除场景“${target.sceneName}”。`);
    } catch {
      setSceneIoError("删除场景失败，请稍后重试。");
    } finally {
      finishSceneIo();
    }
  }

  async function exportScene() {
    beginSceneIo();
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
      const saved = await exportJson(
        `scene-setup-${new Date().toISOString().slice(0, 19).replace(/:/g, "-")}.json`,
        payload,
      );
      setSceneIoMessage(saved ? "场景已导出为 JSON 文件。" : "已取消导出。");
    } catch {
      setSceneIoError("导出失败，请稍后重试。");
    } finally {
      finishSceneIo();
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
    beginSceneIo();
    const fieldTarget = "scene-file-import";
    const ticket = sceneImportFenceRef.current.begin(
      currentSceneAsyncScope(fieldTarget),
    );
    try {
      await observeLocalAction(
        "json_import_scene_draft",
        async (context) => {
          const value = parseSceneImportPayload(
            await readBoundedJsonImport(file, "scene", context),
            true,
          );
          if (
            sceneImportFenceRef.current.decide(
              ticket,
              currentSceneAsyncScope(fieldTarget),
            ) !== "apply" ||
            !(await confirmReplaceSceneDraft("导入文件"))
          )
            return false;
          return (
            applyAsyncResult({
              fence: sceneImportFenceRef.current,
              ticket,
              currentScope: currentSceneAsyncScope(fieldTarget),
              value,
              apply: (next) => applySceneImport(next, "场景导入成功。"),
            }) === "apply"
          );
        },
        { cancelled: (applied) => !applied },
      );
    } catch {
      if (
        sceneImportFenceRef.current.decide(
          ticket,
          currentSceneAsyncScope(fieldTarget),
        ) === "apply"
      ) {
        setSceneIoError("导入失败：文件格式不正确。");
      }
    } finally {
      finishSceneIo();
      sceneImportFenceRef.current.settle(ticket);
      event.target.value = "";
    }
  }

  async function applyGeneratedSceneCandidateToEditor(trigger: HTMLElement) {
    if (
      !generatedSceneCandidate ||
      !(await confirmReplaceSceneDraft("应用生成结果", trigger)) ||
      draftView.current.candidate !== generatedSceneCandidate
    )
      return;
    applySceneImport(
      generatedSceneCandidate,
      "已将生成场景树应用到当前编辑区。",
      "scene-editor:local",
      true,
    );
  }

  function toggleSidebarSection(key: string) {
    setCollapsedSidebarSections((prev) =>
      prev.includes(key) ? prev.filter((k) => k !== key) : [...prev, key],
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
    toggleLayerSelection(layerId);
  }

  function toggleObjectEditor(objectId: string) {
    toggleObjectSelection(objectId);
  }

  function handleSelectLayer(layerId: string) {
    selectSceneLayer(layerId);
  }

  return {
    savedScenes,
    selectedSavedSceneId,
    libraryError,
    reusableActionPendingId,
    reusableError,
    pageHeadingRef,
    reusableSearchQuery,
    setReusableSearchQuery,
    sceneLayers,
    sceneName,
    setSceneName,
    sceneSummary,
    setSceneSummary,
    selectedLayerId,
    selectedObjectId,
    collapsedLayerIds,
    toggleLayerChildren: (id: string) =>
      setCollapsedLayerIds((current) =>
        current.includes(id)
          ? current.filter((value) => value !== id)
          : [...current, id],
      ),
    updateSceneGenerationInput,
    selectedLayer,
    sceneNodeCount,
    sceneObjectCount,
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
    generatedSceneCandidate,
    handleGenerateScene,
    rewriteStrength,
    setRewriteStrength,
    rewritePendingKey,
    rewriteError,
    rewriteModelRecoveries,
    lastRewrite,
    undoLastRewrite,
    rewriteLayerField,
    rewriteObjectField,
    importInputRef,
    collapsedSidebarSections,
    isCompactLayout,
    filteredReusableNodes,
    currentCollapsedNodeEditorSections,
    pageNotice,
    sceneIoPending,
    sceneIoError,
    sceneStorageFailed,
    retrySceneStorage: flushDraft,
    updateLayer,
    saveLayerToReusableLibrary,
    saveObjectToReusableLibrary,
    deleteReusableNode,
    insertReusableNode,
    addChildLayer,
    addObject,
    updateObject,
    removeObject,
    requestDeleteLayer,
    saveLibraryScene,
    loadSavedScene,
    deleteSavedScene,
    exportScene,
    requestImportScene,
    importSceneFromFile,
    applyGeneratedSceneCandidateToEditor,
    toggleSidebarSection,
    toggleNodeEditorSection,
    toggleLayerEditor,
    toggleObjectEditor,
    handleSelectLayer,
  };
}

export type SceneWorkspaceController = ReturnType<typeof useSceneWorkspaceController>;
