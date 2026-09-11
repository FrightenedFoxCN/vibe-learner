import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./tests/browser",
  testMatch: ["scene-dialog.spec.ts", "scene-dialog-independent.spec.ts"],
  workers: 1,
  reporter: [["list"], ["json", { outputFile: "/tmp/vibe-scene-independent-report.json" }]],
  use: { baseURL: "http://127.0.0.1:3428", trace: "retain-on-failure" },
  outputDir: "/tmp/vibe-scene-independent-results",
});
