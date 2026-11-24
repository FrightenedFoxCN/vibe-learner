import assert from "node:assert/strict";
import { test } from "node:test";
import { act } from "react";
import { register } from "tsx/esm/api";
import type { SceneLibraryItemPayload } from "../lib/data/scenes";
import { ApiHttpError } from "../lib/http-error.ts";
import { mountSceneHook } from "./scene-hook-test-support.ts";

const unregister = register();
const { useSceneLibrary } = await import("../hooks/use-scene-library.ts");
unregister();

test("a pending conflict GET cannot revive a deleted scene", async (t) => {
  const scene: SceneLibraryItemPayload = {
    sceneId: "saved-scene",
    revision: 1,
    createdAt: "2026-11-24T00:00:00Z",
    updatedAt: "2026-11-24T00:00:00Z",
    sceneName: "scene",
    sceneSummary: "summary",
    sceneLayers: [],
    selectedLayerId: "root",
    collapsedLayerIds: [],
  };
  let resolveOldRead!: (item: SceneLibraryItemPayload) => void;
  const oldRead = new Promise<SceneLibraryItemPayload>((resolve) => {
    resolveOldRead = resolve;
  });
  const unexpected = () => Promise.reject(new Error("unexpected API call"));
  const library = await mountSceneHook(() =>
    useSceneLibrary({
      listSceneLibrary: async () => [scene],
      listReusableSceneNodes: async () => [],
      createSceneLibraryItem: unexpected,
      updateSceneLibraryItem: () =>
        Promise.reject(
          new ApiHttpError({ status: 409, message: "stale revision", payload: null }),
        ),
      getSceneLibraryItem: () => oldRead,
      deleteSceneLibraryItem: async () => ({ deletedSceneId: scene.sceneId }),
      createReusableSceneNode: unexpected,
      deleteReusableSceneNode: unexpected,
    }),
  );
  t.after(library.unmount);
  await act(() => library.current().bindScene(scene));
  await act(async () => {
    await assert.rejects(
      library.current().updateSceneLibraryItem(scene.sceneId, {
        ...scene,
        expectedRevision: scene.revision,
      }),
      { status: 409 },
    );
  });
  const refreshing = library.current().refreshSceneLibraryItem(scene.sceneId);
  await act(async () => {
    assert.equal(
      await library.current().deleteSceneLibraryItem(scene.sceneId, 2, () => {}),
      true,
    );
  });
  assert.deepEqual(library.current().savedScenes, []);
  await act(async () => {
    resolveOldRead({ ...scene, revision: 2 });
    assert.equal(await refreshing, null);
  });
  assert.deepEqual(library.current().savedScenes, []);
  assert.equal(library.current().getSceneBinding(), null);
});
