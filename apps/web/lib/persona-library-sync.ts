export const PERSONA_LIBRARY_UPDATED_EVENT = "vibe:persona-library-updated";
export const PERSONA_LIBRARY_VERSION_STORAGE_KEY = "vibe-persona-library-version";

export function broadcastPersonaLibraryUpdated() {
  if (typeof window === "undefined") {
    return;
  }

  const version = String(Date.now());
  try {
    window.localStorage.setItem(PERSONA_LIBRARY_VERSION_STORAGE_KEY, version);
  } catch {
    // Ignore storage write failures in restrictive browser modes.
  }
  window.dispatchEvent(
    new CustomEvent(PERSONA_LIBRARY_UPDATED_EVENT, {
      detail: { version }
    })
  );
}

export function isPersonaLibraryStorageEvent(event: StorageEvent) {
  return event.key === PERSONA_LIBRARY_VERSION_STORAGE_KEY && Boolean(event.newValue);
}
