import type { SceneLayer } from "../../lib/scene-editor-model";

function flatten(layers: SceneLayer[], parent = ""): { path: string; layer: SceneLayer }[] {
  return layers.flatMap((layer, index) => {
    const path = `${parent}${index + 1}. ${layer.title}`;
    return [{ path, layer }, ...flatten(layer.children, `${path} / `)];
  });
}

/** Compare human-readable hierarchy paths; generated IDs are unrelated to draft IDs. */
export function SceneProposalPreview({ current, proposed }: { current: SceneLayer[]; proposed: SceneLayer[] }) {
  const before = flatten(current);
  const after = flatten(proposed);
  const oldPaths = new Set(before.map(item => item.path));
  const newPaths = new Set(after.map(item => item.path));
  const removed = before.filter(item => !newPaths.has(item.path));
  const added = after.filter(item => !oldPaths.has(item.path));
  return <div className="proposal-diff">
    <p>层级：{before.length} → {after.length}；物体：{before.reduce((n, item) => n + item.layer.objects.length, 0)} → {after.reduce((n, item) => n + item.layer.objects.length, 0)}</p>
    <p>应用将替换整个编辑树。按层级路径比较：新增 {added.length} 层，移除 {removed.length} 层；重命名或移动按移除和新增显示。</p>
    <details><summary>查看结构与规则变化</summary>
      {removed.map(item => <p key={item.path}><del>移除：{item.path}</del></p>)}
      {after.map(item => {
        const previous = before.find(old => old.path === item.path)?.layer;
        return <div key={item.path}>
          <strong>{previous ? "保留路径" : "新增层级"}：{item.path}</strong>
          <p>规则：<del>{previous?.rules || "空"}</del> → <ins>{item.layer.rules || "空"}</ins></p>
          <p>物体：<del>{previous?.objects.map(object => object.name).join("、") || "无"}</del> → <ins>{item.layer.objects.map(object => object.name).join("、") || "无"}</ins></p>
          {item.layer.objects.map(object => <p key={object.id}>{object.name}：{object.description}；交互：{object.interaction || "未指定"}</p>)}
        </div>;
      })}
    </details>
    <p>请核对上下层规则及物体交互是否冲突；此预览不自动判定语义冲突。</p>
  </div>;
}
