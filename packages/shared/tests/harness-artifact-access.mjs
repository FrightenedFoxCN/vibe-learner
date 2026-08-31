import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

import {
  HarnessArtifactAccessDecodeError,
  decodeHarnessArtifactAccessCases,
  decodeHarnessArtifactAccessGolden,
  decodeHarnessArtifactGrant,
} from "../dist-test/harness-artifact-access.js";

const fixture = (name) => new URL(`../fixtures/harness/${name}`, import.meta.url);
const golden = JSON.parse(await readFile(fixture("artifact-access-golden-v1.json"), "utf8"));
const cases = JSON.parse(await readFile(fixture("artifact-access-cases-v1.json"), "utf8"));

assert.deepEqual(decodeHarnessArtifactAccessGolden(golden), golden);
assert.deepEqual(decodeHarnessArtifactAccessCases(cases), cases);

function cloned(value) { return structuredClone(value); }
function rejects(mutator, reason) {
  const payload = cloned(golden);
  mutator(payload);
  assert.throws(() => decodeHarnessArtifactAccessGolden(payload), (error) => {
    assert.ok(error instanceof HarnessArtifactAccessDecodeError);
    assert.equal(error.code, "harness_artifact_access_decode_error");
    assert.equal(error.reason, reason);
    return true;
  });
}

rejects((payload) => { payload.grant.access_token = "must-never-be-accepted"; }, "unexpected_or_missing_fields");
rejects((payload) => { payload.grant.harness_operation_id = `harness-operation-${"c".repeat(32)}`; }, "identity_mismatch");
rejects((payload) => { payload.allowed_audit.grant_subject_id = `local-installation-${"1".repeat(32)}`; }, "allowed_identity_mismatch");
rejects((payload) => { payload.grant.issued_at = "2026-08-25T10:55:00+08:00"; }, "invalid_string");
rejects((payload) => { payload.grant.issued_at = "2026-02-30T02:55:00Z"; }, "invalid_timestamp");
rejects((payload) => { payload.grant.scopes.reverse(); }, "scopes_not_sorted");
rejects((payload) => { payload.grant.scopes[0].artifact_contract.version = "latest"; }, "contract_version_not_adopted");

{
  const payload = cloned(golden.grant);
  payload.scopes.push(cloned(payload.scopes[0]));
  assert.throws(() => decodeHarnessArtifactGrant(payload), (error) =>
    error instanceof HarnessArtifactAccessDecodeError && error.reason === "duplicate_scope");
}
{
  const payload = cloned(cases);
  payload.cases.reverse();
  assert.throws(() => decodeHarnessArtifactAccessCases(payload), (error) =>
    error instanceof HarnessArtifactAccessDecodeError && error.reason === "cases_not_sorted");
}

console.log("harness artifact access contract tests passed");
