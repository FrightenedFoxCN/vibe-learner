export const APP_NAV_COLLAPSED_STORAGE_KEY = "vibe-nav-collapsed";
export const DEBUG_OVERLAY_OPEN_STORAGE_KEY = "vibe-debug-overlay-open";

export const BROWSER_VIEW_TOGGLE_NAV_EVENT = "vibe:view:toggle-nav";
export const BROWSER_VIEW_TOGGLE_DEBUG_OVERLAY_EVENT = "vibe:view:toggle-debug-overlay";

export const TAURI_VIEW_TOGGLE_NAV_EVENT = "desktop-view-toggle-sidebar";
export const TAURI_VIEW_TOGGLE_DEBUG_OVERLAY_EVENT = "desktop-view-toggle-debug-overlay";

export function readStoredBoolean(key: string) {
  if (typeof window === "undefined") {
    return false;
  }
  return window.localStorage.getItem(key) === "1";
}

export function writeStoredBoolean(key: string, value: boolean) {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.setItem(key, value ? "1" : "0");
}

export function dispatchBrowserViewToggle(eventName: string) {
  if (typeof window === "undefined") {
    return;
  }
  window.dispatchEvent(new Event(eventName));
}
