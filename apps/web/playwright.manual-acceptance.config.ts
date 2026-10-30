import { defineConfig } from "@playwright/test";

// Reuse the existing production Web; this suite never starts or builds Next.
// Start the disposable manual_acceptance_server.py separately on 18996.
export default defineConfig({
  testDir: "./tests/browser",
  testMatch: "manual-acceptance*.spec.ts",
  workers: 1,
  retries: 0,
  timeout: 90_000,
  expect: { timeout: 15_000 },
  reporter: [
    ["list"],
    ["json", { outputFile: "/tmp/vibe-manual-acceptance/results.json" }],
  ],
  outputDir: "/tmp/vibe-manual-acceptance/browser",
  use: {
    baseURL: "http://127.0.0.1:13417",
    actionTimeout: 15_000,
    navigationTimeout: 30_000,
    viewport: { width: 1440, height: 1000 },
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
});
