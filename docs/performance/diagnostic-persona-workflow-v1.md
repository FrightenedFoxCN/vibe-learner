# Persona request-chain diagnostic overhead

The probe measures actual backend generation → application of generated card
contents to a Persona save request → persisted Persona reload. It uses the local
mock provider, real ASGI routes, database and canonical Harness lifecycle. Thirty
pairs follow three warmup pairs, alternating enabled/disabled order. Every sample
starts from its own temporary database and application; application startup and
shutdown are outside the measured interval. Generated content must match the
saved/read-back slots, and the full saved response must equal persisted reload.

The enabled side uses normal event, index and spool workers. The disabled side
uses test-only patches for a null event sink, middleware bypass, and unstarted
index/spool workers. Canonical Harness stays enabled. Structured console logging
is identical on both sides. This is not a production configuration switch.
Different counts, revisions or canonical commit-state populations fail the probe.
Enabled samples additionally require real flow/action/resource references, trace
IDs present in canonical terminal records, content exclusion and zero dropped events.

| Population, 30 samples | P50 (ms) | P95 (ms) | Max (ms) |
| --- | ---: | ---: | ---: |
| Diagnostics enabled | 24.95 | 41.61 | 87.25 |
| Disabled control | 22.09 | 88.68 | 96.61 |
| Signed paired enabled − disabled | 2.77 | 18.88 | 64.77 |
| Post-response queue drain, enabled only | 1.51 | 2.66 | 3.09 |

The predeclared P95 paired-overhead budget is 50 ms, reserving most of a 200 ms
interaction target for domain work. It passed locally. Signed deltas and outliers
are retained: the maximum delta exceeds 50 ms. Independent population percentiles
must not be subtracted or interpreted as logging making the workflow faster.
Fresh applications, scheduling, allocation and filesystem variability affect
these short samples. This is not a live-provider, network, browser/native WebView,
startup or all-workflow performance claim. Queue drain is measured separately
after the response/read-back interval, not silently charged as request latency.

The generation stage's actual canonical commit status was `not_applicable` in both
populations: generating candidate cards does not commit the later Persona. The
Persona save is proved separately by persisted read-back. An early probe used the
wrong response key (`cards` instead of API `items`), and an added check initially
assumed generation must claim a commit; both assumptions were corrected before
the final sample set. An earlier, weaker 30-pair sample measured delta P95 5.70 ms;
the archived result uses the stronger read-back/status checks, not the faster run.

```sh
UV_CACHE_DIR=/tmp/vibe-learner-uv-cache uv run --directory services/ai python -m tests.diagnostic_workflow_probe --samples 30 --output /tmp/diagnostic-persona-workflow.json
```

[Raw final report](diagnostic-persona-workflow-v1.json) includes every paired
sample, health counts, result checks, code digests and platform. Log:
`/tmp/diagnostic-persona-workflow-verified.log`. Other business flows, native
creation/clear and the saturated-spool issue remain separate acceptance work.
