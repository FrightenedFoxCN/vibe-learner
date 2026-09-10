# Study request-chain diagnostic overhead

The measured chain creates a Study Session, sends one learner message through
normal durable chat admission, reloads the operation receipt and reloads the
Session. It uses actual routes, persistence and the mock provider. A one-page
text Document is uploaded/parsed and a seeded Persona selected before timing.
Prerequisite traces are snapshotted before the chain and excluded from its
canonical terminal population; no prior trace is misattributed to chat.

The committed operation receipt must exactly equal query read-back. The complete
Session must equal the receipt result, with exactly one added Turn and one
revision increment. Turn identity, sequence, learner message, assistant reply,
citations and Character Events must match the persisted receipt projections.
The diagnostic operation must resolve to the actual committed `study_chat_reply`
trace and reference the saved Session. Content/filename sentinels are excluded
from diagnostic events. An initial smoke used the workflow name `study_chat` as
the stage; this probe assertion was corrected to the registered stage before
the measured population.

Thirty paired samples follow three warmup pairs, alternating diagnostic mode.
Each uses an independent subprocess/app/storage and default Python GC. The
control bypasses only the diagnostic middleware, sink and index/spool workers;
canonical Harness and console logging remain active. Timing includes the four
requests and in-chain response/read-back validation; preparation, startup,
shutdown, post-response drain, network, UI and live-model latency are excluded.
The predeclared gate is P95 signed enabled-minus-disabled overhead <=50 ms.
All signed deltas, stage durations and GC observations remain in the raw report.
This is one plain-text Study exchange, not an attachment/question/live-provider
performance claim; their functional evidence stays separately scoped.

```sh
UV_CACHE_DIR=/tmp/vibe-learner-uv-cache uv run --directory services/ai python -m tests.diagnostic_workflow_probe --workflow study --profile-stages --isolate-samples --samples 30 --output /tmp/diagnostic-study-workflow.json
```

| Population | P50 ms | P95 ms | Max ms |
| --- | ---: | ---: | ---: |
| Enabled | 50.16 | 70.01 | 70.93 |
| Disabled | 47.92 | 51.02 | 79.16 |
| Signed paired delta | 2.28 | 22.07 | 24.87 |
| Enabled post-response drain | 1.26 | 1.26 | 1.26 |

The fixed gate passed. Every enabled sample has 16 correlated events, one new
committed canonical trace, Session revision 1, one Turn at sequence 1 and zero
drop/read/write failure counts after drain. [Raw report](diagnostic-study-workflow-v1.json)
retains every pair and all three source digests. Log:
`/tmp/diagnostic-study-workflow.log`. Existing Persona, Scene, Document/Planning
and both Tavern modes also receive compatibility smokes after adding prerequisite
trace exclusion; those do not replace their archived performance populations.
Remaining native/rendering budgets and final acceptance stay open.
