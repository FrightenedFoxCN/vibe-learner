import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

import {
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
