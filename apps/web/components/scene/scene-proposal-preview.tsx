import type { SceneLayer, SceneObject } from "../../lib/scene-editor-model";

type FlattenedLayer = { path: string; layer: SceneLayer };
type FieldChange = { label: string; before: string; after: string };
export type SceneProposalConflict = { path: string; message: string };

const layerFields: readonly [keyof SceneLayer, string][] = [
  ["title", "标题"],
  ["scopeLabel", "范围"],
  ["summary", "摘要"],
  ["atmosphere", "氛围"],
  ["rules", "规则"],
  ["entrance", "入口"],
  ["tags", "标签"],
  ["reuseHint", "复用提示"],
];

const objectFields: readonly [keyof SceneObject, string][] = [
  ["name", "名称"],
  ["description", "描述"],
  ["interaction", "交互"],
  ["tags", "标签"],
  ["reuseHint", "复用提示"],
];

function flatten(layers: SceneLayer[], parent = ""): FlattenedLayer[] {
  return layers.flatMap((layer, index) => {
    const path = `${parent}${index + 1}. ${layer.title}`;
    return [{ path, layer }, ...flatten(layer.children, `${path} / `)];
  });
}

function display(value: string | undefined): string {
  return value?.trim() || "空";
}

function changes<T extends object>(
  before: T | undefined,
  after: T,
  fields: readonly [keyof T, string][],
): FieldChange[] {
  if (!before) {
    return fields.map(([field, label]) => ({
      label,
      before: "（新增）",
      after: display(String(after[field] ?? "")),
    }));
  }
  return fields.flatMap(([field, label]) => {
    const previous = display(String(before[field] ?? ""));
    const next = display(String(after[field] ?? ""));
    return previous === next ? [] : [{ label, before: previous, after: next }];
  });
}

function identity(value: { reuseId?: string; name?: string; title?: string }): string {
  return (
    (value.reuseId ?? "").trim() ||
    (value.name ?? value.title ?? "").trim().toLocaleLowerCase()
  );
}

function findObject(
  before: SceneObject[],
  after: SceneObject,
): SceneObject | undefined {
  const key = identity(after);
  return before.find((candidate) => identity(candidate) === key);
}

function ruleClaims(rules: string): Map<string, "allow" | "deny"> {
  const claims = new Map<string, "allow" | "deny">();
  for (const clause of rules
    .split(/[。；;\n]+/)
    .map((part) => part.trim())
    .filter(Boolean)) {
    const match = clause.match(/^(.*?)(禁止|不得|不允许|不可|不能|允许|可以)(.+)$/);
    if (!match) continue;
    const [, subject, marker, action] = match;
    const key = `${subject.trim()}=>${action.trim()}`;
    claims.set(key, /禁止|不得|不允许|不可|不能/.test(marker) ? "deny" : "allow");
  }
  return claims;
}

/** Detect deterministic structural/reference conflicts without claiming semantic rule validation. */
export function findSceneProposalConflicts(
  layers: SceneLayer[],
): SceneProposalConflict[] {
  const conflicts: SceneProposalConflict[] = [];
  const layerReuse = new Map<string, string>();
  const objectReuse = new Map<string, string>();
  for (const { path, layer } of flatten(layers)) {
    if (!layer.title.trim()) conflicts.push({ path, message: "层标题为空。" });
    const layerKey = (layer.reuseId ?? "").trim();
    if (layerKey) {
      const previous = layerReuse.get(layerKey);
      if (previous && previous !== path)
        conflicts.push({ path, message: `复用引用 ${layerKey} 与 ${previous} 重复。` });
      else layerReuse.set(layerKey, path);
    }
    const names = new Map<string, string>();
    for (const object of layer.objects) {
      const objectPath = `${path} / ${object.name || "未命名物体"}`;
      if (!object.name.trim())
        conflicts.push({ path: objectPath, message: "物体名称为空。" });
      const nameKey = object.name.trim().toLocaleLowerCase();
      if (nameKey && names.has(nameKey))
        conflicts.push({
          path: objectPath,
          message: `同一层内与 ${names.get(nameKey)} 使用重复物体名称。`,
        });
      else if (nameKey) names.set(nameKey, objectPath);
      const reuseKey = (object.reuseId ?? "").trim();
      if (reuseKey) {
        const previous = objectReuse.get(reuseKey);
        if (previous && previous !== objectPath)
          conflicts.push({
            path: objectPath,
            message: `物体复用引用 ${reuseKey} 与 ${previous} 重复。`,
          });
        else objectReuse.set(reuseKey, objectPath);
      }
    }
  }
  const flattened = flatten(layers);
  for (const child of flattened) {
    const childClaims = ruleClaims(child.layer.rules);
    for (const parent of flattened.filter((candidate) =>
      child.path.startsWith(`${candidate.path} / `),
    )) {
      const parentClaims = ruleClaims(parent.layer.rules);
      for (const [key, polarity] of childClaims) {
        const parentPolarity = parentClaims.get(key);
        if (parentPolarity && parentPolarity !== polarity) {
          conflicts.push({
            path: child.path,
            message: `规则“${key.replace("=>", " ")}”与父级 ${parent.path} 的${polarity === "allow" ? "禁止" : "允许"}约束冲突。`,
          });
        }
      }
    }
  }
  return conflicts;
}

function renderChanges(items: FieldChange[]) {
  if (!items.length) return null;
  return (
    <div>
      {items.map((item) => (
        <p key={item.label}>
          {item.label}：<del>{item.before}</del> → <ins>{item.after}</ins>
        </p>
      ))}
    </div>
  );
}

/** Compare human-readable hierarchy paths; generated IDs are unrelated to draft IDs. */
export function SceneProposalPreview({
  current,
  proposed,
}: {
  current: SceneLayer[];
  proposed: SceneLayer[];
}) {
  const before = flatten(current);
  const after = flatten(proposed);
  const oldPaths = new Set(before.map((item) => item.path));
  const newPaths = new Set(after.map((item) => item.path));
  const removed = before.filter((item) => !newPaths.has(item.path));
  const added = after.filter((item) => !oldPaths.has(item.path));
  const conflicts = findSceneProposalConflicts(proposed);
  const objectCount = (items: FlattenedLayer[]) =>
    items.reduce((count, item) => count + item.layer.objects.length, 0);

  return (
    <div className="proposal-diff">
      <p>
        层级：{before.length} → {after.length}；物体：{objectCount(before)} →{" "}
        {objectCount(after)}
      </p>
      <p>
        按层级路径比较：新增 {added.length} 层，移除 {removed.length}{" "}
        层；重命名或移动按移除和新增显示。
      </p>
      {conflicts.length ? (
        <div role="alert">
          <strong>发现 {conflicts.length} 个结构约束冲突候选</strong>
          {conflicts.map((conflict) => (
            <p key={`${conflict.path}:${conflict.message}`}>
              {conflict.path}：{conflict.message}
            </p>
          ))}
        </div>
      ) : (
        <p>未发现重复名称、复用引用或必填字段冲突。</p>
      )}
      <details>
        <summary>查看完整字段与结构变化</summary>
        {removed.map((item) => (
          <div key={`removed:${item.path}`}>
            <strong>
              <del>移除：{item.path}</del>
            </strong>
            {renderChanges(changes(item.layer, {} as SceneLayer, layerFields))}
          </div>
        ))}
        {after.map((item) => {
          const previous = before.find((old) => old.path === item.path)?.layer;
          const previousObjects = previous?.objects ?? [];
          const currentObjectKeys = new Set(item.layer.objects.map(identity));
          const removedObjects = previousObjects.filter(
            (object) => !currentObjectKeys.has(identity(object)),
          );
          return (
            <div key={item.path}>
              <strong>
                {previous ? "保留路径" : "新增层级"}：{item.path}
              </strong>
              {renderChanges(changes(previous, item.layer, layerFields))}
              {removedObjects.map((object) => (
                <p key={`removed-object:${item.path}:${object.id}`}>
                  <del>移除物体：{object.name || "未命名"}</del>
                </p>
              ))}
              {item.layer.objects.map((object) => {
                const previousObject = findObject(previousObjects, object);
                return (
                  <div key={object.id}>
                    <strong>物体：{object.name || "未命名"}</strong>
                    <p>
                      {object.name || "未命名"}：{object.description || "未指定"}
                      ；交互：
                      {object.interaction || "未指定"}
                    </p>
                    {renderChanges(changes(previousObject, object, objectFields))}
                  </div>
                );
              })}
            </div>
          );
        })}
      </details>
      <p>
        以上只识别结构、名称和复用引用冲突；规则语义、继承关系及交互可行性仍需人工核对。
      </p>
    </div>
  );
}
