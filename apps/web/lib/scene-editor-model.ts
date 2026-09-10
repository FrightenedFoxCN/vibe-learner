import type { SceneProfile } from "@vibe-learner/shared";
import { validateSceneImportStructure } from "./scene-import-structure";

export interface SceneObject {
  id: string;
  name: string;
  description: string;
  interaction: string;
  tags: string;
  reuseId: string;
  reuseHint: string;
}

export interface SceneLayer {
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

export interface SceneImportPayload {
  sceneName: string;
  sceneSummary: string;
  sceneLayers: SceneLayer[];
  selectedLayerId: string;
  collapsedLayerIds: string[];
}

export const LAYER_TEMPLATES = [
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

export function createId(prefix: string) {
  const suffix = typeof globalThis.crypto?.randomUUID === "function"
    ? globalThis.crypto.randomUUID().slice(0, 8)
    : Math.random().toString(36).slice(2, 10);
  return `${prefix}-${suffix}`;
}

export function createStableSceneToken(seed: string, prefix: string) {
  let value = 0;
  for (const char of seed) {
    value = ((value * 131) + char.charCodeAt(0)) >>> 0;
  }
  return `${prefix}-${value.toString(16).padStart(8, "0")}`;
}

export function defaultLayerReuseId(title: string, scopeLabel: string) {
  return createStableSceneToken(`${title}:${scopeLabel}`, "scene-layer-reuse");
}

export function defaultObjectReuseId(name: string, tags = "") {
  return createStableSceneToken(`${name}:${tags}`, "scene-object-reuse");
}

export function createSceneObject(name = "新物体", fixedId?: string): SceneObject {
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

export function createSceneLayer(templateIndex: number, childLayers: SceneLayer[] = [], fixedId?: string, fixedObjectId?: string): SceneLayer {
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

export function cloneSceneObjectFromLibrary(
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

export function cloneSceneLayerFromLibrary(
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

export const INITIAL_SCENE: SceneLayer[] = [
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

export const SCENE_STORAGE_KEY = "vibe-learner.scene-setup.v1";

export function deriveSceneProfile(
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

export function normalizeSceneTreeNodeForProfile(layer: SceneLayer): import("@vibe-learner/shared").SceneTreeNode {
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

export function countSceneNodes(nodes: import("@vibe-learner/shared").SceneTreeNode[]): number {
  return nodes.reduce((count, node) => count + 1 + countSceneNodes(node.children), 0);
}

export function countSceneObjects(layers: SceneLayer[]): number {
  return layers.reduce(
    (count, layer) => count + layer.objects.length + countSceneObjects(layer.children),
    0
  );
}

export function removeLayerTree(layers: SceneLayer[], targetId: string): SceneLayer[] {
  return layers
    .filter((layer) => layer.id !== targetId)
    .map((layer) => ({
      ...layer,
      children: removeLayerTree(layer.children, targetId)
    }));
}

export function canDeleteLayerSafely(layers: SceneLayer[], targetId: string): boolean {
  const next = removeLayerTree(layers, targetId);
  return next.length > 0;
}

export function collectLayerIds(layers: SceneLayer[]): string[] {
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

export function parseSceneImportPayload(input: unknown, strictFile = false): SceneImportPayload {
  if (strictFile) validateSceneImportStructure(input);
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

export function normalizeSceneLayer(input: unknown): SceneLayer {
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
    tags: typeof record.tags === "string" ? record.tags : Array.isArray(record.tags) ? record.tags.join(",") : "",
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

export function normalizeSceneObject(input: unknown): SceneObject {
  const record = (input ?? {}) as Record<string, unknown>;
  return {
    id: typeof record.id === "string" && record.id ? record.id : createId("scene-object"),
    name: typeof record.name === "string" ? record.name : "未命名物体",
    description: typeof record.description === "string" ? record.description : "",
    interaction: typeof record.interaction === "string" ? record.interaction : "",
    tags: typeof record.tags === "string" ? record.tags : Array.isArray(record.tags) ? record.tags.join(",") : "",
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

export function updateLayerTree(layers: SceneLayer[], targetId: string, updater: (layer: SceneLayer) => SceneLayer): SceneLayer[] {
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

export function findLayerById(layers: SceneLayer[], targetId: string): SceneLayer | null {
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

export function findObjectById(
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

export function findLayerPath(layers: SceneLayer[], targetId: string, trail: string[] = []): string[] {
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

export function inferTemplateIndexFromLayer(layer: SceneLayer): number {
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

