import assert from "node:assert/strict";
import test from "node:test";
import { decodeStudyUnitRevision } from "../lib/study-unit-revision-decode.ts";
import { wireUnitRevision } from "./support/study-unit-revision-wire.ts";

test("preview and accepted read-back bind original identity and one Document revision", () => {
  const ready = decodeStudyUnitRevision(wireUnitRevision(), "plan-1", "document-1");
  const accepted = decodeStudyUnitRevision(wireUnitRevision(true), "plan-1", "document-1");
  assert.equal(ready.result, null);
  assert.equal(accepted.result?.studyUnits[0].id, ready.preview.baseDocument.studyUnits[0].id);
  assert.equal(accepted.planningContextRevision, ready.preview.baseDocument.revision + 1);
});

test("malformed suggestions and inconsistent acceptance fail closed", () => {
  const changes = [
    (raw: any) => { raw.preview.suggestions.study_units[0].include_in_plan = "false"; },
    (raw: any) => { raw.preview.suggestions.study_units[0].revision = 2; },
    (raw: any) => { raw.preview.suggestions.study_units[0].page_end = 3; },
    (raw: any) => { raw.preview.suggestions.study_units.push({ ...raw.preview.suggestions.study_units[0] }); },
    (raw: any) => { raw.preview.plan_id = "foreign"; },
    (raw: any) => { raw.result.revision++; },
    (raw: any) => { raw.planning_context_revision = 0; },
    (raw: any) => { raw.result.study_units[0].id = "foreign"; raw.result.sections[0].id = "foreign"; },
    (raw: any) => { raw.result.title = "unrelated mutation"; },
    (raw: any) => { raw.status = "rejected"; },
  ];
  for (const change of changes) {
    const raw = wireUnitRevision(true);
    change(raw);
    assert.throws(() => decodeStudyUnitRevision(raw, "plan-1", "document-1"));
  }
});
