# Diagnostic workflow overhead v1

`services/ai/tests/diagnostic_workflow_probe.py` measures real ASGI request chains
with the mock provider and temporary application storage. The enabled side uses
normal diagnostic middleware, sink and workers. The disabled control bypasses
only those components; canonical Harness, console logging and Python GC remain
active. This test control is not a production configuration option.

## Method and gate

Three warmup pairs precede 30 measured pairs in alternating mode order. The gate
is P95 of the signed paired enabled-minus-disabled request-chain duration
**at most 50 ms**. Retain negative deltas and outliers; do not subtract independent
population percentiles or GC time. Startup, fixture preparation, shutdown and
post-response queue drain are outside the interval. Queue drain is reported
separately. Network, UI and live-provider latency are outside scope.

Every chain validates full persisted read-back, canonical terminal populations,
flow/action/resource correlation, private-content exclusion and zero dropped
events. Generation-only proposals end `not_applicable`; later saves need separate
read-back. Primary-output commit evidence does not prove every upstream effect.

| Workflow | Measured chain |
| --- | --- |
| `persona` | Generate cards → apply contents to save request → reload Persona |
| `scene` | Generate tree → save Scene Library entry → reload complete tree |
| `document_plan` | Upload text PDF → process stream → reload Document → plan stream → reload Plan |
| `study` | Create Session → chat → reload operation receipt → reload Session |
| `tavern_direct` | Create Room → one-actor turn → reload transcript → reload Run list |
| `tavern_facilitated` | Same chain with three scheduled actors |

Document/Planning streams require committed terminal evidence. Study requires
one new Turn, one revision increment and matching receipt/Session projections;
prerequisite traces are excluded. Tavern verifies contiguous Message sequences,
participant order and one canonical committed trace per actor.

## Reproduction

From the repository root, repeat with the desired workflow name:

```bash
UV_CACHE_DIR=/tmp/vibe-learner-uv-cache uv run --directory services/ai python -m tests.diagnostic_workflow_probe --workflow study --profile-stages --isolate-samples --samples 30 --output /tmp/diagnostic-study-workflow.json
```

`--isolate-samples` creates a new subprocess/app/storage per sample, excluding
process/import/startup time. Omitting it uses repeated applications in one
process. `--profile-stages` records request stages and GC overlaps without
changing GC thresholds or subtracting them from latency. Preserve isolation
mode when comparing results.

## Reference samples

| Workflow / isolation | Enabled P95 ms | Disabled P95 ms | Paired delta P95 ms | Gate | Raw samples |
| --- | ---: | ---: | ---: | --- | --- |
| Persona / shared process | 41.61 | 88.68 | 18.88 | Pass | [Persona](diagnostic-persona-workflow-v1.json) |
| Scene / shared process | 90.86 | 86.71 | 67.74 | Fail | [Scene](diagnostic-scene-workflow-v1.json) |
| Scene / isolated samples | 35.96 | 30.64 | 6.23 | Pass | [Isolated Scene](diagnostic-scene-isolated-v1.json) |
| Document/Planning / isolated samples | 166.37 | 164.27 | 10.92 | Pass | [Document/Planning](diagnostic-document-plan-workflow-v1.json) |
| Study / isolated samples | 70.01 | 51.02 | 22.07 | Pass | [Study](diagnostic-study-workflow-v1.json) |
| Tavern direct / isolated samples | 65.38 | 61.18 | 5.74 | Pass | [Direct](diagnostic-tavern-direct-v1.json) |
| Tavern facilitated / isolated samples | 137.89 | 140.48 | 10.26 | Pass | [Facilitated](diagnostic-tavern-facilitated-v1.json) |

Scene [shared-process stage samples](diagnostic-scene-stages-v1.json) show
request/GC overlap. Isolated samples avoid cross-sample application buildup,
but do not characterize a long-lived server's GC. Both populations and the
original failure remain available; neither justifies a runtime GC workaround.
