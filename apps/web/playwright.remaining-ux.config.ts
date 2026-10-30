import { defineConfig } from "@playwright/test";

// Reuse an existing production server; this suite never builds or starts Next.
export default defineConfig({
  testDir: "./tests/browser",
  testMatch: "remaining-ux*.spec.ts",
  workers: 1,
  retries: 0,
  timeout: 30_000,
  reporter: [["list"], ["json", { outputFile: "/tmp/vibe-remaining-ux/report.json" }]],
  outputDir: "/tmp/vibe-remaining-ux/results",
  use: {
    baseURL: process.env.REMAINING_UX_BASE_URL ?? "http://127.0.0.1:13417",
    browserName: "chromium",
    serviceWorkers: "block",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    { name: "desktop-chromium", use: { viewport: { width: 1440, height: 960 } } },
    // A narrow desktop browser viewport; no real touch, IME or platform claim.
    { name: "narrow-chromium", use: { viewport: { width: 390, height: 844 } } },
  ],
});
