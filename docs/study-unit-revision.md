# Study Unit revision

`revise_study_units` proposes a complete replacement list of textbook units. It does not change the saved Document, tool context, detail map or the current plan's unit references. The provider finishes a conservative plan against the original units. The Plan Workspace displays the saved proposal beside that plan, including old/new titles, PDF physical ranges, classification, inclusion, summaries and retained/removed units.

## Admission and confirmation

Plan generation commits the Plan, an immutable preview, its own `study_unit_revision` Harness binding and the parent v2 creation receipt atomically. The preview binds the exact Document revision, Debug digest, Plan and parent operation. It is available by Plan ID after refresh; no browser recovery identity needs to be invented or replayed.

Accepting uses the existing admitted operation at `planning:study_unit_revision`. The runtime resolves an operation-authorized protected preview/Debug snapshot before applying the pure application projection. A unique existing page range retains its unit ID; changed ranges receive operation-scoped application IDs. The same transaction fences acceptance, checks the base Document/Debug, increments the Document revision once, updates projected Sections and Debug units, and commits the receipt and terminal v3 trace. Read-back verifies the stored projection and trace digests. `/documents/{id}/planning-context` reads Document and Debug in one SQL statement and returns `document_revision`.

Rejection changes only the preview decision. Skipping leaves the ready preview and conservative plan usable. Accepting updates the shared textbook units; existing Plans and Study records retain their original snapshots. Later planning requests use the confirmed Document and its updated watermark. Acceptance does not issue another provider call or regenerate the existing Plan.

The decision state is `ready` → `applying` → `accepted`, `conflict` or `failed`, or `ready` → `rejected`. Matching repeated terminal decisions are idempotent; an opposing decision conflicts. Concurrent acceptance/rejection has one winner. Changed Document or Debug evidence prevents acceptance. Querying an interrupted `applying` operation after 240 seconds fences persistence and terminalizes its active runtime attempt without replay.

The frontend fetches the saved preview on mount, fences late responses after navigation, and disables both decisions after an ambiguous write. GET recovery or reload resolves the durable state. Accepted read-back refreshes the authoritative workspace snapshot. Raw receipts, protected Debug content and trace failure details stay server-side.

## Contracts and migration

- Current Planning runtime/creation projections use v2; the v1 DTOs and commit policy remain available for historical read-back.
- The revise tool has v2 arguments/results and adapter behavior; its result explicitly requires confirmation. Other Planning tools retain their versions.
- Alembic `20261029_0024` adds `study_unit_revision_operations` and widens the closed admission route. SQLite runtime schema repair preserves existing admissions and guards. PostgreSQL DDL retains JSONB; actual PostgreSQL acceptance remains under `REL-POSTGRES-001`.
- The local complete-transaction policy covers Document/Debug, the acceptance receipt and trace. Compatibility JSON mirrors run afterward and are not the authoritative commit.

## Focused verification

- `cd services/ai && uv run python -m unittest tests.test_study_unit_revision tests.test_study_unit_revision_evals tests.test_alembic_sqlite`: CAS conflicts, transaction rollback, competing decisions, fenced prepared outputs, interrupted-runtime recovery, restart and populated migrations.
- `npm run eval:harness:study-unit-revision`: eight developer-authored, provider-free projection cases through the shared HarnessEvalRunner with real preview admissions. This is not independent model-quality evidence.
- `cd services/ai && PYTHONPATH=. uv run python tests/acceptance/study_unit_revision_probe.py`: real PDF parsing, three conservative Plans, concurrent acceptance, stale/rejected decisions, atomic receipt/trace and fresh-application HTTP read-back in a temporary SQLite database.
- `npm --workspace @vibe-learner/web run test:workspace:mutations`: includes the confirmation component's transport/navigation behavior. Strict decoder coverage is in `tests/study-unit-revision-decode.test.ts`.
- `cd apps/web && npx playwright test --config playwright.study-unit-revision.config.ts`: two focused browser cases against a development server and fault-injected API fixtures, covering the diff, response loss, reload, skip and reject. This does not require a production build or replace the device/platform acceptance in `REL-DESKTOP-001`.
