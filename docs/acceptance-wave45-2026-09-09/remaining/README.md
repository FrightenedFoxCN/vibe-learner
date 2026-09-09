# Follow-up after checkpoint 6d9ce05

This is ongoing remediation evidence, not a Wave 4/5 acceptance certificate.
The checkpoint is committed locally; it has not been pushed. The pre-existing
desktop icon modification is outside that commit.

## Implemented and checked

- Persona slot local fallback is idempotent, preserves locked fields, and leaves
  unsupported custom/Scene content unchanged. Whole-setting fallback preserves
  every original slot instead of merging away biography fields.
- Persona/Scene response recovery records now survive default empty response
  lists. Their normal editors show an explicit local-fallback notice.
- Slot schema failures now participate in the existing single structured retry;
  at most two provider requests are issued. Current structured retries are
  reflected as repaired v3 traces, without inheriting an earlier request's records.
- Study catalog/schema drift fails before claim or staging and yields
  `not_committed`. Public fault injection proves zero provider calls and no
  Session revision change. Issued timeouts/network failures remain `uncertain`.
  This does not reclassify arbitrary post-claim exceptions as safe to retry.
- Parser substage wall times are measured at their actual work boundaries.
  Page extraction includes OCR and page normalization; its time must not be
  added to OCR time as independent work. Section timing sums TOC lookup and
  final section selection, with one stage attempt. OCR attempts count pages
  actually sent to OCR. Skipped/uninstrumented work retains unknown metrics.
- Actual macOS OCR exposed a CoreML graph-compilation failure. Initialization
  now makes one CPU retry with the same models and reports `onnxtr_cpu_fallback`.
  A CPU failure stays unavailable; no unbounded retry is added.

## Evidence

- `release.log`: shared/type/frontend/eval/Web build and 538 backend tests passed
  before the final OCR/recovery changes.
- `backend-final.log`: 542 backend tests passed after those changes.
- `targeted-final.log`: 19 targeted boundary tests passed.
- `ocr-run.log` and `ocr-run-native.log`: historical sandbox/CoreML failures.
- `ocr-result.json`: a real two-page image-only English two-column PDF processed
  with local ONNX OCR; both pages recovered, all eight anchor terms found,
  about 4.2 seconds total in the latest run. This is not a multilingual or maximum-size gate.
- `m3-slot-before-trace-fix.json`: three newly authored synthetic long-slot M3
  samples, four provider calls, one structured retry; records the discovered
  incorrect passed trace classification rather than rewriting history.
- `m3-slot-result.json`: three additional synthetic samples after trace repair,
  each passed in one provider call. Deterministic injection separately verifies
  repaired classification; these three live samples did not require retry.
- `desktop-build-final.log`: signed macOS app bundle built and installed.

The original historical-slot outbound replay was rejected by automatic approval
review as an insufficiently authorized private payload. The subsequent M3 runs
use only newly authored synthetic text embedded in the script and never read
the historical persona. API credentials are read from the environment and are
not written into these artifacts. The original exact-input replay remains open.

## Still open

- Ten stages still lack registered eval suites and independently reviewed
  held-out quality/replay coverage. Unit tests and live smoke samples do not
  substitute for those suites.
- Fill-blank semantic grading and persona relationship grounding need reviewed
  quality criteria; no global synonym substitution or semantic-success claim
  has been introduced.
- Broader failure, browser recovery, maximum input and deletion
  combinations still require their respective recorded acceptance cases.
- PostgreSQL is not currently running (the local Docker daemon socket is
  unavailable). Other-platform acceptance and actual provider billing evidence
  are not available in this macOS run.
- Tavern maximum combinations and representative configurations remain open;
  the measured fixture uses six participants and at most four targets per run.
  The post-fix 30 scheduled steps include an upstream 529 and are not an all-pass gate.

No open item above is closed merely by adding this report.

## Further live and desktop results

- Native JSON export now uses a Tauri save dialog and a bounded JSON writer;
  the browser retains its download path. The renderer cannot supply an output
  path. Both imports reject files larger than 8 MiB.
- Persona import is a keyboard/accessibility-visible button. Actual native
  export → file import → export preserved all five builtin Aurora slots and
  every exported field (`persona-roundtrip.json`). This checks the editor, not
  a new database save.
- Scene native export → import → export preserved two layers and six objects
  (`scene-roundtrip.json`). A structurally invalid JSON file was rejected with
  a visible error. Export afterward remained equal except exportedAt
  (`scene-invalid-import.json`). File validation bounds depth/layers/objects/text;
  unfinished local drafts retain their separate permissive restore behavior.
- Native Persona and Scene editors displayed the local-fallback warning during
  a deliberately unreachable setting-provider test. Original settings were
  restored; no historical private persona was sent by that test.
- Tavern M3 before prompt repair: 30 scheduled steps, 21 completed, 3 failed,
  6 blocked; 36 provider requests; 12 passed and 9 repaired successful traces.
  Diagnostic synthetic replies revealed copying the schema rather than producing
  a reply instance. The prompt now explicitly distinguishes those two.
- After prompt repair: 30 scheduled steps, 28 completed, 1 failed on actual
  upstream 529, 1 blocked; 29 requests, zero schema repair retries, 456051
  reported usage tokens. Empirical request p50/p95: 6981/20169 ms. Billed cost
  remains unknown. `tavern-after-prompt-fix.json` truthfully retains passed=false.
- A separate real M3 scoped-child-retry test injected a pre-request failure after
  the first actor committed. Only the failed/blocked actors ran in the child;
  the first message remained unchanged and idempotent replay added zero calls
  (`tavern-retry-result.json`). It does not replay the original 529 request.
- Deterministic fill-blank mismatch feedback now says it did not match the
  predefined answers. Authoring instructions require objective finite answers,
  explicit formatting and question-specific alternatives. This is not a semantic
  grader; the broader grading-quality gate remains open. `grading-tests.log`
  records 18 passing targeted cases.
- `release-latest.log` records the full release check before the final grading
  wording change (542 backend tests); later targeted grading tests passed.
- Desktop lock testing exposed a missing Stronghold unload ACL. Plugin 2.3.1
  `destroy` saves the encrypted snapshot and unloads memory; it does not delete
  the file. Only `stronghold:allow-destroy` is being added. Automatic review
  rejected a wider change including record removal; that permission was removed
  and the narrower build was approved. Native unlock → lock passed. The UI showed locked and read-back reported all
  four runtime secret flags false. Original gemini model settings remained.
  `desktop-delivery.json` records the final installed bundle and 543-test release
  gate (`release-delivery.log`); codesign deep/strict verification passed.

These regression/live cases are not independently reviewed held-out eval suites.
Prompt/component version migration must preserve historical trace decoding and
reviewed baselines; changing the prompt text alone does not close that gate.
