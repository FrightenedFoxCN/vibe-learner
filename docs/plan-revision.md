# Learning Plan revision

Plan Workspace supports explicit revision previews. A learner can edit the course title, overview, today tasks, and the title, focus and order of existing schedule items. This first version preserves the complete schedule target set: it does not add/delete Study Units, chapters or schedule items. IDs, grounding, progress/events and existing Study Session references remain unchanged.

## Persistence and concurrency

`LearningPlanRepository` owns database-authoritative Plan writes. Title, progress, planning-question answers, Study confirmation effects, Study Unit title propagation and deletion use revision CAS. Modern clients send `expected_revision`; legacy callers may omit it, in which case a bounded CAS retry applies their mutation to the latest row. Approving a Study confirmation commits the Plan and Session decision in one transaction; repeated approval does not apply the effect twice.

Each successful mutation increments `revision` and archives the before/after Plan snapshots in the same transaction. Deletion writes a tombstone, preventing an old JSON file from resurrecting a deleted Plan. `plans.json` is insert-only import compatibility and is not rewritten by normal Plan mutations. Alembic 0020/0021 migrate existing rows without rewriting their original JSON or v1 creation receipts. The frozen `LearningPlanRecord` contract remains unchanged; current reads use `VersionedLearningPlanRecord`.

Answering a planning question saves the answer only. To change the plan with that answer, the learner explicitly creates and accepts a revision preview.

## Revision lifecycle

1. POST a new client request ID, current `base_revision` and instruction (or `rollback_revision`). Exact same-key requests return the existing operation; changed same-key payloads conflict.
2. Admission and the `learning_plan_revision` Harness binding share one transaction. The `plan_revision` stage resolves an authorized protected snapshot before a single provider call. The model returns `PlanRevisionProposalV1`, containing content and existing target references only.
3. Strict decode and exact target-set validation precede the durable preview receipt. The preview does not change the Plan.
4. Accepting the preview performs another execution on the same operation, with trace slot 1. Plan CAS, history, acceptance receipt and terminal v3 trace commit atomically. A changed/deleted Plan prevents acceptance. Rejecting changes only the preview status.
5. Rollback prepares historical content against the current base revision and uses the same preview/accept flow. It creates a new revision and retains current progress. History includes all Plan mutations, including progress changes.

Preview and acceptance receipts use immutable application-level receipt slots and the registered `PlanRevisionCommittedProjectionV1`; read-back validates operation, action, base identity, proposal and the exact accepted patch. The complete-transaction commit policy applies to this bounded local receipt/Plan transaction. It makes no claim about upstream provider execution or billing.

GET recovery never reissues a provider request. An ambiguous transport result is `uncertain`; a known invalid provider response is `failed`. Querying a generating/applying operation after 240 seconds fences domain persistence and terminalizes any existing active v3 execution in the same transaction. A crash before runtime construction may leave only the admitted binding and domain failure. There is no automatic model retry.

## Frontend recovery

The browser persists the client request ID before POST. Reload and page return query that ID. A lost acceptance response disables both decision buttons until GET resolves it. Definite pre-admission errors allow a new request; a missing GET record offers explicit clearing of the local recovery reference. Clearing does not cancel a request still reaching the server; the learner must actively generate a new preview, and neither preview changes the Plan without acceptance.

The diff shows the base/current revisions, content and order. Conflicts require a fresh Plan and preview. An accepted result refreshes the authoritative Plan. Raw failure codes remain out of learner-facing notices.

## Validation

- `npm run eval:harness:plan-revision`: seven developer-authored cases through the shared HarnessEvalRunner, with real revision-operation admission, deterministic grading and full system/source identity. Measures strict proposal and patch behavior, not model quality or full transactional rollback.
- `tests.test_plan_revision` and `tests.test_plan_revision_evals`: lifecycle, provider ambiguity and gate regression checks.
- [Independent SQLite/PostgreSQL acceptance](plans/planning-backend-independent-acceptance-2026-09-11.md): concurrency, migration, acceptance, rollback, receipt binding and transaction-failure injection.
- [Independent browser acceptance](plans/planning-frontend-independent-acceptance-2026-09-11.md): eight checks using fault-injected API fixtures and an isolated real backend with the mock model provider. OS-level crash/desktop and representative live-provider quality gates remain in the unified TODO.

Legacy revision admission computes the same pure progress projection as normal Plan reads without rewriting the original row or creation receipt. Accept/reorder/focus changes recompute schedule-derived Study Unit progress before committing; the frontend verifies the same derived projection.
