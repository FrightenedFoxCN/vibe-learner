import assert from "node:assert/strict";
import { registerHooks } from "node:module";
import { test } from "node:test";
import { act } from "react";
import { register } from "tsx/esm/api";
import { mountSceneHook } from "./scene-hook-test-support.ts";

const unregister = register();
const overrides = registerHooks({
  resolve(specifier, context, nextResolve) {
    if (context.parentURL?.endsWith("/hooks/use-scene-workspace-controller.ts")) {
      if (specifier === "../components/ui/confirm-provider")
        return {
          url: "data:text/javascript,export const useConfirm = () => async () => true",
          shortCircuit: true,
        };
      if (specifier === "../components/debug/page-debug-context")
        return {
          url: "data:text/javascript,export const usePageDebugSnapshot = () => {}",
          shortCircuit: true,
        };
    }
    return nextResolve(specifier, context);
  },
});
const { useSceneWorkspaceController } =
  await import("../hooks/use-scene-workspace-controller.ts");
const { collectLayerIds } = await import("../lib/scene-editor-model.ts");
overrides.deregister();
unregister();

test("deleting a subtree removes its collapsed IDs but keeps unrelated ones", async (t) => {
  t.mock.getter(globalThis, "localStorage", () => undefined);
  t.mock.method(globalThis, "fetch", async () => Response.json({ items: [] }));
  const scene = await mountSceneHook(useSceneWorkspaceController);
  t.after(scene.unmount);
  const root = scene.current().sceneLayers[0];
  const subtree = root.children[0];
  const removedIds = collectLayerIds([subtree]);
  assert.ok(removedIds.length > 2);
  await act(() => scene.current().addChildLayer(root.id));
  const sibling = scene.current().sceneLayers[0].children[1];
  await act(() => scene.current().toggleLayerChildren(sibling.id));
  const before = scene.current().collapsedLayerIds;
  assert.ok(removedIds.every((id) => before.includes(id)));
  assert.ok(before.includes(sibling.id));
  await act(() =>
    scene
      .current()
      .requestDeleteLayer(subtree.id, { isConnected: true } as HTMLElement),
  );
  assert.deepEqual(
    scene.current().sceneLayers[0].children.map((layer) => layer.id),
    [sibling.id],
  );
  assert.deepEqual(scene.current().collapsedLayerIds, [sibling.id]);
});
