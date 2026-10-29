import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./tests/browser",
  testMatch: "document-checkpoint.spec.ts",
  workers: 1,
  reporter: "list",
  outputDir: "/tmp/vibe-document-checkpoint-browser",
  use: { baseURL: "http://127.0.0.1:3422", trace: "retain-on-failure" },
  webServer: {
    command: "npm run dev -- --hostname 127.0.0.1 --port 3422",
    url: "http://127.0.0.1:3422",
    timeout: 60000,
    env: { NEXT_TELEMETRY_DISABLED: "1" },
  },
});
