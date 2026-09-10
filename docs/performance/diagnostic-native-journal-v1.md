# Native spool after counter journal integration

The [versioned counter protocol](../diagnostic-native-counter.md) integrates the
alternating-slot checkpoint with legacy/pending recovery and old-reader rejection.
The complete native emit probe was run in development and optimized builds, each
with three warmups and 30 samples per case. The same 25 ms successful-emit and
100 ms contention gates, retention count and publication barriers are retained.

| Build / operation | P50 ms | P95 ms | Max ms | Budget ms |
| --- | ---: | ---: | ---: | ---: |
| Development sparse | 8.00 | 9.00 | 9.04 | 25 |
| Development saturated | 18.86 | 20.03 | 21.12 | 25 |
| Development contended | 51.19 | 51.76 | 51.99 | 100 |
| Optimized sparse | 8.16 | 9.97 | 10.01 | 25 |
| Optimized saturated | 17.91 | 20.07 | 20.07 | 25 |
| Optimized contended | 51.11 | 51.83 | 51.85 | 100 |

Both complete gates pass after an actual implementation change. The original
25.21 ms development and 25.06 ms optimized failures remain archived; these results
do not replace them with selected reruns of unchanged code. Each new probe verifies
256 retained events, the exact eviction count, 33 contention refusals and recovery
after releasing the lock. Local samples are not hard filesystem latency bounds;
warmups mean this gate does not separately certify cold migration latency.

Raw [development](diagnostic-native-journal-dev-v1.json) and
[optimized](diagnostic-native-journal-release-v1.json) reports retain all stage and
whole-emit samples. Logs: `/tmp/diagnostic-native-spool-journal-dev.log`,
`/tmp/diagnostic-native-spool-journal-release.log`.

Twenty-two ordinary native tests pass, including migration/crash/downgrade cases
and the existing full spool tests. Twenty Python storage/desktop/directory tests
pass with `drops.alternate` counted as bounded metadata. The real combined
Rust/Python installation pressure probe also passes: 1,200 native event attempts,
11,971 event-DB quota refusals and 174 index quota refusals, followed by reader
release/recovery and integrity checks. These refusals are expected load evidence,
not zero-loss claims. Peak observed file length is 108,814,136 bytes (~103.77 MiB),
not an atomic installation-wide peak or 200 MiB hard cap. The
[full combined report](diagnostic-journal-installation-v1.json) includes native
binary and counter-source digests, all observations and retained gaps.

Logs: `/tmp/diagnostic-counter-final-native-tests.log`,
`/tmp/diagnostic-counter-python-tests.log`, `/tmp/diagnostic-journal-installation.log`.
Full release verification is recorded in the consolidated acceptance checklist.

Final integration gates passed: `npm run check:release` (745 backend tests in
62.758 seconds, shared/Web reliability and types, all 13 Harness suites and
production Web build), 16 actual Chromium cases in 24.2 seconds, and the normal
native build in 5.46 seconds. The native build excludes test-only crash hooks.
Logs: `/tmp/diagnostic-journal-release-gate.log`,
`/tmp/diagnostic-journal-browser.log`, `/tmp/diagnostic-journal-native-build.log`.
The archived full-spool reports also identify the counter and writer source digests.
