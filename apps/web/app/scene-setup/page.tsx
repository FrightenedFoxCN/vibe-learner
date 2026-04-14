"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type { CSSProperties, MouseEvent as ReactMouseEvent, ReactNode } from "react";
import type { ModelRecovery, SceneProfile } from "@vibe-learner/shared";

import { MaterialIcon, type MaterialIconName } from "../../components/material-icon";
import { TopNav } from "../../components/top-nav";
import { usePageDebugSnapshot } from "../../components/page-debug-context";
import { assistPersonaSlot } from "../../lib/data/personas";
import {
  createReusableSceneNode,
  createSceneLibraryItem,
  deleteReusableSceneNode,
  deleteSceneLibraryItem,
  generateSceneTree,
  listReusableSceneNodes,
  listSceneLibrary,
  type ReusableSceneNodePayload,
  type SceneLibraryItemPayload,
  updateSceneLibraryItem,
} from "../../lib/data/scenes";

interface SceneObject {
  id: string;
  name: string;
  description: string;
  interaction: string;
  tags: string;
  reuseId: string;
  reuseHint: string;
}

interface SceneLayer {
  id: string;
  title: string;
  scopeLabel: string;
  summary: string;
  atmosphere: string;
  rules: string;
  entrance: string;
  tags: string;
  reuseId: string;
  reuseHint: string;
  objects: SceneObject[];
  children: SceneLayer[];
}

interface SceneImportPayload {
  sceneName: string;
  sceneSummary: string;
  sceneLayers: SceneLayer[];
  selectedLayerId: string;
  collapsedLayerIds: string[];
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

function createStableSceneToken(seed: string, prefix: string) {
  let value = 0;
  for (const char of seed) {
    value = ((value * 131) + char.charCodeAt(0)) >>> 0;
  }
  return `${prefix}-${value.toString(16).padStart(8, "0")}`;
}

function defaultLayerReuseId(title: string, scopeLabel: string) {
  return createStableSceneToken(`${title}:${scopeLabel}`, "scene-layer-reuse");
}

function defaultObjectReuseId(name: string, tags = "") {
  return createStableSceneToken(`${name}:${tags}`, "scene-object-reuse");
}

function createSceneObject(name = "新物体", fixedId?: string): SceneObject {
  return {
    id: fixedId ?? createId("scene-object"),
    name,
    description: "补充这个物体在场景中的外观、状态或用途。",
    interaction: "说明学习者或角色如何与它交互。",
    tags: "",
    reuseId: defaultObjectReuseId(name),
    reuseHint: `可复用为“${name}”这一类交互物体。`
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
    tags: `${template.scopeLabel},可复用节点`,
    reuseId: defaultLayerReuseId(template.title, template.scopeLabel),
    reuseHint: `可复用为“${template.title}”这一层场景模板，保留其规则、氛围和进入方式。`,
    objects: [
      {
        id: fixedObjectId ?? createId("scene-object"),
        name: template.objectName,
        description: template.objectDescription,
        interaction: template.objectInteraction,
        tags: template.objectTags,
        reuseId: defaultObjectReuseId(template.objectName, template.objectTags),
        reuseHint: `可复用为“${template.objectName}”这一类核心交互物体。`
      }
    ],
    children: childLayers
  };
}

function cloneSceneObjectFromLibrary(
  object: Pick<SceneObject, "name" | "description" | "interaction" | "tags" | "reuseId" | "reuseHint">
): SceneObject {
  return {
    id: createId("scene-object"),
    name: object.name,
    description: object.description,
    interaction: object.interaction,
    tags: object.tags,
    reuseId: object.reuseId || defaultObjectReuseId(object.name, object.tags),
    reuseHint: object.reuseHint || `可复用为“${object.name}”这一类交互物体。`,
  };
}

function cloneSceneLayerFromLibrary(
  layer: import("@vibe-learner/shared").SceneTreeNode
): SceneLayer {
  return {
    id: createId("scene-layer"),
    title: layer.title,
    scopeLabel: layer.scopeLabel,
    summary: layer.summary,
    atmosphere: layer.atmosphere,
    rules: layer.rules,
    entrance: layer.entrance,
    tags: layer.tags,
    reuseId: layer.reuseId || defaultLayerReuseId(layer.title, layer.scopeLabel),
    reuseHint: layer.reuseHint || `可复用为“${layer.title}”这一层场景模板，保留其规则、氛围和进入方式。`,
    objects: (layer.objects ?? []).map((object) => cloneSceneObjectFromLibrary(object)),
    children: (layer.children ?? []).map((child) => cloneSceneLayerFromLibrary(child)),
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
const SCENE_SIDEBAR_WIDTH = 360;

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
  const [sceneKeywordInput, setSceneKeywordInput] = useState("");
  const [sceneLongTextFile, setSceneLongTextFile] = useState<File | null>(null);
  const [sceneGenerateMode, setSceneGenerateMode] = useState<"keywords" | "long_text">("keywords");
  const [sceneGenerateLayerCount, setSceneGenerateLayerCount] = useState("");
  const [sceneGeneratePending, setSceneGeneratePending] = useState<null | "keywords" | "long_text">(null);
  const [sceneGenerateError, setSceneGenerateError] = useState("");
  const [sceneGenerateMessage, setSceneGenerateMessage] = useState("");
  const [sceneGenerateModelRecoveries, setSceneGenerateModelRecoveries] = useState<ModelRecovery[]>([]);
  const [reusableNodes, setReusableNodes] = useState<ReusableSceneNodePayload[]>([]);
  const [reusableSearchQuery, setReusableSearchQuery] = useState("");
  const [reusableActionPendingId, setReusableActionPendingId] = useState("");
  const [reusableMessage, setReusableMessage] = useState("");
  const [reusableError, setReusableError] = useState("");
  const [generatedSceneCandidate, setGeneratedSceneCandidate] = useState<{
    sceneName: string;
    sceneSummary: string;
    sceneLayers: SceneLayer[];
    selectedLayerId: string;
    collapsedLayerIds: string[];
    usedModel: string;
    usedWebSearch: boolean;
    mode: "keywords" | "long_text";
  } | null>(null);
  const importInputRef = useRef<HTMLInputElement | null>(null);

  const [collapsedSidebarSections, setCollapsedSidebarSections] = useState<string[]>([]);
  const [collapsedNodeEditorSectionsByLayer, setCollapsedNodeEditorSectionsByLayer] = useState<Record<string, string[]>>({});
  const [selectedObjectId, setSelectedObjectId] = useState("");
  const [isCompactLayout, setIsCompactLayout] = useState(false);

  const selectedLayer = useMemo(() => findLayerById(sceneLayers, selectedLayerId), [sceneLayers, selectedLayerId]);
  const selectedObjectTarget = useMemo(
    () => (selectedObjectId ? findObjectById(sceneLayers, selectedObjectId) : null),
    [sceneLayers, selectedObjectId]
  );
  const selectedPath = useMemo(() => findLayerPath(sceneLayers, selectedLayerId), [sceneLayers, selectedLayerId]);
  const sceneProfilePreview = useMemo(
    () => deriveSceneProfile(sceneLayers, selectedLayerId, sceneName.trim(), sceneSummary.trim()),
    [sceneLayers, selectedLayerId, sceneName, sceneSummary]
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
      setSelectedLayerId(sceneLayers[0].id);
    }
  }, [sceneLayers, selectedLayer, selectedLayerId]);

  useEffect(() => {
    if (selectedObjectId && !selectedObjectTarget) {
      setSelectedObjectId("");
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

  function applySceneImport(imported: SceneImportPayload, message: string) {
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
    setSceneIoMessage(message);
  }

  function updateLayer(targetId: string, updater: (layer: SceneLayer) => SceneLayer) {
    setSceneLayers((current) => updateLayerTree(current, targetId, updater));
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
    const newObject = createSceneObject();
    updateLayer(layerId, (layer) => ({
      ...layer,
      objects: [...layer.objects, newObject]
    }));
    setSelectedLayerId("");
    setSelectedObjectId(newObject.id);
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
      setSelectedObjectId("");
    }
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
      applySceneImport(imported, `已载入场景”${target.sceneName}”。`);
      setSelectedSavedSceneId(target.sceneId);
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
      applySceneImport(imported, "场景导入成功。");
    } catch {
      setSceneIoMessage("导入失败：文件格式不正确。");
    } finally {
      event.target.value = "";
    }
  }

  async function handleGenerateScene(mode: "keywords" | "long_text") {
    let inputText = "";
    if (mode === "keywords") {
      inputText = sceneKeywordInput.trim();
    } else {
      const longTextFile = sceneLongTextFile;
      if (!longTextFile) {
        setSceneGenerateError("请先上传长文本文件。");
        return;
      }
      try {
        inputText = (await longTextFile.text()).trim();
      } catch {
        setSceneGenerateError("读取长文本文件失败，请重试。");
        return;
      }
    }
    if (!inputText) {
      setSceneGenerateError(mode === "keywords" ? "请先输入关键词。" : "上传文件内容为空，请更换文件。");
      return;
    }
    const layerCountText = sceneGenerateLayerCount.trim();
    let layerCount: number | null = null;
    if (layerCountText) {
      const parsedLayerCount = Number(layerCountText);
      if (!Number.isInteger(parsedLayerCount) || parsedLayerCount < 1) {
        setSceneGenerateError("层级偏好必须是大于 0 的整数，或留空交给模型决定。");
        return;
      }
      layerCount = parsedLayerCount;
    }
    setSceneGenerateError("");
    setSceneGenerateMessage("");
    setSceneGenerateModelRecoveries([]);
    setSceneGeneratePending(mode);
    try {
      const result = await generateSceneTree({
        mode,
        inputText,
        layerCount,
      });
      const imported = parseSceneImportPayload({
        sceneName: result.sceneName,
        sceneSummary: result.sceneSummary,
        sceneLayers: result.sceneLayers,
        selectedLayerId: result.selectedLayerId,
        collapsedLayerIds: [],
      });
      setGeneratedSceneCandidate({
        ...imported,
        usedModel: result.usedModel,
        usedWebSearch: result.usedWebSearch,
        mode: result.mode,
      });
      setSceneGenerateModelRecoveries(result.modelRecoveries ?? []);
      setSceneGenerateMessage(
        `已生成 ${countSceneNodes(imported.sceneLayers.map((layer) => normalizeSceneTreeNodeForProfile(layer)))} 个节点。模型：${result.usedModel || "unknown"}${result.usedWebSearch ? "，已启用联网搜索。" : "。"}`
      );
    } catch (error) {
      setSceneGenerateError(String(error));
    } finally {
      setSceneGeneratePending(null);
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
    setRewriteError("");
    setRewriteModelRecoveries([]);
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
    setRewriteModelRecoveries([]);
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
      setRewriteError(String(error));
    } finally {
      setRewritePendingKey("");
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
    setSelectedObjectId("");
    setSelectedLayerId((current) => (current === layerId ? "" : layerId));
  }

  function toggleObjectEditor(objectId: string) {
    setSelectedLayerId("");
    setSelectedObjectId((current) => (current === objectId ? "" : objectId));
  }

  function handleSelectLayer(layerId: string) {
    setSelectedObjectId("");
    setSelectedLayerId(layerId);
  }

  function renderSelectedLayerEditor(): ReactNode {
    if (!selectedLayer) {
      return <p style={styles.emptyState}>选择层级后在这里编辑。</p>;
    }

    return (
      <>
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
                onRewriteStrengthChange={setRewriteStrength}
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
                onRewriteStrengthChange={setRewriteStrength}
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
                onRewriteStrengthChange={setRewriteStrength}
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
                onRewriteStrengthChange={setRewriteStrength}
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
                    onRewriteStrengthChange={setRewriteStrength}
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
                    onRewriteStrengthChange={setRewriteStrength}
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
                <MaterialIcon name="upload" size={14} />
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
                <MaterialIcon name="add" size={14} />
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
                  onChange={(event) => setSceneName(event.target.value)}
                  placeholder="例如：高一物理-力学基础"
                />
              </label>
              <label style={styles.sceneSummaryLabel}>
                <span style={styles.fieldLabel}>场景摘要</span>
                <textarea
                  style={styles.sceneSummaryInput}
                  value={sceneSummary}
                  onChange={(event) => setSceneSummary(event.target.value)}
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
                    onChange={(event) => setSceneGenerateLayerCount(event.target.value)}
                    placeholder="留空表示不限"
                  />
                </label>
                <div style={styles.modeSwitchRow}>
                  <div style={styles.modeSwitch}>
                    <button
                      type="button"
                      style={sceneGenerateMode === "keywords" ? styles.modeSwitchButtonActive : styles.modeSwitchButton}
                      onClick={() => setSceneGenerateMode("keywords")}
                    >
                      关键词搜索
                    </button>
                    <button
                      type="button"
                      style={sceneGenerateMode === "long_text" ? styles.modeSwitchButtonActive : styles.modeSwitchButton}
                      onClick={() => setSceneGenerateMode("long_text")}
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
                          ? (sceneGeneratePending === "keywords" ? "replay" : "auto_awesome")
                          : (sceneGeneratePending === "long_text" ? "replay" : "description")
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
                      onChange={(event) => setSceneKeywordInput(event.target.value)}
                      placeholder="输入关键词，例如：赛博校园, 物理实验, 夜间自习, 钟楼广播"
                    />
                  </label>
                ) : (
                  <label key="long-text-mode" style={styles.fieldGroup}>
                    <input
                      type="file"
                      accept=".txt,.md,text/plain,text/markdown"
                      style={styles.fileInput}
                      onChange={(event) => setSceneLongTextFile(event.target.files?.[0] ?? null)}
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
                        <MaterialIcon name="subdirectory_arrow_right" size={14} />
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
                          <MaterialIcon name="subdirectory_arrow_right" size={14} />
                        </button>
                        <button
                          style={styles.sidebarIconButton}
                          type="button"
                          disabled={reusableActionPendingId === item.nodeId}
                          onClick={() => void deleteReusableNode(item.nodeId)}
                          title={reusableActionPendingId === item.nodeId ? "删除中" : "删除复用节点"}
                          aria-label={reusableActionPendingId === item.nodeId ? "删除中" : "删除复用节点"}
                        >
                          <MaterialIcon name={reusableActionPendingId === item.nodeId ? "replay" : "delete"} size={14} />
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
                              <MaterialIcon name="replay" size={14} />
                            </button>
                            <button
                              style={isSelected ? { ...styles.sidebarIconButton, ...styles.sidebarIconButtonPrimary } : styles.sidebarIconButton}
                              type="button"
                              onClick={() => setSelectedSavedSceneId(item.sceneId)}
                              title={isSelected ? "当前更新目标" : "作为更新目标"}
                              aria-label={isSelected ? "当前更新目标" : "作为更新目标"}
                            >
                              <MaterialIcon name="adjust" size={14} />
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
          <SceneIconButton icon="add" label="添加子层" size="micro" variant="accent" onClick={stopCardAction(() => onAddChild(layer.id))} />
          <SceneIconButton icon="adjust" label="添加物体" size="micro" onClick={stopCardAction(() => onAddObject(layer.id))} />
          <SceneIconButton
            icon={reusableActionPendingId === layer.id ? "replay" : "create_new_folder"}
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
            <MaterialIcon name="adjust" size={14} />
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
            icon={reusableActionPendingId === object.id ? "replay" : "create_new_folder"}
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
            <p style={styles.rewritePopoverHint}>数值越高，AI 重写时越接近原始设定。</p>
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
  const tags = [selectedLayer.tags, ...selectedLayer.objects.map((item) => item.tags)]
    .flatMap((item) => item.split(","))
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
    tags: layer.tags,
    reuseId: layer.reuseId,
    reuseHint: layer.reuseHint,
    objects: layer.objects.map((object) => ({
      id: object.id,
      name: object.name,
      description: object.description,
      interaction: object.interaction,
      tags: object.tags,
      reuseId: object.reuseId,
      reuseHint: object.reuseHint,
    })),
    children: layer.children.map((child) => normalizeSceneTreeNodeForProfile(child)),
  };
}

function countSceneNodes(nodes: import("@vibe-learner/shared").SceneTreeNode[]): number {
  return nodes.reduce((count, node) => count + 1 + countSceneNodes(node.children), 0);
}

function countSceneObjects(layers: SceneLayer[]): number {
  return layers.reduce(
    (count, layer) => count + layer.objects.length + countSceneObjects(layer.children),
    0
  );
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

function parseSceneImportPayload(input: unknown): SceneImportPayload {
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
    tags: typeof record.tags === "string" ? record.tags : "",
    reuseId: typeof record.reuseId === "string"
      ? record.reuseId
      : typeof record.reuse_id === "string" && record.reuse_id
        ? record.reuse_id
        : defaultLayerReuseId(
            typeof record.title === "string" ? record.title : "未命名层级",
            typeof record.scopeLabel === "string"
              ? record.scopeLabel
              : typeof record.scope_label === "string"
                ? record.scope_label
                : "未定义范围"
          ),
    reuseHint: typeof record.reuseHint === "string"
      ? record.reuseHint
      : typeof record.reuse_hint === "string" && record.reuse_hint
        ? record.reuse_hint
        : `可复用为“${typeof record.title === "string" ? record.title : "未命名层级"}”这一层场景模板，保留其规则、氛围和进入方式。`,
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
    reuseId: typeof record.reuseId === "string"
      ? record.reuseId
      : typeof record.reuse_id === "string" && record.reuse_id
        ? record.reuse_id
        : defaultObjectReuseId(
            typeof record.name === "string" ? record.name : "未命名物体",
            typeof record.tags === "string" ? record.tags : ""
          ),
    reuseHint: typeof record.reuseHint === "string"
      ? record.reuseHint
      : typeof record.reuse_hint === "string" && record.reuse_hint
        ? record.reuse_hint
        : `可复用为“${typeof record.name === "string" ? record.name : "未命名物体"}”这一类交互物体。`,
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

function findObjectById(
  layers: SceneLayer[],
  targetId: string,
): { layer: SceneLayer; object: SceneObject } | null {
  for (const layer of layers) {
    const object = layer.objects.find((item) => item.id === targetId);
    if (object) {
      return { layer, object };
    }
    const childMatch = findObjectById(layer.children, targetId);
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
