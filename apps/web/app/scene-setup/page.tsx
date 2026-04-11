"use client";

import { useMemo, useState } from "react";
import type { CSSProperties } from "react";

import { TopNav } from "../../components/top-nav";

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

export default function SceneSetupPage() {
  const [sceneLayers, setSceneLayers] = useState<SceneLayer[]>(INITIAL_SCENE);
  const [selectedLayerId, setSelectedLayerId] = useState(INITIAL_SCENE[0]?.id ?? "");

  const selectedLayer = useMemo(() => findLayerById(sceneLayers, selectedLayerId), [sceneLayers, selectedLayerId]);
  const sceneStats = useMemo(() => collectSceneStats(sceneLayers), [sceneLayers]);
  const selectedPath = useMemo(() => findLayerPath(sceneLayers, selectedLayerId), [sceneLayers, selectedLayerId]);

  function updateLayer(targetId: string, updater: (layer: SceneLayer) => SceneLayer) {
    setSceneLayers((current) => updateLayerTree(current, targetId, updater));
  }

  function addChildLayer(parentId: string) {
    setSceneLayers((current) =>
      updateLayerTree(current, parentId, (layer) => ({
        ...layer,
        children: [
          ...layer.children,
          createSceneLayer(Math.min(layer.children.length + layerDepth(layer), LAYER_TEMPLATES.length - 1))
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

  return (
    <main className="with-app-nav" style={styles.page}>
      <TopNav currentPath="/scene-setup" />

      <div style={styles.heading}>
        <h1 style={styles.pageTitle}>场景搭建</h1>
        <p style={styles.pageDesc}>从世界整体一路搭到具体教室。每一层都可以写设定、补互动物体，并把层级之间的过渡关系说明清楚。先选层级，再在右侧补细节。</p>
      </div>

      <section style={styles.metricsRow}>
        <div style={{ ...styles.metricCard, ...styles.metricCardDivider }}>
          <span style={styles.metricLabel}>层级跨度</span>
          <strong style={styles.metricValue}>{sceneStats.layerCount} 层</strong>
          <span style={styles.metricHint}>从世界到教室的完整链条</span>
        </div>
        <div style={{ ...styles.metricCard, ...styles.metricCardDivider }}>
          <span style={styles.metricLabel}>可互动物体</span>
          <strong style={styles.metricValue}>{sceneStats.objectCount} 个</strong>
          <span style={styles.metricHint}>每一层都能放置局部物件</span>
        </div>
        <div style={styles.metricCard}>
          <span style={styles.metricLabel}>当前选中</span>
          <strong style={styles.metricValue}>{selectedLayer?.title ?? "未选择"}</strong>
          <span style={styles.metricHint}>{selectedPath.length ? selectedPath.join(" / ") : "选择任一层级开始编辑"}</span>
        </div>
      </section>

      <section style={styles.workspace}>
        <div style={styles.treePane}>
          <div style={styles.panelHead}>
            <span style={styles.panelTitle}>层级结构</span>
            <span style={styles.panelSubTitle}>从大范围写到小范围，并在每层放入可交互对象。</span>
          </div>
          <div style={styles.treeStack}>
            {sceneLayers.map((layer, index) => (
              <SceneLayerCard
                key={layer.id}
                layer={layer}
                index={index}
                selectedLayerId={selectedLayerId}
                onSelect={setSelectedLayerId}
                onAddChild={addChildLayer}
                onAddObject={addObject}
              />
            ))}
          </div>
        </div>

        <aside style={styles.editorPane}>
          <div style={styles.panelHead}>
            <span style={styles.panelTitle}>层级编辑器</span>
            <span style={styles.panelSubTitle}>所有字段都是可直接写的场景设定。</span>
          </div>

          {selectedLayer ? (
            <>
              <div style={styles.pathChipRow}>
                {selectedPath.map((segment, index) => (
                  <span key={`${segment}-${index}`} style={styles.pathChip}>{segment}</span>
                ))}
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
                  <span style={styles.fieldLabel}>层级总述</span>
                  <textarea
                    style={styles.textarea}
                    value={selectedLayer.summary}
                    onChange={(event) => updateLayer(selectedLayer.id, (layer) => ({ ...layer, summary: event.target.value }))}
                  />
                </label>

                <label style={styles.fieldGroup}>
                  <span style={styles.fieldLabel}>氛围与感知</span>
                  <textarea
                    style={styles.textarea}
                    value={selectedLayer.atmosphere}
                    onChange={(event) => updateLayer(selectedLayer.id, (layer) => ({ ...layer, atmosphere: event.target.value }))}
                  />
                </label>

                <label style={styles.fieldGroup}>
                  <span style={styles.fieldLabel}>进入方式 / 过渡</span>
                  <textarea
                    style={styles.textarea}
                    value={selectedLayer.entrance}
                    onChange={(event) => updateLayer(selectedLayer.id, (layer) => ({ ...layer, entrance: event.target.value }))}
                  />
                </label>

                <label style={styles.fieldGroup}>
                  <span style={styles.fieldLabel}>层级规则</span>
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
                  <button type="button" style={styles.primaryButton} onClick={() => addObject(selectedLayer.id)}>
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
                        <button type="button" style={styles.ghostButton} onClick={() => removeObject(selectedLayer.id, object.id)}>
                          删除
                        </button>
                      </div>

                      <label style={styles.fieldGroup}>
                        <span style={styles.fieldLabel}>外观 / 说明</span>
                        <textarea
                          style={styles.textarea}
                          value={object.description}
                          onChange={(event) => updateObject(selectedLayer.id, object.id, "description", event.target.value)}
                        />
                      </label>

                      <label style={styles.fieldGroup}>
                        <span style={styles.fieldLabel}>交互方式</span>
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
                <button type="button" style={styles.ghostButton} onClick={() => addChildLayer(selectedLayer.id)}>
                  新增下级层级
                </button>
                <span style={styles.helperText}>下级层级会沿用当前层级的语义，再根据更细粒度的空间做收敛。</span>
              </div>
            </>
          ) : (
            <p style={styles.emptyState}>选择一个层级后，这里会显示它的设定、对象和子层级操作。</p>
          )}
        </aside>
      </section>
    </main>
  );
}

function SceneLayerCard({
  layer,
  index,
  selectedLayerId,
  onSelect,
  onAddChild,
  onAddObject
}: {
  layer: SceneLayer;
  index: number;
  selectedLayerId: string;
  onSelect: (layerId: string) => void;
  onAddChild: (layerId: string) => void;
  onAddObject: (layerId: string) => void;
}) {
  const isSelected = layer.id === selectedLayerId;
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

        <div style={styles.layerMetaRow}>
          <span style={styles.layerMetaItem}>{layer.objects.length} 个物体</span>
          <span style={styles.layerMetaItem}>{layer.children.length} 个子层级</span>
        </div>

        <div style={styles.objectChipRow}>
          {layer.objects.slice(0, 3).map((object) => (
            <span key={object.id} style={styles.objectChip}>{object.name}</span>
          ))}
          {layer.objects.length > 3 ? <span style={styles.objectChip}>+{layer.objects.length - 3}</span> : null}
        </div>

        <div style={styles.cardActions}>
          <button type="button" style={styles.cardButton} onClick={(event) => { event.stopPropagation(); onSelect(layer.id); }}>
            编辑
          </button>
          <button type="button" style={styles.cardButton} onClick={(event) => { event.stopPropagation(); onAddObject(layer.id); }}>
            添加物体
          </button>
          <button type="button" style={styles.cardButton} onClick={(event) => { event.stopPropagation(); onAddChild(layer.id); }}>
            添加子层
          </button>
        </div>
      </article>

      {layer.children.length ? (
        <div style={styles.childStack}>
          {layer.children.map((child, childIndex) => (
            <SceneLayerCard
              key={child.id}
              layer={child}
              index={childIndex}
              selectedLayerId={selectedLayerId}
              onSelect={onSelect}
              onAddChild={onAddChild}
              onAddObject={onAddObject}
            />
          ))}
        </div>
      ) : null}
    </div>
  );
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

function collectSceneStats(layers: SceneLayer[]) {
  let layerCount = 0;
  let objectCount = 0;
  const stack = [...layers];
  while (stack.length) {
    const layer = stack.pop();
    if (!layer) {
      continue;
    }
    layerCount += 1;
    objectCount += layer.objects.length;
    stack.push(...layer.children);
  }
  return { layerCount, objectCount };
}

function layerDepth(layer: SceneLayer): number {
  let depth = 0;
  let current: SceneLayer | null = layer;
  while (current.children.length) {
    depth += 1;
    current = current.children[0] ?? null;
  }
  return depth;
}

const styles: Record<string, CSSProperties> = {
  page: {
    minHeight: "100vh",
    maxWidth: 1460,
    margin: "0 auto",
    padding: "20px 24px 40px",
    display: "grid",
    gap: 20,
    alignContent: "start",
  },
  heading: {
    display: "grid",
    gap: 6,
    paddingBottom: 14,
    borderBottom: "1px solid var(--border)",
  },
  pageTitle: {
    margin: 0,
    fontSize: 20,
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
  metricsRow: {
    display: "grid",
    gridTemplateColumns: "repeat(3, minmax(0, 1fr))",
    border: "1px solid var(--border)",
  },
  metricCard: {
    padding: 16,
    display: "grid",
    gap: 4,
  },
  metricCardDivider: {
    borderRightWidth: 1,
    borderRightStyle: "solid",
    borderRightColor: "var(--border)",
  },
  metricLabel: {
    fontSize: 11,
    fontWeight: 600,
    textTransform: "uppercase",
    letterSpacing: "0.07em",
    color: "var(--muted)",
  },
  metricValue: {
    fontSize: 18,
    fontWeight: 700,
    color: "var(--ink)",
  },
  metricHint: {
    fontSize: 12,
    lineHeight: 1.6,
    color: "var(--muted)",
  },
  workspace: {
    display: "grid",
    gridTemplateColumns: "minmax(0, 1.15fr) minmax(360px, 0.85fr)",
    border: "1px solid var(--border)",
    alignItems: "start",
  },
  treePane: {
    padding: 20,
    display: "grid",
    gap: 16,
    alignContent: "start",
  },
  editorPane: {
    borderLeft: "1px solid var(--border)",
    padding: 20,
    display: "grid",
    gap: 18,
    alignContent: "start",
    position: "sticky",
    top: 16,
  },
  panelHead: {
    paddingBottom: 10,
    borderBottom: "1px solid var(--border)",
    marginBottom: 2,
    display: "grid",
    gap: 4,
  },
  panelTitle: {
    fontSize: 13,
    fontWeight: 700,
    color: "var(--ink)",
    letterSpacing: "0.01em",
  },
  panelSubTitle: {
    fontSize: 12,
    color: "var(--muted)",
  },
  treeStack: {
    display: "grid",
    gap: 10,
  },
  cardGroup: {
    display: "grid",
    gap: 8,
  },
  layerCard: {
    borderWidth: 1,
    borderStyle: "solid",
    borderColor: "var(--border)",
    background: "var(--panel)",
    padding: 14,
    display: "grid",
    gap: 10,
    cursor: "pointer",
  },
  layerCardActive: {
    borderColor: "var(--accent)",
    boxShadow: "0 0 0 2px var(--accent-soft) inset",
  },
  layerTopRow: {
    display: "flex",
    alignItems: "flex-start",
    gap: 10,
  },
  layerIndexBadge: {
    width: 28,
    height: 28,
    background: "var(--accent)",
    color: "#fff",
    display: "grid",
    placeItems: "center",
    fontSize: 11,
    fontWeight: 800,
    letterSpacing: "0.08em",
    flexShrink: 0,
  },
  layerHeadCopy: {
    display: "grid",
    gap: 2,
    minWidth: 0,
  },
  layerScope: {
    fontSize: 11,
    fontWeight: 600,
    textTransform: "uppercase",
    letterSpacing: "0.07em",
    color: "var(--muted)",
  },
  layerTitle: {
    margin: 0,
    fontSize: 14,
    fontWeight: 700,
    color: "var(--ink)",
    lineHeight: 1.2,
  },
  layerSummary: {
    margin: 0,
    fontSize: 12,
    lineHeight: 1.6,
    color: "var(--muted)",
  },
  layerMetaRow: {
    display: "flex",
    flexWrap: "wrap",
    gap: 6,
  },
  layerMetaItem: {
    padding: "3px 8px",
    background: "var(--accent-soft)",
    color: "var(--accent)",
    fontSize: 11,
    fontWeight: 600,
  },
  objectChipRow: {
    display: "flex",
    flexWrap: "wrap",
    gap: 6,
  },
  objectChip: {
    padding: "3px 8px",
    border: "1px solid var(--border)",
    background: "var(--bg)",
    fontSize: 11,
    color: "var(--muted)",
  },
  cardActions: {
    display: "flex",
    flexWrap: "wrap",
    gap: 8,
  },
  cardButton: {
    border: "1px solid var(--border)",
    background: "white",
    color: "var(--ink)",
    padding: "4px 10px",
    fontSize: 12,
    cursor: "pointer",
    height: 28,
  },
  childStack: {
    paddingLeft: 16,
    borderLeft: "2px solid var(--border)",
    display: "grid",
    gap: 8,
  },
  pathChipRow: {
    display: "flex",
    flexWrap: "wrap",
    gap: 6,
  },
  pathChip: {
    padding: "3px 8px",
    background: "var(--panel)",
    border: "1px solid var(--border)",
    fontSize: 11,
    color: "var(--muted)",
  },
  formGrid: {
    display: "grid",
    gap: 12,
  },
  fieldGroup: {
    display: "grid",
    gap: 6,
  },
  compactField: {
    display: "grid",
    gap: 6,
    flex: 1,
  },
  fieldLabel: {
    fontSize: 11,
    fontWeight: 600,
    textTransform: "uppercase",
    letterSpacing: "0.07em",
    color: "var(--muted)",
  },
  input: {
    width: "100%",
    height: 36,
    border: "1px solid var(--border)",
    background: "var(--panel)",
    padding: "0 10px",
    color: "var(--ink)",
    fontSize: 13,
    outline: "none",
  },
  textarea: {
    width: "100%",
    minHeight: 72,
    border: "1px solid var(--border)",
    background: "var(--panel)",
    padding: "8px 10px",
    color: "var(--ink)",
    fontSize: 13,
    lineHeight: 1.6,
    resize: "vertical",
    outline: "none",
  },
  objectsSection: {
    display: "grid",
    gap: 10,
  },
  objectsHead: {
    display: "flex",
    justifyContent: "space-between",
    gap: 10,
    alignItems: "center",
  },
  objectsTitle: {
    margin: 0,
    fontSize: 13,
    fontWeight: 700,
    color: "var(--ink)",
  },
  objectsHint: {
    margin: "3px 0 0",
    fontSize: 12,
    lineHeight: 1.6,
    color: "var(--muted)",
  },
  primaryButton: {
    border: "none",
    background: "var(--accent)",
    color: "white",
    height: 36,
    padding: "0 14px",
    fontWeight: 600,
    cursor: "pointer",
    fontSize: 13,
    flexShrink: 0,
  },
  objectList: {
    display: "grid",
    gap: 10,
  },
  objectCard: {
    padding: 12,
    border: "1px solid var(--border)",
    background: "var(--bg)",
    display: "grid",
    gap: 10,
  },
  objectRow: {
    display: "flex",
    alignItems: "end",
    gap: 10,
  },
  ghostButton: {
    border: "1px solid var(--border)",
    background: "white",
    color: "var(--ink)",
    height: 36,
    padding: "0 12px",
    cursor: "pointer",
    fontSize: 13,
    display: "inline-flex",
    alignItems: "center",
    flexShrink: 0,
  },
  editorActions: {
    display: "flex",
    alignItems: "center",
    gap: 10,
    flexWrap: "wrap",
  },
  helperText: {
    fontSize: 12,
    color: "var(--muted)",
  },
  emptyState: {
    margin: 0,
    padding: "20px 0",
    color: "var(--muted)",
    lineHeight: 1.7,
    fontSize: 13,
  },
};