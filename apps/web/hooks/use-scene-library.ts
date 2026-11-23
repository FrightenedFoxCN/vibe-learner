"use client";

import { useEffect, useEffectEvent, useRef, useState } from "react";
import * as api from "../lib/data/scenes";
import { isApiHttpError } from "../lib/http-error";

type SceneLibraryPort = Pick<
  typeof api,
  | "listSceneLibrary"
  | "listReusableSceneNodes"
  | "createSceneLibraryItem"
  | "updateSceneLibraryItem"
  | "getSceneLibraryItem"
  | "deleteSceneLibraryItem"
  | "createReusableSceneNode"
  | "deleteReusableSceneNode"
>;

// A late initial list is reconciled with successful local writes and deletions.
// Failed writes never enter this projection, and unmounted owners ignore it.
function useLibraryCollection<T>(
  load: () => Promise<T[]>,
  identity: (item: T) => string,
) {
  const [items, setItems] = useState<T[]>([]);
  const [error, setError] = useState("");
  const active = useRef(true);
  const committed = useRef(new Map<string, T | null>());
  // Load the initial snapshot on mount, not when a write changes the collection.
  const loadInitialSnapshot = useEffectEvent((isCurrent: () => boolean) => {
    void load()
      .then((snapshot) => {
        if (!isCurrent()) return;
        const merged = new Map(snapshot.map((item) => [identity(item), item]));
        for (const [id, item] of committed.current)
          item === null ? merged.delete(id) : merged.set(id, item);
        setItems([...merged.values()]);
      })
      .catch((reason) => {
        if (isCurrent()) setError(String(reason));
      });
  });
  useEffect(() => {
    active.current = true;
    let current = true;
    loadInitialSnapshot(() => current);
    return () => {
      current = false;
      active.current = false;
    };
  }, []);
  function apply(id: string, item: T | null) {
    if (!active.current) return;
    committed.current.set(id, item);
    setItems((current) =>
      item === null
        ? current.filter((value) => identity(value) !== id)
        : current.some((value) => identity(value) === id)
          ? current.map((value) => (identity(value) === id ? item : value))
          : [item, ...current],
    );
  }
  return { items, error, apply, active };
}

export function useSceneLibrary(port: SceneLibraryPort = api) {
  const scenes = useLibraryCollection(port.listSceneLibrary, (item) => item.sceneId);
  const nodes = useLibraryCollection(
    port.listReusableSceneNodes,
    (item) => item.nodeId,
  );
  const [boundSceneId, setBoundSceneId] = useState("");
  const binding = useRef<{ sceneId: string; revision: number } | null>(null);
  const bindingEpoch = useRef(0);
  const pending = useRef(new Set<string>());
  const [reusableActionPendingId, setReusableActionPendingId] = useState("");
  const [reusableMessage, setReusableMessage] = useState("");
  const [reusableError, setReusableError] = useState("");
  const reusableRequest = useRef(0);
  function bindScene(target: typeof binding.current) {
    binding.current = target;
    bindingEpoch.current += 1;
    setBoundSceneId(target?.sceneId ?? "");
  }
  async function mutate<T>(key: string, operation: () => Promise<T>): Promise<T> {
    if (!scenes.active.current) throw new Error("scene_library_unmounted");
    if (pending.current.has(key)) throw new Error("scene_library_write_in_progress");
    pending.current.add(key);
    try {
      return await operation();
    } finally {
      pending.current.delete(key);
    }
  }
  const createSceneLibraryItem: typeof api.createSceneLibraryItem = (input, context) =>
    mutate("scene:create", async () => {
      const epoch = bindingEpoch.current;
      const created = await port.createSceneLibraryItem(input, context);
      scenes.apply(created.sceneId, created);
      if (scenes.active.current && bindingEpoch.current === epoch) bindScene(created);
      return created;
    });
  const updateSceneLibraryItem: typeof api.updateSceneLibraryItem = (
    id,
    input,
    context,
  ) =>
    mutate(`scene:${id}`, async () => {
      const epoch = bindingEpoch.current;
      const updated = await port.updateSceneLibraryItem(id, input, context);
      scenes.apply(updated.sceneId, updated);
      if (scenes.active.current && bindingEpoch.current === epoch) bindScene(updated);
      return updated;
    });
  function deleteSceneLibraryItem(
    id: string,
    expectedRevision: number,
    beforeRemove: () => void,
  ) {
    return mutate(`scene:${id}`, async () => {
      try {
        await port.deleteSceneLibraryItem(id, expectedRevision);
      } catch (error) {
        if (!isApiHttpError(error)) throw error;
        if (error.status === 409) {
          scenes.apply(id, await port.getSceneLibraryItem(id));
          return false;
        }
        if (error.status !== 404) throw error;
      }
      if (!scenes.active.current) return false;
      beforeRemove();
      scenes.apply(id, null);
      if (binding.current?.sceneId === id) bindScene(null);
      return true;
    });
  }
  const createReusableSceneNode: typeof api.createReusableSceneNode = (input) =>
    mutate(`node:create:${input.nodeType}:${input.reuseId}`, async () => {
      const created = await port.createReusableSceneNode(input);
      nodes.apply(created.nodeId, created);
      return created;
    });
  const deleteReusableSceneNode: typeof api.deleteReusableSceneNode = (id) =>
    mutate(`node:${id}`, async () => {
      const result = await port.deleteReusableSceneNode(id);
      nodes.apply(id, null);
      return result;
    });
  async function runReusableAction(
    id: string,
    message: string,
    action: () => Promise<unknown>,
  ) {
    if (!nodes.active.current) return;
    const request = ++reusableRequest.current;
    setReusableError("");
    setReusableMessage("");
    setReusableActionPendingId(id);
    try {
      await action();
      if (nodes.active.current && request === reusableRequest.current)
        setReusableMessage(message);
    } catch (error) {
      if (nodes.active.current && request === reusableRequest.current)
        setReusableError(String(error));
    } finally {
      if (nodes.active.current && request === reusableRequest.current)
        setReusableActionPendingId("");
    }
  }
  return {
    savedScenes: scenes.items,
    reusableNodes: nodes.items,
    libraryError: [scenes.error, nodes.error].filter(Boolean).join("；"),
    selectedSavedSceneId: boundSceneId,
    getSceneBinding: () => binding.current,
    bindScene,
    createSceneLibraryItem,
    updateSceneLibraryItem,
    deleteSceneLibraryItem,
    createReusableSceneNode,
    deleteReusableSceneNode,
    reusableActionPendingId,
    reusableMessage,
    reusableError,
    setReusableMessage,
    setReusableError,
    runReusableAction,
  };
}
