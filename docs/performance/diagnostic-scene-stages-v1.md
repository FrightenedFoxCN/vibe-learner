# Scene overhead: request stages and garbage collection

The [original 30-pair run](diagnostic-scene-workflow-v1.md) failed the 50 ms
paired P95 gate at 67.74 ms. The probe now optionally records each real request's
elapsed time and overlaps with Python GC callbacks. No GC threshold changes,
forced collection, disabled GC, adjusted durations or production changes are used.
All persistence and diagnostic correlation assertions remain active.

The next 30 pairs in one process had four chains above 50 ms. Every such chain
had a generation-2 collection during generation; save/reload stayed short.

| Pair (zero-based) | Mode | Generation request ms | Gen-2 collection ms |
| --- | --- | ---: | ---: |
| 5 | enabled | 67.90 | 46.43 |
| 12 | disabled | 74.43 | 54.15 |
| 19 | enabled | 84.17 | 61.93 |
| 26 | disabled | 81.99 | 62.17 |

The profiled run's signed delta P95 was 49.69 ms and maximum 62.90 ms. It does not
retroactively pass the original failure. GC overlap is measured wall time, not
CPU attribution; durations are not subtracted from the performance gate. The
original run lacked GC callbacks, so its individual stalls cannot be conclusively
attributed from this later run alone.

To test interference from preceding temporary applications, `--isolate-samples`
runs each sample in a new Python subprocess with fresh application/storage and
normal GC enabled. Timing still covers only generation, preparation/save and
persisted reload; Python imports/process startup/application startup are outside
it. Both sides use identical isolation, alternating order, three warmup pairs and
30 measured pairs. This is a distinct experimental population, not selection of
fast samples from the original run. All raw pairs are retained.

| Isolated population | P50 ms | P95 ms | Max ms |
| --- | ---: | ---: | ---: |
| Enabled | 33.45 | 35.96 | 38.04 |
| Disabled | 29.58 | 30.64 | 31.70 |
| Signed paired delta | 3.76 | 6.23 | 8.28 |
| Enabled post-response drain | 1.26 | 1.27 | 1.27 |

No generation-2 collections occurred during these measured isolated requests.
All generated tree read-backs, canonical populations, event correlation, private
sentinel exclusion and zero-drop checks passed. The fixed 50 ms P95 gate passed
for isolated samples. This supports cross-sample GC interference in the repeated
application benchmark; it does not establish long-lived service GC behavior,
all-workflow overhead, native rendering or live-provider latency. Remaining
workflow/native requirements stay tracked in the acceptance checklist. No runtime GC workaround is justified by
this evidence.

```sh
UV_CACHE_DIR=/tmp/vibe-learner-uv-cache uv run --directory services/ai python -m tests.diagnostic_workflow_probe --workflow scene --profile-stages --samples 30 --output /tmp/diagnostic-scene-stages.json
UV_CACHE_DIR=/tmp/vibe-learner-uv-cache uv run --directory services/ai python -m tests.diagnostic_workflow_probe --workflow scene --profile-stages --isolate-samples --samples 30 --output /tmp/diagnostic-scene-isolated.json
```

Raw [shared-process stages](diagnostic-scene-stages-v1.json) and
[isolated-process stages](diagnostic-scene-isolated-v1.json) retain per-request GC
overlap, whole-chain signed timings and source digests. The first report predates
the subprocess option and therefore has a different source digest. Logs:
`/tmp/diagnostic-scene-stages.log` and `/tmp/diagnostic-scene-isolated.log`.

The Persona branch also passed the subprocess/profile compatibility smoke (three
warmup pairs and one measured pair); `/tmp/diagnostic-persona-isolated-smoke.log`.
This does not replace its archived 30-pair performance population.
