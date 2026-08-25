import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { decodeDocumentRecord } from "../lib/document-decode.ts";
import { decodePersonaProfile, decodeSceneProfile } from "../lib/persona-scene-decode.ts";
import { decodeLearningPlan } from "../lib/planning-decode.ts";
import { StrictStreamStateMachine } from "../lib/stream-decode.ts";
import { decodeStudySession } from "../lib/study-session-decode.ts";
import { normalizeTavernErrorDetail } from "../lib/tavern-decode.ts";

type Domain = "document" | "plan" | "persona" | "scene" | "study" | "tavern" | "stream";
type Category = "identity" | "type" | "envelope" | "stream_state";
type DecoderName =
  | "document_record"
  | "learning_plan"
  | "persona_profile"
  | "scene_profile"
  | "study_session"
  | "tavern_error_detail"
  | "stream_state_machine";

interface AdversarialCase {
  case_id: string;
  domain: Domain;
  category: Category;
  decoder: DecoderName;
  input: unknown;
  invocation: Record<string, unknown>;
  expected_error: {
    name: string;
    code: string;
    path: string;
    reason: string;
  };
}

interface AdversarialCatalog {
  schema_version: string;
  cases: AdversarialCase[];
}

const fixtureUrl = new URL(
  "../../../packages/shared/fixtures/adversarial/web-strict-decode-v1.json",
  import.meta.url,
);
const catalog = JSON.parse(readFileSync(fixtureUrl, "utf8")) as AdversarialCatalog;

function requiredString(
  value: Record<string, unknown>,
  key: string,
  caseId: string,
): string {
  const item = value[key];
  if (typeof item !== "string") {
    assert.fail(`${caseId}: invocation.${key} must be a string`);
  }
  assert.ok(item.length > 0, `${caseId}: invocation.${key} must not be empty`);
  return item;
}

function executeFixture(fixture: AdversarialCase): void {
  const invocation = fixture.invocation;
  switch (fixture.decoder) {
    case "document_record":
      decodeDocumentRecord(
        fixture.input,
        requiredString(invocation, "expected_document_id", fixture.case_id),
      );
      return;
    case "learning_plan":
      decodeLearningPlan(fixture.input, {
        expectedPlanId: requiredString(invocation, "expected_plan_id", fixture.case_id),
      });
      return;
    case "persona_profile":
      decodePersonaProfile(fixture.input);
      return;
    case "scene_profile":
      decodeSceneProfile(fixture.input);
      return;
    case "study_session":
      decodeStudySession(fixture.input, {
        expectedSessionId: requiredString(invocation, "expected_session_id", fixture.case_id),
      });
      return;
    case "tavern_error_detail":
      normalizeTavernErrorDetail(fixture.input);
      return;
    case "stream_state_machine": {
      assert.ok(Array.isArray(fixture.input), `${fixture.case_id}: stream input must be frames`);
      const machine = new StrictStreamStateMachine({
        streamKind: requiredString(invocation, "stream_kind", fixture.case_id) as "document_process" | "learning_plan",
        subject: {
          subjectType: requiredString(invocation, "subject_type", fixture.case_id) as "document" | "learning_plan_request",
          subjectId: requiredString(invocation, "subject_id", fixture.case_id),
        },
      });
      fixture.input.forEach((frame, index) => machine.accept(frame, `stream.frames[${index}]`));
      machine.finish();
      return;
    }
  }
}

function decodeFailure(error: unknown): {
  name: unknown;
  code: unknown;
  path: unknown;
  reason: unknown;
} {
  assert.ok(error instanceof Error, "strict decoder must throw an Error");
  const failure = error as Error & { code?: unknown; path?: unknown; reason?: unknown };
  const marker = typeof failure.path === "string" ? ` at ${failure.path}` : "";
  const derivedReason = marker && failure.message.endsWith(marker)
    ? failure.message.slice(0, -marker.length)
    : undefined;
  return {
    name: failure.name,
    code: failure.code,
    path: failure.path,
    reason: failure.reason ?? derivedReason,
  };
}

test("QG-002 shared adversarial catalog has closed domain and attack coverage", () => {
  assert.equal(catalog.schema_version, "web-strict-decode-adversarial-v1");
  assert.ok(Array.isArray(catalog.cases));
  assert.deepEqual(
    [...new Set(catalog.cases.map((fixture) => fixture.domain))].sort(),
    ["document", "persona", "plan", "scene", "stream", "study", "tavern"],
  );
  assert.deepEqual(
    [...new Set(catalog.cases.map((fixture) => fixture.category))].sort(),
    ["envelope", "identity", "stream_state", "type"],
  );
  assert.equal(
    new Set(catalog.cases.map((fixture) => fixture.case_id)).size,
    catalog.cases.length,
    "case IDs must be unique",
  );
});

for (const fixture of catalog.cases) {
  test(`${fixture.case_id} rejects ${fixture.domain}/${fixture.category}`, () => {
    let thrown: unknown;
    try {
      executeFixture(fixture);
    } catch (error) {
      thrown = error;
    }
    assert.notEqual(thrown, undefined, `${fixture.case_id}: adversarial input was accepted`);
    assert.deepEqual(
      decodeFailure(thrown),
      fixture.expected_error,
      `${fixture.case_id}: failure golden drifted`,
    );
  });
}
