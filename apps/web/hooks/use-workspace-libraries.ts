"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { PersonaProfile, SceneProfile } from "@vibe-learner/shared";
import { listPersonas } from "../lib/data/personas";
import { listSceneLibrary, type SceneLibraryItemPayload } from "../lib/data/scenes";
import {
  PERSONA_LIBRARY_UPDATED_EVENT,
  isPersonaLibraryStorageEvent,
} from "../lib/persona-library-sync";
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

export function useWorkspaceLibraries(
  options: WorkspaceLibraryOptions,
  port: WorkspaceLibraryPort = defaultPort,
) {
  const { listPersonas: loadPersonas, listSceneLibrary: loadScenes } = port;
  const [sceneLibraryItems, setSceneLibraryItems] = useState<SceneLibraryItemPayload[]>(
    [],
  );
  const [selectedSceneLibraryId, setSelectedSceneLibraryId] = useState(
    options.initialSceneId ?? "",
  );
  const callbacks = useRef(options);
  callbacks.current = options;
  const mounted = useRef(false);
  const sceneSelectionTouched = useRef(Boolean(options.initialSceneId));
  const personaSequence = useRef(0),
    sceneSequence = useRef(0);
  const personaRead = useRef<Promise<void> | null>(null),
    sceneRead = useRef<Promise<void> | null>(null);

  const readPersonas = useCallback(async () => {
    const sequence = ++personaSequence.current;
    try {
      const personas = await loadPersonas();
      if (mounted.current && sequence === personaSequence.current)
        callbacks.current.onPersonas(personas);
    } catch (error) {
      if (mounted.current && sequence === personaSequence.current)
        logWorkspaceError("workflow:persona_library:refresh_error", error);
    }
  }, [loadPersonas]);
  const refreshPersonaLibrary = useCallback(
    ({ reuseInFlight = false } = {}): Promise<void> => {
      if (!mounted.current) return Promise.resolve();
      if (reuseInFlight && personaRead.current) return personaRead.current;
      const pending = readPersonas();
      personaRead.current = pending;
      void pending.finally(() => {
        if (personaRead.current === pending) personaRead.current = null;
      });
      return pending;
    },
    [readPersonas],
  );
  const readScenes = useCallback(async () => {
    const sequence = ++sceneSequence.current;
    try {
      const items = await loadScenes();
      if (!mounted.current || sequence !== sceneSequence.current) return;
      setSceneLibraryItems(items);
      setSelectedSceneLibraryId((current) =>
        current && items.some((item) => item.sceneId === current) ? current : "",
      );
    } catch (error) {
      if (mounted.current && sequence === sceneSequence.current)
        logWorkspaceError("workflow:scene_library:refresh_error", error);
    }
  }, [loadScenes]);
  const refreshSceneLibrary = useCallback(
    ({ reuseInFlight = false } = {}): Promise<void> => {
      if (!mounted.current) return Promise.resolve();
      if (reuseInFlight && sceneRead.current) return sceneRead.current;
      const pending = readScenes();
      sceneRead.current = pending;
      void pending.finally(() => {
        if (sceneRead.current === pending) sceneRead.current = null;
      });
      return pending;
    },
    [readScenes],
  );
  const invalidateReads = useCallback(() => {
    ++personaSequence.current;
    ++sceneSequence.current;
    personaRead.current = null;
    sceneRead.current = null;
  }, []);
  useEffect(() => {
    mounted.current = true;
    void refreshSceneLibrary();
    const updated = () => {
      void refreshPersonaLibrary();
    };
    const storage = (event: StorageEvent) => {
      if (isPersonaLibraryStorageEvent(event)) updated();
    };
    window.addEventListener(PERSONA_LIBRARY_UPDATED_EVENT, updated);
    window.addEventListener("storage", storage);
    return () => {
      mounted.current = false;
      invalidateReads();
      window.removeEventListener(PERSONA_LIBRARY_UPDATED_EVENT, updated);
      window.removeEventListener("storage", storage);
    };
  }, [invalidateReads, refreshPersonaLibrary, refreshSceneLibrary]);
  useEffect(() => {
    if (!options.planScene || selectedSceneLibraryId || sceneSelectionTouched.current)
      return;
    const matched = sceneLibraryItems.find(
      (item) => item.sceneName === options.planScene?.sceneName,
    );
    if (matched) setSelectedSceneLibraryId(matched.sceneId);
  }, [options.planScene, sceneLibraryItems, selectedSceneLibraryId]);
  const selectSceneLibraryId = useCallback((sceneId: string) => {
    sceneSelectionTouched.current = true;
    setSelectedSceneLibraryId(sceneId);
  }, []);
  return {
    sceneLibraryItems,
    selectedSceneLibraryId,
    setSelectedSceneLibraryId: selectSceneLibraryId,
    refreshPersonaLibrary,
    refreshSceneLibrary,
  };
}
