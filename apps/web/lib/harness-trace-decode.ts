import type {
  HarnessAttempt, HarnessCheckV2, HarnessCommitEvidence, HarnessCommitEvidenceV3,
  HarnessCommittedResourceRef, HarnessCommittedResourceRefV3, HarnessContextEnvelope,
  HarnessContextEnvelopeV3, HarnessContractRef, HarnessResourceRef, HarnessResourceRefV3,
  HarnessSnapshotRef, HarnessSnapshotRefV3, HarnessTraceV2, HarnessTraceV3,
  HarnessResourceType, HarnessStage, HarnessWorkflow,
} from "@vibe-learner/shared";
import {
  HARNESS_COMPONENT_REGISTRATIONS, HARNESS_OPERATION_COMMIT_POLICIES,
  HARNESS_OPERATION_STAGE_REGISTRATIONS, HARNESS_RESOURCE_EVIDENCE_POLICIES,
  HARNESS_STAGE_WORKFLOWS,
} from "../../../packages/shared/src/harness.ts";
import { StrictResponseDecoder, type DecodeFailure } from "./strict-response-decode.ts";

const WORKFLOWS = ["document_parse", "ocr", "study_unit_cleanup", "planning", "persona", "scene", "study_chat", "tavern", "frontend_decode"] as const;
const ARTIFACTS = ["document_upload", "document_debug", "ocr_page", "study_unit_input", "planning_context", "persona_snapshot", "scene_snapshot", "study_session_snapshot", "tavern_room_snapshot", "tavern_transcript", "frontend_response_fixture"] as const;
const STATUSES = ["passed", "repaired", "failed", "skipped"] as const;
const PHASES = ["generate", "decode", "validate", "repair", "commit", "rollback"] as const;

/** Decode wire structure and cross-field evidence; canonical digests and database
 * read-back remain Python/server authority, not a browser verification claim. */
export function decodeVersionedHarnessTrace(
  raw: unknown, path: string, schema: "harness-trace-v2" | "harness-trace-v3", fail: DecodeFailure,
): HarnessTraceV2 | HarnessTraceV3 {
  const d = new StrictResponseDecoder(fail);
  const require = (condition: boolean, p: string, reason: string) => { if (!condition) fail(p, reason); };
  const obj = (value: unknown, p: string, keys: readonly string[]) => {
    const record = d.record(value, p);
    for (const key of Object.keys(record)) require(keys.includes(key), `${p}.${key}`, "unknown_field");
    for (const key of keys) d.field(record, key, p);
    return record;
  };
  const str = (value: unknown, p: string, max = 160, empty = false) => {
    const result = d.string(value, p, empty);
    require(result.length <= max, p, "string_too_long");
    return result;
  };
  const nullable = <T>(value: unknown, p: string, decode: (v: unknown, p: string) => T): T | null => value === null ? null : decode(value, p);
  const list = <T>(value: unknown, p: string, decode: (v: unknown, p: string) => T, max = 64, min = 0): T[] => {
    if (!Array.isArray(value)) return fail(p, "expected_array");
    require(value.length >= min && value.length <= max, p, "array_length_out_of_bounds");
    return value.map((item, index) => decode(item, `${p}[${index}]`));
  };
  const digest = (value: unknown, p: string) => {
    const result = str(value, p, 64);
    require(/^[0-9a-f]{64}$/.test(result), p, "invalid_sha256_digest");
    return result;
  };
  const utc = (value: unknown, p: string) => {
    const result = str(value, p, 64);
    const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.\d{1,6})?(?:Z|\+00:00)$/.exec(result);
    require(match !== null && Number.isFinite(Date.parse(result)), p, "invalid_utc_timestamp");
    if (match) {
      const instant = new Date(result);
      require(instant.getUTCFullYear() === Number(match[1]) && instant.getUTCMonth() + 1 === Number(match[2]) && instant.getUTCDate() === Number(match[3]) && instant.getUTCHours() === Number(match[4]) && instant.getUTCMinutes() === Number(match[5]) && instant.getUTCSeconds() === Number(match[6]), p, "invalid_utc_timestamp");
    }
    return result;
  };
  const contract = (value: unknown, p: string): HarnessContractRef => {
    const r = obj(value, p, ["name", "version"]);
    const result = { name: str(r.name, `${p}.name`, 160), version: str(r.version, `${p}.version`, 160) };
    if (schema === "harness-trace-v3") {
      require(/^[A-Za-z][A-Za-z0-9._-]{0,159}$/.test(result.name) && /^[A-Za-z0-9][A-Za-z0-9._-]{0,159}$/.test(result.version), p, "invalid_versioned_contract");
      require(!/^(?:pending|latest|unknown)(?:$|[-_])/i.test(result.version), p, "unregistered_contract_version");
    }
    return result;
  };
  const sameContract = (a: HarnessContractRef, b: HarnessContractRef) => a.name === b.name && a.version === b.version;
  const ordered = (keys: string[], p: string) => {
    require(new Set(keys).size === keys.length, p, "duplicate_reference");
    require(keys.every((key, index) => index === 0 || keys[index - 1]! < key), p, "references_not_sorted");
  };
  const resourceId = (value: unknown, p: string) => {
    const result = str(value, p);
    if (schema === "harness-trace-v3") require(/^[A-Za-z0-9][A-Za-z0-9:._-]{0,159}$/.test(result), p, "invalid_resource_id");
    return result;
  };
  const resourceType = (value: unknown, p: string): HarnessResourceType => d.enumeration(value, Object.keys(HARNESS_RESOURCE_EVIDENCE_POLICIES) as HarnessResourceType[], p);
  const resource = (value: unknown, p: string): HarnessResourceRef => {
    const r = obj(value, p, ["resource_type", "resource_id", "revision"]);
    return { resourceType: schema === "harness-trace-v3" ? resourceType(r.resource_type, `${p}.resource_type`) : str(r.resource_type, `${p}.resource_type`, 96), resourceId: resourceId(r.resource_id, `${p}.resource_id`), revision: nullable(r.revision, `${p}.revision`, (v, pp) => d.integer(v, pp)) };
  };
  const resourceV3 = (value: unknown, p: string): HarnessResourceRefV3 => {
    const ref = resource(value, p);
    return { ...ref, resourceType: resourceType(ref.resourceType, `${p}.resource_type`) };
  };
  const snapshotBase = (r: Record<string, unknown>, p: string) => ({ artifactId: str(r.artifact_id, `${p}.artifact_id`), digestAlgorithm: d.enumeration(r.digest_algorithm, ["sha256"] as const, `${p}.digest_algorithm`), payloadDigest: digest(r.payload_digest, `${p}.payload_digest`) });
  const snapshot = (value: unknown, p: string): HarnessSnapshotRef => {
    const r = obj(value, p, ["artifact_type", "artifact_id", "schema_version", "digest_algorithm", "payload_digest"]);
    return { ...snapshotBase(r, p), artifactType: str(r.artifact_type, `${p}.artifact_type`, 96), schemaVersion: str(r.schema_version, `${p}.schema_version`) };
  };
  const snapshotV3 = (value: unknown, p: string): HarnessSnapshotRefV3 => {
    const r = obj(value, p, ["artifact_type", "artifact_id", "contract", "digest_algorithm", "payload_digest"]);
    const result = { ...snapshotBase(r, p), artifactType: d.enumeration(r.artifact_type, ARTIFACTS, `${p}.artifact_type`), contract: contract(r.contract, `${p}.contract`) };
    require(/^[A-Za-z0-9][A-Za-z0-9._-]{0,159}$/.test(result.artifactId), `${p}.artifact_id`, "invalid_artifact_id");
    return result;
  };
  const trace = obj(raw, path, ["trace_schema_version", "trace_id", "operation_id", "parent_trace_id", "workflow", "stage", "status", "contract", "context", "output_digest", "checks", "attempt_records", "recovery_strategy", "error_code", "duration_ms", "commit_evidence", "started_at", "completed_at"]);
  d.equal(trace.trace_schema_version, schema, `${path}.trace_schema_version`);
  const workflow = d.enumeration(trace.workflow, WORKFLOWS, `${path}.workflow`);
  const operationId = str(trace.operation_id, `${path}.operation_id`);
  if (schema === "harness-trace-v3") require(/^harness-operation-[0-9a-f]{32}$/.test(operationId), `${path}.operation_id`, "invalid_harness_operation_id");
  const stage = str(trace.stage, `${path}.stage`);
  const p = `${path}.context`;
  const contextKeys = ["workflow", "operation_id", "subject_refs", "component_versions", "snapshot_refs", "digest_algorithm", "input_digest", "context_digest"];
  const c = obj(trace.context, p, [...contextKeys, ...(schema === "harness-trace-v3" ? ["context_contract", "stage", "input_contract", "digest_contract", "policy_contract", "prompt_contract"] : ["schema_name", "schema_version", "policy_version", "prompt_version"])]);
  d.equal(c.workflow, workflow, `${p}.workflow`);
  d.equal(c.operation_id, operationId, `${p}.operation_id`);
  const commonContext = { workflow, operationId, componentVersions: list(c.component_versions, `${p}.component_versions`, contract), digestAlgorithm: d.enumeration(c.digest_algorithm, ["sha256"] as const, `${p}.digest_algorithm`), inputDigest: digest(c.input_digest, `${p}.input_digest`), contextDigest: digest(c.context_digest, `${p}.context_digest`) };
  ordered(commonContext.componentVersions.map((item) => item.name), `${p}.component_versions`);
  let context: HarnessContextEnvelope | HarnessContextEnvelopeV3;
  if (schema === "harness-trace-v3") {
    const typedStage = d.enumeration(stage, Object.keys(HARNESS_STAGE_WORKFLOWS) as HarnessStage[], `${path}.stage`);
    d.equal(HARNESS_STAGE_WORKFLOWS[typedStage], workflow, `${path}.stage`);
    d.equal(c.stage, stage, `${p}.stage`);
    const contextContract = contract(c.context_contract, `${p}.context_contract`);
    require(sameContract(contextContract, { name: "HarnessContextEnvelopeV3", version: "harness-context-v3" }), `${p}.context_contract`, "context_contract_mismatch");
    const digestContract = contract(c.digest_contract, `${p}.digest_contract`);
    require(sameContract(digestContract, { name: "HarnessContextManifestDigest", version: "harness-context-manifest-digest-v1" }), `${p}.digest_contract`, "digest_contract_mismatch");
    const registration = Object.values(HARNESS_OPERATION_STAGE_REGISTRATIONS).find((item) => item === HARNESS_OPERATION_STAGE_REGISTRATIONS[`${workflow}:${typedStage}` as keyof typeof HARNESS_OPERATION_STAGE_REGISTRATIONS]);
    require(registration !== undefined, `${p}.component_versions`, "stage_unregistered");
    const expected = registration?.componentNames.map((name) => HARNESS_COMPONENT_REGISTRATIONS[name].contract).sort((a, b) => (a?.name ?? "") < (b?.name ?? "") ? -1 : 1) ?? [];
    require(expected.length === commonContext.componentVersions.length && expected.every((item, index) => item !== null && sameContract(item, commonContext.componentVersions[index]!)), `${p}.component_versions`, "component_registration_mismatch");
    const subjectRefs = list(c.subject_refs, `${p}.subject_refs`, resourceV3);
    subjectRefs.forEach((ref, index) => {
      const policy = HARNESS_RESOURCE_EVIDENCE_POLICIES[ref.resourceType].contextEvidence;
      require(policy === "authoritative_revision" ? ref.revision !== null : policy === "operation_identity" && ref.revision === null, `${p}.subject_refs[${index}]`, "context_resource_evidence_unsupported");
    });
    context = { ...commonContext, contextContract: { name: "HarnessContextEnvelopeV3", version: "harness-context-v3" }, digestContract: { name: "HarnessContextManifestDigest", version: "harness-context-manifest-digest-v1" }, stage: typedStage, inputContract: contract(c.input_contract, `${p}.input_contract`), subjectRefs, snapshotRefs: list(c.snapshot_refs, `${p}.snapshot_refs`, snapshotV3), policyContract: nullable(c.policy_contract, `${p}.policy_contract`, contract), promptContract: nullable(c.prompt_contract, `${p}.prompt_contract`, contract) };
  } else {
    context = { ...commonContext, schemaName: str(c.schema_name, `${p}.schema_name`), schemaVersion: str(c.schema_version, `${p}.schema_version`), subjectRefs: list(c.subject_refs, `${p}.subject_refs`, resource), snapshotRefs: list(c.snapshot_refs, `${p}.snapshot_refs`, snapshot), policyVersion: nullable(c.policy_version, `${p}.policy_version`, str), promptVersion: nullable(c.prompt_version, `${p}.prompt_version`, str) };
  }
  ordered(context.subjectRefs.map((item) => `${item.resourceType}\0${item.resourceId}`), `${p}.subject_refs`);
  ordered(context.snapshotRefs.map((item) => `${item.artifactType}\0${item.artifactId}`), `${p}.snapshot_refs`);
  const committedResource = (value: unknown, pp: string): HarnessCommittedResourceRef => {
    const r = obj(value, pp, ["resource_type", "resource_id", "expected_revision", "committed_revision", "first_sequence", "last_sequence", "payload_digest"]);
    const result = { resourceType: schema === "harness-trace-v3" ? resourceType(r.resource_type, `${pp}.resource_type`) : str(r.resource_type, `${pp}.resource_type`, 96), resourceId: resourceId(r.resource_id, `${pp}.resource_id`), expectedRevision: nullable(r.expected_revision, `${pp}.expected_revision`, (v, q) => d.integer(v, q)), committedRevision: nullable(r.committed_revision, `${pp}.committed_revision`, (v, q) => d.integer(v, q)), firstSequence: nullable(r.first_sequence, `${pp}.first_sequence`, (v, q) => d.integer(v, q, 1)), lastSequence: nullable(r.last_sequence, `${pp}.last_sequence`, (v, q) => d.integer(v, q, 1)), payloadDigest: digest(r.payload_digest, `${pp}.payload_digest`) };
    require((result.firstSequence === null) === (result.lastSequence === null) && (result.firstSequence === null || result.firstSequence <= result.lastSequence!), pp, "invalid_sequence_range");
    require(result.expectedRevision === null || result.committedRevision === null || result.committedRevision >= result.expectedRevision, pp, "revision_regressed");
    if (schema === "harness-trace-v3") {
      const policy = HARNESS_RESOURCE_EVIDENCE_POLICIES[resourceType(result.resourceType, `${pp}.resource_type`)].commitEvidence;
      require(policy !== "unsupported", pp, "commit_resource_unsupported");
      if (policy === "revision") require(result.expectedRevision !== null && result.committedRevision !== null && result.firstSequence === null, pp, "revision_evidence_required");
      if (policy === "sequence") require(result.expectedRevision === null && result.committedRevision === null && result.firstSequence !== null && result.firstSequence === result.lastSequence, pp, "single_sequence_evidence_required");
      if (policy === "digest") require(result.expectedRevision === null && result.committedRevision === null && result.firstSequence === null, pp, "digest_position_forbidden");
    }
    return result;
  };
  const committedResourceV3 = (value: unknown, pp: string): HarnessCommittedResourceRefV3 => { const ref = committedResource(value, pp); return { ...ref, resourceType: resourceType(ref.resourceType, `${pp}.resource_type`) }; };
  const ep = `${path}.commit_evidence`;
  const e = obj(trace.commit_evidence, ep, ["status", "effect_batch_id", "payload_contract", "digest_algorithm", "digest_scope", "attempted_resource_refs", "committed_resources", "payload_digest", "committed_at", "rollback_reason_code", "rolled_back_at"]);
  const commonEvidence = { status: d.enumeration(e.status, ["not_applicable", "not_committed", "committed", "rolled_back"] as const, `${ep}.status`), effectBatchId: nullable(e.effect_batch_id, `${ep}.effect_batch_id`, str), payloadContract: nullable(e.payload_contract, `${ep}.payload_contract`, contract), digestAlgorithm: nullable(e.digest_algorithm, `${ep}.digest_algorithm`, (v, q) => d.enumeration(v, ["sha256"] as const, q)), digestScope: nullable(e.digest_scope, `${ep}.digest_scope`, (v, q) => d.enumeration(v, ["committed_projection", "committed_batch"] as const, q)), payloadDigest: nullable(e.payload_digest, `${ep}.payload_digest`, digest), committedAt: nullable(e.committed_at, `${ep}.committed_at`, utc), rollbackReasonCode: str(e.rollback_reason_code, `${ep}.rollback_reason_code`, 160, true), rolledBackAt: nullable(e.rolled_back_at, `${ep}.rolled_back_at`, utc) };
  const evidence: HarnessCommitEvidence | HarnessCommitEvidenceV3 = schema === "harness-trace-v3" ? { ...commonEvidence, attemptedResourceRefs: list(e.attempted_resource_refs, `${ep}.attempted_resource_refs`, resourceV3), committedResources: list(e.committed_resources, `${ep}.committed_resources`, committedResourceV3) } : { ...commonEvidence, attemptedResourceRefs: list(e.attempted_resource_refs, `${ep}.attempted_resource_refs`, resource), committedResources: list(e.committed_resources, `${ep}.committed_resources`, committedResource) };
  const attemptedKeys = evidence.attemptedResourceRefs.map((item) => `${item.resourceType}\0${item.resourceId}`);
  const committedKeys = evidence.committedResources.map((item) => `${item.resourceType}\0${item.resourceId}`);
  ordered(attemptedKeys, `${ep}.attempted_resource_refs`); ordered(committedKeys, `${ep}.committed_resources`);
  const metadata = [evidence.effectBatchId, evidence.payloadContract, evidence.digestAlgorithm, evidence.digestScope];
  const noCommit = evidence.committedResources.length === 0 && evidence.payloadDigest === null && evidence.committedAt === null;
  const noRollback = evidence.rollbackReasonCode === "" && evidence.rolledBackAt === null;
  if (evidence.digestScope === "committed_projection") require(attemptedKeys.length === 1, ep, "projection_requires_single_resource");
  if (evidence.status === "not_applicable") require(metadata.every((item) => item === null) && attemptedKeys.length === 0 && noCommit && noRollback, ep, "not_applicable_evidence_not_empty");
  if (evidence.status === "not_committed") require(noCommit && noRollback && (attemptedKeys.length ? metadata.every((item) => item !== null) : metadata.every((item) => item === null)), ep, "invalid_not_committed_evidence");
  if (evidence.status === "rolled_back") require(metadata.every((item) => item !== null) && attemptedKeys.length > 0 && noCommit && evidence.rollbackReasonCode !== "" && evidence.rolledBackAt !== null, ep, "invalid_rollback_evidence");
  if (evidence.status === "committed") {
    require(metadata.every((item) => item !== null) && attemptedKeys.length > 0 && evidence.payloadDigest !== null && evidence.committedAt !== null && noRollback, ep, "committed_evidence_incomplete");
    require(JSON.stringify(attemptedKeys) === JSON.stringify(committedKeys), ep, "commit_resource_set_mismatch");
    evidence.attemptedResourceRefs.forEach((item, index) => require(item.revision === evidence.committedResources[index]?.expectedRevision, ep, "commit_expected_revision_mismatch"));
    if (evidence.digestScope === "committed_projection") require(evidence.payloadDigest === evidence.committedResources[0]?.payloadDigest, ep, "projection_digest_mismatch");
  }
  if (schema === "harness-trace-v3") evidence.attemptedResourceRefs.forEach((item, index) => {
    const policy = HARNESS_RESOURCE_EVIDENCE_POLICIES[resourceType(item.resourceType, ep)];
    require(policy.commitEvidence === "revision" || item.revision === null, `${ep}.attempted_resource_refs[${index}]`, "attempt_revision_forbidden");
    if (evidence.status === "committed") require(policy.commitEvidence !== "unsupported" && (policy.commitEvidence !== "revision" || item.revision !== null), ep, "attempt_commit_proof_required");
    if (evidence.status === "rolled_back") require(policy.rollbackEvidence !== "unsupported", ep, "rollback_resource_unsupported");
  });
  const attempts = list(trace.attempt_records, `${path}.attempt_records`, (value, pp): HarnessAttempt => {
    const r = obj(value, pp, ["attempt_id", "attempt_index", "phase", "status", "output_digest", "error_code", "duration_ms"]);
    const result = { attemptId: str(r.attempt_id, `${pp}.attempt_id`), attemptIndex: d.integer(r.attempt_index, `${pp}.attempt_index`, 1), phase: d.enumeration(r.phase, PHASES, `${pp}.phase`), status: d.enumeration(r.status, ["passed", "failed", "skipped"] as const, `${pp}.status`), outputDigest: nullable(r.output_digest, `${pp}.output_digest`, digest), errorCode: str(r.error_code, `${pp}.error_code`, 160, true), durationMs: d.integer(r.duration_ms, `${pp}.duration_ms`) };
    require((result.status === "failed") === (result.errorCode !== ""), pp, "attempt_error_status_mismatch"); return result;
  }, 128, 1);
  const checks = list(trace.checks, `${path}.checks`, (value, pp): HarnessCheckV2 => { const r = obj(value, pp, ["name", "status", "code", "message"]); return { name: str(r.name, `${pp}.name`), status: d.enumeration(r.status, ["passed", "failed", "warning", "skipped"] as const, `${pp}.status`), code: str(r.code, `${pp}.code`, 160, true), message: str(r.message, `${pp}.message`, 2000, true) }; }, 256);
  const base = { traceId: str(trace.trace_id, `${path}.trace_id`), operationId, parentTraceId: nullable(trace.parent_trace_id, `${path}.parent_trace_id`, str), workflow, status: d.enumeration(trace.status, STATUSES, `${path}.status`), contract: contract(trace.contract, `${path}.contract`), outputDigest: nullable(trace.output_digest, `${path}.output_digest`, digest), checks, attemptRecords: attempts, recoveryStrategy: str(trace.recovery_strategy, `${path}.recovery_strategy`, 320), errorCode: str(trace.error_code, `${path}.error_code`, 160, true), durationMs: d.integer(trace.duration_ms, `${path}.duration_ms`), startedAt: utc(trace.started_at, `${path}.started_at`), completedAt: utc(trace.completed_at, `${path}.completed_at`) };
  require(base.parentTraceId !== base.traceId, path, "parent_trace_self_reference");
  require(Date.parse(base.completedAt) >= Date.parse(base.startedAt), path, "trace_time_range_invalid");
  require(new Set(attempts.map((item) => item.attemptId)).size === attempts.length, path, "attempt_id_duplicate");
  require(attempts.every((item, index) => item.attemptIndex === index + 1 && item.durationMs <= base.durationMs), path, "invalid_attempt_order_or_duration");
  const failedAttempts = attempts.filter((item) => item.status === "failed");
  const failedChecks = checks.filter((item) => item.status === "failed");
  const warnings = checks.filter((item) => item.status === "warning");
  const repairs = attempts.filter((item) => item.phase === "repair" && item.status === "passed");
  const commits = attempts.filter((item) => item.phase === "commit");
  const rollbacks = attempts.filter((item) => item.phase === "rollback");
  const outputs = attempts.filter((item) => ["generate", "decode", "validate", "repair"].includes(item.phase));
  const success = base.status === "passed" || base.status === "repaired";
  require((base.status === "failed") === (base.errorCode !== ""), path, "trace_error_status_mismatch");
  if (base.status === "passed") require(!failedAttempts.length && !failedChecks.length && !warnings.length && !repairs.length && base.recoveryStrategy === "none", path, "passed_trace_contains_failure_or_recovery");
  if (base.status === "repaired") require(base.recoveryStrategy !== "none" && repairs.length > 0 && (failedAttempts.length > 0 || warnings.length > 0) && !failedChecks.length, path, "repaired_trace_evidence_missing");
  if (base.status === "failed") require(failedAttempts.length > 0 || failedChecks.length > 0, path, "failed_trace_evidence_missing");
  if (base.status === "skipped") require(base.outputDigest === null && base.recoveryStrategy === "none" && !failedChecks.length && attempts.every((item) => item.status === "skipped") && evidence.status === "not_applicable", path, "skipped_trace_contains_execution");
  if (success) {
    const last = outputs.at(-1);
    require(base.outputDigest !== null && last?.phase === "validate" && last.status === "passed" && last.outputDigest === base.outputDigest, path, "terminal_output_validation_missing");
    if (base.status === "repaired") require(repairs.at(-1)!.attemptIndex < last!.attemptIndex, path, "validation_after_repair_required");
  }
  if (evidence.status === "committed") require(success && commits.at(-1) === attempts.at(-1) && commits.at(-1)?.status === "passed" && commits.at(-1)?.outputDigest === evidence.payloadDigest, path, "terminal_commit_attempt_mismatch");
  if (evidence.status === "not_applicable") require(commits.length === 0 && rollbacks.length === 0, path, "not_applicable_commit_attempt_forbidden");
  if (evidence.status === "not_committed") require(!commits.some((item) => item.status === "passed") && !rollbacks.length && (attemptedKeys.length ? commits.at(-1)?.status === "failed" : commits.length === 0), path, "not_committed_attempt_mismatch");
  if (evidence.status === "rolled_back") require(base.status === "failed" && commits.at(-1) === attempts.at(-2) && commits.at(-1)?.status === "failed" && !commits.some((item) => item.status === "passed") && rollbacks.at(-1) === attempts.at(-1) && rollbacks.at(-1)?.status === "passed", path, "rollback_attempt_chain_invalid");
  for (const timestamp of [evidence.committedAt, evidence.rolledBackAt]) if (timestamp !== null) require(Date.parse(timestamp) >= Date.parse(base.startedAt) && Date.parse(timestamp) <= Date.parse(base.completedAt), path, "effect_time_outside_trace");
  if (schema === "harness-trace-v3" && "contextContract" in context) {
    const hasClaim = ["committed", "rolled_back"].includes(evidence.status) || evidence.payloadContract !== null || attemptedKeys.length > 0 || committedKeys.length > 0;
    const candidates = Object.values(HARNESS_OPERATION_COMMIT_POLICIES).filter((item) => item.workflow === workflow && item.stage === stage && sameContract(item.traceContract, base.contract));
    if (candidates.length || hasClaim) {
      const policy = candidates.find((item) => evidence.payloadContract !== null && sameContract(item.payloadContract, evidence.payloadContract));
      if (!(base.status === "failed" && evidence.status === "not_committed" && !hasClaim)) {
        require(policy !== undefined, ep, "operation_commit_policy_unregistered");
        if (policy) {
          require(policy.statusRules.some((rule) => rule.traceStatus === base.status && rule.commitStatus === evidence.status) && policy.digestScope === evidence.digestScope, ep, "operation_commit_policy_mismatch");
          require(context.subjectRefs.filter((ref) => ref.resourceType === policy.subjectResourceType).length === policy.subjectResourceCount, ep, "operation_subject_count_mismatch");
          const allowed: readonly HarnessResourceType[] = policy.resourceRules.map((rule) => rule.resourceType);
          require([...evidence.attemptedResourceRefs, ...evidence.committedResources].every((ref) => allowed.includes(resourceType(ref.resourceType, ep))), ep, "operation_resource_set_mismatch");
          for (const rule of policy.resourceRules) {
            const a = evidence.attemptedResourceRefs.filter((ref) => ref.resourceType === rule.resourceType).length;
            const b = evidence.committedResources.filter((ref) => ref.resourceType === rule.resourceType).length;
            require(evidence.status === "committed" ? a === rule.committedAttemptedCount && b === rule.committedResourceCount : a >= rule.notCommittedAttemptedMin && a <= rule.notCommittedAttemptedMax && b === 0, ep, "operation_resource_count_mismatch");
          }
        }
      }
    }
    return { ...base, traceSchemaVersion: "harness-trace-v3", stage: context.stage, context, commitEvidence: { ...evidence, attemptedResourceRefs: evidence.attemptedResourceRefs.map((ref) => ({ ...ref, resourceType: resourceType(ref.resourceType, ep) })), committedResources: evidence.committedResources.map((ref) => ({ ...ref, resourceType: resourceType(ref.resourceType, ep) })) } };
  }
  if (!("schemaName" in context)) return fail(p, "legacy_context_required");
  return { ...base, traceSchemaVersion: "harness-trace-v2", stage, context, commitEvidence: evidence };
}

/** Decode a production v3 trace for domain-owned API boundaries. */
export function decodeHarnessTraceV3(
  raw: unknown,
  path: string,
  fail: DecodeFailure,
): HarnessTraceV3 {
  return decodeVersionedHarnessTrace(raw, path, "harness-trace-v3", fail) as HarnessTraceV3;
}
