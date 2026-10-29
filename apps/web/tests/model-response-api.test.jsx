import { dom } from "./support/dom.js";
import assert from "node:assert/strict";
import { after, test } from "node:test";
import {
  getRuntimeSettings,
  updateRuntimeSettings,
  applyRuntimeSessionSecrets,
  clearRuntimeSessionSecrets,
  probeRuntimeOpenAIModels,
} from "../lib/data/runtime-settings.ts";
import {
  getModelToolConfig,
  updateModelToolConfig,
} from "../lib/data/model-tools.ts";
import { getModelUsageStats } from "../lib/data/model-usage.ts";
import {
  diagnosticSnapshot,
  registerDiagnosticPage,
} from "../lib/diagnostics.ts";
import { ModelResponseDecodeError } from "../lib/model-response-decode.ts";

after(() => dom.window.close());

test("all configuration reads and writes reject malformed responses once and retain request diagnostics", async () => {
  const original = globalThis.fetch;
  const page = registerDiagnosticPage("/settings");
  const cases = [
    [getRuntimeSettings, "runtime-settings-response-v1", "/runtime-settings"],
    [
      () => updateRuntimeSettings({ showDebugInfo: false }),
      "runtime-settings-response-v1",
      "/runtime-settings",
    ],
    [
      () => applyRuntimeSessionSecrets({ openaiApiKey: "PRIVATE_SENTINEL" }),
      "runtime-settings-response-v1",
      "/runtime-settings/session-secrets",
    ],
    [
      clearRuntimeSessionSecrets,
      "runtime-settings-response-v1",
      "/runtime-settings/session-secrets",
    ],
    [
      getModelToolConfig,
      "model-tool-config-response-v1",
      "/model-tools/config",
    ],
    [
      () =>
        updateModelToolConfig([
          {
            stageName: "study_chat",
            toolName: "read_page_range_content",
            enabled: false,
          },
        ]),
      "model-tool-config-response-v1",
      "/model-tools/config",
    ],
    [
      () =>
        probeRuntimeOpenAIModels({
          apiKey: "PRIVATE_SENTINEL",
          baseUrl: "https://example.invalid",
          model: "fixture",
          features: ["plan"],
        }),
      "runtime-model-probe-response-v1",
      "/runtime-settings/check-openai-models",
    ],
    [getModelUsageStats, "model-usage-stats-response-v1", "/model-usage/stats"],
  ];
  try {
    for (const [index, [invoke, contract, path]] of cases.entries()) {
      let calls = 0;
      const requestId = `model_decode_${index}`;
      globalThis.fetch = async (url) => {
        calls++;
        assert.equal(new URL(url).pathname, path);
        return Response.json(null, { headers: { "X-Request-ID": requestId } });
      };
      await assert.rejects(invoke(), ModelResponseDecodeError);
      assert.equal(
        calls,
        1,
        "failed mutation read-back must not replay the write",
      );
      const events = diagnosticSnapshot().events.filter(
        (event) =>
          event.request_id === requestId && event.name === "decode_failed",
      );
      assert.equal(events.length, 1);
      assert.equal(events[0].decode_contract, contract);
      assert.equal(events[0].page_view_id, page.id);
      assert.ok(events[0].decode_path);
    }
    assert.ok(
      !JSON.stringify(diagnosticSnapshot()).includes("PRIVATE_SENTINEL"),
    );
  } finally {
    globalThis.fetch = original;
    page.dispose();
  }
});
