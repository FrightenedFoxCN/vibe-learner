import type { HarnessArtifactType, HarnessContractRef } from "./harness";

export const HARNESS_ARTIFACT_PRINCIPAL_SCHEMA_VERSION =
  "harness-artifact-principal-v1" as const;
export const HARNESS_ARTIFACT_GRANT_SCHEMA_VERSION =
  "harness-artifact-grant-v1" as const;
export const HARNESS_ARTIFACT_ACCESS_AUDIT_SCHEMA_VERSION =
  "harness-artifact-access-audit-v1" as const;
export const HARNESS_ARTIFACT_ACCESS_CASES_SCHEMA_VERSION =
  "harness-artifact-access-cases-v1" as const;
export const HARNESS_ARTIFACT_ACCESS_GOLDEN_SCHEMA_VERSION =
  "harness-artifact-access-golden-v1" as const;
export const HARNESS_ARTIFACT_ACCESS_CONTRACT_REGISTRY_VERSION =
  "harness-artifact-access-contract-registry-v1" as const;

export type HarnessArtifactPrincipalKind = "local_installation";
export type HarnessArtifactAuthorizationMode = "server_resolved_principal";
export type HarnessArtifactPermission = "read" | "verify_digest";
export type HarnessArtifactAccessOutcome =
  | "allowed"
  | "principal_required"
  | "forbidden"
  | "grant_not_active"
  | "expired"
  | "revoked";

// Canonical wire DTOs deliberately keep Python's snake_case JSON names.
export interface HarnessArtifactPrincipalV1 {
  schema_name: "HarnessArtifactPrincipal";
  schema_version: typeof HARNESS_ARTIFACT_PRINCIPAL_SCHEMA_VERSION;
  principal_kind: HarnessArtifactPrincipalKind;
  principal_id: string;
}

export interface HarnessArtifactGrantScopeV1 {
  artifact_type: HarnessArtifactType;
  artifact_id: string;
  artifact_contract: HarnessContractRef;
  permission: HarnessArtifactPermission;
}

export interface HarnessArtifactGrantV1 {
  schema_name: "HarnessArtifactGrant";
  schema_version: typeof HARNESS_ARTIFACT_GRANT_SCHEMA_VERSION;
  grant_id: string;
  harness_operation_id: string;
  subject: HarnessArtifactPrincipalV1;
  authorization_mode: HarnessArtifactAuthorizationMode;
  scopes: HarnessArtifactGrantScopeV1[];
  issued_at: string;
  expires_at: string;
  revoked_at: string | null;
}

export interface HarnessArtifactAccessAuditV1 {
  schema_name: "HarnessArtifactAccessAudit";
  schema_version: typeof HARNESS_ARTIFACT_ACCESS_AUDIT_SCHEMA_VERSION;
  outcome: HarnessArtifactAccessOutcome;
  evaluated_at: string;
  presented_principal_id: string | null;
  grant_id: string;
  harness_operation_id: string;
  grant_harness_operation_id: string;
  grant_subject_id: string;
  artifact_type: HarnessArtifactType;
  artifact_id: string;
  artifact_contract: HarnessContractRef;
  permission: HarnessArtifactPermission;
}

export interface HarnessArtifactAccessCaseV1 {
  case_id: string;
  presented_principal_id: string | null;
  harness_operation_id: string;
  artifact_id: string;
  evaluated_at: string;
  grant_expires_at: string;
  grant_revoked_at: string | null;
  expected_outcome: HarnessArtifactAccessOutcome;
}

export interface HarnessArtifactAccessCasesV1 {
  schema_name: "HarnessArtifactAccessCases";
  schema_version: typeof HARNESS_ARTIFACT_ACCESS_CASES_SCHEMA_VERSION;
  grant_harness_operation_id: string;
  cases: HarnessArtifactAccessCaseV1[];
}

export interface HarnessArtifactAccessGoldenV1 {
  schema_name: "HarnessArtifactAccessGolden";
  schema_version: typeof HARNESS_ARTIFACT_ACCESS_GOLDEN_SCHEMA_VERSION;
  principal: HarnessArtifactPrincipalV1;
  grant: HarnessArtifactGrantV1;
  allowed_audit: HarnessArtifactAccessAuditV1;
}

export class HarnessArtifactAccessDecodeError extends Error {
  readonly code = "harness_artifact_access_decode_error";

  constructor(readonly path: string, readonly reason: string) {
    super(`${path}:${reason}`);
    this.name = "HarnessArtifactAccessDecodeError";
  }
}

const PRINCIPAL_ID = /^local-installation-[0-9a-f]{32}$/;
const GRANT_ID = /^harness-artifact-grant-[0-9a-f]{32}$/;
const OPERATION_ID = /^harness-operation-[0-9a-f]{32}$/;
const ARTIFACT_ID = /^[A-Za-z0-9][A-Za-z0-9._-]{0,159}$/;
const CONTRACT_TOKEN = /^[A-Za-z0-9][A-Za-z0-9:._-]{0,159}$/;
const CASE_ID = /^[a-z][a-z0-9-]{0,79}$/;
const UTC_TIMESTAMP = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z$/;

const ARTIFACT_TYPES = [
  "document_upload", "document_debug", "ocr_page", "study_unit_input",
  "planning_context", "persona_snapshot", "scene_snapshot",
  "study_session_snapshot", "tavern_room_snapshot", "tavern_transcript",
  "frontend_response_fixture",
] as const satisfies readonly HarnessArtifactType[];
const PERMISSIONS = ["read", "verify_digest"] as const;
const OUTCOMES = [
  "allowed", "principal_required", "forbidden", "grant_not_active", "expired", "revoked",
] as const;

function fail(path: string, reason: string): never {
  throw new HarnessArtifactAccessDecodeError(path, reason);
}

function record(raw: unknown, path: string, expectedKeys: readonly string[]): Record<string, unknown> {
  if (raw === null || typeof raw !== "object" || Array.isArray(raw)) fail(path, "expected_object");
  const value = raw as Record<string, unknown>;
  const actual = Object.keys(value).sort();
  const expected = [...expectedKeys].sort();
  if (actual.length !== expected.length || actual.some((key, index) => key !== expected[index])) {
    fail(path, "unexpected_or_missing_fields");
  }
  return value;
}

function text(raw: unknown, path: string, pattern: RegExp): string {
  if (typeof raw !== "string" || !pattern.test(raw)) fail(path, "invalid_string");
  return raw;
}

function enumeration<const T extends readonly string[]>(raw: unknown, values: T, path: string): T[number] {
  if (typeof raw !== "string" || !(values as readonly string[]).includes(raw)) fail(path, "invalid_enum");
  return raw as T[number];
}

function timestamp(raw: unknown, path: string): string {
  const value = text(raw, path, UTC_TIMESTAMP);
  const parsed = new Date(value);
  const parts = /^([0-9]{4})-([0-9]{2})-([0-9]{2})T([0-9]{2}):([0-9]{2}):([0-9]{2})/.exec(value);
  if (!parts || !Number.isFinite(parsed.getTime())
    || parsed.getUTCFullYear() !== Number(parts[1])
    || parsed.getUTCMonth() + 1 !== Number(parts[2])
    || parsed.getUTCDate() !== Number(parts[3])
    || parsed.getUTCHours() !== Number(parts[4])
    || parsed.getUTCMinutes() !== Number(parts[5])
    || parsed.getUTCSeconds() !== Number(parts[6])) {
    fail(path, "invalid_timestamp");
  }
  return value;
}

function nullableTimestamp(raw: unknown, path: string): string | null {
  return raw === null ? null : timestamp(raw, path);
}

function nullablePrincipalId(raw: unknown, path: string): string | null {
  return raw === null ? null : text(raw, path, PRINCIPAL_ID);
}

function contract(raw: unknown, path: string): HarnessContractRef {
  const value = record(raw, path, ["name", "version"]);
  const name = text(value.name, `${path}.name`, CONTRACT_TOKEN);
  const version = text(value.version, `${path}.version`, CONTRACT_TOKEN);
  const normalized = version.trim().toLowerCase();
  if (normalized.startsWith("pending-") || ["latest", "unknown", "none"].includes(normalized)) {
    fail(`${path}.version`, "contract_version_not_adopted");
  }
  return { name, version };
}

function sameContract(left: HarnessContractRef, right: HarnessContractRef): boolean {
  return left.name === right.name && left.version === right.version;
}

function scopeKey(scope: HarnessArtifactGrantScopeV1): string {
  return [scope.artifact_type, scope.artifact_id, scope.artifact_contract.name,
    scope.artifact_contract.version, scope.permission].join("\u0000");
}

export function decodeHarnessArtifactPrincipal(raw: unknown, path = "principal"): HarnessArtifactPrincipalV1 {
  const value = record(raw, path, ["schema_name", "schema_version", "principal_kind", "principal_id"]);
  if (value.schema_name !== "HarnessArtifactPrincipal" || value.schema_version !== HARNESS_ARTIFACT_PRINCIPAL_SCHEMA_VERSION) {
    fail(path, "contract_mismatch");
  }
  return {
    schema_name: "HarnessArtifactPrincipal",
    schema_version: HARNESS_ARTIFACT_PRINCIPAL_SCHEMA_VERSION,
    principal_kind: enumeration(value.principal_kind, ["local_installation"] as const, `${path}.principal_kind`),
    principal_id: text(value.principal_id, `${path}.principal_id`, PRINCIPAL_ID),
  };
}

export function decodeHarnessArtifactGrantScope(raw: unknown, path = "scope"): HarnessArtifactGrantScopeV1 {
  const value = record(raw, path, ["artifact_type", "artifact_id", "artifact_contract", "permission"]);
  return {
    artifact_type: enumeration(value.artifact_type, ARTIFACT_TYPES, `${path}.artifact_type`),
    artifact_id: text(value.artifact_id, `${path}.artifact_id`, ARTIFACT_ID),
    artifact_contract: contract(value.artifact_contract, `${path}.artifact_contract`),
    permission: enumeration(value.permission, PERMISSIONS, `${path}.permission`),
  };
}

export function decodeHarnessArtifactGrant(raw: unknown, path = "grant"): HarnessArtifactGrantV1 {
  const value = record(raw, path, ["schema_name", "schema_version", "grant_id", "harness_operation_id",
    "subject", "authorization_mode", "scopes", "issued_at", "expires_at", "revoked_at"]);
  if (value.schema_name !== "HarnessArtifactGrant" || value.schema_version !== HARNESS_ARTIFACT_GRANT_SCHEMA_VERSION) {
    fail(path, "contract_mismatch");
  }
  if (!Array.isArray(value.scopes) || value.scopes.length < 1 || value.scopes.length > 64) fail(`${path}.scopes`, "invalid_array_length");
  const scopes = value.scopes.map((item, index) => decodeHarnessArtifactGrantScope(item, `${path}.scopes[${index}]`));
  const keys = scopes.map(scopeKey);
  if (new Set(keys).size !== keys.length) fail(`${path}.scopes`, "duplicate_scope");
  if (keys.some((key, index) => index > 0 && keys[index - 1]! > key)) fail(`${path}.scopes`, "scopes_not_sorted");
  const issuedAt = timestamp(value.issued_at, `${path}.issued_at`);
  const expiresAt = timestamp(value.expires_at, `${path}.expires_at`);
  const revokedAt = nullableTimestamp(value.revoked_at, `${path}.revoked_at`);
  if (Date.parse(expiresAt) <= Date.parse(issuedAt)) fail(path, "expiry_invalid");
  if (revokedAt !== null && Date.parse(revokedAt) < Date.parse(issuedAt)) fail(path, "revocation_invalid");
  return {
    schema_name: "HarnessArtifactGrant", schema_version: HARNESS_ARTIFACT_GRANT_SCHEMA_VERSION,
    grant_id: text(value.grant_id, `${path}.grant_id`, GRANT_ID),
    harness_operation_id: text(value.harness_operation_id, `${path}.harness_operation_id`, OPERATION_ID),
    subject: decodeHarnessArtifactPrincipal(value.subject, `${path}.subject`),
    authorization_mode: enumeration(value.authorization_mode, ["server_resolved_principal"] as const, `${path}.authorization_mode`),
    scopes, issued_at: issuedAt, expires_at: expiresAt, revoked_at: revokedAt,
  };
}

export function decodeHarnessArtifactAccessAudit(raw: unknown, path = "access_audit"): HarnessArtifactAccessAuditV1 {
  const value = record(raw, path, ["schema_name", "schema_version", "outcome", "evaluated_at",
    "presented_principal_id", "grant_id", "harness_operation_id", "grant_harness_operation_id",
    "grant_subject_id", "artifact_type", "artifact_id", "artifact_contract", "permission"]);
  if (value.schema_name !== "HarnessArtifactAccessAudit" || value.schema_version !== HARNESS_ARTIFACT_ACCESS_AUDIT_SCHEMA_VERSION) {
    fail(path, "contract_mismatch");
  }
  const audit: HarnessArtifactAccessAuditV1 = {
    schema_name: "HarnessArtifactAccessAudit", schema_version: HARNESS_ARTIFACT_ACCESS_AUDIT_SCHEMA_VERSION,
    outcome: enumeration(value.outcome, OUTCOMES, `${path}.outcome`),
    evaluated_at: timestamp(value.evaluated_at, `${path}.evaluated_at`),
    presented_principal_id: nullablePrincipalId(value.presented_principal_id, `${path}.presented_principal_id`),
    grant_id: text(value.grant_id, `${path}.grant_id`, GRANT_ID),
    harness_operation_id: text(value.harness_operation_id, `${path}.harness_operation_id`, OPERATION_ID),
    grant_harness_operation_id: text(value.grant_harness_operation_id, `${path}.grant_harness_operation_id`, OPERATION_ID),
    grant_subject_id: text(value.grant_subject_id, `${path}.grant_subject_id`, PRINCIPAL_ID),
    artifact_type: enumeration(value.artifact_type, ARTIFACT_TYPES, `${path}.artifact_type`),
    artifact_id: text(value.artifact_id, `${path}.artifact_id`, ARTIFACT_ID),
    artifact_contract: contract(value.artifact_contract, `${path}.artifact_contract`),
    permission: enumeration(value.permission, PERMISSIONS, `${path}.permission`),
  };
  if ((audit.presented_principal_id === null) !== (audit.outcome === "principal_required")) {
    fail(path, "principal_outcome_mismatch");
  }
  if (audit.outcome === "allowed" && (
    audit.presented_principal_id !== audit.grant_subject_id
    || audit.harness_operation_id !== audit.grant_harness_operation_id
  )) {
    fail(path, "allowed_identity_mismatch");
  }
  return audit;
}

function decodeHarnessArtifactAccessCase(raw: unknown, path: string): HarnessArtifactAccessCaseV1 {
  const value = record(raw, path, ["case_id", "presented_principal_id", "harness_operation_id",
    "artifact_id", "evaluated_at", "grant_expires_at", "grant_revoked_at", "expected_outcome"]);
  return {
    case_id: text(value.case_id, `${path}.case_id`, CASE_ID),
    presented_principal_id: nullablePrincipalId(value.presented_principal_id, `${path}.presented_principal_id`),
    harness_operation_id: text(value.harness_operation_id, `${path}.harness_operation_id`, OPERATION_ID),
    artifact_id: text(value.artifact_id, `${path}.artifact_id`, ARTIFACT_ID),
    evaluated_at: timestamp(value.evaluated_at, `${path}.evaluated_at`),
    grant_expires_at: timestamp(value.grant_expires_at, `${path}.grant_expires_at`),
    grant_revoked_at: nullableTimestamp(value.grant_revoked_at, `${path}.grant_revoked_at`),
    expected_outcome: enumeration(value.expected_outcome, OUTCOMES, `${path}.expected_outcome`),
  };
}

export function decodeHarnessArtifactAccessCases(raw: unknown, path = "artifact_access_cases"): HarnessArtifactAccessCasesV1 {
  const value = record(raw, path, ["schema_name", "schema_version", "grant_harness_operation_id", "cases"]);
  if (value.schema_name !== "HarnessArtifactAccessCases" || value.schema_version !== HARNESS_ARTIFACT_ACCESS_CASES_SCHEMA_VERSION) {
    fail(path, "contract_mismatch");
  }
  if (!Array.isArray(value.cases) || value.cases.length < 1 || value.cases.length > 64) fail(`${path}.cases`, "invalid_array_length");
  const cases = value.cases.map((item, index) => decodeHarnessArtifactAccessCase(item, `${path}.cases[${index}]`));
  const caseIds = cases.map((item) => item.case_id);
  if (new Set(caseIds).size !== caseIds.length) fail(`${path}.cases`, "duplicate_case");
  if (caseIds.some((caseId, index) => index > 0 && caseIds[index - 1]! > caseId)) fail(`${path}.cases`, "cases_not_sorted");
  return {
    schema_name: "HarnessArtifactAccessCases", schema_version: HARNESS_ARTIFACT_ACCESS_CASES_SCHEMA_VERSION,
    grant_harness_operation_id: text(value.grant_harness_operation_id, `${path}.grant_harness_operation_id`, OPERATION_ID),
    cases,
  };
}

export function decodeHarnessArtifactAccessGolden(raw: unknown, path = "artifact_access_golden"): HarnessArtifactAccessGoldenV1 {
  const value = record(raw, path, ["schema_name", "schema_version", "principal", "grant", "allowed_audit"]);
  if (value.schema_name !== "HarnessArtifactAccessGolden" || value.schema_version !== HARNESS_ARTIFACT_ACCESS_GOLDEN_SCHEMA_VERSION) {
    fail(path, "contract_mismatch");
  }
  const principal = decodeHarnessArtifactPrincipal(value.principal, `${path}.principal`);
  const grant = decodeHarnessArtifactGrant(value.grant, `${path}.grant`);
  const audit = decodeHarnessArtifactAccessAudit(value.allowed_audit, `${path}.allowed_audit`);
  const firstScope = grant.scopes[0]!;
  if (grant.subject.principal_id !== principal.principal_id || audit.outcome !== "allowed" ||
      audit.presented_principal_id !== principal.principal_id || audit.grant_subject_id !== principal.principal_id ||
      audit.grant_id !== grant.grant_id || audit.harness_operation_id !== grant.harness_operation_id ||
      audit.grant_harness_operation_id !== grant.harness_operation_id || audit.artifact_type !== firstScope.artifact_type ||
      audit.artifact_id !== firstScope.artifact_id || !sameContract(audit.artifact_contract, firstScope.artifact_contract) ||
      audit.permission !== firstScope.permission) fail(path, "identity_mismatch");
  return {
    schema_name: "HarnessArtifactAccessGolden", schema_version: HARNESS_ARTIFACT_ACCESS_GOLDEN_SCHEMA_VERSION,
    principal, grant, allowed_audit: audit,
  };
}

export const harnessArtifactAccessContractRegistrySnapshot = () => ({
  schema_name: "HarnessArtifactAccessContractRegistry" as const,
  schema_version: HARNESS_ARTIFACT_ACCESS_CONTRACT_REGISTRY_VERSION,
  authoritative_boundary: {
    principal_kind: "local_installation" as const,
    authorization_mode: "server_resolved_principal" as const,
    grant_is_bearer_secret: false,
    grant_is_operation_scoped: true,
    missing_principal_outcome: "principal_required" as const,
  },
  contracts: {
    principal: { name: "HarnessArtifactPrincipal" as const, version: HARNESS_ARTIFACT_PRINCIPAL_SCHEMA_VERSION },
    grant: { name: "HarnessArtifactGrant" as const, version: HARNESS_ARTIFACT_GRANT_SCHEMA_VERSION },
    audit: { name: "HarnessArtifactAccessAudit" as const, version: HARNESS_ARTIFACT_ACCESS_AUDIT_SCHEMA_VERSION },
  },
  permissions: PERMISSIONS,
  outcomes: OUTCOMES,
});
