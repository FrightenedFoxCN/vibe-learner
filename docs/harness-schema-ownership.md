# Harness Schema And Ownership

## Purpose

This document is the cross-workflow ownership registry for Harness adoption. It prevents one broad domain record from serving simultaneously as model output, application state, persistence payload, and public API response.

The repository now has a versioned v2 evidence contract, but the business workflows in this table are not automatically harnessed. A workflow is complete only after its own typed proposal, strict decode, invariants, bounded recovery, commit boundary, trace, fixtures, and release metrics are implemented.

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
| Study Chat | session revision, learner input, bounded history, persona/scene/document snapshots, allowed toolset | reply, citations, Character Event content and typed effect proposals | turn/event IDs, line segment IDs, memory/affinity/follow-up/scene/projected-document/plan-confirmation effects, revision and timestamps | chat exchange and refreshed session | `HRN-STUDY-001` |
| Tavern | room revision, trigger, roster snapshots, bounded transcript and policy | `TavernActorReply` display/performance/target proposal | speaker, room/run/step/message IDs, schedule, reply anchor, sequence, lineage, revision and terminal state | Tavern room/run/message responses | `HRN-TAV-001`, `HRN-TAV-002` |
| Frontend decode | request identity/sequence, expected response contract/version | decoded candidate or typed decode error; never a default-filled fake domain record | accepted response order, stale/cancel state and recovery action | view-model projection plus debug evidence | `HRN-WEB-001` |

Known ownership violations are migration work, not precedent. In particular, the current Scene generation transport accepts layer/object/reuse IDs and Planning can accept schedule-chapter IDs. Their workflow tasks must replace those shapes with domain-specific proposal DTOs before those workflows are described as harnessed.

## Evidence contract versions

### Legacy v1

`HarnessTraceRecord` / `HarnessTraceV1` is the existing Tavern validation summary. Its `version` combines policy/prompt information, it has no trace identity or commit evidence, and it must not be presented as replay-complete. Existing stored records remain readable without invented metadata.

### v2

`HarnessTraceV2` is the contract for new workflow adoption. It separates:

- `trace_schema_version` from output contract, context, policy, and prompt versions;
- `trace_id`, `operation_id`, and optional `parent_trace_id`;
- the output `contract` from the versioned `context` envelope;
- ordered generate/decode/validate/repair/commit/rollback attempts;
- proposal/output digest from final committed-payload digest;
- validation status from explicit committed/not-committed/rolled-back evidence, including effect-batch identity, attempted resources, per-resource projection digests/revisions/sequences, and rollback reason/time;
- failure code from user-readable check messages.

The context stores sorted resource/snapshot references, named component versions, and canonical SHA-256 digests—not hidden prompts, full source documents, secret keys, or raw private guidance. Canonical payloads use UTF-8 JSON with sorted keys, compact separators, explicit `null`, and no `NaN`/infinity. `canonical_harness_digest` is the shared backend implementation; do not introduce workflow-local serialization rules.

`HarnessCommitEvidence` distinguishes a single committed projection from a canonically ordered committed batch. A `committed_projection` contains exactly one attempted/committed resource and its envelope digest equals that resource's projection digest. A `committed_batch` digest is recomputed from the payload contract plus the sorted committed-resource manifest; each manifest entry binds its own final projection digest, revision, and sequence evidence. Attempted revisions must match the corresponding committed resource's expected revisions. These digests cover final app-owned committed projections, not model output or an API response. A successful trace's last output attempt must be a passed validation carrying the terminal output digest; a repaired trace must validate again after repair. A committed trace ends with a successful commit attempt whose digest matches the commit evidence. A rolled-back trace contains no successful commit and ends with an adjacent failed commit followed by a successful rollback, with no claimed committed resources.

## Wire compatibility

- Missing `trace_schema_version` decodes as legacy v1.
- Exact `trace_schema_version = harness-trace-v2` decodes strictly as v2.
- Unknown explicit versions are rejected; they are never downgraded to v1.
- New workflow integrations emit v2. Existing v1 records are not automatically upgraded.
- A migration may preserve old payloads or add migration evidence, but it must not invent a historical trace ID, timestamp, attempt chain, or successful commit.

Python exposes snake_case persistence/wire models. Shared TypeScript exposes the matching camelCase frontend projection with the same required/null semantics. `apps/web/lib/api.ts` still needs a true `unknown -> decoded value | typed error` boundary under `HRN-WEB-001`; a type declaration or permissive normalizer is not validation. Until that decoder lands, the existing Tavern v1 normalizer explicitly rejects every payload carrying `trace_schema_version` instead of silently degrading v2 into a fake v1 record.

`HarnessProposalEnvelope` must be parameterized with a domain model derived from `HarnessV2Model`; the unparameterized/`Any` form and permissive domain models are rejected. It includes operation identity and output contract reference, but this runtime guard does not replace each workflow's semantic ownership invariants.

`HarnessWorkflow` is intentionally a closed registry. Adding a workflow requires the same atomic change to the Python enum, TypeScript union, frontend decoder routing, ownership table, and eval registry.

## Persistence migration rule

Most legacy aggregate JSON payloads lack `schema_name`, `schema_version`, and migration provenance, and many Pydantic domain records currently ignore extra fields. Do not turn on `extra="forbid"` across all legacy records at once. Migrate one aggregate at a time:

1. inventory existing stored shapes;
2. define a versioned committed-record envelope;
3. add explicit legacy decoding and migration fixtures;
4. write the new shape only after projection invariants pass;
5. expose typed failure evidence when migration or commit fails.

## Adoption gate

A workflow may be labeled harnessed only when evidence covers malformed output, semantic boundary failure, recovery exhaustion, duplicate requests, relevant concurrency, commit failure, and replay. A v2 schema by itself satisfies none of those business-flow gates.
