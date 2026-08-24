# Harness Schema And Ownership

## Purpose

This document is the cross-workflow ownership registry for Harness adoption. It prevents one broad domain record from serving simultaneously as model output, application state, persistence payload, and public API response.

The repository has registered v1, v2, and v3 evidence contracts, but the business workflows in this table are not automatically harnessed. V3 adds a hardened context foundation; a workflow is complete only after its own typed proposal, strict decode, invariants, bounded recovery, protected artifact resolver, commit boundary, trace, fixtures, and release metrics are implemented.

## Four schema roles

Every adopted workflow separates these roles:

1. `Typed Input`: bounded caller input plus application-owned resource references.
2. `Proposal`: untrusted model or heuristic output. It contains only content or effect proposals that the worker is allowed to suggest.
3. `Committed Record`: application-projected state after validation. IDs, identity, revision, sequence, timestamps, relationships, and committed status are assigned here.
4. `API Response`: a public projection decoded independently by the frontend. It is not trusted merely because TypeScript declares a type.

A persistence payload is a versioned committed-record representation. It must not become an implicit proposal schema.

## Application-owned fields

Model and heuristic proposal schemas must not create or control:

- application resource, message, turn, trace, event, or effect IDs;
- speaker/author identity;
- database relationship IDs, except references chosen from an application-supplied allow-list;
- revision, sequence, ordering token, timestamp, or committed status;
- retry lineage, idempotency key, request/operation identity, or commit evidence;
- direct state changes such as memory writes, affinity changes, follow-up scheduling, scene mutations, overlays, or plan confirmations.

Those values are assigned while projecting a validated proposal into committed records or applying validated effect proposals.

An upstream provider's `tool_call_id` is a transport correlation reference, not an application resource ID. It may be retained in debug evidence exactly as received, but it must not be reused as a database identity, effect target, idempotency key, or authorization decision. Planning and Study Chat still need strict tool-name, argument, and effect validation under their workflow tasks.

## Workflow ownership registry

| Workflow | Typed input/context | Proposal boundary | Application-owned committed state | API projection | Adoption task |
|---|---|---|---|---|---|
| Document extraction | uploaded document reference, parser/OCR versions and budgets | extracted pages, section/chunk candidates, warnings | document status, stored paths, page/section/chunk IDs, debug record identity and terminal state | document/debug/stream responses | `HRN-DOC-001` |
| OCR | page references, OCR engine/version and forced-fallback policy | page text/blocks/confidence proposals | selected extraction method, page attribution, terminal error and debug evidence | document/debug/stream responses | `HRN-DOC-001` |
| Study Unit cleanup | parsed sections/chunks and cleanup policy | bounded units referring only to supplied Section IDs/page ranges | Study Unit IDs, document ownership, persisted order and document/debug projection | document/planning-context responses | `HRN-DOC-001` |
| Planning | goal, document/Study Unit refs, persona/scene snapshots, toolset/version | plan text, tasks and schedule proposals referring to allowed Study Unit/Section anchors | plan/schedule/chapter IDs, progress state, document/debug updates, trace linkage and timestamps | plan and planning-trace responses | `HRN-PLAN-001` |
| Persona | user source text/cards plus generation policy | summary, relationship, address and strict slot/card content proposals | persona/card IDs, source, ordering, timestamps and persistence | persona/card responses | `HRN-PERSONA-001` |
| Scene | source text/keywords plus depth/size policy | scene/layer/object content tree with no IDs or reuse IDs | all scene/layer/object/reuse IDs, selected path, library identity and timestamps | scene setup/library/generation responses | `HRN-SCENE-001` |
| Study Chat | stable client request ID, expected Session revision, learner input/attachment manifest, bounded history, persona/scene/document snapshots, allowed toolset | reply, citations, Character Event content and typed effect proposals | operation/turn/event IDs, line segment IDs, memory/affinity/follow-up/scene/projected-document/plan-confirmation effects, revision and timestamps | operation receipt; committed receipt contains chat exchange and refreshed Session | `STUDY-OP-ADMIT-001`, `HRN-STUDY-001` |
| Tavern | room revision, trigger, roster snapshots, bounded transcript and policy | `TavernActorReply` display/performance/target proposal | speaker, room/run/step/message IDs, schedule, reply anchor, sequence, lineage, revision and terminal state | Tavern room/run/message responses | `HRN-TAV-001`, `HRN-TAV-002` |
| Frontend decode | request identity/sequence, expected response contract/version | decoded candidate or typed decode error; never a default-filled fake domain record | accepted response order, stale/cancel state and recovery action | view-model projection plus debug evidence | `HRN-WEB-001` |

Known ownership violations are migration work, not precedent. In particular, the current Scene generation transport accepts layer/object/reuse IDs and Planning can accept schedule-chapter IDs. Their workflow tasks must replace those shapes with domain-specific proposal DTOs before those workflows are described as harnessed.

## Evidence contract versions

### Legacy v1

`HarnessTraceRecord` / `HarnessTraceV1` is the existing Tavern validation summary. Its `version` combines policy/prompt information, it has no trace identity or commit evidence, and it must not be presented as replay-complete. Existing stored records remain readable without invented metadata.

### v2

`HarnessTraceV2` is the first strict evidence contract and remains frozen for compatibility. It separates:

- `trace_schema_version` from output contract, context, policy, and prompt versions;
- `trace_id`, `operation_id`, and optional `parent_trace_id`;
- the output `contract` from the versioned `context` envelope;
- ordered generate/decode/validate/repair/commit/rollback attempts;
- proposal/output digest from final committed-payload digest;
- validation status from explicit committed/not-committed/rolled-back evidence, including effect-batch identity, attempted resources, per-resource projection digests/revisions/sequences, and rollback reason/time;
- failure code from user-readable check messages.

The context stores sorted resource/snapshot references, named component versions, and canonical SHA-256 digests—not hidden prompts, full source documents, secret keys, or raw private guidance. Canonical payloads use UTF-8 JSON with sorted keys, compact separators, explicit `null`, and no `NaN`/infinity. `canonical_harness_digest` is the shared backend implementation; do not introduce workflow-local serialization rules.

`HarnessCommitEvidence` distinguishes a single committed projection from a canonically ordered committed batch. A `committed_projection` contains exactly one attempted/committed resource and its envelope digest equals that resource's projection digest. A `committed_batch` digest is recomputed from the payload contract plus the sorted committed-resource manifest; each manifest entry binds its own final projection digest, revision, and sequence evidence. Attempted revisions must match the corresponding committed resource's expected revisions. These digests cover final app-owned committed projections, not model output or an API response. A successful trace's last output attempt must be a passed validation carrying the terminal output digest; a repaired trace must validate again after repair. A committed trace ends with a successful commit attempt whose digest matches the commit evidence. A rolled-back trace contains no successful commit and ends with an adjacent failed commit followed by a successful rollback, with no claimed committed resources.

### v3

`HarnessTraceV3` retains the v2 lifecycle and commit semantics while replacing the context field with `HarnessContextEnvelopeV3`. V3 closes workflow/stage/resource/artifact vocabularies, requires a server-owned operation identity, binds input/context/digest contracts, fills the exact component set from a central `(workflow, stage)` registry, and recomputes the context digest from trace-visible evidence. The operation ID is validated and bound by the trace, but intentionally excluded from context identity so identical context can be compared across separate operations.

`HarnessSafeManifest` is an explicit review marker, not a generic serialization escape hatch. Each concrete manifest uses `extra="forbid"` and declares an exact allowlist equal to its fields. Trace-visible manifests reject open objects, `Any`, unordered collections, formatted/path-like types and sensitive field names. Protected user/document/prompt/transcript content must be retained behind the future artifact resolver; a snapshot digest alone is an integrity reference and never a replay-complete claim.

`HARNESS_RESOURCE_EVIDENCE_POLICIES` separates four questions for every closed resource type: storage semantics, admissible context freshness proof, successful commit proof, and rollback proof. The shared golden registry is the cross-language authority. Attempted references in `not_committed` evidence identify intended targets and therefore may name resources whose successful commit proof is not migrated; they must not carry invented revisions. `committed` accepts only registered proof shapes, and v3 `rolled_back` rejects every resource until a read-back or compensation proof contract is implemented. This is stricter than v2 by design and does not reinterpret persisted v2 evidence.

Currently only Tavern Room has authoritative-revision context and revision commit shape support, and that revision covers room control metadata plus run admission rather than transcript history. Tavern Message has single-sequence append shape support but is not a valid context subject: its ID is not room-scoped freshness proof. These generic shapes do not by themselves prove operation semantics. Before production v3 adoption, a versioned committed-projection contract must bind room/message/sequence, and an operation policy must bind workflow/stage/payload contract to its permitted resource set so actor append cannot claim a Room revision and create/delete cannot masquerade as an update. A future protected transcript-anchor snapshot must also bind room ID, message/anchor ID, sequence/window, and projection digest before message context can be enabled. Document, page, debug, Study Unit, plan/trace, Persona, Scene, Study Session, Tavern Run, and frontend request remain unsupported until their domain adoption commits add truthful evidence.

Study Session now has an authoritative aggregate revision and application-owned contiguous turn sequence under `AUD-001`. That is concurrency infrastructure, not automatic Harness resource adoption: `study_session` remains unsupported for v3 context/commit evidence until `HRN-STUDY-001` registers its freshness semantics, operation-specific committed projection, artifact/effect boundary, and read-back validation. Never attach the new Session revision to a turn, memory, attachment, or other embedded effect as though it were that resource's own revision.

`STUDY-OP-ADMIT-001` adds a server-owned Study Chat operation record, not a model proposal or a Harness trace. `(session_id, client_request_id)` plus a versioned canonical request fingerprint identifies one admitted intent; `expected_session_revision` is bound into that request and cannot be changed on replay. Public receipts expose only operation status, safe retry policy, timestamps, committed Session/Turn identity, an error code, and—only for `committed`—the existing chat exchange. The committed result is validated against the same Session/Turn projection before read-back. Provider `tool_call_id`, attachment IDs, generated-image IDs, overlay IDs, follow-up IDs, and other effect identities are not derived from the client key.

The operation state is not effect evidence. `admitted` / `running` / `uncertain` never authorize blind replay; `not_committed` authorizes retry only with durable proof that execution never began. A committed final Turn does not imply that earlier model tools, file preparation, provider requests, or external effects share its transaction.

Interactive questions use a separate non-Harness ownership slice. `StudyQuestionProposalV1` contains only model-suggestible prompt/options/private answer material. The application projects it into `StudyInteractiveQuestionRecordV2`, whose `StudyQuestionGradingSpecV1` stays server-only; the API exposes `StudyQuestionPromptResponseV1` and reveals `StudyQuestionResultResponseV1` only after commit. `StudyQuestionAttemptRequest` contains only Turn ID, expected Session revision, stable client attempt identity, and submitted answer. The server-owned verdict, Session result patch, and durable `study_question_attempts` receipt commit atomically. This closes the previous grading leak and client-verdict boundary, but it does not register a new Harness stage or make the broader Study Chat/effect workflow v3-adopted.

`StudyChatEffectProposalV1` is the discriminated union for the current database slice: `StudyMemoryUpsertEffectProposalV1`, `StudyAffinityDeltaEffectProposalV1`, or `StudyPlanConfirmationEffectProposalV1`. These contracts own only normalized memory content, bounded affinity delta/reason, or bounded plan content. `HarnessPreparedEffectV1` adds application-owned operation, batch, effect, global slot, adapter/contract, and exact Session/Plan target references. The in-process collector provides a base-plus-prepared overlay for memory and affinity reads, but it is not a durable prepare journal. Final commit derives memory/event/confirmation identity and timestamp, applies all slots with the Turn/Session revision/operation receipt transaction, and stores `StudyChatCommittedEffectBatchV1` inside the server-only operation payload for strict same-snapshot read-back; the public API projection drops it. This internal committed receipt is not a registered v3 operation claim. Follow-up, Scene, projection/overlay, file/provider compensation, protected artifacts, v3 context/trace, strict nested public decode, and eval fixtures remain owned by `SCH-HRN-EFFECT-001`, `STUDY-EFFECT-COMMIT-001`, and `HRN-STUDY-001`.

`HARNESS_OPERATION_COMMIT_POLICIES` now supplies that workflow-neutral operation layer. Each policy binds the exact workflow/stage/output contract/committed-projection contract key, trace-to-commit status rules, digest scope, context subject cardinality, resource type cardinality, and evidence scope. Unknown keys, wrong contract versions, resource subsets/supersets, and rollback claims fail closed. Its shared Python/TypeScript golden registry is `operation-commit-policies-v1.json`.

The initial Tavern policy adopts only `TavernActorReply/tavern-actor-reply-v2` and exactly one persona Message projection. `TavernPersonaMessageCommittedProjectionV1` contains the complete committed record including content; a content-free `TavernPersonaMessageCommitBindingV1` carries identity plus its canonical digest. Server-only `TavernPersonaMessageCommitMetadataV1` persists operation/effect-batch identity in the same transaction as the Message and is deliberately absent from the API/OpenAPI schema. A repository method reads Message/Run/Step/Participant/reply-anchor from one database snapshot, and the sidecar rejects cross-room, cross-run, cross-step, reply-anchor, schedule, Persona snapshot/hash, request, operation/effect-batch, sequence, and digest mismatches even if an attacker recomputes a self-consistent caller payload. The policy is explicitly `primary_output_only`, not complete transaction-effect evidence: Step/Run state and Room sequence watermark still lack committed resource projections. Begin-run and Room create/delete remain unsupported. Production still stores legacy v1 actor traces; `HRN-TAV-V3-001` must build/resolve protected context artifacts and emit the registered v2/v3 evidence before production Tavern can be called fully adopted. The historical `TavernActorReply/tavern-actor-reply-v1` context fixture remains readable and is not reinterpreted as adopted operation evidence.

## Wire compatibility

- Missing `trace_schema_version` decodes as legacy v1.
- Exact `trace_schema_version = harness-trace-v2` decodes strictly as v2.
- Exact `trace_schema_version = harness-trace-v3` decodes strictly as v3.
- Unknown explicit versions are rejected; they are never downgraded to v1.
- New workflow integrations emit v3. Existing v1/v2 records are not automatically upgraded.
- A migration may preserve old payloads or add migration evidence, but it must not invent a historical trace ID, timestamp, attempt chain, or successful commit.

Python exposes snake_case persistence/wire models and is the canonical digest authority. Shared TypeScript exposes the matching camelCase frontend projection with the same required/null semantics but does not generate digests. `apps/web/lib/api.ts` still needs a true `unknown -> decoded value | typed error` boundary under `HRN-WEB-001`; a type declaration or permissive normalizer is not validation. Until that decoder lands, the existing Tavern v1 normalizer rejects explicit trace-schema payloads instead of silently degrading v2/v3 into a fake v1 record.

`HarnessProposalEnvelope` must be parameterized with a domain model derived from `HarnessV2Model`; the unparameterized/`Any` form and permissive domain models are rejected. It includes operation identity and output contract reference, but this runtime guard does not replace each workflow's semantic ownership invariants.

`HarnessWorkflow`, `HarnessStage`, `HarnessResourceType`, and `HarnessArtifactType` are intentionally closed for v3. Adding a value requires the same atomic change to Python, TypeScript, the stage/component registry, frontend decoder routing, ownership table, and eval registry. V2's open string reference fields remain frozen for persisted compatibility.

## Operation-stage ownership

The shared operation-stage registry distinguishes business execution from lifecycle attempts and UI progress. Its `eval_route` is only a stable routing key until `HRN-EVAL-001` provides a runner.

| Workflow / stage | Real boundary | Registered producer components | Adoption status |
|---|---|---|---|
| Document / `document_parse` | parent orchestration over extraction, OCR fallback, Section detection and chunks | `document_parser` | version deliberately unregistered; parent flow is not v3-adopted |
| Document / `page_extraction` | whole-document page extraction and cleanup; OCR is a fallback/child workflow | `document_page_extractor` | algorithm contract registered; no production trace yet |
| OCR / `ocr_page` | one page OCR attempt | `ocr_engine` | version deliberately unregistered |
| Document / `section_detection` | TOC-first and heading-heuristic Section construction | `document_section_detector` | algorithm contract registered; no production trace yet |
| Document / `chunk_building` | validated Sections plus page content to Chunk candidates | `document_chunk_builder` | algorithm contract registered; no production trace yet |
| Study Unit / `study_unit_cleanup` | Sections/Chunks to ordered Study Unit proposal | `study_unit_cleaner` | version deliberately unregistered |
| Planning / `plan_generation` | bounded context to Learning Plan proposal | `planning_prompt`, `planning_toolset` | prompt version deliberately unregistered |
| Planning / `planning_tool_execution` | one allowed tool call to one typed result boundary | `planning_tool_runtime`, `planning_toolset` | boundary registered; strict argument decode still open |
| Persona, Scene, Study Chat, Frontend Decode | existing broad generation/reply/decode boundaries | domain components | component versions deliberately unregistered |
| Tavern / `actor_reply` | one scheduled persona proposal and its validation | prompt, persona compiler, scheduler | component versions registered; production trace remains legacy v1 |

Do not add `plan_projection`, `actor_decode`, `atomic_commit`, or similar stages: those are attempt phases or commit evidence. Likewise stream event names are not Harness stages. A component algorithm contract is not the installed dependency/model version and does not by itself prove Harness adoption.

## Persistence migration rule

Most legacy aggregate JSON payloads lack `schema_name`, `schema_version`, and migration provenance, and many Pydantic domain records currently ignore extra fields. Do not turn on `extra="forbid"` across all legacy records at once. Migrate one aggregate at a time:

1. inventory existing stored shapes;
2. define a versioned committed-record envelope;
3. add explicit legacy decoding and migration fixtures;
4. write the new shape only after projection invariants pass;
5. expose typed failure evidence when migration or commit fails.

## Adoption gate

A workflow may be labeled harnessed only when evidence covers malformed output, semantic boundary failure, recovery exhaustion, duplicate requests, relevant concurrency, commit failure, and protected artifact replay. A v2/v3 schema or context builder by itself satisfies none of those business-flow gates.
