import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests/browser",
  testMatch: "study-unit-revision.spec.ts",
  workers: 1,
  reporter: "list",
  outputDir: "/tmp/vibe-study-unit-revision-browser",
  use: { baseURL: "http://127.0.0.1:3418", trace: "retain-on-failure" },
  webServer: {
    command: "npm run dev -- --hostname 127.0.0.1 --port 3418",
    url: "http://127.0.0.1:3418",
    timeout: 60_000,
    env: { NEXT_TELEMETRY_DISABLED: "1" },
  },
});
