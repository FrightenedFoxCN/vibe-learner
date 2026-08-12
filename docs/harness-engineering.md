# Harness Engineering

## Scope

Harness engineering is a repository-wide reliability discipline. Tavern interaction is the first new workflow to adopt the contract from its initial schema, but the same lifecycle must progressively cover:

- document extraction, OCR fallback, cleanup, and Study Unit arrangement;
- learning-plan prompt assembly, tool execution, strict parsing, and persistence;
- persona and scene generation;
- study chat, tool effects, citations, memory, and Character Events;
- Tavern speaker scheduling, actor generation, and message commit;
- frontend response decoding, request ordering, recovery, and debug reporting.

The harness is not one prompt and not one validator. It is the versioned boundary around an unreliable or stateful operation.

## Canonical lifecycle

```mermaid
flowchart LR
    A[Prepare typed input] --> B[Snapshot and digest context]
    B --> C[Execute model or deterministic worker]
    C --> D[Decode strict schema]
    D --> E[Validate domain invariants]
    E -->|valid| F[Commit effects atomically]
    E -->|repairable| G[Bounded repair]
    G --> D
    E -->|failed| H[Persist failure evidence]
    F --> I[Emit typed result and trace]
    H --> I
```

Every adopted workflow should make these concerns explicit:

1. typed, bounded input owned by the application;
2. versioned prompt/parser/heuristic and stable context snapshot;
3. strict output schema with application-owned identity and IDs;
4. deterministic invariant checks after parsing;
5. bounded recovery with a named strategy and attempt ceiling;
6. state effects proposed before validation and committed only after validation;
7. an observable trace suitable for debug replay and regression evaluation;
8. idempotency, optimistic revision checks, or a transactional append boundary where writes occur.

## Shared evidence schema

Python: `services/ai/app/models/harness.py`

TypeScript: `packages/shared/src/harness.ts`

The wire contract has three deliberate versions:

- `HarnessTraceV1` is the legacy Tavern validation summary. Its historical `version` combines policy and prompt information, and it has no trace identity or commit evidence. It remains readable but must not be described as replay-complete.
- `HarnessTraceV2` is the first strict evidence envelope and remains frozen for compatibility. It has trace/operation/parent identity, independent output-contract and named context-component/policy/prompt versions, snapshot references, ordered attempt records, output digest, terminal error, explicit commit/rollback evidence, and an RFC 3339 UTC start/completion interval.
- `HarnessTraceV3` preserves the v2 lifecycle fields while requiring `HarnessContextEnvelopeV3`: a closed workflow/stage pair, registered component set, typed subject/snapshot references, service-owned operation ID, named input/context/digest contracts, and a trace-visible context digest that validators recompute. V3 is the target for future workflow adoption; it does not rewrite historical v2 evidence.

Unknown explicit trace-schema versions are rejected. Missing `trace_schema_version` means legacy v1; old records are not assigned invented v2/v3 identities, timestamps, attempts, or commit claims. New workflow integrations should emit v3, while the existing Tavern production path remains v1 until a separate runtime migration is tested.

`HarnessContextEnvelope` is the already-registered v2 wire shape and remains unchanged. `HarnessContextEnvelopeV3` adds the stronger context foundation. Its input and snapshot digests are computed only over explicit `HarnessSafeManifest` DTOs whose exact fields have been reviewed; `Any`, open maps/objects, unordered sets, formatted/path-like values, and secret-bearing field names are rejected. Full hidden prompts, textbook/OCR source text, user guidance, transcripts, credentials, file paths, filenames, and attachments belong in protected artifacts, never in trace-visible manifests. `HarnessProposalEnvelope` is metadata only: each workflow still requires its own strict proposal DTO.

`app.services.harness_context.build_harness_context` is the v3 workflow-neutral construction boundary. It selects a closed `(workflow, stage)` registry, fills required component versions, canonicalizes references, and returns only a trace-safe evidence envelope. Component registrations without an audited contract use explicit `null`, so context construction fails with `harness_stage_component_version_unregistered`; a `pending-*` string is not treated as a version. Tavern has registered names for fixture validation, but its production path still emits v1 and is not thereby migrated.

`HarnessStage` names a domain operation boundary, while `HarnessAttemptPhase` names work inside one stage. Page extraction, Section detection, chunk building, and one planning tool call are stages because each has its own producer, failure boundary, timing, and evaluation route. Generate/decode/validate/repair/commit/rollback remain attempt phases; `page_parsed`, `sections_built`, `model_tool_call`, and similar NDJSON values are stream event types. They must not be promoted to stages. The machine-readable operation-stage registry is shared through `packages/shared/fixtures/harness/operation-stage-registry-v1.json`; its eval routes are stable routing keys for the future eval runner, not evidence that those eval suites already exist.

The current registered algorithm contracts for page extraction, Section detection, chunk building, the planning tool catalog, and its runtime identify the reviewed application behavior. They do not encode the installed PyMuPDF/OCR/model package version, which belongs in a typed context or protected snapshot. The planning runtime still treats malformed tool arguments permissively, so `planning_tool_execution` is registered as a real boundary but remains unadopted until `HRN-PLAN-001` supplies strict decode, invariants, terminal evidence, and fixtures.

The builder establishes integrity identity, not replay availability. `HarnessSnapshotRefV3` is only an integrity reference until `HRN-CTX-ARTIFACT-001` provides an authorized, immutable, retention-aware resolver with typed missing/expired/forbidden/digest-mismatch outcomes. SHA-256 detects changes; it does not provide confidentiality, and low-entropy secrets must not be hashed into public evidence. Python backend code is currently the sole canonical digest authority. TypeScript consumes wire evidence but does not generate canonical digests; browser support would require an explicit shared canonical-bytes specification and cross-language vectors.

Resource identity is not evidence by itself. `HARNESS_RESOURCE_EVIDENCE_POLICIES` is the closed, machine-readable registry for resource semantics plus context, commit, and rollback capabilities. Its Python and TypeScript projections are checked against one shared golden JSON registry. Context subjects fail closed unless their policy has an implemented freshness proof. `not_committed` may still name any closed resource as an attempted target because that is intent evidence, not a successful write claim; `committed` requires its registered revision or single-message sequence proof, and v3 `rolled_back` remains unavailable until a resource registers read-back or compensation proof. A missing revision must not be replaced by a constant `0`, and a parent aggregate revision must not be attached to a Study Unit or page as though it were that resource's own revision.

The first supported resource evidence is deliberately narrow:

- `tavern_room` is a revisioned control aggregate. Its revision covers room metadata/roster updates and run-admission CAS; it does not cover transcript drift, resource creation, hard deletion, or every run/step state transition.
- `tavern_message` is an append-only committed resource. The generic resource ref permits exactly one sequence point for one message, but truthful production adoption remains blocked until a versioned committed-projection DTO/digest binds the room, message, and sequence and an operation policy binds permitted resource sets. Message IDs are not accepted as v3 context freshness evidence until a protected transcript-anchor snapshot and resolver bind room, anchor, sequence, and projection digest.
- all other registered resources remain unsupported for context and successful commit evidence until their owning workflow migrates. They may be named only as honest failed attempts with no fabricated revision.

V3 operation claims also fail closed through `HARNESS_OPERATION_COMMIT_POLICIES`. The full key is workflow, stage, output-contract name/version, and committed-projection contract name/version; a generic resource capability cannot authorize a business operation. The first policy is intentionally limited to Tavern `actor_reply` using `TavernActorReply/tavern-actor-reply-v2`. It permits exactly one attempted/committed `tavern_message`, a single-sequence proof, and `TavernPersonaMessageCommittedProjection/tavern-persona-message-committed-projection-v1`. Its `primary_output_only` evidence scope proves the persona Message projection only: the same short transaction also advances Room `last_sequence`, completes the Step, and may terminalize the Run, so this policy must never be presented as full transaction-effect coverage. Begin-run, Room create/delete, failure finalization, and cancel have no successful operation policy and therefore remain fail closed.

The committed projection contains application-owned operation, effect-batch, room, message, run, step, reply-anchor, persona, content, performance, sequence, request, and timestamp fields but never embeds its Harness trace. The operation and effect-batch identity come from versioned server-only commit metadata written atomically with the persona Message; they are not supplied by the validating trace. Its complete canonical DTO is protected material because it contains conversation content. The trace-safe `TavernPersonaMessageCommitBinding` omits content and carries the canonical projection digest. `get_actor_commit_read_back` reads Message/Run/Step/Participant/reply-anchor records from one database snapshot; `validate_harness_operation_commit` rebuilds the projection inside the validator, revalidates Persona snapshot hashes, roster order, full schedule and same-Room earlier reply anchor, then binds it to trace resource evidence. Supplying a second caller-labeled “authoritative” projection or rebinding an old commit to a new operation/effect batch is not accepted. The internal commit metadata is excluded from API serialization and OpenAPI. The existing `TavernActorReply/tavern-actor-reply-v1` v3 fixture remains a context-foundation compatibility record; it is readable but cannot be called operation-commit adopted.

Protected artifact policy is similarly explicit:

- an artifact ID is opaque, immutable, scoped to an authorized subject, and bound to a versioned contract and digest;
- authorization is checked before content is read, and retention/expiry is part of the resolver result;
- read-back recomputes the digest and returns typed `resolved`, `not_found`, `expired`, `forbidden`, `digest_mismatch`, or `schema_unsupported` evidence;
- trace-visible refs never contain source text, prompts, transcript content, file paths, credentials, or other secrets;
- `document_debug` and `planning_trace` are inspectable, removable caches, not durable replay artifacts.

The implementation route is `resource evidence registry -> operation/stage vocabulary -> protected artifact resolver -> workflow-neutral operation runtime -> per-domain adoption`. `HRN-CTX-001` tracks completion of that whole rollout; it is not a circular prerequisite that prevents individual domains from using the runtime primitives as they become available.

Workflow-specific policies remain in their domain schema. For example, Tavern limits participant messages and checks cross-speaker impersonation, while document parsing checks page coverage, extraction density, OCR availability, and Study Unit bounds.

See `harness-schema-ownership.md` for the workflow ownership registry, nullability rules, proposal boundaries, and compatibility policy.

## Adoption matrix

| Workflow | Existing reliability pieces | Missing harness boundary |
|---|---|---|
| Document parsing | OCR fallback, warnings, debug record | versioned checks, stage traces, replay fixtures, performance budgets |
| Planning | strict-ish JSON, model recovery records, tool trace | true JSON schema validation, effect boundary, unified trace, eval matrix |
| Persona/scene generation | Pydantic normalization, retry | prompt/version digest, semantic invariants, regression fixtures |
| Study chat | reply recovery, tool trace, citations, Study Session revision CAS and sequenced turn append | durable request admission/idempotency, transactional tool-effect proposals, strict decoder, v3 evidence |
| Tavern | normalized room/run/step schema, low-trust persona compiler, strict actor decode, server-owned scheduler, semantic checks, bounded recovery trace, per-actor commit, partial state, scoped child retry, leased resume/cancel fencing, strict browser v1 decode | v3 runtime/artifact migration, total prompt budget, authoritative retry-chain view, eval matrix |
| Frontend API | Tavern fail-closed decoder, request/room fencing, monotonic terminal reconciliation | repository-wide runtime decoders, timeout/cancel semantics, trace forwarding |

## User-facing transparency

Ordinary UI should show concise recovery state, not raw codes or prompts:

- passed: no interruption or a low-noise checked indicator;
- repaired: explain that one response was corrected and allow details to expand;
- failed: preserve user input, name the failed stage, and offer a scoped retry;
- debug: show check codes, versions, digests, attempts, durations, and raw trace excerpts.

Harness self-checks are evidence, not a promise that content is objectively correct.

## Evaluation and release gates

Each workflow must add fixtures for malformed schemas, boundary violations, retry exhaustion, duplicate requests, concurrency, and state-commit failure. CI should report at least:

- schema-valid rate before and after repair;
- recovery and failure rates;
- state-commit consistency;
- p50/p95 stage duration;
- workflow-specific accuracy, grounding, or identity-consistency metrics.

No workflow should be described as harnessed until its failure path and protected artifact replay/evaluation path are tested, not merely its happy-path prompt or its ability to instantiate a v3 context fixture.

The matrix records incremental adoption, not a Tavern-only rollout. A completed Tavern slice or the existence of the v2/v3 evidence schemas does not change the status of parsing, planning, persona/scene generation, Study Chat, or frontend decoding; each remains open until its own effect, failure, and replay boundaries pass the same rubric.

Tavern's `context_digest` is one domain-specific integrity input: it covers room title, scene, harness policy, roster order, and participant prompt hashes. Room revision covers metadata and run-admission CAS, while `terminal_sequence` is the transcript watermark used by retry checks; neither alone is replay-complete transcript evidence. Other workflows must define their own versioned context envelope rather than reusing Tavern fields or treating one digest function as a universal answer.

The current production Tavern records still carry legacy v1 traces. Lease recovery, cancel fencing, strict frontend decode, or a field named `context_digest` do not change that version statement. V3 adoption closes only when protected snapshots, resource evidence, v3 attempt/commit traces, compatibility decoding, and eval fixtures are emitted by the real Tavern path.
