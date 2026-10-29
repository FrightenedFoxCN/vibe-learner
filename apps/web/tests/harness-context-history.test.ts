import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { HISTORICAL_HARNESS_CONTEXT_PROFILES } from "../../../packages/shared/src/harness-context-history.ts";
import { decodeVersionedHarnessTrace } from "../lib/harness-trace-decode.ts";

const read = (name: string) =>
  JSON.parse(
    readFileSync(
      new URL(`../../../packages/shared/fixtures/harness/${name}`, import.meta.url),
      "utf8",
    ),
  );

test("browser history profiles match Python's golden and decode actual archived v3 traces", () => {
  assert.deepEqual(
    HISTORICAL_HARNESS_CONTEXT_PROFILES,
    read("context-history-v1.json").profiles,
  );
  for (const raw of read("context-history-traces-v1.json").traces) {
    const decoded = decodeVersionedHarnessTrace(
      raw,
      "archived",
      "harness-trace-v3",
      (path, reason) => {
        throw new Error(`${path}: ${reason}`);
      },
    );
    assert.equal(decoded.context.contextDigest, raw.context.context_digest);
    for (const field of ["input_contract", "prompt_contract", "component_versions"]) {
      const forged = structuredClone(raw);
      if (forged.context[field] === null) continue;
      if (Array.isArray(forged.context[field]))
        forged.context[field][0].version = "forged-component-v999";
      else forged.context[field].version += "-mixed";
      assert.throws(() =>
        decodeVersionedHarnessTrace(
          forged,
          "forged",
          "harness-trace-v3",
          (path, reason) => {
            throw new Error(`${path}: ${reason}`);
          },
        ),
      );
    }
  }
  assert.equal(Object.isFrozen(HISTORICAL_HARNESS_CONTEXT_PROFILES), true);
  assert.equal(
    Object.isFrozen(HISTORICAL_HARNESS_CONTEXT_PROFILES[0].component_versions),
    true,
  );
});
