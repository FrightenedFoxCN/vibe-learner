import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import {
  SETTINGS_RESPONSE_CONTRACTS,
  RUNTIME_CAPABILITY_STATUSES,
  RUNTIME_CAPABILITY_SOURCES,
  RUNTIME_READINESS_STATUSES,
  RUNTIME_PROBE_FEATURES,
} from "@vibe-learner/shared/settings-response-contracts";
import {
  decodeRuntimeSettings,
  decodeRuntimeModelProbe,
} from "../lib/runtime-settings-decode.ts";
import { decodeModelToolConfig } from "../lib/model-tools-decode.ts";
import { decodeModelUsageStats } from "../lib/model-usage-decode.ts";
import { ModelResponseDecodeError } from "../lib/model-response-decode.ts";

const fixture = JSON.parse(
  readFileSync(
    new URL(
      "../../../packages/shared/fixtures/settings/responses-v1.json",
      import.meta.url,
    ),
    "utf8",
  ),
);
const copy = (key: string) => structuredClone(fixture[key]);

test("shared enums and versions match Python-owned response fixtures", () => {
  assert.deepEqual(SETTINGS_RESPONSE_CONTRACTS, fixture.contracts);
  assert.deepEqual(
    RUNTIME_CAPABILITY_STATUSES,
    fixture.vocabularies.capability_statuses,
  );
  assert.deepEqual(
    RUNTIME_CAPABILITY_SOURCES,
    fixture.vocabularies.capability_sources,
  );
  assert.deepEqual(
    RUNTIME_READINESS_STATUSES,
    fixture.vocabularies.readiness_statuses,
  );
  assert.deepEqual(RUNTIME_PROBE_FEATURES, fixture.vocabularies.probe_features);
  assert.equal(
    decodeRuntimeSettings(copy("runtime_settings")).openaiChatTemperature,
    0.35,
  );
  assert.equal(
    decodeModelToolConfig(copy("model_tools")).stages[0].tools[0]
      .effectiveEnabled,
    false,
  );
  assert.equal(
    decodeRuntimeModelProbe(copy("model_probe"), {
      model: "fixture-model",
      features: ["plan"],
    }).featureReadiness.plan?.status,
    "ready",
  );
  const usage = decodeModelUsageStats(copy("model_usage"));
  assert.equal(usage.totalTokens, 207); // Independent provider counter, not input + output.
  assert.equal(usage.totalPromptTokens, 150);
});

test("scalar, missing, null, and unsupported versions fail every domain", () => {
  for (const [key, decode] of [
    ["runtime_settings", decodeRuntimeSettings],
    ["model_tools", decodeModelToolConfig],
    ["model_probe", decodeRuntimeModelProbe],
    ["model_usage", decodeModelUsageStats],
  ] as const) {
    for (const value of [
      null,
      [],
      true,
      "false",
      5,
      {},
      { ...copy(key), contract_version: null },
      { ...copy(key), contract_version: "future" },
    ]) {
      assert.throws(() => decode(value), ModelResponseDecodeError);
    }
  }
});

test("settings reject coercion, unknown provider, and invalid model limits", () => {
  for (const [key, invalid] of [
    ["show_debug_info", "false"],
    ["openai_chat_model_multimodal", 1],
    ["openai_api_key_configured", null],
    ["openai_api_key", false],
    ["plan_provider", "surprise"],
    ["openai_plan_model", 17],
    ["openai_chat_temperature", Number.NaN],
    ["openai_setting_temperature", Infinity],
    ["openai_chat_temperature", 2.1],
    ["openai_chat_history_messages", 0],
    ["openai_timeout_seconds", "30"],
    ["openai_chat_max_tokens", 63],
    ["openai_setting_max_tokens", 16385],
    ["openai_chat_tool_max_rounds", 1.5],
  ]) {
    assert.throws(
      () =>
        decodeRuntimeSettings({
          ...copy("runtime_settings"),
          [key as string]: invalid,
        }),
      ModelResponseDecodeError,
    );
  }
  const missing = copy("runtime_settings");
  delete missing.openai_timeout_seconds;
  assert.throws(() => decodeRuntimeSettings(missing), ModelResponseDecodeError);
});

test("tool config rejects string booleans, duplicate identity, and contradictory gates", () => {
  for (const key of ["enabled", "available", "effective_enabled"]) {
    const raw = copy("model_tools");
    raw.stages[0].tools[0][key] = "false";
    assert.throws(() => decodeModelToolConfig(raw), ModelResponseDecodeError);
  }
  for (const mutate of [
    (r: any) => {
      r.stages[0].stage_enabled = "false";
    },
    (r: any) => {
      r.stages[0].tools[0].effective_enabled = true;
    },
    (r: any) => {
      r.stages[0].stage_enabled = false;
      r.stages[0].tools[0].available = true;
    },
    (r: any) => {
      r.stages[0].tools[0].audit_basis = [5];
    },
    (r: any) => {
      r.stages[0].tools.push(r.stages[0].tools[0]);
    },
    (r: any) => {
      r.stages.push(r.stages[0]);
    },
    (r: any) => {
      delete r.stages[0].tools[0].available;
    },
  ]) {
    const raw = copy("model_tools");
    mutate(raw);
    assert.throws(() => decodeModelToolConfig(raw), ModelResponseDecodeError);
  }
});

test("probe keeps listing and readiness independent and rejects unknown or foreign results", () => {
  const callable = copy("model_probe");
  callable.available = false;
  callable.models = [];
  callable.capabilities = {};
  assert.equal(
    decodeRuntimeModelProbe(callable, {
      model: "fixture-model",
      features: ["plan"],
    }).featureReadiness.plan?.status,
    "ready",
  );
  for (const mutate of [
    (r: any) => {
      r.available = "false";
    },
    (r: any) => {
      r.models = [5];
    },
    (r: any) => {
      r.capabilities = [];
    },
    (r: any) => {
      r.capabilities["fixture-model"].multimodal.status = "maybe";
    },
    (r: any) => {
      r.capabilities["fixture-model"].web_search.source = "provider_claim";
    },
    (r: any) => {
      r.feature_readiness.plan.status = "success";
    },
    (r: any) => {
      r.feature_readiness.plan.model = "foreign";
    },
    (r: any) => {
      r.feature_readiness.foreign = r.feature_readiness.plan;
    },
    (r: any) => {
      r.feature_readiness.study = r.feature_readiness.plan;
    },
    (r: any) => {
      delete r.feature_readiness.plan;
    },
    (r: any) => {
      r.models = [];
    },
  ]) {
    const raw = copy("model_probe");
    mutate(raw);
    assert.throws(
      () =>
        decodeRuntimeModelProbe(raw, {
          model: "fixture-model",
          features: ["plan"],
        }),
      ModelResponseDecodeError,
    );
  }
});

test("usage rejects non-finite, negative, fractional, string and unsafe counts and false aggregates", () => {
  for (const count of [
    "10",
    null,
    true,
    -1,
    1.5,
    Infinity,
    Number.NaN,
    Number.MAX_SAFE_INTEGER + 1,
  ]) {
    for (const target of ["bucket", "record", "total"]) {
      const raw = copy("model_usage");
      if (target === "bucket") raw.buckets[0].prompt_tokens = count;
      if (target === "record") raw.records[0].completion_tokens = count;
      if (target === "total") raw.total_tokens = count;
      assert.throws(() => decodeModelUsageStats(raw), ModelResponseDecodeError);
    }
  }
  for (const mutate of [
    (r: any) => {
      r.total_tokens++;
    },
    (r: any) => {
      r.records[0].prompt_tokens++;
    },
    (r: any) => {
      r.buckets.push(r.buckets[0]);
    },
    (r: any) => {
      r.records[1].id = r.records[0].id;
    },
  ]) {
    const raw = copy("model_usage");
    mutate(raw);
    assert.throws(() => decodeModelUsageStats(raw), ModelResponseDecodeError);
  }
});

test("legacy defaults apply only to documented absent fields, never to malformed present values", () => {
  const settings = copy("runtime_settings");
  delete settings.contract_version;
  for (const name of [
    "openai_api_key_configured",
    "openai_plan_api_key_configured",
    "openai_setting_api_key_configured",
    "openai_chat_api_key_configured",
  ])
    delete settings[name];
  settings.plan_provider = "openai";
  assert.equal(decodeRuntimeSettings(settings).planProvider, "litellm");
  assert.equal(decodeRuntimeSettings(settings).openaiApiKeyConfigured, false);
  delete settings.openai_chat_max_tokens;
  assert.throws(
    () => decodeRuntimeSettings(settings),
    ModelResponseDecodeError,
  );
  const probe = {
    available: true,
    models: ["model"],
    capabilities: { model: {} },
  };
  assert.equal(
    decodeRuntimeModelProbe(probe).capabilities.model.multimodal.status,
    "unknown",
  );
  assert.throws(
    () => decodeRuntimeModelProbe({ ...probe, feature_readiness: null }),
    ModelResponseDecodeError,
  );
  const usage = copy("model_usage");
  delete usage.contract_version;
  delete usage.records;
  assert.deepEqual(decodeModelUsageStats(usage).records, []);
  const current = copy("runtime_settings");
  delete current.openai_api_key_configured;
  assert.throws(() => decodeRuntimeSettings(current), ModelResponseDecodeError);
});
