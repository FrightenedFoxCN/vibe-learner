import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

import {
  HARNESS_COMPONENT_REGISTRATIONS,
  HARNESS_OPERATION_COMMIT_POLICIES,
  HARNESS_OPERATION_STAGE_REGISTRATIONS,
  HARNESS_STAGE_WORKFLOWS,
  harnessOperationCommitPolicyRegistrySnapshot,
  harnessOperationStageRegistrySnapshot,
  harnessResourceEvidencePolicyRegistrySnapshot,
} from "../dist-test/harness.js";
import {
  HARNESS_EFFECT_ADAPTER_POLICIES,
  harnessEffectAdapterPolicyRegistrySnapshot,
} from "../dist-test/harness-effect.js";
import { harnessArtifactAccessContractRegistrySnapshot } from "../dist-test/harness-artifact-access.js";

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

const commitFixtureUrl = new URL(
  "../fixtures/harness/operation-commit-policies-v1.json",
  import.meta.url,
);
const expectedCommitPolicies = JSON.parse(await readFile(commitFixtureUrl, "utf8"));

assert.deepEqual(harnessOperationCommitPolicyRegistrySnapshot(), expectedCommitPolicies);

const effectFixtureUrl = new URL(
  "../fixtures/harness/effect-adapter-policies-v1.json",
  import.meta.url,
);
const expectedEffectPolicies = JSON.parse(await readFile(effectFixtureUrl, "utf8"));
assert.deepEqual(harnessEffectAdapterPolicyRegistrySnapshot(), expectedEffectPolicies);
assert.equal(Object.isFrozen(HARNESS_EFFECT_ADAPTER_POLICIES), true);
assert.equal(
  Object.isFrozen(HARNESS_EFFECT_ADAPTER_POLICIES.study_plan_confirmation_create),
  true,
);

assert.equal(Object.isFrozen(HARNESS_COMPONENT_REGISTRATIONS), true);
assert.equal(
  Object.isFrozen(HARNESS_COMPONENT_REGISTRATIONS.tavern_actor_prompt.contract),
  true,
);
assert.equal(Object.isFrozen(HARNESS_OPERATION_STAGE_REGISTRATIONS), true);
assert.equal(Object.isFrozen(HARNESS_OPERATION_COMMIT_POLICIES), true);
assert.equal(
  Object.isFrozen(Object.values(HARNESS_OPERATION_COMMIT_POLICIES)[0].resourceRules),
  true,
);
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

const artifactAccessFixtureUrl = new URL(
  "../fixtures/harness/artifact-access-contract-registry-v1.json",
  import.meta.url,
);
const expectedArtifactAccess = JSON.parse(
  await readFile(artifactAccessFixtureUrl, "utf8"),
);
assert.deepEqual(
  harnessArtifactAccessContractRegistrySnapshot(),
  expectedArtifactAccess,
);
