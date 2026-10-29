import { defineConfig } from "@playwright/test";
import tavernOrder from "./playwright.tavern-order.config";

export default defineConfig({
  ...tavernOrder,
  testMatch: "resource-requests-live.spec.ts",
  reporter: [
    ["list"],
    [
      "json",
      {
        outputFile: `/tmp/vibe-resource-requests-${process.env.WEB_DEDUPE_PHASE ?? "after"}-report.json`,
      },
    ],
  ],
  outputDir: `/tmp/vibe-resource-requests-${process.env.WEB_DEDUPE_PHASE ?? "after"}`,
});
