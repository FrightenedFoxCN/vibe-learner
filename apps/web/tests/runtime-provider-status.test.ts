import assert from "node:assert/strict";
import test from "node:test";
import { runtimeProviderStatus } from "../lib/runtime-provider-status.ts";

const noKeys = {
  planProvider: "litellm" as const,
  openaiApiKeyConfigured: false,
  openaiPlanApiKeyConfigured: false,
  openaiSettingApiKeyConfigured: false,
  openaiChatApiKeyConfigured: false,
};

test("provider fallback only applies when every effective key is absent", () => {
  assert.deepEqual(runtimeProviderStatus({ ...noKeys, planProvider: "mock" }), {
    provider: "mock",
    missing: [],
  });
  assert.deepEqual(runtimeProviderStatus(noKeys), {
    provider: "mock",
    missing: ["计划", "人格与场景", "对话与酒馆"],
  });
  assert.deepEqual(
    runtimeProviderStatus({ ...noKeys, openaiChatApiKeyConfigured: true }),
    { provider: "litellm", missing: ["计划", "人格与场景"] },
  );
  assert.deepEqual(
    runtimeProviderStatus({
      ...noKeys,
      openaiApiKeyConfigured: true,
      openaiPlanApiKeyConfigured: true,
      openaiSettingApiKeyConfigured: true,
      openaiChatApiKeyConfigured: true,
    }),
    { provider: "litellm", missing: [] },
  );
});
