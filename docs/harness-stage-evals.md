# Harness stage regression suites

The ten previously missing operation-stage suites now execute through
`HarnessEvalRunner`, alongside the three existing pilot suites. These are
developer-authored deterministic regression cases, not independently reviewed
held-out quality baselines. All thirteen manifest entries have eval registrations;
this does not close the Wave 4/5 joint acceptance gate.

## Coverage

Each suite version is its name with underscores replaced by hyphens, followed
by `-v1`. The checked-in cases and gate counts live in
`packages/shared/fixtures/harness/stage-regression-{cases,gates}-v1.json`.

| Suite | Cases | Production behavior exercised |
| --- | ---: | --- |
| `document_process_regression` | 6 | Parsed Document output validation; missing/duplicate pages, foreign references, page bounds |
| `page_extraction_regression` | 2 | Real searchable PDF extraction, page ordering, text anchors, native-text OCR bypass |
| `section_detection_regression` | 2 | TOC and no-TOC paths, unique sections and bounded page ranges |
| `chunk_building_regression` | 4 | Regular, empty, nested and Unicode content; text conservation and section attribution |
| `ocr_page_regression` | 5 | OCR engine seam with deterministic results: gain, failure, unavailable, no gain and native bypass |
| `study_unit_cleanup_regression` | 3 | Production cleanup with ordinary sections, missing sections and backmatter |
| `plan_generation_regression` | 8 | Strict proposal decoding, unit/chapter/slice references, duplicate units, owned IDs, page bounds and goal-only fallback |
| `persona_generation_regression` | 15 | Proposal validation, locked/custom/idempotent fallback, structured repair, exhausted repair and user-control preservation |
| `scene_generation_regression` | 8 | Strict proposal and committed projection, nested trees, depth limits, paths, tags, owned IDs and reusable-node authorization |
| `frontend_decode_regression` | 11 | Actual TypeScript response decoders and v3 trace routing, including malformed contracts and stage mismatches |
| **Total** | **64** | |

Persona repair uses the production provider adapter with a fixture transport.
Its system configuration declares at most two attempts/provider-adapter calls
and one repair. No external model request is issued. OCR fixtures replace the
engine result, so these cases measure fallback/selection behavior, not neural
OCR accuracy. Frontend cases launch Node against the production decoders; an
unexpected JavaScript error remains infrastructure failure rather than an
accepted negative sample.

## Running and reviewing

Use the repository's Node 26 runtime and uv-managed Python environment:

```bash
npm run eval:harness:stages
npm run eval:harness:stages -- --list-suites
npm run eval:harness:stages -- --suite persona_generation_regression
npm run eval:harness:stages -- --output-dir /tmp/harness-stage-eval
npm run eval:harness:pr
npm run check:release
```

`eval:harness:pr` runs the existing three pilots followed by all ten stage suites.
The stage gate requires the exact checked-in sample count and every sample and
aggregate report to pass. A failed or broken result exits nonzero. The generic
eval CLI also exits nonzero for a non-passing report.

The output directory contains each suite's `input.json` (run and case records),
`raw-samples.json`, `aggregate.json` and `gate.json`. Records bind the actual
environment, source revision, dirty-source digest when applicable, tested-system
configuration, fixture digests and admitted operation identity. Temporary test
databases are removed after execution. Re-running creates new operation/run
identities; deterministic comparison concerns case behavior, not those IDs or
wall-clock timings.

Case or expectation changes require reviewing the corresponding production
behavior and updating the versioned fixture/gate counts together. Do not lower
the gate or convert broken execution into candidate success to absorb a failure.
The suite tests inject wrong observations for every stage, bypass production
validators, corrupt fixture digests and crash the executor to check failure
ownership and gate behavior.

## Identity and evidence boundaries

Every sample uses real durable admission and authoritative binding read-back in
an isolated SQLite database. Frontend Decode has its own generic workflow
operation kind; migration `20260909_0019` widens the closed route constraints
while preserving existing rows and immutable-binding guards. Runtime SQLite
compatibility repair covers databases that do not run Alembic. Downgrade refuses
to discard existing Frontend Decode admission tombstones.

Document and Planning stage runs terminate as interrupted/not committed because
the suite does not commit their domain output. The other stage admissions are
terminalized without a product-output commit. No synthetic v3 terminal trace or
protected replay evidence is fabricated. Candidate schema-validity metrics
describe the typed stage observation; an intentionally rejected bad proposal
passes only when the grader confirms the expected rejection behavior.

These suites close the missing executable-registration and deterministic
regression coverage gap. Real MiniMax M3 quality, neural OCR accuracy, protected
artifact replay, full workflow commit/recovery, broader maximum-input coverage
and independent UX/reliability revalidation retain their separate acceptance
requirements in `harness-roadmap.md`.

Recovery and maximum-input follow-up: the [2026-09-10 technical acceptance](acceptance-wave45-2026-09-10/recovery-limits/README.md) records 24 abrupt process windows, configured size boundaries, and real HTTP read-back after restart. Run `npm run test:acceptance:recovery-limits` for this separate technical matrix. Quality review remains deferred.
