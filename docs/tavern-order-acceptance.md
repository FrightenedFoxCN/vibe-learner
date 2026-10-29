# Tavern facilitated-order acceptance

This focused check exercises the real browser, current strict decoders and the
production FastAPI/Tavern repositories against temporary SQLite. It covers
reverse target selection, restoration of a generating Room and a partial-run
child retry after the user changes the next round's targets.

## Reproduction

```bash
npm --workspace @vibe-learner/web run test:tavern:order:live
```

The command starts the development frontend on `127.0.0.1:3437` and a disposable
mock backend on `127.0.0.1:18447`. The backend's test-only controls hold a named
actor or fail it once. They live under `tests/acceptance/` and do not enter the
production router. Actor generation still crosses the production admission,
protected snapshot, Harness validation, per-actor commit, lineage and retry
boundaries. There are no intercepted API responses or live-provider calls.

Playwright writes the report to `/tmp/vibe-tavern-order-report.json`, raw
Room/Run/Step/Message/callback evidence under `/tmp/vibe-tavern-order-browser/`,
and the active-retry screenshot to `/tmp/vibe-tavern-order-active-retry.png`.
All fixture messages and personas are synthetic; the SQLite directory is removed
when the server exits.

## Observed matrix

The 2026-10-29 run used macOS 27.0.1 arm64, Node 26.12.1, Python 3.13.5, Chromium,
the Next development frontend and the local mock provider. Personas are created
as Alpha, Bravo, Charlie, then the Room roster is deliberately ordered Bravo,
Charlie, Alpha. The browser selects targets in reverse roster order, Alpha,
Charlie, Bravo. This separates persona creation, display and click order.

| Path | Browser and server evidence |
| --- | --- |
| Reverse selection | Preview and roster show Bravo → Charlie → Alpha; server `scheduled_participant_ids` and Speaker Steps use the same order |
| Reload during first actor | Bravo is held after entering the provider boundary; reload restores the pending operation and display-order preview rather than starting a new turn |
| Complete restored run | Exactly three actor callbacks, Bravo → Charlie → Alpha; one user Message and three persona Messages with sequences 1–4; terminal roster shows previous-round replies |
| Middle actor fails once | Root is `partial`; steps are completed/failed/blocked for Bravo/Charlie/Alpha; Bravo's committed Message is retained |
| Retarget before retry | User selects only Bravo for the next round; retry still schedules Charlie → Alpha, with a new child bound to the original root |
| Active retry display | Preview follows the in-flight child; Bravo stays selected but is marked “下轮目标”, Charlie generates and Alpha waits |
| Retry commit and reload | Child completes both unfinished steps; the Message chain is Bravo → Charlie → Alpha; Bravo's original Message ID is unchanged; recovered callout suppresses another retry |

The partial-case callback list is Bravo, Charlie (injected failure), Charlie,
Alpha. There is no second Bravo callback and no extra user Message. Reply anchors
link Charlie to the saved Bravo Message and Alpha to the committed Charlie
Message. Raw evidence records the actual IDs and server projections for these
assertions.

## Finding and fix

Before the fix, the actual child correctly ran Charlie → Alpha while Interaction
Composer still displayed the newly selected Bravo. The black-box browser check
failed on that mismatch. The frontend now derives active reply recipients from
the pending server Run schedule, falling back to the foreground operation's
targets until admission is visible. The Composer orders those recipients by the
room roster. In-flight targets do not overwrite the next-round selection; an
idle selected participant outside the current schedule is labeled accordingly.
Once the operation settles, the preview returns to the selected next-round set.

The server target-set contract, operation identity, child scope and participant
snapshots are unchanged. Existing controller/panel regressions plus the two
focused panel cases pass; type/style gates pass. The two real-backend browser
paths passed after the fix. This is a scoped browser/runtime acceptance, not a
live-provider quality, native-device, IME, transport-cancellation or cross-platform
certification; those retain their separate backlog scope.
