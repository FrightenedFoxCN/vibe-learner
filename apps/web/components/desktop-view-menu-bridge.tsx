"use client";

import { useEffect } from "react";

import { getDesktopRuntimeConfig } from "../lib/runtime-config";
import {
  BROWSER_VIEW_TOGGLE_DEBUG_OVERLAY_EVENT,
  BROWSER_VIEW_TOGGLE_NAV_EVENT,
  dispatchBrowserViewToggle,
  TAURI_VIEW_TOGGLE_DEBUG_OVERLAY_EVENT,
  TAURI_VIEW_TOGGLE_NAV_EVENT
} from "../lib/view-preferences";

export function DesktopViewMenuBridge() {
  useEffect(() => {
    if (!getDesktopRuntimeConfig()?.isDesktop) {
      return;
    }

    let disposed = false;
    let unlistenCallbacks: Array<() => void> = [];

    void (async () => {
      const { listen } = await import("@tauri-apps/api/event");
      const unlistenNav = await listen(TAURI_VIEW_TOGGLE_NAV_EVENT, () => {
        dispatchBrowserViewToggle(BROWSER_VIEW_TOGGLE_NAV_EVENT);
      });
      const unlistenDebug = await listen(TAURI_VIEW_TOGGLE_DEBUG_OVERLAY_EVENT, () => {
        dispatchBrowserViewToggle(BROWSER_VIEW_TOGGLE_DEBUG_OVERLAY_EVENT);
      });

      if (disposed) {
        unlistenNav();
        unlistenDebug();
        return;
      }
      unlistenCallbacks = [unlistenNav, unlistenDebug];
    })();

    return () => {
      disposed = true;
      unlistenCallbacks.forEach((callback) => callback());
    };
  }, []);

  return null;
}
