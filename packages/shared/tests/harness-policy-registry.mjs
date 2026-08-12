import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

import { harnessResourceEvidencePolicyRegistrySnapshot } from "../src/harness.ts";

const fixtureUrl = new URL(
  "../fixtures/harness/resource-evidence-policies-v1.json",
  import.meta.url,
);
const expected = JSON.parse(await readFile(fixtureUrl, "utf8"));

assert.deepEqual(harnessResourceEvidencePolicyRegistrySnapshot(), expected);
