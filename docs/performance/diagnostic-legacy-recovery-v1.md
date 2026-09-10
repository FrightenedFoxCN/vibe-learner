# Legacy diagnostic recovery observation

The [raw local report](diagnostic-legacy-recovery-v1.json) records one synthetic
144 MiB freelist event database, its 128 MiB ordinary admission envelope, and a
512 MiB additional recovery workspace allowance. All 200 existing safe events
plus the new event were retained; SQLite integrity passed and ordinary admission
resumed. Source hashes and environment are included. The probe can be repeated:

```sh
UV_CACHE_DIR=/tmp/vibe-learner-uv-cache uv run --directory services/ai python -m tests.diagnostic_recovery_probe
```

This is one functional recovery measurement, run while release checks could be
active; it is not a latency percentile, overhead baseline or performance gate.
It measures elapsed writer startup/drain/close, and before/after file lengths,
not peak allocated disk blocks, memory or complete installation space.

Recovery initially checkpoints and attempts normal admission. If still blocked,
it compacts the normal retained set before considering physical-pressure
retention. Deletions and existing loss counters share SQLite transactions. A
cooperative five-second SQL deadline, one-minute retry throttle and conservative
workspace/free-space checks bound automated work. Sources outside the envelope,
readers or low free space can leave recovery deferred; normal business commits
remain independent. The workspace allowance is a transient exception to the
ordinary limit, and is shown in storage queries/exports/UI. It is not an enforced
200 MiB installation-wide cap.

`tests.test_diagnostic_recovery` additionally exercises real event/index startup,
lossless freelist compaction, necessary pressure eviction, space/reader/deadline
refusal, the startup/close race, and subprocess exits before deletion commit,
after commit, and during VACUUM. Restart checks integrity and deletion counts.
Native platform acceptance and aggregate accounting remain separate work.
