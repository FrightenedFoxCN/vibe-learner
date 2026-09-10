"use client";

import { useEffect, useRef, useState } from "react";
import * as api from "../lib/data/scenes";

type SceneLibraryPort = Pick<typeof api, "listSceneLibrary" | "listReusableSceneNodes" | "createSceneLibraryItem" | "updateSceneLibraryItem" | "deleteSceneLibraryItem" | "createReusableSceneNode" | "deleteReusableSceneNode">;

// A late initial list is reconciled with successful local writes and deletions.
// Failed writes never enter this projection, and unmounted owners ignore it.
function useLibraryCollection<T>(load: () => Promise<T[]>, identity: (item: T) => string) {
  const [items, setItems] = useState<T[]>([]);
  const [error, setError] = useState("");
  const active = useRef(true);
  const committed = useRef(new Map<string, T | null>());
  useEffect(() => {
    active.current = true;
    let current = true;
    void load().then(snapshot => {
      if (!current) return;
      const merged = new Map(snapshot.map(item => [identity(item), item]));
      for (const [id, item] of committed.current) item === null ? merged.delete(id) : merged.set(id, item);
      setItems([...merged.values()]);
    }).catch(reason => { if (current) setError(String(reason)); });
    return () => { current = false; active.current = false; };
  }, []);
  function apply(id: string, item: T | null) {
    if (!active.current) return;
    committed.current.set(id, item);
    setItems(current => item === null
      ? current.filter(value => identity(value) !== id)
      : current.some(value => identity(value) === id)
        ? current.map(value => identity(value) === id ? item : value)
        : [item, ...current]);
  }
  return { items, error, apply, active };
}

export function useSceneLibrary(port: SceneLibraryPort = api) {
  const scenes = useLibraryCollection(port.listSceneLibrary, item => item.sceneId);
  const nodes = useLibraryCollection(port.listReusableSceneNodes, item => item.nodeId);
  const [selectedSavedSceneId, setSelectedId] = useState("");
  const selection = useRef({ id: "", revision: 0 });
  const pending = useRef(new Set<string>());
  const [reusableActionPendingId, setReusableActionPendingId] = useState("");
  const [reusableMessage, setReusableMessage] = useState("");
  const [reusableError, setReusableError] = useState("");
  const reusableRequest = useRef(0);
  useEffect(() => {
    if (!selection.current.id && selection.current.revision === 0 && scenes.items[0]) {
      selection.current.id = scenes.items[0].sceneId;
      setSelectedId(selection.current.id);
    }
  }, [scenes.items]);
  function setSelectedSavedSceneId(id: string) {
    selection.current = { id, revision: selection.current.revision + 1 };
    setSelectedId(id);
  }
  async function mutate<T>(key: string, operation: () => Promise<T>): Promise<T> {
    if (!scenes.active.current) throw new Error("scene_library_unmounted");
    if (pending.current.has(key)) throw new Error("scene_library_write_in_progress");
    pending.current.add(key);
    try { return await operation(); }
    finally { pending.current.delete(key); }
  }
  const createSceneLibraryItem: typeof api.createSceneLibraryItem = (input, context) => mutate("scene:create", async () => {
    const revision = selection.current.revision;
    const created = await port.createSceneLibraryItem(input, context);
    scenes.apply(created.sceneId, created);
    if (scenes.active.current && selection.current.revision === revision) setSelectedSavedSceneId(created.sceneId);
    return created;
  });
  const updateSceneLibraryItem: typeof api.updateSceneLibraryItem = (id, input, context) => mutate(`scene:${id}`, async () => {
    const updated = await port.updateSceneLibraryItem(id, input, context);
    scenes.apply(updated.sceneId, updated);
    return updated;
  });
  const deleteSceneLibraryItem: typeof api.deleteSceneLibraryItem = id => mutate(`scene:${id}`, async () => {
    const result = await port.deleteSceneLibraryItem(id);
    scenes.apply(id, null);
    if (scenes.active.current && selection.current.id === id) setSelectedSavedSceneId("");
    return result;
  });
  const createReusableSceneNode: typeof api.createReusableSceneNode = input => mutate(`node:create:${input.nodeType}:${input.reuseId}`, async () => {
    const created = await port.createReusableSceneNode(input);
    nodes.apply(created.nodeId, created);
    return created;
  });
  const deleteReusableSceneNode: typeof api.deleteReusableSceneNode = id => mutate(`node:${id}`, async () => {
    const result = await port.deleteReusableSceneNode(id);
    nodes.apply(id, null);
    return result;
  });
  async function runReusableAction(id: string, message: string, action: () => Promise<unknown>) {
    if (!nodes.active.current) return;
    const request = ++reusableRequest.current;
    setReusableError(""); setReusableMessage(""); setReusableActionPendingId(id);
    try {
      await action();
      if (nodes.active.current && request === reusableRequest.current) setReusableMessage(message);
    } catch (error) {
      if (nodes.active.current && request === reusableRequest.current) setReusableError(String(error));
    } finally {
      if (nodes.active.current && request === reusableRequest.current) setReusableActionPendingId("");
    }
  }
  return {
    savedScenes: scenes.items, reusableNodes: nodes.items,
    libraryError: [scenes.error, nodes.error].filter(Boolean).join("；"),
    selectedSavedSceneId, setSelectedSavedSceneId,
    createSceneLibraryItem, updateSceneLibraryItem, deleteSceneLibraryItem,
    createReusableSceneNode, deleteReusableSceneNode,
    reusableActionPendingId, reusableMessage, reusableError,
    setReusableMessage, setReusableError, runReusableAction,
  };
}
