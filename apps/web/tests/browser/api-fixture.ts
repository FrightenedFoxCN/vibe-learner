import type { Page } from "@playwright/test";

export async function observeRequests(page: Page) {
  const requests: { method: string; path: string }[] = [];
  await page.addInitScript(() => {
    window.__VIBE_LEARNER_DESKTOP_CONFIG__ = { aiBaseUrl: "http://127.0.0.1:18999", isDesktop: false, platform: "unknown", secretStorageMode: "plain_text", vaultState: "unconfigured", vaultPath: "", storageRoot: "", startupError: "" };
  });
  await page.route("http://127.0.0.1:18999/**", async route => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    requests.push({ method: request.method(), path });
    let json: unknown = { items: [] };
    if (path === "/personas") json = { items: [{
      id: "fixture-mentor", revision: 1, name: "Fixture Mentor", source: "builtin",
      summary: "Tutor", relationship: "Teacher", learner_address: "Student", system_prompt: "Teach",
      reference_hints: [], slots: [], available_emotions: ["calm"], available_actions: ["point"],
      default_speech_style: "clear",
    }] };
    if (path === "/runtime-settings") json = { plan_provider: "mock" };
    if (path === "/model-tools/config" || path === "/model-usage/stats") json = {};
    if (path === "/tavern/rooms") json = { contract_version: "tavern-room-list-v1", items: [], next_cursor: null };
    await route.fulfill({ json });
  });
  return requests;
}
