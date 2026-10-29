import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./tests/browser",
  testMatch: "planning-page-scope.spec.ts",
  workers: 1,
  reporter: "list",
  outputDir: "/tmp/vibe-page-scope-browser",
  use: { baseURL: "http://127.0.0.1:3421", trace: "retain-on-failure" },
  webServer: {
    command: "npm run dev -- --hostname 127.0.0.1 --port 3421",
    url: "http://127.0.0.1:3421",
    timeout: 60000,
    env: { NEXT_TELEMETRY_DISABLED: "1" },
  },
});
