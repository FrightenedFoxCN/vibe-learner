import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests/browser",
  testMatch: "settings-decode.spec.ts",
  workers: 1,
  reporter: "list",
  outputDir: "/tmp/vibe-settings-decode-browser",
  use: { baseURL: "http://127.0.0.1:3419", trace: "retain-on-failure" },
  webServer: {
    command: "npm run dev -- --hostname 127.0.0.1 --port 3419",
    url: "http://127.0.0.1:3419",
    timeout: 60_000,
    env: { NEXT_TELEMETRY_DISABLED: "1" },
  },
});
