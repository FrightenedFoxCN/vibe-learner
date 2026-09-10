# Document and Planning request-chain diagnostic overhead

This probe uploads a one-page synthetic text PDF, consumes the real Document
processing stream, reloads the persisted Document, consumes the real Planning
stream with the mock provider, and reloads the saved Learning Plan. The PDF is
prepared and a seeded Persona selected before timing. Both streams must end with
strictly validated committed terminal evidence; their complete committed domain
projections must equal the read-back responses (the stream-only Harness trace is
checked separately). Page, chunk, Study Unit and schedule counts must be nonzero
and match across paired modes. The private document sentinel must reach the
persisted Document while staying out of diagnostic events.

The shared probe retains the default Python GC policy, canonical Harness and
console logging. Only the diagnostic sink/middleware and index/spool workers are
bypassed for the control. Each sample has its own subprocess, app and storage;
three warmup pairs precede 30 measured pairs in alternating mode order. Timings
include five actual requests plus in-chain stream decoding, payload preparation
and read-back assertions. Process/import/app startup, synthetic PDF preparation,
Persona lookup, post-response queue drain, shutdown, UI and network are excluded.
This measures one-page text parsing and mock Planning; actual OCR recognition,
provider tool latency and representative live-model quality are separate scopes.

Enabled samples require Document and Learning Plan resource references, all five
action identities, private filename/text/objective exclusion and zero dropped
events. The actual parser emits operation references for Document, OCR and Study
Unit cleanup, plus Planning. Every linked canonical trace must be terminal; the
Document parse and Plan generation parent traces must each prove `committed`.
Direct trace IDs are optional on these operation-linked stream events. An initial
probe incorrectly expected stream projection equality including its extra Harness
field, then assumed the two user workflows had only two canonical operations;
these test assumptions were corrected before the final population.

The predeclared gate is signed paired enabled-minus-disabled P95 <=50 ms. Raw
signed deltas, GC observations and stage durations are retained, without subtracting
GC or queue drain from measured request time. Different population percentiles
must not be subtracted as an overhead estimate.

```sh
UV_CACHE_DIR=/tmp/vibe-learner-uv-cache uv run --directory services/ai python -m tests.diagnostic_workflow_probe --workflow document_plan --profile-stages --isolate-samples --samples 30 --output /tmp/diagnostic-document-plan-workflow.json
```

| Population, 30 samples | P50 ms | P95 ms | Max ms |
| --- | ---: | ---: | ---: |
| Enabled | 158.60 | 166.37 | 170.06 |
| Disabled | 154.06 | 164.27 | 171.24 |
| Signed paired delta | 4.68 | 10.92 | 12.12 |
| Enabled post-response drain | 1.27 | 1.28 | 1.30 |

The 50 ms P95 gate passed. Every enabled sample produced 25 correlated events,
4 verified canonical operations and 7 terminal traces: two `committed` parents
and five `not_applicable` component outcomes. The one-page input yielded one
chunk, one Study Unit and one schedule entry. All enabled health counters for
drops/write failures/read failures/queued events were zero after drain.

[Complete raw report](diagnostic-document-plan-workflow-v1.json) includes both
probe/helper digests and every sample. Log:
`/tmp/diagnostic-document-plan-workflow.log`. The Persona/Scene branches are also
checked with three warmup pairs and one measured pair each after generalizing
result comparison; those are compatibility smokes, not new performance baselines.
Remaining Study/Tavern and native performance requirements are not closed here.
