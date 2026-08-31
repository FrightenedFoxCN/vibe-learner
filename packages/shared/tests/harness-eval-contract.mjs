import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

import {
  HARNESS_EVAL_FAILURE_TAXONOMY,
  HarnessEvalDecodeError,
  decodeHarnessEvalCase,
  decodeHarnessEvalContractGolden,
  decodeHarnessEvalFailureTaxonomy,
  decodeHarnessEvalReport,
  decodeHarnessEvalRun,
  decodeHarnessEvalSample,
  harnessEvalFailureTaxonomyRegistrySnapshot,
} from "../dist-test/harness-eval.js";


const goldenUrl = new URL(
  "../fixtures/harness/eval-contract-golden-v1.json",
  import.meta.url,
);
const taxonomyUrl = new URL(
  "../fixtures/harness/eval-failure-taxonomy-v1.json",
  import.meta.url,
);
const golden = JSON.parse(await readFile(goldenUrl, "utf8"));
const taxonomy = JSON.parse(await readFile(taxonomyUrl, "utf8"));

assert.deepEqual(decodeHarnessEvalContractGolden(golden), golden);
assert.deepEqual(decodeHarnessEvalFailureTaxonomy(taxonomy), taxonomy);
assert.deepEqual(harnessEvalFailureTaxonomyRegistrySnapshot(), taxonomy);
assert.equal(Object.isFrozen(HARNESS_EVAL_FAILURE_TAXONOMY), true);
assert.equal(
  Object.isFrozen(HARNESS_EVAL_FAILURE_TAXONOMY.candidate_decode_failed),
  true,
);
assert.equal(
  Object.isFrozen(
    HARNESS_EVAL_FAILURE_TAXONOMY.candidate_decode_failed.allowed_sample_statuses,
  ),
  true,
);
assert.throws(
  () => {
    HARNESS_EVAL_FAILURE_TAXONOMY.candidate_decode_failed.owner = "runner";
  },
  TypeError,
);

function cloned(value) {
  return structuredClone(value);
}

function assertDecodeFailure(callback, reason) {
  assert.throws(callback, (error) => {
    assert.ok(error instanceof HarnessEvalDecodeError);
    assert.equal(error.code, "harness_eval_decode_error");
    assert.equal(error.reason, reason);
    return true;
  });
}

{
  const payload = cloned(golden.case);
  payload.schema_version = "harness-eval-case-v2";
  assertDecodeFailure(
    () => decodeHarnessEvalCase(payload),
    "expected_harness-eval-case-v1",
  );
}

{
  const payload = cloned(golden.case);
  payload.eval_route = "planning.tool_execution";
  assertDecodeFailure(() => decodeHarnessEvalCase(payload), "route_mismatch");
}

{
  const payload = cloned(golden.case);
  payload.source = {
    source_mode: "protected_artifact",
    artifact_type: "tavern_transcript",
    artifact_id: "protected-artifact-1",
    artifact_contract: {
      name: "TavernTranscriptFixture",
      version: "tavern-transcript-fixture-v1",
    },
    payload_digest: "a".repeat(64),
  };
  assertDecodeFailure(
    () => decodeHarnessEvalCase(payload),
    "sensitivity_source_mismatch",
  );
}

{
  const payload = cloned(golden.run);
  payload.tested_system.budgets.max_attempts = "2";
  assertDecodeFailure(() => decodeHarnessEvalRun(payload), "expected_safe_integer");
}

{
  const payload = cloned(golden.run);
  payload.environment.hostname = "must-not-enter-content-free-config";
  assertDecodeFailure(() => decodeHarnessEvalRun(payload), "unexpected_or_missing_fields");
}

{
  const payload = cloned(golden.sample);
  payload.raw_output = "must never enter CI evidence";
  assertDecodeFailure(
    () => decodeHarnessEvalSample(payload),
    "unexpected_or_missing_fields",
  );
}

{
  const payload = cloned(golden.sample);
  payload.harness_operation_id = "caller-operation-1";
  assertDecodeFailure(
    () => decodeHarnessEvalSample(payload),
    "expected_bounded_string",
  );
}

{
  const payload = cloned(golden.sample);
  payload.metrics[0].value = Number.NaN;
  assertDecodeFailure(() => decodeHarnessEvalSample(payload), "expected_safe_integer");
}

{
  const payload = cloned(golden.sample);
  payload.completed_at = "2026-02-30T03:00:00Z";
  assertDecodeFailure(() => decodeHarnessEvalSample(payload), "invalid_utc_timestamp");
}

{
  const payload = cloned(golden.sample);
  const grader = payload.grader_results[0];
  grader.execution_status = "error";
  grader.verdict = null;
  grader.score = null;
  grader.failure_codes = ["grader_execution_failed"];
  assertDecodeFailure(
    () => decodeHarnessEvalSample(payload),
    "infrastructure_failure_not_broken",
  );
}

{
  const payload = cloned(golden.report);
  payload.passed_count = 0;
  assertDecodeFailure(
    () => decodeHarnessEvalReport(payload),
    "terminal_counts_mismatch",
  );
}

{
  const payload = cloned(golden.report);
  payload.raw_samples_artifact.sample_count = 2;
  assertDecodeFailure(() => decodeHarnessEvalReport(payload), "raw_samples_mismatch");
}

{
  const payload = cloned(taxonomy);
  const candidate = payload.entries.find(
    (entry) => entry.code === "candidate_decode_failed",
  );
  candidate.owner = "runner";
  assertDecodeFailure(
    () => decodeHarnessEvalFailureTaxonomy(payload),
    "candidate_blame_mismatch",
  );
}
