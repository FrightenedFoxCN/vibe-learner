/** Validate user files before permissive legacy-field normalization changes a draft. */
export function validateSceneImportStructure(input: unknown): void {
  const object = (value: unknown): Record<string, unknown> => {
    if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("invalid_scene_object");
    return value as Record<string, unknown>;
  };
  const root = Array.isArray(input) ? {} : object(input);
  if (root.version !== undefined && root.version !== 1) throw new Error("unsupported_scene_import_version");
  const layers = Array.isArray(input) ? input : root.sceneLayers ?? root.scene_layers;
  if (!Array.isArray(layers) || !layers.length) throw new Error("invalid_scene_layers");
  let layerCount = 0;
  let objectCount = 0;
  let textCount = 0;
  const textFields = (record: Record<string, unknown>, fields: string[]) => {
    for (const field of fields) {
      const value = record[field];
      if (value === undefined) continue;
      if (typeof value !== "string") throw new Error("invalid_scene_text");
      textCount += [...value].length;
    }
    if (textCount > 60_000) throw new Error("scene_text_budget_exceeded");
  };
  const tags = (record: Record<string, unknown>) => {
    if (record.tags === undefined) return;
    if (typeof record.tags === "string") textFields(record, ["tags"]);
    else if (Array.isArray(record.tags) && record.tags.every((tag) => typeof tag === "string")) {
      textFields({ tags: record.tags.join(",") }, ["tags"]);
    } else throw new Error("invalid_scene_tags");
  };
  const children = (record: Record<string, unknown>, key: string): unknown[] => {
    if (record[key] === undefined) return [];
    if (!Array.isArray(record[key])) throw new Error("invalid_scene_children");
    return record[key] as unknown[];
  };
  const visit = (value: unknown, depth: number) => {
    if (depth > 8 || ++layerCount > 64) throw new Error("scene_layer_budget_exceeded");
    const layer = object(value);
    if (typeof layer.title !== "string" || !layer.title.trim()) throw new Error("invalid_scene_title");
    textFields(layer, ["title", "scopeLabel", "scope_label", "summary", "atmosphere", "rules", "entrance", "reuseHint", "reuse_hint"]);
    tags(layer);
    for (const raw of children(layer, "objects")) {
      if (++objectCount > 128) throw new Error("scene_object_budget_exceeded");
      const item = object(raw);
      if (typeof item.name !== "string" || !item.name.trim()) throw new Error("invalid_scene_object_name");
      textFields(item, ["name", "description", "interaction", "reuseHint", "reuse_hint"]);
      tags(item);
    }
    for (const child of children(layer, "children")) visit(child, depth + 1);
  };
  textFields(root, ["sceneName", "scene_name", "sceneSummary", "scene_summary"]);
  for (const layer of layers) visit(layer, 1);
}
