# Populated resource-read boundaries v1

`populated-resource-reads-v1` measures browser API request counts and ordering,
not production load time or bundle size. It uses historical Room/Run data and a
saved Learning Plan rather than the empty-library initial-route fixture.

## Reproduction and evidence

```bash
npm --workspace @vibe-learner/web run test:resources:live
```

This starts the Next development frontend and the existing disposable
SQLite/mock Tavern acceptance backend on loopback ports 3437/18447. Each case
creates two synthetic personas, a Room with one completed facilitated Run, and
one saved Learning Plan through the real API. No provider is contacted. Browser
routes only delay real HTTP responses or discard one already-committed response;
they never invent a response DTO.

The checked-in [raw request evidence](web-resource-reads-v1.json) includes each
request's phase, method, URL path, monotonic start/end time, HTTP status/failure,
the fixture identities and source-file digests. `before` was recorded against
production code at `9ae0a45`; `after` uses the implementation digests in the file.
Times are observation data; no latency improvement is inferred from these
artificial delays. Measurement used macOS 27.0.1 arm64, Node 26.12.1, Python
3.13.5, Chromium 153 and the development frontend.

Full rerun reports and attachments are written under
`/tmp/vibe-resource-requests-after/` with
`/tmp/vibe-resource-requests-after-report.json`. The optional
`WEB_DEDUPE_PHASE=before` changes the artifact namespace and disables the new
count assertions to capture the historical implementation; it does not change
application behavior. To reproduce the old counts, run the probe against the
named base implementation.

## Observed before/after

One sample of each scripted path is retained per implementation. This is a
deterministic structural check, not a statistical timing benchmark.

| Scripted path | Before | After | v1 boundary |
| --- | ---: | ---: | --- |
| Eight concurrent focus events: Documents | 8 GETs | 1 GET | 1 in-flight snapshot read |
| Eight concurrent focus events: Plans | 8 GETs | 1 GET | 1 in-flight snapshot read |
| Eight concurrent focus events: Personas | 8 GETs | 1 GET | 1 in-flight library read |
| Eight concurrent focus events: Scenes | 8 GETs | 1 GET | 1 in-flight library read |
| Return from Tavern to Plan with focus during initialization: Documents/Plans/Scenes | 10 each | 2 each | At most 2 per resource in this dev-mode remount path |
| The same return path: Personas | 18 | 2 | At most 2; no extra library read while a snapshot already loads Personas |
| Plan → Study shared-owner navigation | 0 collection GETs | 0 | No remount-driven Document/Plan/Persona/Scene reads |
| Eight Tavern focus events with historical Room/Run | 0 reads | 0 | Learning owner's listener is gone; Tavern adds no focus loop |
| 900ms Tavern poll with 1400ms actual response delay | Max 1 in-flight poll | Max 1 | Never overlap foreground polls |
| Lost turn response after real commit | 1 new Room tail, 1 lineage read and 1 Room-list read | Same | Fresh authoritative read-back is required |
| Run reads begun after the lost response | 2 | 1 | Stop old foreground discovery when handing off to fresh read-back |
| Lost-response case actor execution | 2 callbacks, 1 learner POST | Same | No historical/current turn replay |

The two collection reads on return are the development lifecycle replay, which
deactivates/reactivates the owner. A new owner never shares a projection ticket
with an invalidated lifetime. This bound is scoped to this fixture; it does not
replace the separate production route inventory or certify a production timing
budget.

The baseline lost-response phase showed a new foreground poll beginning while
the fresh recovery Run read was still in flight. That poll was redundant. The
foreground operation now releases its discovery ownership when a terminal
response arrives or recovery takes over, and the interval checks ownership before
issuing another request. An already-issued old poll can still finish, but cannot
replace the fresh read-back. Sharing that older pending response with recovery
would instead risk returning the wrong state.

## Implementation policy

`WorkspaceSnapshotLoader.loadOnFocus()` joins an owned in-flight snapshot. Its
existing `load()` remains the explicit fresh-read path; it increments the
projection ticket and fences older results. Settlement, failure and deactivation
remove the coalescing entry. Completed values are not cached, so a later focus
still revalidates. If the snapshot already includes Personas, the library path
does not issue a second focus read of the same resource.

`useWorkspaceLibraries` supports opt-in in-flight reuse for focus refreshes.
Explicit refresh and Persona change/storage events start new reads. The existing
sequence guard still rejects late values. A newer library-owned Persona update
also fences the Persona slice of an older mixed snapshot while allowing that
snapshot's Documents and Plans to finish. Callbacks use the mounted owner and
current selections; unmount retires read identities/listeners.

Tavern retains single-in-flight polling, mutation/version fencing, terminal
monotonicity and separate lineage read-back. Discovery stops before the terminal
or ambiguous-response handoff; the required fresh reads are preserved. The
performance fixture checks these boundaries alongside the focus optimization
instead of applying a global URL cache across domain operations.

Focused verification uses the snapshot-loader and workspace-library modules,
their existing failure/selection/unmount cases, and the two real-backend browser
paths. Production builds, full test suites, real-provider latency and platform
acceptance are separate work.
