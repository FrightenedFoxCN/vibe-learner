# Native spool stage investigation

The initial saturated-ring report remains a failed observation (P95 25.21 ms
against 25 ms). Test-only, thread-local checkpoints now divide a saturated emit
into admission, counter recovery, scan/sort, eviction synchronization, counter
checkpoint and event commit. They are compiled out of normal application builds
and are enabled only around the opt-in benchmark's saturated emissions.

| Stage | Unchanged runtime P50 (ms) | P95 (ms) |
| --- | ---: | ---: |
| Lock admission | 0.06 | 0.13 |
| Counter recovery | 0.05 | 0.09 |
| Directory scan and sort | 2.05 | 2.89 |
| Eviction and directory sync | 3.90 | 4.82 |
| Counter file sync, rename and directory sync | 7.93 | 8.12 |
| Event serialization, file sync, rename and directory sync | 7.90 | 8.10 |

The unchanged runtime's total P95 was 23.09 ms in this run, below 25 ms.
This does not erase the original failed sample set. Per-stage percentile values
must not be summed to reconstruct the total percentile.

A small experiment replaced full-path comparison with validated filename-string
comparison, leaving synchronization unchanged. Total P95 was 24.81 ms and the
scan/sort stage's P50/P95 was 2.87/3.73 ms. This does not establish an improvement
over the unchanged runtime; the experiment was reverted. All 11 ordinary native
tests passed during the experiment. Final production code retains its original
ordering and durability protocol; the only retained code change is test-only
measurement instrumentation.

The dominant local costs are durable filesystem synchronization, with enough run
variation to cross the narrow 25 ms threshold. No synchronization was removed and
no budget was widened. Native overhead acceptance remains unresolved rather than
being certified by selecting the passing rerun. Further system-level comparison
must retain actual lifecycle scope and filesystem variability.

- [Unchanged-runtime raw stages](diagnostic-native-spool-stages-v1.json)
- [Rejected sorting experiment raw stages](diagnostic-native-spool-name-sort-v1.json)
- [Initial failed report and method](diagnostic-render-and-spool-v1.md)

Reproduce using the existing `spool_performance_probe` command documented in the
method; `raw.saturated_stages_ms` now contains each sample's nonoverlapping stage
durations. Local logs: `/tmp/diagnostic-native-spool-stages.log` and
`/tmp/diagnostic-native-spool-name-sort.log`.
