export function serializeSceneTree(
  nodes: import("@vibe-learner/shared").SceneTreeNode[] | undefined,
): Array<Record<string, unknown>> {
  return (nodes ?? []).map((node) => ({
    id: node.id,
    title: node.title,
    scope_label: node.scopeLabel,
    summary: node.summary,
    atmosphere: node.atmosphere,
    rules: node.rules,
    entrance: node.entrance,
    tags: node.tags,
    reuse_id: node.reuseId,
    reuse_hint: node.reuseHint,
    objects: (node.objects ?? []).map((object) => ({
      id: object.id,
      name: object.name,
      description: object.description,
      interaction: object.interaction,
      tags: object.tags,
      reuse_id: object.reuseId,
      reuse_hint: object.reuseHint,
    })),
    children: serializeSceneTree(node.children),
  }));
}

export function serializeSceneProfile(
  sceneProfile: import("@vibe-learner/shared").SceneProfile | null | undefined,
) {
  if (!sceneProfile) {
    return null;
  }
  return {
    scene_name: sceneProfile.sceneName,
    scene_id: sceneProfile.sceneId,
    title: sceneProfile.title,
    summary: sceneProfile.summary,
    tags: sceneProfile.tags,
    selected_path: sceneProfile.selectedPath,
    focus_object_names: sceneProfile.focusObjectNames,
    scene_tree: serializeSceneTree(sceneProfile.sceneTree),
  };
}
