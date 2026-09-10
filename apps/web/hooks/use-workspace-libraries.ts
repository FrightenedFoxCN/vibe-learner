"use client";

import { useEffect, useRef, useState } from "react";
import type { PersonaProfile, SceneProfile } from "@vibe-learner/shared";
import { listPersonas } from "../lib/data/personas";
import { listSceneLibrary, type SceneLibraryItemPayload } from "../lib/data/scenes";
import { PERSONA_LIBRARY_UPDATED_EVENT, isPersonaLibraryStorageEvent } from "../lib/persona-library-sync";
import { logWorkspaceError } from "../lib/learning-workspace-telemetry";

interface WorkspaceLibraryOptions {
  initialSceneId?: string;
  planScene?: SceneProfile | null;
  onPersonas: (personas: PersonaProfile[]) => void;
}
export interface WorkspaceLibraryPort {
  listPersonas: typeof listPersonas;
  listSceneLibrary: typeof listSceneLibrary;
}
const defaultPort: WorkspaceLibraryPort = { listPersonas, listSceneLibrary };

export function useWorkspaceLibraries(options: WorkspaceLibraryOptions, port: WorkspaceLibraryPort = defaultPort) {
  const [sceneLibraryItems, setSceneLibraryItems] = useState<SceneLibraryItemPayload[]>([]);
  const [selectedSceneLibraryId, setSelectedSceneLibraryId] = useState(options.initialSceneId ?? "");
  const callbacks = useRef(options); callbacks.current = options;
  const mounted = useRef(false);
  const personaSequence = useRef(0), sceneSequence = useRef(0);

  async function refreshPersonaLibrary() {
    if (!mounted.current) return;
    const sequence = ++personaSequence.current;
    try {
      const personas = await port.listPersonas();
      if (mounted.current && sequence === personaSequence.current) callbacks.current.onPersonas(personas);
    } catch (error) {
      if (mounted.current && sequence === personaSequence.current) logWorkspaceError("workflow:persona_library:refresh_error", error);
    }
  }
  async function refreshSceneLibrary() {
    if (!mounted.current) return;
    const sequence = ++sceneSequence.current;
    try {
      const items = await port.listSceneLibrary();
      if (!mounted.current || sequence !== sceneSequence.current) return;
      setSceneLibraryItems(items);
      setSelectedSceneLibraryId(current => current && items.some(item => item.sceneId === current) ? current : items[0]?.sceneId ?? "");
    } catch (error) {
      if (mounted.current && sequence === sceneSequence.current) logWorkspaceError("workflow:scene_library:refresh_error", error);
    }
  }
  useEffect(() => {
    mounted.current = true;
    void refreshSceneLibrary();
    const updated = () => { void refreshPersonaLibrary(); };
    const storage = (event: StorageEvent) => { if (isPersonaLibraryStorageEvent(event)) updated(); };
    window.addEventListener(PERSONA_LIBRARY_UPDATED_EVENT, updated);
    window.addEventListener("storage", storage);
    return () => {
      mounted.current = false; ++personaSequence.current; ++sceneSequence.current;
      window.removeEventListener(PERSONA_LIBRARY_UPDATED_EVENT, updated);
      window.removeEventListener("storage", storage);
    };
  }, []);
  useEffect(() => {
    if (!options.planScene || selectedSceneLibraryId) return;
    const matched = sceneLibraryItems.find(item => item.sceneName === options.planScene?.sceneName);
    if (matched) setSelectedSceneLibraryId(matched.sceneId);
  }, [options.planScene, sceneLibraryItems, selectedSceneLibraryId]);
  return { sceneLibraryItems, selectedSceneLibraryId, setSelectedSceneLibraryId, refreshPersonaLibrary, refreshSceneLibrary };
}
