import { defineConfig } from "@playwright/test";

// Starts the already-built production bundle. Never invokes dev or build.
export default defineConfig({
  testDir: "./tests/browser",
  testMatch: "remaining-recovery.spec.ts",
  workers: 1,
  retries: 0,
  timeout: 30_000,
  reporter: [
    ["list"],
    ["json", { outputFile: "/tmp/vibe-browser-recovery-final/report.json" }],
  ],
  outputDir: "/tmp/vibe-browser-recovery-final/results",
  use: {
    baseURL: "http://127.0.0.1:13417",
    browserName: "chromium",
    serviceWorkers: "block",
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
  },
  projects: [
    { name: "desktop-chromium", use: { viewport: { width: 1440, height: 960 } } },
    // A desktop Chromium viewport, not a physical touch/IME device.
    { name: "narrow-chromium", use: { viewport: { width: 390, height: 844 } } },
  ],
  webServer: {
    command: "npm run start -- --hostname 127.0.0.1 --port 13417",
    url: "http://127.0.0.1:13417",
    reuseExistingServer: false,
    timeout: 30_000,
    gracefulShutdown: { signal: "SIGTERM", timeout: 5000 },
    env: { NEXT_TELEMETRY_DISABLED: "1" },
  },
});
