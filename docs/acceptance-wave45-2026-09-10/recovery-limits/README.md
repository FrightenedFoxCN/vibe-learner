# Recovery and maximum-input technical acceptance

Scope: developer-authored recovery, atomicity, size-boundary and transport tests.
Quality review was explicitly deferred by the user. No independent-review or
real-model quality attestation is claimed. All newly generated inputs are
synthetic; the HTTP service uses a separate temporary SQLite store and mock
provider. This run did not use the desktop Vault or historical user content.

## Abrupt process recovery

`services/ai/tests/test_wave45_process_recovery.py` covers **24 crash windows**.
Each child calls `os._exit(73)` at its designated boundary, bypassing cleanup and
`finally`. The parent opens fresh database connections and checks SQLite integrity
and foreign keys. These tests extend the existing exception-based fault tests.

| Workflow | Crash windows | Recovery assertion |
| --- | ---: | --- |
| Document | Admission, after commit, four transaction statement boundaries | Abandoned operations fail; partial debug/document writes roll back; committed result and binding survive |
| Planning | Before provider, after provider-start marker, after commit, six transaction boundaries | Pre-provider is not committed; issued calls remain uncertain; all partial projections roll back; committed replay performs no second generation |
| Persona / Scene | During generation and after terminal trace but before generic operation terminalization, for each workflow | Incomplete proposals fail closed; persisted successful terminal evidence recovers completed status; binding remains identical |
| Study | Admission, claim, provider-start marker | Expired admission is safely not committed; claimed/issued operations remain uncertain and cannot be reclaimed; Session revision stays unchanged |
| Tavern | Pending run and interruption after one actor commits | Six-person roster with four targets resumes only unfinished actors; preserved messages/identities remain exact; repeated terminal resume adds no calls |

Study/Tavern deadline expiry is simulated by updating persisted test deadlines
after the process exits. No production clock or claim budget is changed. The
existing suites additionally check concurrent admission/CAS, cancellation,
heartbeat fencing, bounded claim exhaustion, scoped child retry, tamper/deletion
handling, protected artifact authorization, and file/effect compensation.

## Exact limits and stress inputs

`test_wave45_input_limits.py`, the additional real-size case in
`test_harness_performance.py`, and frontend import/draft tests exercise:

| Input | Accepted boundary | Rejected boundary / additional assertion |
| --- | --- | --- |
| Scene tree | Depth 8, 64 layers, 128 objects **simultaneously** | One extra layer/object or depth; 192 unique projected IDs; library save and database reopen preserve the full tree |
| Scene text | 60,000 Unicode codepoints | 60,001; production proposal/projection and frontend import counting |
| Persona generated setting | 64 slots × 8,000 characters; 16,000-character suggested prompt | 65 slots, 8,001 slot characters, 16,001 prompt characters |
| Persona card proposal | 24 cards with maximum scalar lengths and 24 unique tags each | 25 cards or tags |
| Persona authored save | 64 slots × 100,000 characters, maximum name/summary/relationship/address/prompt and reference hints | Overflow rejected without inserting a persona; database reopen preserves 6.4 million slot characters; frontend JSON/draft conversion preserves content and controls while normalizing owned ordering |
| Planning proposal | 24 schedule items × 24 chapters × 24 slices, 32 references, 12 tasks | Overflow at each collection boundary; total 13,824 slices validated |
| Request text | Planning objective 12,000; Study message/prefix 20,000 each; Tavern message 4,000 and guidance 1,000 | One character over each limit |
| Tavern roster/schedule | Six participants, four facilitated targets | Seventh participant or fifth target; actual maximum-roster runtime recovery above |
| JSON import | Exactly 8 MiB for both editors | One byte over rejected before file reading; UTF-8 byte counting; malformed JSON followed by a valid retry |
| Resolved snapshots | 64 MiB per snapshot, 128 MiB aggregate at actual configured limits | One byte over either limit rejected by the production runtime resolver boundary |
| Searchable PDF stress | 256 pages, 256 Sections, 512 chunks, 422,144 extracted characters, 1,418,719-byte synthetic PDF | All 256 page anchors and page order preserved through real parsing, cleanup and atomic commit |

The upload path currently has no declared file/page maximum, so the PDF case is
a **stress sample**, not proof of a nonexistent maximum. `CHUNK_MAX_CHARS` is a
packing target: a single unsplittable text unit can exceed it. This run does not
change those policies or claim a neural-OCR/multilingual maximum. The large
synthetic PDF's heuristic Study Unit grouping is not a quality assertion.

The existing versioned Harness budget tests cover context/reference/evidence
and attempt ceilings plus worker non-execution after rejection. Resolved size
limits act after resolution, not as a streaming database allocation guarantee.

## Real HTTP restart and frontend read-back

The existing isolated `server.py` and `http_matrix.py` were run at
`127.0.0.1:18046` with a fresh temporary database. The matrix completed Document,
Planning, Persona, Scene, Study and six-person Tavern flows and idempotent replay.
After **SIGKILL** of that service, a fresh server opened the same database.
Both actual TypeScript live-wire decoder tests passed against the restarted
service: Study committed operation receipt and Tavern aggregate/terminal resume.

This is actual HTTP and production decoder execution. It does not represent
native desktop clicking, rendered-page reload/focus/IME validation, PostgreSQL
restart, OS power-loss guarantees, or provider exactly-once execution.

## Reproduction and evidence

```bash
npm run test:acceptance:recovery-limits
npm run check:release
```

The acceptance command combines the new recovery/limit tests with existing
Document, Planning, runtime/migration, effects/artifacts, Study, Tavern,
Persona/Scene and frontend reliability suites. Live-wire tests need their
documented environment variables; the dedicated restart run supplied those
variables and had zero skips.

- `new-cases.log`: 13 new recovery/input test methods, including 24 crash windows.
- `recovery-limits-gate.log`: initial combined gate, 179 backend tests passed;
  169 frontend tests passed and two optional live-wire cases skipped. This was
  before adding the real-size snapshot case to the command.
- `http-matrix.log`, `http-summary.json`, `http-outcomes.json`: fresh HTTP run.
- `http-after-process-restart.log`: both live-wire cases passed after SIGKILL and restart, zero skips.
- `import-bytes.log`: exact-byte, over-limit and Unicode import tests.
- `release.log`: final complete release check passed: 565 backend tests, shared/frontend checks, all 13 registered eval suites and production Web build, including the added snapshot case.

Technical coverage above is completed; deferred quality review is not treated
as passed, and the Wave 4/5 joint independent acceptance status remains separate.
