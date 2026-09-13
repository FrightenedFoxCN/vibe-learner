import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

import { modelRuntimeConfigSnapshot } from "../dist-test/model-runtime-config.js";

const fixture = JSON.parse(await readFile(
  new URL("../fixtures/model-runtime-config-v1.json", import.meta.url),
  "utf8",
));

assert.deepEqual(modelRuntimeConfigSnapshot(), fixture);
console.log("model runtime config contract tests passed");
