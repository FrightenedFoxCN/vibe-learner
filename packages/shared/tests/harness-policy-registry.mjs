import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

import {
  HARNESS_COMPONENT_REGISTRATIONS,
  HARNESS_OPERATION_STAGE_REGISTRATIONS,
  HARNESS_STAGE_WORKFLOWS,
  harnessOperationStageRegistrySnapshot,
  harnessResourceEvidencePolicyRegistrySnapshot,
} from "../dist-test/harness.js";

const fixtureUrl = new URL(
  "../fixtures/harness/resource-evidence-policies-v1.json",
  import.meta.url,
);
const expected = JSON.parse(await readFile(fixtureUrl, "utf8"));

assert.deepEqual(harnessResourceEvidencePolicyRegistrySnapshot(), expected);

const stageFixtureUrl = new URL(
  "../fixtures/harness/operation-stage-registry-v1.json",
  import.meta.url,
);
const expectedStages = JSON.parse(await readFile(stageFixtureUrl, "utf8"));

assert.deepEqual(harnessOperationStageRegistrySnapshot(), expectedStages);

assert.equal(Object.isFrozen(HARNESS_COMPONENT_REGISTRATIONS), true);
assert.equal(
  Object.isFrozen(HARNESS_COMPONENT_REGISTRATIONS.tavern_actor_prompt.contract),
  true,
);
assert.equal(Object.isFrozen(HARNESS_OPERATION_STAGE_REGISTRATIONS), true);
assert.equal(Object.isFrozen(HARNESS_STAGE_WORKFLOWS), true);
assert.equal(
  Object.isFrozen(HARNESS_OPERATION_STAGE_REGISTRATIONS["tavern:actor_reply"].componentNames),
  true,
);
assert.throws(
  () => {
    HARNESS_COMPONENT_REGISTRATIONS.tavern_actor_prompt.contract.version =
      "forged-valid-v999";
  },
  TypeError,
);
for (const key of Object.keys(HARNESS_OPERATION_STAGE_REGISTRATIONS)) {
  const [workflow, stage] = key.split(":");
  assert.equal(HARNESS_STAGE_WORKFLOWS[stage], workflow);
}
assert.deepEqual(harnessOperationStageRegistrySnapshot(), expectedStages);
