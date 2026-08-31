import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

import {
  TOOL_MANIFEST_BY_KEY,
  TOOL_MANIFEST_GOLDEN,
  TOOL_MANIFEST_REGISTRY,
  projectProviderTools,
  resolveToolManifestEntry,
} from "../dist-test/tool-manifest.js";


const fixtureUrl = new URL(
  "../fixtures/harness/tool-manifest-v1.json",
  import.meta.url,
);
const fixture = JSON.parse(await readFile(fixtureUrl, "utf8"));

assert.deepEqual(TOOL_MANIFEST_GOLDEN, fixture);
assert.equal(TOOL_MANIFEST_REGISTRY.schema_version, "tool-manifest-v1");
assert.equal(TOOL_MANIFEST_REGISTRY.tools.length, 37);
assert.equal(
  TOOL_MANIFEST_REGISTRY.tools.filter((entry) => entry.workflow === "planning")
    .length,
  6,
);
assert.equal(
  TOOL_MANIFEST_REGISTRY.tools.filter((entry) => entry.workflow === "study_chat")
    .length,
  31,
);
assert.equal(Object.keys(TOOL_MANIFEST_BY_KEY).length, 37);
assert.ok(Object.isFrozen(TOOL_MANIFEST_GOLDEN));
assert.ok(Object.isFrozen(TOOL_MANIFEST_REGISTRY.tools[0]));

for (const entry of TOOL_MANIFEST_REGISTRY.tools) {
  assert.equal(entry.parallel.runtime_mode, "serial");
  assert.equal(entry.parallel.parallel_safe, false);
  assert.deepEqual(
    entry.effect_steps.map((step) => step.sequence),
    entry.effect_steps.map((_, index) => index),
  );
  const provider = TOOL_MANIFEST_GOLDEN.provider_functions.find(
    (item) => item.key === entry.key,
  );
  assert.ok(provider);
  assert.equal(provider.projection.function.name, entry.canonical_name);
  assert.equal(provider.projection.function.strict, true);
  assertClosedObjects(provider.projection.function.parameters);
}

const generated =
  TOOL_MANIFEST_BY_KEY["study_chat:study_chat_reply:generate_projected_image"];
assert.deepEqual(
  generated.effect_steps.map((step) => step.boundary_kind),
  ["external_call", "database_write"],
);
assert.deepEqual(
  generated.effect_steps.map((step) => step.adapter?.name),
  ["study_provider_execution", "study_projection_mutation"],
);

const planningContent = resolveToolManifestEntry({
  workflow: "planning",
  offeredInStage: "plan_generation",
  transportName: "read_page_range_content",
});
const studyContent = resolveToolManifestEntry({
  workflow: "study_chat",
  offeredInStage: "study_chat_reply",
  transportName: "read_page_range_content",
});
assert.notEqual(planningContent.key, studyContent.key);
assert.notEqual(
  planningContent.input_contract.version,
  studyContent.input_contract.version,
);

const dependencies = new Set(
  TOOL_MANIFEST_REGISTRY.tools.flatMap((entry) => entry.dependencies),
);
const capabilities = new Set(
  TOOL_MANIFEST_REGISTRY.tools.flatMap((entry) => entry.provider_capabilities),
);
assert.equal(
  projectProviderTools({
    workflow: "planning",
    offeredInStage: "plan_generation",
    availableDependencies: dependencies,
    providerCapabilities: capabilities,
  }).length,
  6,
);
assert.equal(
  projectProviderTools({
    workflow: "study_chat",
    offeredInStage: "study_chat_reply",
    availableDependencies: dependencies,
    providerCapabilities: capabilities,
  }).length,
  31,
);

function assertClosedObjects(value) {
  if (Array.isArray(value)) {
    for (const item of value) {
      assertClosedObjects(item);
    }
    return;
  }
  if (value === null || typeof value !== "object") {
    return;
  }
  if (value.type === "object") {
    assert.equal(value.additionalProperties, false);
  }
  for (const child of Object.values(value)) {
    assertClosedObjects(child);
  }
}

console.log("tool manifest contract tests passed");
