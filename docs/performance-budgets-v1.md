# Performance Budgets v1

## Status and scope

This is the versioned release budget for focused performance work. A TODO that
depends on this document must record its fixture, benchmark environment, raw
sample artifact, and before/after result. A faster developer machine does not
authorize silently weakening the data-shape or query-count gates.

The first registered scenario is `tavern-room-list-v1`. It covers room-history
pagination only; the selected Room detail and retry-chain authoritative view are
separate reads and must not be reconstructed from a paged summary list.

## Reference environment

- Apple M4 MacBook Air, 10 cores, 16 GB RAM;
- macOS 26.6.1;
- Node.js 26.7.0;
- uv 0.12.3;
- production Next.js build for payload and server integration checks;
- React profiling build (`react-dom/profiling`) for the render-duration gate;
- FastAPI with local SQLite on the same machine;
- mock provider, no network/model calls;
- no debug profiler or coverage instrumentation during timing.

CI may use a different named environment. It must preserve the absolute shape,
query, and payload gates below. Timing results from a slower environment are
reported separately and do not overwrite this v1 reference without a reviewed
budget-version change.

## `tavern-room-list-v1`

### Fixture

- fixture generator contract `tavern-room-list-fixture-v1`, seed
  `vibe-learner-tavern-1000-v1`, stored with the implementation benchmark;
- 1,000 Tavern Rooms with deterministic 24-character IDs;
- Room timestamps form deterministic 7-Room equal-`updated_at` groups. Both the
  30-item and 50-item page boundaries split such a group, so the Room-ID
  tie-breaker is exercised across pages;
- 1–6 Participants per Room, including the six-participant worst case;
- message counts large enough to exercise aggregation without loading Message
  bodies;
- every Room title is exactly 64 Unicode scalar values; every Persona ID is 24
  ASCII characters and every participant display name is exactly 48 Unicode
  scalar values. The maximum-page payload sample uses six Participants for all
  50 Rooms;
- stable order `(updated_at DESC, id DESC)`;
- default page size 30, hard maximum 50.

### Gates

| Measure | v1 release gate |
| --- | ---: |
| SQL statements per page | at most 4 |
| Uncompressed JSON payload, 30-item default page | at most 192 KiB |
| Uncompressed JSON payload, 50-item maximum page | at most 320 KiB |
| Warm server response P95, 30-item page | at most 100 ms |
| Warm server response P95, 50-item page | at most 120 ms |
| React commit `actualDuration` P95, append 30 summaries | at most 50 ms |
| Rendered Room summary buttons retained in the DOM | at most 100 |

Cursor values bind both sort fields. Equal timestamps are resolved by Room ID,
and pages must contain no duplicate or skipped Room. Changing a Room's sort key
during traversal may move it between snapshots; the client must keep the
currently selected Room visible from its authoritative detail even when its
summary is outside loaded pages.

### Measurement protocol

1. Build the production frontend and create a fresh local SQLite fixture.
2. Warm the endpoint and UI five times without recording samples.
3. Record at least 50 server samples for the first, middle, and final pages at
   both page sizes. Count SQL statements through the database instrumentation,
   and measure serialized response bytes before compression.
4. Record at least 30 React Profiler commits while appending a default page to a
   list near the beginning, middle, and end of the fixture.
5. Store machine-readable raw samples with the implementation change. Report
   P50/P95, maximum, sample count, commit SHA, environment, and fixture seed.
6. Fail the gate if any structural limit is exceeded or any P95 timing exceeds
   its threshold. Do not discard slow samples except for a documented benchmark
   process failure.

## Changing a budget

Budget changes require a new document version, code/evidence showing why the old
gate is no longer representative, and independent review. An implementation
regression is not a reason to edit the budget in place.
