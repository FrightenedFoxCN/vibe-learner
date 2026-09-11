import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

import {
  HARNESS_OPERATION_STAGE_REGISTRATIONS,
} from "../dist-test/harness.js";
import {
  HARNESS_WORKFLOW_MANIFEST,
  HARNESS_WORKFLOW_MANIFEST_ENTRIES,
  HARNESS_WORKFLOW_MANIFEST_EVAL_CASE_VERSION,
  HARNESS_WORKFLOW_MANIFEST_TOOL_MANIFEST_VERSION,
  harnessWorkflowManifestSnapshot,
  requireExecutableWorkflowManifestEntry,
  validateHarnessWorkflowManifest,
} from "../dist-test/harness-manifest.js";


const fixtureUrl = new URL(
  "../fixtures/harness/workflow-manifest-v1.json",
  import.meta.url,
);
const fixture = JSON.parse(await readFile(fixtureUrl, "utf8"));

assert.deepEqual(harnessWorkflowManifestSnapshot(), fixture);
assert.deepEqual(HARNESS_WORKFLOW_MANIFEST, fixture);
assert.equal(HARNESS_WORKFLOW_MANIFEST.stages.length, 14);
assert.equal(Object.isFrozen(HARNESS_WORKFLOW_MANIFEST), true);
assert.equal(Object.isFrozen(HARNESS_WORKFLOW_MANIFEST.stages), true);
assert.equal(Object.isFrozen(HARNESS_WORKFLOW_MANIFEST.stages[0]), true);
assert.equal(Object.isFrozen(HARNESS_WORKFLOW_MANIFEST.stages[0].registration), true);
assert.equal(Object.isFrozen(HARNESS_WORKFLOW_MANIFEST_ENTRIES), true);

const keys = HARNESS_WORKFLOW_MANIFEST.stages.map((entry) => entry.key);
assert.deepEqual(keys, [...keys].sort());
assert.equal(new Set(keys).size, keys.length);
assert.deepEqual(
  new Set(keys),
  new Set(Object.keys(HARNESS_OPERATION_STAGE_REGISTRATIONS)),
);

for (const entry of HARNESS_WORKFLOW_MANIFEST.stages) {
  const vocabulary = HARNESS_OPERATION_STAGE_REGISTRATIONS[entry.key];
  assert.ok(vocabulary, entry.key);
  assert.equal(entry.owner_module, vocabulary.ownerModule);
  assert.deepEqual(
    entry.component_contracts.map((component) => component.component_name),
    vocabulary.componentNames,
  );
  assert.deepEqual(
    entry.component_contracts.map((component) => component.component_name),
    [...entry.component_contracts]
      .map((component) => component.component_name)
      .sort(),
  );
  assert.equal(entry.eval_route.status, "registered");
  assert.equal(entry.eval_route.value, vocabulary.evalRoute);
  const implemented = true;
  assert.equal(entry.registration.status, implemented ? "registered" : "unregistered");
  if (!implemented) {
    assert.throws(() => requireExecutableWorkflowManifestEntry(entry.workflow, entry.stage), /stage_unregistered/);
  }
  assert.equal(entry.eval_suites.status, "registered");
  if (entry.allowed_artifact_types.status === "registered") {
    assert.deepEqual(
      entry.allowed_artifact_types.artifact_types,
      [...new Set(entry.allowed_artifact_types.artifact_types)].sort(),
    );
  }
}

const statuses = new Set(collectValuesForKey(fixture, "status"));
assert.deepEqual(
  statuses,
  new Set(["registered", "not_applicable"]),
);
const serialized = JSON.stringify(fixture).toLowerCase();
for (const placeholder of ['"pending-', '"latest"', '"unknown"']) {
  assert.equal(serialized.includes(placeholder), false);
}

const toolExecution =
  HARNESS_WORKFLOW_MANIFEST_ENTRIES["planning:planning_tool_execution"];
assert.equal(toolExecution.toolset_contract.status, "registered");
assert.equal(
  toolExecution.toolset_contract.contract.name,
  "ToolManifestRegistry",
);
assert.equal(
  toolExecution.toolset_contract.contract.version,
  HARNESS_WORKFLOW_MANIFEST_TOOL_MANIFEST_VERSION,
);
assert.equal(
  HARNESS_WORKFLOW_MANIFEST_EVAL_CASE_VERSION,
  "harness-eval-case-v1",
);

const tavern = requireExecutableWorkflowManifestEntry("tavern", "actor_reply");
assert.equal(tavern.registration.status, "registered");
assert.equal(tavern.eval_suites.status, "registered");
assert.deepEqual(tavern.eval_suites.contracts, [
  {
    name: "tavern_identity_eval",
    version: "tavern-identity-eval-v1",
  },
]);
const planning = requireExecutableWorkflowManifestEntry("planning", "plan_generation");
assert.equal(planning.registration.status, "registered");
assert.deepEqual(planning.eval_suites, { status: "registered", contracts: [{ name: "plan_generation_regression", version: "plan-generation-regression-v1" }] });
assert.throws(
  () => requireExecutableWorkflowManifestEntry("tavern", "plan_generation"),
  /stage_unknown/,
);

validateHarnessWorkflowManifest(fixture);
for (const mutate of [
  (value) => {
    value.sensitive_payload = "forbidden";
  },
  (value) => {
    value.stages[0].registration.status = "pending";
  },
  (value) => {
    [value.stages[0], value.stages[1]] = [value.stages[1], value.stages[0]];
  },
  (value) => {
    value.stages.at(-1).input_contract.contract.version = "latest";
  },
]) {
  const changed = structuredClone(fixture);
  mutate(changed);
  assert.throws(
    () => validateHarnessWorkflowManifest(changed),
    /registry_drift/,
  );
}

assert.throws(
  () => {
    HARNESS_WORKFLOW_MANIFEST.stages.at(-1).input_contract.contract.version =
      "forged-v999";
  },
  TypeError,
);

const forbiddenKeys = new Set([
  "raw_prompt",
  "prompt_content",
  "system_prompt",
  "guidance",
  "document_content",
  "transcript_content",
  "secret",
  "token",
  "file_path",
  "raw_payload",
]);
for (const key of collectKeys(fixture)) {
  assert.equal(forbiddenKeys.has(key), false, key);
}

console.log("harness workflow manifest contract tests passed");


function collectValuesForKey(value, target) {
  if (Array.isArray(value)) {
    return value.flatMap((item) => collectValuesForKey(item, target));
  }
  if (value === null || typeof value !== "object") {
    return [];
  }
  return [
    ...(target in value ? [value[target]] : []),
    ...Object.values(value).flatMap((item) => collectValuesForKey(item, target)),
  ];
}

function collectKeys(value) {
  if (Array.isArray(value)) {
    return new Set(value.flatMap((item) => [...collectKeys(item)]));
  }
  if (value === null || typeof value !== "object") {
    return new Set();
  }
  return new Set([
    ...Object.keys(value),
    ...Object.values(value).flatMap((item) => [...collectKeys(item)]),
  ]);
}
