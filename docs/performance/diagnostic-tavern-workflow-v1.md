# Tavern request-chain diagnostic overhead

Two separate populations measure actual mock-provider direct (one actor) and
facilitated (three actors) runs. Each chain creates a Room, posts a user turn,
reloads the Room transcript and reloads the Run list. Persona prerequisites are
created before timing. Full typed read-backs must equal the original committed
Run and input/generated Messages; contiguous message sequences and participant
order are verified. Diagnostic Message references must carry the exact room ID
and sequence. Each operation must resolve to one committed canonical trace per
actor. All content sentinels are excluded from events.

Each population uses 30 pairs after three warmup pairs, alternating mode order,
with fresh subprocess/app/storage and default Python GC for every sample.
Enabled uses the normal diagnostic middleware/sink/workers; disabled bypasses
only those components. Canonical Harness and structured console logging stay
unchanged. The chain timing includes request decoding and read-back assertions;
startup, Persona setup, shutdown and post-response queue drain are excluded.
This measures the complete named backend path with a mock provider, not network,
native UI, live-model, cancellation or partial-retry latency. Fault/recovery
functional evidence remains in the existing acceptance suites.

Both gates are predeclared signed paired P95 overhead <=50 ms. All signed deltas
and maxima remain in the raw reports; GC time is observed, never subtracted.

| Population | P50 ms | P95 ms | Max ms |
| --- | ---: | ---: | ---: |
| direct enabled | 62.90 | 65.38 | 65.92 |
| direct disabled | 59.45 | 61.18 | 64.32 |
| direct paired_delta | 3.22 | 5.74 | 6.71 |
| direct post_response_drain | 2.53 | 2.54 | 2.54 |
| facilitated enabled | 131.51 | 137.89 | 155.99 |
| facilitated disabled | 128.90 | 140.48 | 142.63 |
| facilitated paired_delta | 3.80 | 10.26 | 24.04 |
| facilitated post_response_drain | 2.53 | 2.54 | 3.03 |

Both gates passed. All enabled samples have zero drop/read/write failure counts
and empty queues after drain. Each direct sample proves one committed actor and
two messages; facilitated proves three committed actors and four messages. These
are scoped primary-output commit claims, not proof of every upstream effect.

```sh
UV_CACHE_DIR=/tmp/vibe-learner-uv-cache uv run --directory services/ai python -m tests.diagnostic_workflow_probe --workflow tavern_direct --profile-stages --isolate-samples --samples 30 --output /tmp/diagnostic-tavern-direct.json
UV_CACHE_DIR=/tmp/vibe-learner-uv-cache uv run --directory services/ai python -m tests.diagnostic_workflow_probe --workflow tavern_facilitated --profile-stages --isolate-samples --samples 30 --output /tmp/diagnostic-tavern-facilitated.json
```

Complete raw [direct](diagnostic-tavern-direct-v1.json) and
[facilitated](diagnostic-tavern-facilitated-v1.json) reports retain probe/helper
digests and every sample. Logs: `/tmp/diagnostic-tavern-direct.log` and
`/tmp/diagnostic-tavern-facilitated.log`. Study and remaining native performance
acceptance remain separate work.
