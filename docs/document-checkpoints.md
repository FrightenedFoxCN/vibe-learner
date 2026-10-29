# Document OCR checkpoints

Document processing saves bounded partial work under the real admitted process
operation. A failed/interrupted operation can expose saved work without marking
the shared Document as processed. Plan Workspace shows the saved page count,
recent page snippets and completed Study Units in the Document Checkpoint Panel.
It preserves the selected Document ID in session storage so reload can query the
same server record; no uploaded file needs to be sent again for an OCR resume.

## What survives

- Each completed extraction/OCR page is saved before progress callbacks or the
  next page's cooperative budget check. A process exit therefore retains the
  durable prefix, including OCR metadata needed by later parser stages.
- A complete parser report is saved before Study Unit cleanup. The complete
  runtime output is saved before the outer Harness checks the elapsed deadline.
  An elapsed wall-time after cleanup cannot erase an already saved report/Unit
  output merely because the parent operation remains not committed.
- Failed/unavailable OCR pages are retried. Degraded forced-OCR reports and empty
  cleanup output cannot become a shortcut that perpetually reuses failed OCR.
- Checkpoint writes use a SQL fence on the owning running operation. Recovery or
  terminalization prevents an old worker from appending or replacing checkpoint
  work. Individual saved pages are immutable within that operation.

The staged content budget is 8 MiB per operation and at most 10,000 raw page
records. Page data is normalized and digested; the parser/report/output snapshot
strictly validates identity and ordering. When a complete reusable report/output
fits but raw page rows would exceed the budget, the transaction compacts obsolete
page rows into that complete stage. If the next stage itself cannot fit, the
existing durable prefix remains and `storage_limited=true` explicitly reports
that only saved work can be reused. This is a staged-content limit, not an
installation-wide SQLite/WAL/disk certification. Immutable committed Document
receipts use the existing domain projection boundary and remain available for
query-only duplicate read-back.

## Explicit resume and identity

The learner chooses “从保存进度继续处理”. POST `/documents/{id}/process` or
`/process/stream` carries the saved `resume_from_operation_id` and the same
`force_ocr` value. The server verifies the upload SHA-256, reviewed parser/OCR/
cleanup component contracts, parser type, concrete OCR engine/model directory,
explicit model-file digests and relevant package versions. Dependency versions
are compatibility inputs, not invented component adoption evidence.

Admission requires a failed/interrupted source and the exact Document revision
left by that source's recovery. A newer edit/process prevents stale checkpoint
admission. The source-to-child row and new process admission/Harness binding share
one transaction. Each source has at most one child, and concurrent repeated
requests cannot start another parser. A running/failed child returns a conflict
for that source; queries can inspect it, and a failed child can itself be the
source of the next explicit resume. A completed child reads its existing receipt
without parsing again; a superseded committed projection returns 409.

The relation is owned by `document_checkpoint_resumes`; generic Harness parent
bindings remain Tavern-only. Reuse input enters the child's operation-authorized
protected upload snapshot and is resolved before execution. The child reruns the
normal strict output checks and Document/Debug/CAS/receipt/terminal-trace commit.
Cached pages/reports do not borrow another operation's successful commit claim.
Observed stage metrics stay absent or zero when no new stage work ran.

The current parser component is `document-parser-v2`; the Document workflow
manifest, adapter, typed input and protected snapshot use v2. The output and
commit projection stay on their existing v1 contracts. Historical DTOs and stored
v3 trace evidence remain unchanged. Alembic `20261029_0025` adds the three domain
tables; empty schemas can downgrade, while retained checkpoint data must be
explicitly exported/removed before downgrade.

## Read-back and UI

- GET `/documents/{id}/checkpoint` reads the latest operation checkpoint.
- GET `/documents/{id}/checkpoints/{operation_id}` reads one exact checkpoint.
- `document-checkpoint-response-v1` separates `checkpoint_only` from `committed`,
  returns up to 64 recent page previews, saved Units, source/child identities,
  capacity state and a nullable committed result. GET never starts parsing.
- The strict browser decoder checks identities, counters, enum/boolean types and
  commit/result consistency. After response loss the panel queries the original
  source and its child; it does not automatically reissue POST. An explicit
  “继续同一次续跑” action retains the same source identity and is server-idempotent.
- A committed result enables “使用该教材生成计划”. This separately requested plan
  uses the saved Document watermark and current goal/page-range draft; it skips
  upload and OCR. Late panel results are fenced after Document changes/unmount.

## Focused evidence

- `npm run test:ai:document:checkpoints`: ten cases covering page failure, parent
  budget expiry after complete Units, restart/fencing, changed input/config,
  corruption, capacity, concurrent duplicate admission, degraded-page retry,
  stale revision and actual HTTP restart/read-back. Real HTTP checkpoint JSON is
  decoded by the production TypeScript decoder in Node.
- `npm run test:acceptance:document-checkpoints`: three fresh Python processes;
  the first exits via `os._exit` during OCR, the second opens the database and
  recognizes only the two remaining pages, the third repeats the resume and
  proves zero parser calls with the same committed result.
- `npm --workspace @vibe-learner/web run test:workspace:checkpoints`: strict decode,
  response loss/query-only child recovery, session-storage restoration and late
  result fencing. The generation suite covers planning from a resumed Document
  without a new upload/parse.
- `npm --workspace @vibe-learner/web run test:workspace:checkpoints:browser`: a
  focused Chromium development-server case for saved snippets, reload, lost
  response, GET recovery and the committed continuation action.
- The nine-case `document_process_regression` suite runs through the existing
  HarnessEvalRunner. It includes new complete, foreign-scope and incomplete checkpoint output cases.
  Related migration, Document CAS and process-operation
  regressions remain separate targeted gates. OCR recognition is deterministic in
  recovery fixtures; real multilingual OCR/platform stress remains OCR-STRESS-001.
