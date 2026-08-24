# Independent Product and UX Audit — 2026-08-12

## Purpose and method

This report preserves findings from independent read-only agents so the agents
implementing a fix are not also the sole source of product or UX truth. The
audit followed real user tasks across Document upload and processing, Planning,
Study Chat, Persona, Scene, Tavern, frontend decoding, recovery, accessibility,
and scale behavior. TODO entries are not treated as proof of implementation.

Evidence is classified as:

- **defect**: current code permits the failure;
- **missing capability**: the desired reliability or UX boundary is not yet
  implemented;
- **documentation drift**: docs describe behavior that differs from code;
- **verified behavior**: code and tests provide direct positive evidence.

Static findings include exact reproduction and acceptance criteria. Browser
visual findings still require a host-accessible 390×844 device/IME/focus pass;
the audit Browser could not reach the host localhost service.

## Priority summary

| Priority | Area | Evidence status | Required outcome |
| --- | --- | --- | --- |
| P0 | Study Chat effects | defect | One stable operation makes DB effects at-most-once and external uncertainty explicit |
| P1 | Document processing | defect | Cleanup and multi-write failures always reach a durable terminal state |
| P1 | Planning/tools | defect | Strict tool/proposal decode and recoverable atomic persistence |
| P1 | Scene generation | schema ownership defect | Model proposal cannot own application IDs or unbounded recursive state |
| P1 | Frontend decode | missing capability | Per-domain strict decode, stream terminal state, identity and stale-result fences |
| P1 | Tavern run UX | defect | Truthful per-step roster state and prominent scoped recovery |
| P1 | Tavern mobile | defect | Empty-room setup and active-room composer are primary mobile tasks |
| P2 | Provider truth | UX defect | Mock generation is visibly labeled in every generation workspace |
| P2 | Accessibility | missing capability | Live status, error focus, visible focus and modal focus containment |
| P2 | Tavern scale | performance risk | Cursor-paged room summaries with bounded query/DOM budgets |
| P3 | User manual | documentation drift | Home copy, Scene snapshot source, and Plan recovery claims match code |

## P0 — Study Chat can replay already-committed tool effects

### Revalidation status

The underlying aggregate lost-update prerequisite passed independent
persistence and UX revalidation under `AUD-001`. Concurrent Study Session
append/create/import retains every sibling with unique contiguous Turn
sequences; Session mutation uses bounded revision CAS; legacy and partially
migrated schemas recover without silently accepting partial Turn identity;
same-ID divergent imports, coerced watermarks, immutable committed-Turn
rewrites, and row/payload projection drift fail closed. The browser narrowly
decodes committed Session revision, Turn watermark, ID, and sequence, orders by
sequence, and shows a safe visible error without leaking decoder paths or
offering a blind retry.

This closes the aggregate lost-update prerequisite only and narrows, but does
not close, this P0 finding. Stable Study Chat request admission, terminal
receipt read-back, typed effect proposals, attachment staging, and truthful
`uncertain` recovery remain absent; the broader frontend Study DTO boundary is
still open under `HRN-WEB-STUDY-DEC-001`.

### Evidence

- `apps/web/hooks/use-learning-workspace-controller.ts` resends a visible
  message after failure without a stable request/operation identity.
- `apps/web/lib/api.ts` sends Study Chat without an idempotency key.
- `services/ai/app/services/model_provider.py` executes tool calls before the
  final structured reply is decoded and validated.
- `services/ai/app/services/study_session_chat_runtime.py` immediately mutates
  session memory, affinity, follow-ups, projections, and related session state.
- `services/ai/app/services/session_scene.py` immediately mutates Scene state.
- `services/ai/app/api/routes.py` cancels pending follow-ups before generation,
  and appends the visible turn only after model/tool execution and final reply
  parsing.
- `services/ai/app/services/study_chat_attachments.py` can store image/PDF files
  before `_run_study_chat`; generated images/files and provider calls are not
  ordinary database effects.

### Reproduction

1. Let the model call `write_session_memory`, affinity, follow-up, projection,
   or Scene mutation tools.
2. After the tool succeeds, force an invalid final payload, disconnect, or
   timeout.
3. Use the Study Console retry action.
4. Observe that the complete tool loop runs again even though an earlier effect
   may already be durable.

### User impact

Memory or Scene changes can repeat, affinity can be counted twice, and duplicate
follow-ups can be scheduled. The user cannot distinguish `not_committed`,
`committed`, or `uncertain`, so retry is not semantically safe.

### Acceptance

- Every Study Chat intent has one stable server-recognized request and operation
  identity across timeout, reconnect, retry, and replay.
- The first deployable slice durably admits one request ID/fingerprint before
  generation. A duplicate returns the recorded terminal result; a non-terminal
  or unverifiable result is `uncertain` and cannot be blindly replayed.
- The full migration classifies pure reads, database writes, file/outbox writes,
  and external/provider effects. Model tools produce strict typed effect
  proposals rather than mutating stores during generation.
- Application-owned effect IDs derive from the operation and effect slot.
- Each effect class declares prepare, commit, compensation, and read-back. The
  final validated reply, turn, and database effects commit through one
  transaction/CAS boundary, while file/outbox/external effects use durable
  staging and truthful recovery state.
- Duplicate requests return the original terminal result without re-executing a
  model or effect.
- Disconnect, timeout, invalid final payload, duplicate request, concurrent
  request, attachment cleanup, and per-effect/commit-failure fixtures prove
  database effects happen at most once. A database transaction is not evidence
  of exactly-once external/provider execution.
- User-facing recovery distinguishes `not_committed`, `committed`, and
  `uncertain`; an external effect without provider idempotency or authoritative
  read-back stays `uncertain`; raw trace remains in Debug.

## P1 — Document cleanup and persistence are outside the failure boundary

### Implementation status (2026-08-24)

The repair now durably admits a versioned operation before parsing, commits the
Document projection, Debug projection, digests, and terminal receipt in one
transaction, records explicit failed/interrupted `not_committed` outcomes, and
terminalizes abandoned operations during startup. Implementer fault gates cover
cleanup, each projection boundary, interruption, forced OCR, startup recovery,
read-back tampering, and post-commit progress failure. The finding remains open
until the repository-required independent fault review is recorded; full v3
Document adoption remains separate under `HRN-DOC-001`.

### Evidence

`services/ai/app/services/documents.py` catches parser failures, but Study Unit
cleanup and the subsequent debug/document writes occur after that `try/except`.
The debug record is saved before the Document aggregate. Cleanup or either write
can therefore leave a Document stuck in `processing` or create a half-commit.

### Reproduction

Inject a failure into `build_study_units`, the `document_debug` save, or the
following Document save. Inspect the Document status and the two aggregates.

### Acceptance

The current defect repair is a prerequisite to full Harness adoption:

- an independent operation journal/staging record is terminal truth even when
  the Document or debug projection write itself fails;
- cleanup, first-write, second-write, interrupt, and forced-OCR fault injection
  cannot strand `processing` or leave an unknowable half-commit;
- Debug and Document projections commit atomically or through staging/read-back
  recovery; neither can silently become the sole completed write.

After that boundary is safe, Document Harness adoption adds explicit
Extraction/OCR, Section, Chunk, Study Unit and commit stages, component/context
versions, invariants, v3 terminal traces, replay, and eval. A v3 trace alone is
not the defect repair.

## P1 — Planning silently weakens malformed tool/proposal data and multi-writes

### Schema implementation status (2026-08-24)

All six Planning tools now use strict versioned argument/result DTOs; malformed
JSON, extra fields, and wrong types return a typed field path without tool
execution. Final model output is a strict `LearningPlanProposalV1`, permits one
bounded repair, and cannot provide plan/schedule/chapter IDs, state, revision,
or timestamps. Unknown/duplicate Study Unit refs and illegal chapter/slice
ranges, ordering, or Section refs fail closed instead of disappearing. The
finding remains open for the independent operation journal and atomic
Document/Debug/Trace/Plan commit boundary plus independent revalidation.

### Evidence

- `services/ai/app/services/plan_tool_runtime.py` can turn malformed arguments
  into an empty object rather than a typed decode failure.
- `services/ai/app/services/model_provider.py` parses final plan data as generic
  dictionaries and drops invalid schedule-chapter items.
- `services/ai/app/services/plans.py` writes debug/document, planning trace, and
  plan across separate persistence operations.

### Acceptance

Planning has two prerequisite boundaries before full Harness adoption:

- **schema ownership:** every tool execution decodes its own versioned argument
  contract, and the final plan proposal has a separate strict contract. Bad
  fields carry a typed path and never become `{}` or disappear silently. The
  model never owns application IDs, revisions, timestamps, or committed state;
- **commit boundary:** an operation journal/staging record binds request identity
  and base revision. Plan/Document/debug/trace persistence is atomic or uses
  durable read-back recovery and idempotency.

Malformed tool args, dropped chapter candidates, duplicate request, stale
revision, interrupt, and each write boundary need failure fixtures. Only after
both prerequisites land does Planning Harness add versioned prompt/toolset/context,
attempt/check traces, artifact replay, and grounding/tool-correctness eval.

## P1 — Scene proposal and committed schemas are not separated

### Evidence

`services/ai/app/services/model_provider.py` accepts model-provided layer,
object, and `reuse_id` identities. `services/ai/app/models/api.py` and Scene
services reuse committed records as model generation response, user-authored
save input, and persistence shape. Recursive depth, node count, identity
uniqueness, and selected path are not proven at the proposal boundary.

### Acceptance

- A strict `SceneProposal` cannot mint layer/object IDs, arbitrary reuse IDs, or
  timestamps. It may reference an application-provided reusable-node allow-list
  identity; the application resolves that reference and projects committed IDs
  only after validation.
- Depth, total nodes, per-layer objects, unique IDs, valid selected path, and
  bounded text have explicit invariants.
- Malformed children fail closed or follow a bounded, traced repair policy.
- User-authored committed DTOs and model proposals use separate endpoints/types;
  save APIs accept committed DTOs with revision/CAS, not raw model proposals.

## P1 — Non-Tavern frontend decoding is fail-open

### Evidence

`apps/web/lib/api.ts` uses a generic `readJson<T>` assertion and domain
normalizers that coerce with `String`, `Number`, `Boolean`, or defaults. The
Document, Planning, Persona, Scene, and Study domains lack the strict Tavern
decoder's identity, enum, finite-number, ordering, and aggregate ownership
checks. Streaming clients do not receive or require a versioned
operation/subject/event identity plus a legal committed terminal event.

Stale-result risks are also domain-specific:

- Study responses can apply after the current plan/session selection changes.
- Persona assist can write an old result into the current draft/field.
- Scene assist can overwrite edits made while a request is running.

### Acceptance

- `HRN-WEB-001` is a tracking epic. Document, Planning, Persona/Scene, and Study
  decoders close separately; shared adversarial fixtures do not prove a decoder
  has adopted them.
- Each domain has `unknown -> value | typed DecodeError`, shared fixtures, and
  exact field paths.
- Decoders reject wrong response identity, unknown enums, `NaN`/infinity,
  invalid nullability, duplicates, reversed ranges, broken references, and
  illegal terminal regressions.
- Backend stream contracts supply a contract version, operation/subject
  identity, monotonic event sequence or resume token, payload digest, and
  committed terminal evidence. Frontend state machines accept only registered
  transitions and succeed only on the matching committed terminal projection;
  EOF fails only if that terminal was not seen.
- A duplicate event ID with the same digest is ignored idempotently; the same ID
  with different bytes, an unknown transition, or any post-terminal state event
  fails closed.
- Study, Persona, and Scene bind results to operation ID, subject ID, draft
  revision, and field target; late results are discarded or shown as candidates.
- Main UI shows passed/repaired/failed/commit-uncertain status; raw Harness data
  stays in Debug. Legacy `ModelRecoveryRecord` is not relabeled as v3 evidence.

## P1 — Tavern Participant Roster overstates generation state

### Evidence

`apps/web/components/tavern-workspace.tsx` optimistically marks all selected
targets as `generating`, then gives that array precedence over server speaker
steps. Facilitated execution is sequential: normally one claimed step is
`generating` and later steps are `pending`.

### Acceptance

- Before server truth arrives, the UI says the run is starting or marks only the
  first eligible step.
- Once steps exist, server state wins: claimed actor is `generating`; future
  actors are `pending`; terminal states cannot be overwritten optimistically.
- Direct, facilitated, partial, resume, cancel, and stale-response fixtures pass.

## P1 — Tavern recovery is hidden and mobile task order is wrong

### Evidence

- Scoped retry for `partial`/`failed` runs is inside collapsed Reliability
  Details rather than near the Interaction Composer.
- On narrow layouts the Conversation Panel remains before Session/Setup; an
  empty transcript has a large minimum height and says “from the left”, so a
  first-time 390×844 user crosses a dead area before reaching room creation.

### Acceptance

- A terminal partial/failed run shows a primary action near Header/Composer,
  including saved message count and unfinished persona names.
- Retry targets only eligible steps; a recovered parent no longer exposes the
  same retry action.
- With no room, Setup/Session precedes the empty transcript. With an active room,
  Composer is in the first viewport or persistently reachable.
- “Create Tavern” scrolls and focuses the title field; copy avoids desktop-only
  spatial directions.
- A host browser validates 390×844 viewport, keyboard, touch, IME composition,
  focus order, and no horizontal overflow.

## P2 — Provider truth, accessibility, and Tavern scale

### Mock provider truth

The default local/mock provider produces template replies, but the main Plan,
Study, and Tavern workspaces do not consistently label that mode. Every
generation workspace must show a non-intrusive “local simulation; no real model
call” label. Reliability copy must explain that structural/commit reliability
does not prove factual or content quality.

### Accessibility

Plan, Study, Persona, and Scene async notices need semantic live regions. Errors
must focus a summary and restore focus after recovery. All controls need visible
`:focus-visible` treatment and 44px targets. The Debug Overlay already closes on
Escape. It still needs `role="dialog"`, `aria-modal`, initial focus, focus
containment, background inertness, and trigger focus restoration. The Scene
delete-layer dialog already has dialog/modal semantics but lacks Escape close,
initial focus, focus containment, background inertness, and trigger focus
restoration.

### Tavern room scale

`GET /tavern/rooms` reads all rooms and participant summaries and the UI renders
all room buttons. Add `(updated_at DESC, id DESC)` cursor pagination with default
30 and maximum 50, page-local aggregation, and load-more. The selected room must
remain available across pages, while retry-chain truth continues to use its
independent authoritative view rather than room-list pagination. The 1,000-room
fixture must meet the versioned query, payload, server P95, and React P95 gates
in `docs/performance-budgets-v1.md`.

## P3 — Documentation drift

- Align the Home subtitle in `docs/user_manual.md` with the rendered page.
- Describe Tavern Scene selection as a snapshot from the saved Scene Library,
  unless current unsaved Scene drafts become selectable.
- The manual says Plan generation rounds show recovery count and descriptions,
  but `document-setup.tsx` does not parse recovery events or render those fields.
  Either implement the claimed main-UI behavior or remove the promise.

## Verified behavior

The audit found direct evidence for these capabilities and they should not be
reopened without contradictory runtime evidence:

- normalized Tavern Room/Participant/Message/Run/Step persistence;
- append-only room message sequence;
- direct and roster-ordered facilitated runs;
- partial preservation, scoped child retry, resume, lease takeover, and cancel
  commit fencing;
- strict Tavern browser decode, aggregate identity checks, terminal run fencing,
  draft recovery, IME composition fencing, and transcript backward paging with
  scroll-anchor preservation;
- Debug Overlay Escape-to-close behavior;
- operation commit policy/schema foundation with server-only operation/effect
  receipt and adversarial read-back validation. Production Tavern traces remain
  legacy v1 until its explicit v3 adoption gate closes.

## Independent revalidation rule

Each finding should be fixed in a focused commit. Before fast-forwarding that
commit to local `main`, a non-implementing agent should rerun the reproduction
and judge the acceptance criteria. Passing a developer-authored happy-path test
alone does not close an independent UX or reliability finding.
