# Harness performance budgets v1

Update: the authorized 2026-09-09 joint acceptance run used MiniMax M3 and
reproduced the local performance gates. Joint acceptance did not pass; real
Tavern usage/latency evidence now includes 30 scheduled steps before and after
prompt repair. After repair, 28 completed, one failed with upstream 529 and one
was blocked; 29 provider requests had empirical p50/p95 of 6981/20169 ms and
456051 usage tokens. This is one repeated synthetic configuration, not a
maximum-input or representative-population gate. Billed cost remains unknown.
See also [the follow-up evidence](acceptance-wave45-2026-09-09/remaining/README.md). See
[the acceptance report](acceptance-wave45-2026-09-09/README.md). The no-provider
statement below describes the earlier implementation run only.

Wave 5 implementation and local measurements are complete. Independent
acceptance is pending together with Wave 4. At the user's request, no real
provider calls were made; live provider latency, billed tokens/cost, repair rate,
failure rate and representative provider/model configuration remain open.

## Executable limits

`app.models.harness_performance` owns `harness-performance-budget-v1`.
Limits apply to one admitted runtime stage; equality passes.

| Dimension | Limit | Boundary |
|---|---:|---|
| Canonical context UTF-8 bytes | 256 KiB | Before resolver/worker |
| Subject plus snapshot references | 64 | Before resolver/worker |
| One resolved snapshot | 64 MiB | After authorization/resolution, before worker |
| All resolved snapshots | 128 MiB | After authorization/resolution, before worker |
| Existing runtime attempts | 64 | Before heartbeat-wrapped callback |
| Existing attempt/check canonical bytes | 1 MiB | Before heartbeat-wrapped callback |

The snapshot size check measures resolved payloads, not a streaming database
read allocation limit. Attempt/evidence limits check the existing journal before
the next callback, not a maximum final trace size; failure/terminal evidence may
still append. Existing policy-specific repair ceilings remain in force. An
expired wall-time budget now prevents starting the next callback.

Initial pre-execution budget failures record a content-free typed
`HarnessBudgetViolationV1` (version, dimension, actual, limit) in a failed check.
Canonical measurement uses UTF-8 and the canonical JSON settings; it never
publishes a protected-content digest. No public proposal or API DTO is expanded.

Batch resolution shares one database session/transaction while retaining each
request's exact grant, operation, contract, permission, retention and digest
checks before content access. Tavern, Study and broad-adoption resolver bridges
use the batch path. Results preserve request order. Unexpected transaction
errors roll the batch back; ordinary typed denials remain individual results.

## Reproduce the local gate

From the repository root:

```sh
npm run bench:harness -- --samples 30 --output ../../docs/performance-samples/harness-local-v1-macos-arm64-2026-09-09.json
```

The command uses temporary SQLite and synthetic content, with five warmups per
case and at least 30 measured samples. It requires the `cl100k_base` tokenizer
data cache (first use may download public tokenizer data). It reads no runtime
provider settings or credentials and makes zero provider calls. Each JSON report
contains raw samples, nearest-rank p50/p95, environment/dependency versions,
base commit, changed-source hashes, fixture/budget versions, limits and failures.

| Local measurement | p95 ceiling |
|---|---:|
| Admitted Persona runtime, protected 8 KiB input, strict proposal, trace | 500 ms |
| One snapshot resolution | 100 ms |
| Eight snapshot resolutions | 300 ms |
| 64 snapshot resolutions | 1500 ms |
| Tavern prompt preflight plus tokenizer | 1500 ms |
| Planning two-tool serial round | 100 ms |

The runtime measurement includes the lifecycle and database work; it is not an
isolated estimate of incremental Harness overhead. Resolver before/after uses
the same protected payload and grants with individual transactions versus one
batch. The batch SQL gate is at most `6 * reference_count + 3` statements.
These are local regression ceilings, not production latency promises.

Raw evidence: [macOS arm64 samples](performance-samples/harness-local-v1-macos-arm64-2026-09-09.json).

Developer validation on 2026-09-09: `npm run check:release` passed (526 backend
tests, 163 frontend tests passed with two optional skips, shared/type checks,
three deterministic PR eval suites, production Web build). After adding the
suffix-oracle and attempt-ceiling regressions, the affected performance and
Tavern prompt suites passed all 25 tests. The local benchmark passed every
timing, token, byte, SQL and correctness gate. This is implementation evidence.

## Tavern fixture and optimization

The fixture has six personas, a large bilingual scene and 40 messages of 8,000
characters. It exercises transcript trimming with the production actor schema,
prompt rendering, recovery reserve, partition limits and preflight. It reports
original/final prompt and transcript bytes, persona/cast/scene bytes, removals,
estimated tokens and actual `cl100k_base` content tokens including recovery.
This is a long synthetic case, not proof of every maximum-size input combination
or a provider-specific chat wrapper. Provider measurements are explicitly null.

The preflight skips token scans of byte-ineligible nonempty transcripts and
estimates the recovery-inclusive prompt once, since that estimator is additive.
Oldest-message removal, error precedence and final prompt remain unchanged.
An exhaustive suffix-oracle regression verifies the retained prompt and estimate.
Existing tests cover partition boundaries, trimming and content-free evidence.

## Planning decision and rollback

Retain serial execution: all six Tool Manifest registrations are
`parallel_safe=false`; some tools mutate planning state. The local round reads
one Study Unit detail and estimates completion, respecting each tool's one-call
per-round ceiling. It validates successful typed results, grounding and provider
call ordering. The before/after windows run the same serial implementation; they
do not demonstrate a parallel speedup or fewer model rounds.

Any future parallel proposal must first register all batch members as safe,
provide one immutable input snapshot, prove no dependent effects, preserve
result order and pass held-out correctness and same-round performance gates.
Reject parallel mode if any prerequisite fails. Reject this local optimization
if output/authorization regressions occur, the SQL ceiling is exceeded, or a
named p95 ceiling fails on the recorded environment; do not weaken safety limits
to conceal a timing regression.

## Pending joint acceptance

- Independently reproduce Wave 4 workflow, recovery, browser/desktop and live-wire gates.
- Independently reproduce Wave 5 raw samples and adversarial budget/authorization cases.
- After separate authorization, select representative Tavern provider/model configurations
  and measure live latency, billed usage/cost, repair/failure rates and full six-actor runs.
- Review maximum supported input combinations beyond this synthetic fixture.

Developer regression checks and local samples do not close these items.
