import { defineConfig } from "@playwright/test";
import { fileURLToPath } from "node:url";

export default defineConfig({
  testDir: "./tests/browser",
  testMatch: "study-recovery-live.spec.ts",
  workers: 1,
  reporter: "list",
  outputDir: "/tmp/vibe-study-recovery-browser",
  use: { baseURL: "http://127.0.0.1:3435", trace: "retain-on-failure" },
  webServer: [
    {
      command: "uv run --frozen python tests/acceptance/study_recovery_server.py",
      cwd: fileURLToPath(new URL("../../services/ai", import.meta.url)),
      url: "http://127.0.0.1:18445/health",
      timeout: 60000,
      env: {
        PYTHONPATH: ".",
        LITELLM_LOCAL_MODEL_COST_MAP: "True",
        UV_CACHE_DIR: "/tmp/vibe-learner-uv-cache",
      },
    },
    {
      command: "npm run dev -- --hostname 127.0.0.1 --port 3435",
      url: "http://127.0.0.1:3435",
      timeout: 60000,
      env: {
        NEXT_TELEMETRY_DISABLED: "1",
        NEXT_PUBLIC_AI_BASE_URL: "http://127.0.0.1:18445",
      },
    },
  ],
});
