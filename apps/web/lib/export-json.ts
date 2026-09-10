"use client";

import { observeLocalAction } from "./diagnostic-actions.ts";
import { getDesktopRuntimeConfig } from "./runtime-config";

export async function exportJson(filename: string, payload: unknown): Promise<boolean> {
  return observeLocalAction("json_export_handoff", async () => {
    const contents = JSON.stringify(payload, null, 2);
    if (getDesktopRuntimeConfig()?.isDesktop) {
      const { invoke } = await import("@tauri-apps/api/core");
      return invoke<boolean>("desktop_export_json", { filename, contents });
    }
    const url = URL.createObjectURL(new Blob([contents], { type: "application/json" }));
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = filename;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    // Allow the browser to consume the download before releasing its source.
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    return true;
  }, { cancelled: saved => !saved });
}
