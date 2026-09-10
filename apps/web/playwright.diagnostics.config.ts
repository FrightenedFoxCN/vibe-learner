import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests/browser",
  testMatch: "diagnostics-live.spec.ts",
  workers: 1,
  reporter: [["list"], ["json", { outputFile: "/tmp/unified-debug-browser-report.json" }]],
  use: { baseURL: "http://127.0.0.1:3417", trace: "retain-on-failure" },
  outputDir: "/tmp/unified-debug-browser-results",
  webServer: [
    { command: "npm run start -- --hostname 127.0.0.1 --port 3417", url: "http://127.0.0.1:3417", timeout: 30000 },
    { command: "cd ../../services/ai && UV_CACHE_DIR=/tmp/vibe-learner-uv-cache uv run python -m tests.diagnostic_browser_server", url: "http://127.0.0.1:18998/health", timeout: 30000 },
  ],
});
