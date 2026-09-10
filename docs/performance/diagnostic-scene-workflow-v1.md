# Scene request-chain diagnostic overhead

Thirty paired samples after three warmup pairs execute actual mock-provider Scene
creation proposals, POST the generated tree to `/scene-library`, and GET the saved
scene by ID. Every sample uses fresh application/storage. Full saved/read-back
responses, all generated tree contents, selected layer and empty collapsed IDs
must match. Canonical generation ends `not_applicable`; the separate user save is
proved by persisted read-back. Root-layer counts, revisions and terminal status
populations must match between enabled and disabled runs.

The control and timing boundaries follow the [Persona method](diagnostic-persona-workflow-v1.md):
real ASGI and database, unchanged canonical Harness and console logging, with only
diagnostic middleware, sink and background workers bypassed in the control.
Startup, shutdown, post-response drain, network, UI and live providers are excluded.
Enabled samples require flow/action/resource and canonical trace correlation,
private sentinel exclusion and zero drops. All 30 samples passed these functional
checks, with zero write/read failures and empty queues after drain.

| Population | P50 (ms) | P95 (ms) | Max (ms) |
| --- | ---: | ---: | ---: |
| Enabled | 27.41 | 90.86 | 97.11 |
| Disabled | 24.14 | 86.71 | 111.96 |
| Signed paired enabled − disabled | 3.08 | 67.74 | 73.73 |
| Post-response drain | 1.26 | 1.27 | 1.29 |

**The predeclared P95 paired overhead budget of 50 ms failed.** Two enabled
samples produced deltas of 67.74 and 73.73 ms. The cause has not yet been isolated;
similar absolute outliers on the disabled side do not establish that logging is
free of overhead. Retain this report when adding request-stage measurements;
a faster rerun alone must not close the finding. This is scoped backend mock
performance evidence, not native WebView or representative live-model acceptance.

```sh
UV_CACHE_DIR=/tmp/vibe-learner-uv-cache uv run --directory services/ai python -m tests.diagnostic_workflow_probe --workflow scene --samples 30 --output /tmp/diagnostic-scene-workflow.json
```

[Raw report](diagnostic-scene-workflow-v1.json) retains all signed pairs, health
and canonical outcome populations plus probe digest. The command deliberately
exited nonzero for its failed performance gate. Log:
`/tmp/diagnostic-scene-workflow.log`. The retained Persona branch was also exercised
with three warmup pairs and one measured smoke pair; this is compatibility evidence,
not a replacement for its previously archived 30-pair result.
