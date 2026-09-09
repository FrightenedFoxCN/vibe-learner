import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests/browser",
  workers: 1,
  reporter: [["list"], ["json", { outputFile: "/tmp/vibe-learner-route-report.json" }]],
  use: { baseURL: "http://127.0.0.1:3417", trace: "retain-on-failure" },
  outputDir: "/tmp/vibe-learner-browser-results",
  webServer: {
    command: "npm run start -- --hostname 127.0.0.1 --port 3417",
    url: "http://127.0.0.1:3417",
    reuseExistingServer: false,
    timeout: 30_000,
  },
});
