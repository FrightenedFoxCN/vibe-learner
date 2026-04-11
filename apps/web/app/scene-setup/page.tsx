"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type { CSSProperties } from "react";
import type { SceneProfile } from "@vibe-learner/shared";

import { TopNav } from "../../components/top-nav";
import {
  assistPersonaSlot,
  createSceneLibraryItem,
  deleteSceneLibraryItem,
  listSceneLibrary,
  updateSceneLibraryItem,
} from "../../lib/api";

interface SceneObject {
  id: string;
  name: string;
  description: string;
  interaction: string;
  tags: string;
}

interface SceneLayer {
  id: string;
  title: string;
  scopeLabel: string;
  summary: string;
  atmosphere: string;
  rules: string;
  entrance: string;
  objects: SceneObject[];
  children: SceneLayer[];
}

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

const LAYER_TEMPLATES = [
  {
    title: "世界整体",
    scopeLabel: "宏观世界",
    summary: "学术秩序、文明规则与公共资源的总背景。",
    atmosphere: "整体气候、信息流速与社会节奏都在这里被定义。",
    rules: "所有更小的场景必须继承这里的基础物理与文化规则。",
    entrance: "从世界层出发，先决定这套知识世界如何运转。",
    objectName: "世界公告塔",
    objectDescription: "发布全域通知、考试时间与公共事件。",
    objectInteraction: "任何人都能读取；高层用户可以更新公告。",
    objectTags: "广播, 公共信息"
  },
  {
    title: "大区 / 城市群",
    scopeLabel: "区域层",
    summary: "城市之间的交通、学术资源与制度差异。",
    atmosphere: "区域节奏比世界更快，开始出现明显的知识分流。",
    rules: "不同城区共享大世界规则，但可以拥有独立的微气候与管理方式。",
    entrance: "把抽象世界压缩成一个可以被行走、穿梭和观察的区域。",
    objectName: "中继轨道站",
    objectDescription: "连接不同城市群的交通节点。",
    objectInteraction: "可在候车屏查看路线，并触发区域事件。",
    objectTags: "交通, 节点"
  },
  {
    title: "城区 / 校园街区",
    scopeLabel: "城市层",
    summary: "校园外部街区、生活设施和学习者日常活动的交界。",
    atmosphere: "开始出现人流、商店、公告栏与临时活动。",
    rules: "允许出现校园外延设施，但仍要服务于学习与到达教室的路径。",
    entrance: "这里负责把世界规则转译成可被行走的街区体验。",
    objectName: "街区导览牌",
    objectDescription: "标出教学楼、食堂、档案馆与活动广场。",
    objectInteraction: "拖动切换路线，点击可展开局部信息。",
    objectTags: "导视, 路线"
  },
  {
    title: "校园 / 教学楼",
    scopeLabel: "建筑层",
    summary: "教学楼、图书区与公共走廊构成的日常学习场景。",
    atmosphere: "声音更安静，空间更规则，互动更集中。",
    rules: "楼层内的物件、张贴与动线要服务于课堂秩序。",
    entrance: "把宏观世界收束到一栋可以上下穿行的建筑。",
    objectName: "钟楼广播器",
    objectDescription: "提醒课程开始、实验安排与楼层切换。",
    objectInteraction: "可被教师或管理员触发，也可作为时间提示。",
    objectTags: "课堂, 时间"
  },
  {
    title: "具体教室",
    scopeLabel: "微观教室",
    summary: "最终落点，承载讲台、座位、板书与局部互动细节。",
    atmosphere: "所有设定都要收敛到可直接用于对话和演示的颗粒度。",
    rules: "必须明确可见物体、可交互点位与课堂活动边界。",
    entrance: "这里是场景搭建的最后一层，也是最接近真实互动的一层。",
    objectName: "可移动课桌",
    objectDescription: "便于分组、演示与临时重排座位。",
    objectInteraction: "支持拖拽移动，触发分组讨论或走动讲解。",
    objectTags: "教室, 可交互"
  }
] as const;

function createId(prefix: string) {
  const suffix = typeof globalThis.crypto?.randomUUID === "function"
    ? globalThis.crypto.randomUUID().slice(0, 8)
    : Math.random().toString(36).slice(2, 10);
  return `${prefix}-${suffix}`;
}

function createSceneObject(name = "新物体", fixedId?: string): SceneObject {
  return {
    id: fixedId ?? createId("scene-object"),
    name,
    description: "补充这个物体在场景中的外观、状态或用途。",
    interaction: "说明学习者或角色如何与它交互。",
    tags: ""
  };
}

function createSceneLayer(templateIndex: number, childLayers: SceneLayer[] = [], fixedId?: string, fixedObjectId?: string): SceneLayer {
  const template = LAYER_TEMPLATES[templateIndex] ?? LAYER_TEMPLATES[LAYER_TEMPLATES.length - 1];
  return {
    id: fixedId ?? createId("scene-layer"),
    title: template.title,
    scopeLabel: template.scopeLabel,
    summary: template.summary,
    atmosphere: template.atmosphere,
    rules: template.rules,
    entrance: template.entrance,
    objects: [
      {
        id: fixedObjectId ?? createId("scene-object"),
        name: template.objectName,
        description: template.objectDescription,
        interaction: template.objectInteraction,
        tags: template.objectTags
      }
    ],
    children: childLayers
  };
}

const INITIAL_SCENE: SceneLayer[] = [
  createSceneLayer(0, [
    createSceneLayer(1, [
      createSceneLayer(2, [
        createSceneLayer(3, [
          createSceneLayer(4, [], "scene-classroom", "scene-classroom-object")
        ], "scene-building", "scene-building-object")
      ], "scene-campus", "scene-campus-object")
    ], "scene-district", "scene-district-object")
  ], "scene-world", "scene-world-object")
];

const SCENE_STORAGE_KEY = "vibe-learner.scene-setup.v1";

export default function SceneSetupPage() {
  const [sceneLayers, setSceneLayers] = useState<SceneLayer[]>(INITIAL_SCENE);
  const [sceneName, setSceneName] = useState("示例场景");
  const [sceneSummary, setSceneSummary] = useState("从世界整体的学术框架出发，逐层建立观察者在微观教室中的完整感受。这个示例展示了如何从宏观规则层层推导到具体互动对象。");
  const [selectedLayerId, setSelectedLayerId] = useState(INITIAL_SCENE[0]?.id ?? "");
  const [collapsedLayerIds, setCollapsedLayerIds] = useState<string[]>([]);
  const [savedScenes, setSavedScenes] = useState<import("../../lib/api").SceneLibraryItemPayload[]>([]);
  const [selectedSavedSceneId, setSelectedSavedSceneId] = useState("");
  const [rewriteStrength, setRewriteStrength] = useState(0.6);
  const [rewritePendingKey, setRewritePendingKey] = useState("");
  const [rewriteError, setRewriteError] = useState("");
  const [lastRewrite, setLastRewrite] = useState<RewriteUndoEntry | null>(null);
  const [pendingDeleteLayerId, setPendingDeleteLayerId] = useState("");
  const [sceneIoMessage, setSceneIoMessage] = useState("");
  const importInputRef = useRef<HTMLInputElement | null>(null);

  const selectedLayer = useMemo(() => findLayerById(sceneLayers, selectedLayerId), [sceneLayers, selectedLayerId]);
  const selectedPath = useMemo(() => findLayerPath(sceneLayers, selectedLayerId), [sceneLayers, selectedLayerId]);
  const sceneProfilePreview = useMemo(
    () => deriveSceneProfile(sceneLayers, selectedLayerId, sceneName.trim(), sceneSummary.trim()),
    [sceneLayers, selectedLayerId, sceneName, sceneSummary]
  );

  useEffect(() => {
    if (!selectedLayer && sceneLayers[0]?.id) {
      setSelectedLayerId(sceneLayers[0].id);
    }
  }, [sceneLayers, selectedLayer]);

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
        setSceneLayers(imported.sceneLayers);
        setSceneName(String(imported.sceneName || ""));
        setSceneSummary(String(imported.sceneSummary || ""));
        const knownIds = new Set(collectLayerIds(imported.sceneLayers));
        const preferredId = imported.selectedLayerId && knownIds.has(imported.selectedLayerId)
          ? imported.selectedLayerId
          : imported.sceneLayers[0]?.id ?? "";
        setSelectedLayerId(preferredId);
        setCollapsedLayerIds(imported.collapsedLayerIds.filter((id) => knownIds.has(id)));
        setSceneIoMessage("已加载本地保存场景。");
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

  useEffect(() => {
    let active = true;
    const hydrateLibrary = async () => {
      try {
        const items = await listSceneLibrary();
        if (!active) {
          return;
        }
        setSavedScenes(items);
        if (!selectedSavedSceneId && items[0]) {
          setSelectedSavedSceneId(items[0].sceneId);
        }
      } catch {
        if (active) {
          setSavedScenes([]);
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
        selectedLayerId,
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
  }, [sceneLayers, sceneName, sceneSummary, selectedLayerId, collapsedLayerIds]);

  function updateLayer(targetId: string, updater: (layer: SceneLayer) => SceneLayer) {
    setSceneLayers((current) => updateLayerTree(current, targetId, updater));
  }

  function addChildLayer(parentId: string) {
    setSceneLayers((current) =>
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
    updateLayer(layerId, (layer) => ({
      ...layer,
      objects: [...layer.objects, createSceneObject()]
    }));
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
    updateLayer(layerId, (layer) => ({
      ...layer,
      objects: layer.objects.filter((object) => object.id !== objectId)
    }));
  }

  function removeLayer(layerId: string) {
    setSceneLayers((current) => {
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

  function toggleLayerCollapsed(layerId: string) {
    setCollapsedLayerIds((current) =>
      current.includes(layerId)
        ? current.filter((id) => id !== layerId)
        : [...current, layerId]
    );
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
      const sceneProfile = deriveSceneProfile(sceneLayers, selectedLayerId, trimmedSceneName, trimmedSceneSummary);
      const payload = {
        sceneName: trimmedSceneName,
        sceneSummary: trimmedSceneSummary,
        sceneLayers,
        selectedLayerId,
        collapsedLayerIds,
        sceneProfile: sceneProfile ?? null,
      };
      if (mode === "upsert" && selectedSavedSceneId) {
        const updated = await updateSceneLibraryItem(selectedSavedSceneId, payload);
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
      const knownIds = new Set(collectLayerIds(imported.sceneLayers));
      setSceneLayers(imported.sceneLayers);
      setSceneName(String(imported.sceneName || ""));
      setSceneSummary(String(imported.sceneSummary || ""));
      setSelectedLayerId(
        imported.selectedLayerId && knownIds.has(imported.selectedLayerId)
          ? imported.selectedLayerId
          : imported.sceneLayers[0]?.id ?? ""
      );
      setCollapsedLayerIds(imported.collapsedLayerIds.filter((id) => knownIds.has(id)));
      setSelectedSavedSceneId(target.sceneId);
      setSceneIoMessage(`已载入场景”${target.sceneName}”。`);
    } catch {
      setSceneIoMessage(`载入场景”${target.sceneName}”时数据格式异常。`);
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

  function exportScene() {
    try {
      const payload = {
        version: 1,
        exportedAt: new Date().toISOString(),
        sceneName,
        sceneSummary,
        sceneLayers,
        selectedLayerId,
        collapsedLayerIds,
      };
      const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `scene-setup-${new Date().toISOString().slice(0, 19).replace(/:/g, "-")}.json`;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
      setSceneIoMessage("场景已导出为 JSON 文件。");
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
    try {
      const content = await file.text();
      const parsed = JSON.parse(content);
      const imported = parseSceneImportPayload(parsed);
      const knownIds = new Set(collectLayerIds(imported.sceneLayers));
      setSceneLayers(imported.sceneLayers);
      setSceneName(String(imported.sceneName || ""));
      setSceneSummary(String(imported.sceneSummary || ""));
      setSelectedLayerId(
        imported.selectedLayerId && knownIds.has(imported.selectedLayerId)
          ? imported.selectedLayerId
          : imported.sceneLayers[0]?.id ?? ""
      );
      setCollapsedLayerIds(imported.collapsedLayerIds.filter((id) => knownIds.has(id)));
      setSceneIoMessage("场景导入成功。");
    } catch {
      setSceneIoMessage("导入失败：文件格式不正确。");
    } finally {
      event.target.value = "";
    }
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
    setRewriteError("");
    setRewritePendingKey(pendingKey);
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
      updateLayer(layerId, (currentLayer) => ({
        ...currentLayer,
        [field]: result.slot.content
      }));
      setLastRewrite({
        kind: "layer",
        key: pendingKey,
        label,
        layerId,
        field,
        previousValue
      });
    } catch (error) {
      setRewriteError(String(error));
    } finally {
      setRewritePendingKey("");
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
    setRewriteError("");
    setRewritePendingKey(pendingKey);
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
      updateObject(layerId, objectId, field, result.slot.content);
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
      setRewriteError(String(error));
    } finally {
      setRewritePendingKey("");
    }
  }

  return (
    <main className="with-app-nav" style={styles.page}>
      <div style={styles.workspaceShell}>
        <div style={styles.mainColumn}>
          <TopNav currentPath="/scene-setup" />
          <div style={styles.heading}>
            <h1 style={styles.pageTitle}>场景搭建</h1>
            <p style={styles.pageDesc}>从世界整体一路搭到具体教室。每一层都可以写设定、补互动物体，并把层级之间的过渡关系说明清楚。先选层级，再在右侧补细节。</p>
          </div>

          <section style={styles.editorShell}>
            <div style={styles.treePane}>
          <div style={styles.panelHead}>
            <span style={styles.panelTitle}>层级结构</span>
          </div>
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
                collapsedLayerIds={collapsedLayerIds}
                onSelect={setSelectedLayerId}
                onToggleCollapse={toggleLayerCollapsed}
                onAddChild={addChildLayer}
                onAddObject={addObject}
                onDeleteLayer={requestDeleteLayer}
                canDeleteLayerForId={(layerId) => canDeleteLayerSafely(sceneLayers, layerId)}
              />
            ))}
          </div>
        </div>

        <aside style={styles.editorPane}>
          <div style={styles.panelHead}>
            <span style={styles.panelTitle}>层级编辑器</span>
          </div>

          {selectedLayer ? (
            <>
              <div style={styles.pathChipRow}>
                {selectedPath.map((segment, index) => (
                  <span key={`${segment}-${index}`} style={styles.pathChip}>{segment}</span>
                ))}
              </div>

              <div style={styles.rewriteControlRow}>
                <label style={styles.rewriteControlLabel}>AI 重写强度 {(rewriteStrength * 100).toFixed(0)}%</label>
                <input
                  style={styles.rewriteSlider}
                  type="range"
                  min={0.05}
                  max={1}
                  step={0.05}
                  value={rewriteStrength}
                  onChange={(event) => setRewriteStrength(Number(event.target.value))}
                />
                {lastRewrite ? (
                  <button
                    type="button"
                    style={styles.btnSmall}
                    onClick={undoLastRewrite}
                    disabled={Boolean(rewritePendingKey)}
                  >
                    撤销重写（{lastRewrite.label}）
                  </button>
                ) : null}
                {rewriteError ? <span style={styles.errorText}>{rewriteError}</span> : null}
              </div>

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
                  <span style={styles.fieldLabelRow}>
                    <span style={styles.fieldLabel}>层级总述</span>
                    <button
                      type="button"
                      style={styles.btnSmall}
                      onClick={() => void rewriteLayerField(selectedLayer.id, "summary", "层级总述")}
                      disabled={Boolean(rewritePendingKey)}
                    >
                      {rewritePendingKey === `${selectedLayer.id}:summary` ? "AI 重写中…" : "AI 重写"}
                    </button>
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
                    <button
                      type="button"
                      style={styles.btnSmall}
                      onClick={() => void rewriteLayerField(selectedLayer.id, "atmosphere", "氛围与感知")}
                      disabled={Boolean(rewritePendingKey)}
                    >
                      {rewritePendingKey === `${selectedLayer.id}:atmosphere` ? "AI 重写中…" : "AI 重写"}
                    </button>
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
                    <button
                      type="button"
                      style={styles.btnSmall}
                      onClick={() => void rewriteLayerField(selectedLayer.id, "entrance", "进入方式 / 过渡")}
                      disabled={Boolean(rewritePendingKey)}
                    >
                      {rewritePendingKey === `${selectedLayer.id}:entrance` ? "AI 重写中…" : "AI 重写"}
                    </button>
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
                    <button
                      type="button"
                      style={styles.btnSmall}
                      onClick={() => void rewriteLayerField(selectedLayer.id, "rules", "层级规则")}
                      disabled={Boolean(rewritePendingKey)}
                    >
                      {rewritePendingKey === `${selectedLayer.id}:rules` ? "AI 重写中…" : "AI 重写"}
                    </button>
                  </span>
                  <textarea
                    style={styles.textarea}
                    value={selectedLayer.rules}
                    onChange={(event) => updateLayer(selectedLayer.id, (layer) => ({ ...layer, rules: event.target.value }))}
                  />
                </label>
              </div>

              <div style={styles.objectsSection}>
                <div style={styles.objectsHead}>
                  <div>
                    <p style={styles.objectsTitle}>可互动物体</p>
                    <p style={styles.objectsHint}>在当前层级里继续补充可见、可触发、可移动或可交谈的对象。</p>
                  </div>
                  <button type="button" style={styles.btnPrimary} onClick={() => addObject(selectedLayer.id)}>
                    添加物体
                  </button>
                </div>

                <div style={styles.objectList}>
                  {selectedLayer.objects.map((object) => (
                    <article key={object.id} style={styles.objectCard}>
                      <div style={styles.objectRow}>
                        <label style={styles.compactField}>
                          <span style={styles.fieldLabel}>物体名称</span>
                          <input
                            style={styles.input}
                            value={object.name}
                            onChange={(event) => updateObject(selectedLayer.id, object.id, "name", event.target.value)}
                          />
                        </label>
                        <button type="button" style={styles.btnGhost} onClick={() => removeObject(selectedLayer.id, object.id)}>
                          删除
                        </button>
                      </div>

                      <label style={styles.fieldGroup}>
                        <span style={styles.fieldLabelRow}>
                          <span style={styles.fieldLabel}>外观 / 说明</span>
                          <button
                            type="button"
                            style={styles.btnSmall}
                            onClick={() => void rewriteObjectField(selectedLayer.id, object.id, "description", "物体外观与说明")}
                            disabled={Boolean(rewritePendingKey)}
                          >
                            {rewritePendingKey === `${selectedLayer.id}:${object.id}:description` ? "AI 重写中…" : "AI 重写"}
                          </button>
                        </span>
                        <textarea
                          style={styles.textarea}
                          value={object.description}
                          onChange={(event) => updateObject(selectedLayer.id, object.id, "description", event.target.value)}
                        />
                      </label>

                      <label style={styles.fieldGroup}>
                        <span style={styles.fieldLabelRow}>
                          <span style={styles.fieldLabel}>交互方式</span>
                          <button
                            type="button"
                            style={styles.btnSmall}
                            onClick={() => void rewriteObjectField(selectedLayer.id, object.id, "interaction", "物体交互方式")}
                            disabled={Boolean(rewritePendingKey)}
                          >
                            {rewritePendingKey === `${selectedLayer.id}:${object.id}:interaction` ? "AI 重写中…" : "AI 重写"}
                          </button>
                        </span>
                        <textarea
                          style={styles.textarea}
                          value={object.interaction}
                          onChange={(event) => updateObject(selectedLayer.id, object.id, "interaction", event.target.value)}
                        />
                      </label>

                      <label style={styles.fieldGroup}>
                        <span style={styles.fieldLabel}>标签</span>
                        <input
                          style={styles.input}
                          value={object.tags}
                          onChange={(event) => updateObject(selectedLayer.id, object.id, "tags", event.target.value)}
                        />
                      </label>
                    </article>
                  ))}
                </div>
              </div>

              <div style={styles.editorActions}>
                <button type="button" style={styles.btnGhost} onClick={() => addChildLayer(selectedLayer.id)}>
                  新增下级层级
                </button>
                <button
                  type="button"
                  style={styles.btnGhost}
                  onClick={() => requestDeleteLayer(selectedLayer.id)}
                  disabled={!canDeleteLayerSafely(sceneLayers, selectedLayer.id)}
                >
                  删除当前层级
                </button>
                <span style={styles.helperText}>下级层级会沿用当前层级的语义，再根据更细粒度的空间做收敛。</span>
              </div>
            </>
          ) : (
            <p style={styles.emptyState}>选择一个层级后，这里会显示它的设定、对象和子层级操作。</p>
          )}
        </aside>
          </section>
        </div>

        <aside style={styles.sidebarPane}>
          {sceneIoMessage && <p style={styles.sidebarStatusMsg}>{sceneIoMessage}</p>}

              <div style={styles.sidebarSection}>
                <span style={styles.panelTitle}>当前草稿</span>
                <label style={styles.sceneNameLabel}>
                  <span style={styles.fieldLabel}>场景名称</span>
                  <input
                    style={styles.sceneNameInput}
                    value={sceneName}
                    onChange={(event) => setSceneName(event.target.value)}
                    placeholder="例如：高一物理-力学基础"
                  />
                </label>
                <label style={styles.sceneSummaryLabel}>
                  <span style={styles.fieldLabel}>场景 summary</span>
                  <textarea
                    style={styles.sceneSummaryInput}
                    value={sceneSummary}
                    onChange={(event) => setSceneSummary(event.target.value)}
                    placeholder="用自己的话描述这个场景。"
                  />
                </label>
              </div>

              <div style={styles.sidebarSection}>
                <span style={styles.panelTitle}>场景库 / 导入 / 导出</span>
                <div style={styles.sceneActionButtons}>
                  <button type="button" style={styles.btnPrimary} onClick={() => void saveLibraryScene("upsert")}>
                    {selectedSavedSceneId ? "更新已保存场景" : "保存到场景库"}
                  </button>
                  <button
                    type="button"
                    style={styles.btnGhost}
                    onClick={() => void saveLibraryScene("create")}
                  >
                    另存为新场景
                  </button>
                </div>
                <div style={styles.sceneActionButtons}>
                  <button type="button" style={styles.btnGhost} onClick={requestImportScene}>导入 JSON</button>
                  <button type="button" style={styles.btnGhost} onClick={exportScene}>导出 JSON</button>
                </div>
              </div>

              <div style={{ ...styles.sidebarSection, flex: 1, overflowY: "auto", minHeight: 0 }}>
                <span style={styles.panelTitle}>已保存场景</span>
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
                          <div style={styles.savedSceneActions}>
                            <button type="button" style={styles.btnSmall} onClick={() => void loadSavedScene(item.sceneId)}>载入</button>
                            <button type="button" style={styles.btnSmall} onClick={() => setSelectedSavedSceneId(item.sceneId)}>作为更新目标</button>
                            <button type="button" style={styles.btnSmallDanger} onClick={() => void deleteSavedScene(item.sceneId)}>删除</button>
                          </div>
                        </div>
                      );
                    })}
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
  collapsedLayerIds,
  onSelect,
  onToggleCollapse,
  onAddChild,
  onAddObject,
  onDeleteLayer,
  canDeleteLayerForId
}: {
  layer: SceneLayer;
  index: number;
  selectedLayerId: string;
  collapsedLayerIds: string[];
  onSelect: (layerId: string) => void;
  onToggleCollapse: (layerId: string) => void;
  onAddChild: (layerId: string) => void;
  onAddObject: (layerId: string) => void;
  onDeleteLayer: (layerId: string) => void;
  canDeleteLayerForId: (layerId: string) => boolean;
}) {
  const isSelected = layer.id === selectedLayerId;
  const isCollapsed = collapsedLayerIds.includes(layer.id);
  const hasChildren = layer.children.length > 0;
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

        <p style={styles.layerSummary}>{layer.summary}</p>

        <div style={styles.objectChipRow}>
          {layer.objects.slice(0, 3).map((object) => (
            <span key={object.id} style={styles.objectChip}>{object.name}</span>
          ))}
          {layer.objects.length > 3 ? <span style={styles.objectChip}>+{layer.objects.length - 3}</span> : null}
        </div>

        <div style={styles.cardActions}>
          <button type="button" style={styles.btnMicro} onClick={(event) => { event.stopPropagation(); onAddObject(layer.id); }}>
            添加物体
          </button>
          <button type="button" style={styles.btnMicro} onClick={(event) => { event.stopPropagation(); onAddChild(layer.id); }}>
            添加子层
          </button>
          <button
            type="button"
            style={styles.btnMicro}
            onClick={(event) => { event.stopPropagation(); onToggleCollapse(layer.id); }}
            disabled={!hasChildren}
          >
            {isCollapsed ? "展开子树" : "收起子树"}
          </button>
          <button
            type="button"
            style={styles.btnMicro}
            onClick={(event) => { event.stopPropagation(); onDeleteLayer(layer.id); }}
            disabled={!canDeleteLayerForId(layer.id)}
          >
            删除层级
          </button>
        </div>
      </article>

      {hasChildren && !isCollapsed ? (
        <div style={styles.childStack}>
          {layer.children.map((child, childIndex) => (
            <SceneLayerCard
              key={child.id}
              layer={child}
              index={childIndex}
              selectedLayerId={selectedLayerId}
              collapsedLayerIds={collapsedLayerIds}
              onSelect={onSelect}
              onToggleCollapse={onToggleCollapse}
              onAddChild={onAddChild}
              onAddObject={onAddObject}
              onDeleteLayer={onDeleteLayer}
              canDeleteLayerForId={canDeleteLayerForId}
            />
          ))}
        </div>
      ) : null}
    </div>
  );
}

function deriveSceneProfile(
  layers: SceneLayer[],
  selectedLayerId: string,
  sceneName: string,
  sceneSummary: string,
): SceneProfile | undefined {
  if (!layers.length) {
    return undefined;
  }
  const selectedPath = findLayerPath(layers, selectedLayerId);
  const selectedLayer = findLayerById(layers, selectedLayerId) ?? layers[0];
  const normalizedPath = selectedPath.length ? selectedPath : [selectedLayer.title || "学习场景"];
  const focusObjects = selectedLayer.objects
    .slice(0, 4)
    .map((item) => item.name.trim())
    .filter(Boolean);
  const tags = selectedLayer.objects
    .flatMap((item) => item.tags.split(","))
    .map((item) => item.trim())
    .filter(Boolean)
    .slice(0, 8);
  const summary = sceneSummary.trim();

  return {
    sceneName,
    sceneId: selectedLayer.id,
    title: selectedLayer.title || normalizedPath[normalizedPath.length - 1] || "默认教室",
    summary,
    tags,
    selectedPath: normalizedPath,
    focusObjectNames: focusObjects,
    sceneTree: layers.map((layer) => normalizeSceneTreeNodeForProfile(layer)),
  };
}

function normalizeSceneTreeNodeForProfile(layer: SceneLayer): import("@vibe-learner/shared").SceneTreeNode {
  return {
    id: layer.id,
    title: layer.title,
    scopeLabel: layer.scopeLabel,
    summary: layer.summary,
    atmosphere: layer.atmosphere,
    rules: layer.rules,
    entrance: layer.entrance,
    objects: layer.objects.map((object) => ({
      id: object.id,
      name: object.name,
      description: object.description,
      interaction: object.interaction,
      tags: object.tags,
    })),
    children: layer.children.map((child) => normalizeSceneTreeNodeForProfile(child)),
  };
}

function countSceneNodes(nodes: import("@vibe-learner/shared").SceneTreeNode[]): number {
  return nodes.reduce((count, node) => count + 1 + countSceneNodes(node.children), 0);
}

function removeLayerTree(layers: SceneLayer[], targetId: string): SceneLayer[] {
  return layers
    .filter((layer) => layer.id !== targetId)
    .map((layer) => ({
      ...layer,
      children: removeLayerTree(layer.children, targetId)
    }));
}

function canDeleteLayerSafely(layers: SceneLayer[], targetId: string): boolean {
  const next = removeLayerTree(layers, targetId);
  return next.length > 0;
}

function collectLayerIds(layers: SceneLayer[]): string[] {
  const result: string[] = [];
  const stack = [...layers];
  while (stack.length) {
    const layer = stack.pop();
    if (!layer) {
      continue;
    }
    result.push(layer.id);
    stack.push(...layer.children);
  }
  return result;
}

function parseSceneImportPayload(input: unknown): {
  sceneName: string;
  sceneSummary: string;
  sceneLayers: SceneLayer[];
  selectedLayerId: string;
  collapsedLayerIds: string[];
} {
  const container = input as {
    sceneName?: unknown;
    scene_name?: unknown;
    sceneSummary?: unknown;
    scene_summary?: unknown;
    sceneLayers?: unknown;
    scene_layers?: unknown;
    selectedLayerId?: unknown;
    selected_layer_id?: unknown;
    collapsedLayerIds?: unknown;
    collapsed_layer_ids?: unknown;
  };
  const rawLayers = Array.isArray(input)
    ? input
    : Array.isArray(container.sceneLayers)
      ? container.sceneLayers
      : Array.isArray(container.scene_layers)
        ? container.scene_layers
      : null;
  if (!rawLayers?.length) {
    throw new Error("invalid_scene_layers");
  }
  const sceneLayers = rawLayers.map((entry) => normalizeSceneLayer(entry));
  const selectedLayerId = typeof container.selectedLayerId === "string"
    ? container.selectedLayerId
    : typeof container.selected_layer_id === "string"
      ? container.selected_layer_id
      : "";
  const collapsedLayerIds = Array.isArray(container.collapsedLayerIds)
    ? container.collapsedLayerIds.filter((value): value is string => typeof value === "string")
    : Array.isArray(container.collapsed_layer_ids)
      ? container.collapsed_layer_ids.filter((value): value is string => typeof value === "string")
    : [];

  return {
    sceneName: typeof container.sceneName === "string"
      ? container.sceneName
      : typeof container.scene_name === "string"
        ? container.scene_name
        : "",
    sceneSummary: typeof container.sceneSummary === "string"
      ? container.sceneSummary
      : typeof container.scene_summary === "string"
        ? container.scene_summary
        : "",
    sceneLayers,
    selectedLayerId,
    collapsedLayerIds,
  };
}

function normalizeSceneLayer(input: unknown): SceneLayer {
  const record = (input ?? {}) as Record<string, unknown>;
  const rawObjects = Array.isArray(record.objects) ? record.objects : [];
  const rawChildren = Array.isArray(record.children) ? record.children : [];

  return {
    id: typeof record.id === "string" && record.id ? record.id : createId("scene-layer"),
    title: typeof record.title === "string" ? record.title : "未命名层级",
    scopeLabel: typeof record.scopeLabel === "string"
      ? record.scopeLabel
      : typeof record.scope_label === "string"
        ? record.scope_label
        : "未定义范围",
    summary: typeof record.summary === "string" ? record.summary : "",
    atmosphere: typeof record.atmosphere === "string" ? record.atmosphere : "",
    rules: typeof record.rules === "string" ? record.rules : "",
    entrance: typeof record.entrance === "string" ? record.entrance : "",
    objects: rawObjects.map((entry) => normalizeSceneObject(entry)),
    children: rawChildren.map((entry) => normalizeSceneLayer(entry)),
  };
}

function normalizeSceneObject(input: unknown): SceneObject {
  const record = (input ?? {}) as Record<string, unknown>;
  return {
    id: typeof record.id === "string" && record.id ? record.id : createId("scene-object"),
    name: typeof record.name === "string" ? record.name : "未命名物体",
    description: typeof record.description === "string" ? record.description : "",
    interaction: typeof record.interaction === "string" ? record.interaction : "",
    tags: typeof record.tags === "string" ? record.tags : "",
  };
}

function updateLayerTree(layers: SceneLayer[], targetId: string, updater: (layer: SceneLayer) => SceneLayer): SceneLayer[] {
  return layers.map((layer) => {
    if (layer.id === targetId) {
      return updater(layer);
    }
    return {
      ...layer,
      children: updateLayerTree(layer.children, targetId, updater)
    };
  });
}

function findLayerById(layers: SceneLayer[], targetId: string): SceneLayer | null {
  for (const layer of layers) {
    if (layer.id === targetId) {
      return layer;
    }
    const childMatch = findLayerById(layer.children, targetId);
    if (childMatch) {
      return childMatch;
    }
  }
  return null;
}

function findLayerPath(layers: SceneLayer[], targetId: string, trail: string[] = []): string[] {
  for (const layer of layers) {
    const nextTrail = [...trail, layer.title];
    if (layer.id === targetId) {
      return nextTrail;
    }
    const childTrail = findLayerPath(layer.children, targetId, nextTrail);
    if (childTrail.length) {
      return childTrail;
    }
  }
  return [];
}

function inferTemplateIndexFromLayer(layer: SceneLayer): number {
  const exactMatch = LAYER_TEMPLATES.findIndex(
    (template) => template.title === layer.title && template.scopeLabel === layer.scopeLabel
  );
  if (exactMatch >= 0) {
    return exactMatch;
  }
  const titleMatch = LAYER_TEMPLATES.findIndex((template) => template.title === layer.title);
  if (titleMatch >= 0) {
    return titleMatch;
  }
  return 0;
}

const styles: Record<string, CSSProperties> = {
  // ── page shell ────────────────────────────────────────────
  page: {
    minHeight: "100vh",
    maxWidth: 1460,
    margin: "0 auto",
    padding: 0,
  },
  workspaceShell: {
    display: "grid",
    gridTemplateColumns: "minmax(0, 1fr) 300px",
    alignItems: "stretch",
    minHeight: "100vh",
  },
  mainColumn: {
    display: "grid",
    alignContent: "start",
    minHeight: "100vh",
  },
  heading: {
    display: "grid",
    gap: 4,
    padding: "16px 24px 12px",
    borderBottom: "1px solid var(--border)",
  },
  editorShell: {
    display: "grid",
    gridTemplateColumns: "minmax(280px, 1fr) minmax(0, 1.6fr)",
    alignItems: "start",
    minHeight: "calc(100vh - 120px)",
  },
  pageTitle: {
    margin: 0,
    fontSize: 18,
    fontWeight: 700,
    color: "var(--ink)",
    lineHeight: 1.2,
  },
  pageDesc: {
    margin: 0,
    fontSize: 13,
    color: "var(--muted)",
    lineHeight: 1.6,
  },
  // ── sidebar fields ────────────────────────────────────────
  sceneNameLabel: { display: "grid", gap: 6 },
  sceneSummaryLabel: { display: "grid", gap: 6 },
  sceneNameInput: {
    width: "100%",
    border: "1px solid var(--border)",
    padding: "7px 10px",
    background: "var(--panel)",
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
    background: "var(--panel)",
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
    border: "1px solid var(--border)",
    background: "var(--panel)",
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
  sidebarPane: { borderLeft: "1px solid var(--border)", display: "flex", flexDirection: "column", position: "sticky", top: 0, height: "100vh" },
  sidebarSection: {
    padding: "14px 16px",
    borderBottom: "1px solid var(--border)",
    display: "grid",
    gap: 10,
    alignContent: "start",
    justifyItems: "stretch",
  },
  sidebarStatusMsg: { margin: 0, padding: "8px 16px", fontSize: 12, color: "var(--muted)", borderBottom: "1px solid var(--border)" },
  treePane: { padding: "16px 20px", display: "grid", gap: 14, alignContent: "start" },
  editorPane: { borderLeft: "1px solid var(--border)", padding: "16px 20px", display: "grid", gap: 16, alignContent: "start", position: "sticky", top: 0 },
  panelHead: { paddingBottom: 10, borderBottom: "1px solid var(--border)", display: "grid", gap: 3 },
  panelTitle: { fontSize: 11, fontWeight: 700, color: "var(--muted)", textTransform: "uppercase", letterSpacing: "0.06em" },
  hiddenInput: { display: "none" },
  treeStack: { display: "grid", gap: 8 },
  cardGroup: { display: "grid", gap: 6 },
  layerCard: { borderWidth: 1, borderStyle: "solid", borderColor: "var(--border)", background: "var(--panel)", padding: 12, display: "grid", gap: 8, cursor: "pointer" },
  layerCardActive: { borderColor: "var(--accent)", boxShadow: "0 0 0 2px var(--accent-soft) inset" },
  layerTopRow: { display: "flex", alignItems: "flex-start", gap: 8 },
  layerIndexBadge: { width: 22, height: 22, background: "var(--accent)", color: "#fff", display: "grid", placeItems: "center", fontSize: 10, fontWeight: 800, letterSpacing: "0.06em", flexShrink: 0 },
  layerHeadCopy: { display: "grid", gap: 2, minWidth: 0 },
  layerScope: { fontSize: 10, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.07em", color: "var(--muted)" },
  layerTitle: { margin: 0, fontSize: 13, fontWeight: 600, color: "var(--ink)", lineHeight: 1.2 },
  layerSummary: { margin: 0, fontSize: 12, lineHeight: 1.5, color: "var(--muted)" },
  objectChipRow: { display: "flex", flexWrap: "wrap", gap: 4 },
  objectChip: { padding: "2px 6px", border: "1px solid var(--border)", background: "var(--bg)", fontSize: 10, color: "var(--muted)" },
  cardActions: { display: "flex", flexWrap: "wrap", gap: 4 },
  childStack: { paddingLeft: 12, borderLeft: "2px solid var(--border)", display: "grid", gap: 6 },
  pathChipRow: { display: "flex", flexWrap: "wrap", gap: 4 },
  pathChip: { padding: "2px 6px", background: "var(--panel)", border: "1px solid var(--border)", fontSize: 11, color: "var(--muted)" },
  rewriteControlRow: { display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8, paddingBottom: 4, borderBottom: "1px solid var(--border)" },
  rewriteControlLabel: { fontSize: 11, color: "var(--muted)" },
  rewriteSlider: { width: 80, flexShrink: 0 },
  formGrid: { display: "grid", gap: 12 },
  fieldGroup: { display: "grid", gap: 6 },
  compactField: { display: "grid", gap: 6, flex: 1 },
  fieldLabel: { fontSize: 11, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.07em", color: "var(--muted)" },
  fieldLabelRow: { display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8 },
  input: { width: "100%", height: 36, border: "1px solid var(--border)", background: "var(--panel)", padding: "0 10px", color: "var(--ink)", fontSize: 13, outline: "none" },
  textarea: { width: "100%", minHeight: 72, border: "1px solid var(--border)", background: "var(--panel)", padding: "8px 10px", color: "var(--ink)", fontSize: 13, lineHeight: 1.6, resize: "vertical", outline: "none" },
  objectsSection: { display: "grid", gap: 10 },
  objectsHead: { display: "flex", justifyContent: "space-between", gap: 10, alignItems: "center" },
  objectsTitle: { margin: 0, fontSize: 13, fontWeight: 600, color: "var(--ink)" },
  objectsHint: { margin: "2px 0 0", fontSize: 12, lineHeight: 1.5, color: "var(--muted)" },
  objectList: { display: "grid", gap: 8 },
  objectCard: { padding: 12, border: "1px solid var(--border)", background: "var(--panel)", display: "grid", gap: 10 },
  objectRow: { display: "flex", alignItems: "end", gap: 10 },
  editorActions: { display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap", paddingTop: 4, borderTop: "1px solid var(--border)" },
  helperText: { fontSize: 12, color: "var(--muted)" },
  emptyState: { margin: 0, padding: "20px 0", color: "var(--muted)", lineHeight: 1.7, fontSize: 13 },
  errorText: { fontSize: 12, color: "var(--danger, #b42318)", lineHeight: 1.5 },
  btnPrimary: { border: "none", background: "var(--accent)", color: "white", height: 34, padding: "0 14px", fontWeight: 600, cursor: "pointer", fontSize: 13, flexShrink: 0, display: "inline-flex", alignItems: "center" },
  btnGhost: { border: "1px solid var(--border)", background: "transparent", color: "var(--ink)", height: 34, padding: "0 12px", cursor: "pointer", fontSize: 13, flexShrink: 0, display: "inline-flex", alignItems: "center" },
  btnDanger: { border: "none", background: "var(--danger, #b42318)", color: "white", height: 34, padding: "0 12px", cursor: "pointer", fontSize: 13, fontWeight: 600, display: "inline-flex", alignItems: "center" },
  btnSmall: { border: "1px solid var(--border)", background: "transparent", color: "var(--muted)", height: 26, padding: "0 8px", cursor: "pointer", fontSize: 11, display: "inline-flex", alignItems: "center", flexShrink: 0 },
  btnSmallDanger: { border: "1px solid var(--danger, #b42318)", background: "transparent", color: "var(--danger, #b42318)", height: 26, padding: "0 8px", cursor: "pointer", fontSize: 11, display: "inline-flex", alignItems: "center" },
  btnMicro: { border: "1px solid var(--border)", background: "transparent", color: "var(--muted)", padding: "1px 6px", fontSize: 11, cursor: "pointer", height: 22, display: "inline-flex", alignItems: "center" },
  confirmOverlay: { position: "fixed", inset: 0, background: "rgba(15, 23, 42, 0.35)", display: "grid", placeItems: "center", zIndex: 30, padding: 16 },
  confirmDialog: { width: "min(480px, 100%)", background: "white", border: "1px solid var(--border)", display: "grid", gap: 12, padding: 20, boxShadow: "0 14px 28px rgba(15, 23, 42, 0.12)" },
  confirmTitle: { margin: 0, fontSize: 15, fontWeight: 700, color: "var(--ink)" },
  confirmText: { margin: 0, fontSize: 13, lineHeight: 1.6, color: "var(--muted)" },
  confirmActions: { display: "flex", justifyContent: "flex-end", gap: 8 },
};
