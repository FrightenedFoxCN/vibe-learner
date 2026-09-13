# M3 Planning held-out workload review — 2026-09-13

## Scope

The user explicitly authorized external testing of full-book-derived Planning context against the official MiniMax endpoint `https://api.minimax.cn/v1`. The probe parsed each PDF locally and sent the initial Planning context plus model-requested text tool results; it did not upload the PDF binary. Credentials and local reasoning were excluded from the report.

Held-out sources:

- Walter Rudin, *Fourier Analysis on Groups* (298 physical PDF pages)
- Ralph Hexter and David Townsend, eds., *The Oxford Handbook of Medieval Latin Literature* (681 pages)
- Joël Dor, *Clinical Lacan* in Chinese translation (141 pages)

All user-unspecified Planning intent fields remained `{status: "unknown", value: null}`. Concrete choices were recorded only in `resolved_planning_intent` with `source=model_inferred`.

## Baseline results

| Source | Boundary | Calls | Tokens | Time | Model-selected scope | Quality review |
| --- | ---: | ---: | ---: | ---: | --- | --- |
| Fourier | pass | 2 | 20,652 | 87.6 s | pp. 13–17, 3 × 35 min | Visually grounded in Chapter 1, §1.1 Haar measure and convolution; workload is plausible. |
| Medieval Latin | mechanical pass | 2 | 29,245 | 84.1 s | pp. 14–432 and 655–663, 6 × 90 min | Five learn sessions assign 46–110 pages each without explaining selection or overview. The old gate missed this. |
| Clinical Lacan | mechanical pass | 2 | 31,965 | 58.1 s | pp. 1–31, 4 × 25 min | One learn session assigns 10 pages and one review assigns 31 pages without an explicit tradeoff. The old gate missed this. |

The Medieval Latin boundary pages were visually checked: p.14 starts “The Current Questions and Future Prospects of Medieval Latin Studies”; p.59 ends the “Canonicity” bibliography; p.60 starts “Latin as an Acquired Language”; p.169 ends “The Idea of Latinity”; and p.170 starts “Readers and Manuscripts”. The proposed structure was source-aligned, but the per-session workload was not credible as complete study.

## Implemented boundary

Production Planning now uses `LearningPlanProposalV3` and `LearningPlanPrompt@planning-prompt-v6`.

Each schedule item carries:

- `coverage_mode`: `complete`, `selective`, or `overview`
- `workload_rationale`: persisted learner-visible explanation

The application computes distinct physical pages per session. A conservative baseline is three minutes per page for `learn` and one minute per page for `review`. Exceeding the baseline is allowed, but only with `selective` or `overview` plus a rationale of at least 40 characters. The prompt requires the rationale to explain the pedagogical reason, compressed or omitted scope, and follow-up path. This is an auditability boundary, not an assertion that the rationale is pedagogically correct.

The fields are preserved through the provider projection, committed Plan record, API decoder, shared TypeScript contract, and Plan Overview Panel. Historical proposal v2 remains decode-only compatible.

## Live v3 result

The successful Clinical Lacan v3 run committed with exact read-back equality:

- 4 sessions × 25 minutes, Chinese output
- original page and outline intent remained `unknown`
- resolved scope was pp. 16–41 with `model_inferred` provenance
- 2 provider calls, 4 tool calls, 51,479 tokens, 88.3 seconds
- no schema repair
- sessions 1, 2, and 4 used `complete`
- session 3 used `selective`, narrowed a ten-page chapter anchor to an eight-page reading slice, and supplied a 125-character rationale explaining the time constraint, deferred pages, and follow-up session

The probe option requesting finalization after one tool round was recorded but did not apply an intervention: the production runner had already removed tools and requested a JSON object for the final round.

Compared with the older Clinical Lacan run, token use increased by about 61% and elapsed time by about 52%. The additional source reads and Study Unit revision improved plan structure, but cost remains high.

## Residual findings

Visual review of every cited Clinical Lacan page 16–41 found two remaining quality defects:

1. The revised first Study Unit spans pp. 16–23, although p.16 is a table-of-contents page and pp.17–18 are the preface; the first chapter starts on p.19. The schedule therefore retains a coarse boundary despite correctly focusing on Chapter 1.
2. The selective rationale described pp.40–41 as discussion of the real, imaginary, and symbolic father, although those pages were not read by the tool and the rendered pages do not support that description. The rationale itself became a hallucination surface.

The prompt was tightened after this review: workload rationale may explain only scheduling mechanics and verified content. Unread pages must be described generically as unverified remaining pages by physical range, without predicting their concepts, arguments, or examples. This final wording has deterministic coverage but has not yet received another live-provider confirmation.

Two additional v3 attempts demonstrate a separate latency risk:

- Medieval Latin: 190.7 seconds, 36,355 observed tokens, provider/Harness wall-time exhaustion, operation `uncertain`, no committed plan.
- Clinical Lacan: 202.0 seconds, one completed 10,175-token tool round followed by provider/Harness wall-time exhaustion, operation `uncertain`, no committed plan.

## Verification

- 43 targeted Planning, workload-probe, contract, and limit tests passed.
- Planning frontend decoder tests passed.
- Repository Web reliability suite passed.
- All ten Harness stage regression suites passed; Planning ran 8 cases.
- Full backend suite passed all 913 tests after updating the expected Planning runtime DTO digest.
