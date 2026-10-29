import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests/browser",
  testMatch: ["tavern-copy-independent.spec.ts", "tavern-controller.spec.ts"],
  workers: 1,
  reporter: "list",
  outputDir: "/tmp/vibe-tavern-controller-browser",
  use: { baseURL: "http://127.0.0.1:3420", trace: "retain-on-failure" },
  webServer: {
    command: "npm run dev -- --hostname 127.0.0.1 --port 3420",
    url: "http://127.0.0.1:3420",
    timeout: 60_000,
    env: { NEXT_TELEMETRY_DISABLED: "1" },
  },
});
