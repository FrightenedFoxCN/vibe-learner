import { defineConfig } from "@playwright/test";
import { fileURLToPath } from "node:url";

export default defineConfig({
  testDir: "./tests/browser",
  testMatch: "tavern-order-live.spec.ts",
  workers: 1,
  reporter: [["list"], ["json", { outputFile: "/tmp/vibe-tavern-order-report.json" }]],
  outputDir: "/tmp/vibe-tavern-order-browser",
  use: { baseURL: "http://127.0.0.1:3437", trace: "retain-on-failure" },
  webServer: [
    {
      command: "uv run --frozen python tests/acceptance/tavern_order_server.py",
      cwd: fileURLToPath(new URL("../../services/ai", import.meta.url)),
      url: "http://127.0.0.1:18447/health",
      timeout: 60000,
      env: {
        PYTHONPATH: ".",
        LITELLM_LOCAL_MODEL_COST_MAP: "True",
        UV_CACHE_DIR: "/tmp/vibe-learner-uv-cache",
      },
    },
    {
      command: "npm run dev -- --hostname 127.0.0.1 --port 3437",
      url: "http://127.0.0.1:3437",
      timeout: 60000,
      env: {
        NEXT_TELEMETRY_DISABLED: "1",
        NEXT_PUBLIC_AI_BASE_URL: "http://127.0.0.1:18447",
      },
    },
  ],
});
