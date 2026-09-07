# Study chapter switching triggers unbounded requests on ordinary and deep-link routes: audit evidence

Observed through the root agent browser walkthrough, independently counted from backend.log. No server mutation or repeat reproduction was performed for this analysis.

## Measured event

- Session: session-bb8c1558f4.
- Request starts: 2026-09-05 23:50:11.366 through 23:50:56.565, log-local time, a 45.199 second window.
- 7,135 unique structured request.start IDs for PATCH /study-sessions/session-bb8c1558f4.
- 7,135 matching request.end records: 7,123 HTTP 200; 12 HTTP 409.
- Average 157.86 starts/second; maximum 182 starts in the wall-clock second 23:50:32.
- Uvicorn access lines were excluded to avoid double/triple counting.
- At 23:50:11.842, a concurrent automatic Study prelude operation became uncertain with study_chat_committed_session_revision_mismatch. This is a logged secondary failure, not a guessed cause of the request storm.

## Independent ordinary-route control

The root agent separately opened ordinary /study with no query parameters, created a Lyra Session for plan B, successfully exchanged ordinary chat, and then selected schedule-2. The same request storm occurred. Therefore the primary P1 finding covers ordinary chapter switching; it does not require a deep link. The persistent URL selection is a separate confirmed navigation defect.

- Session: session-5c6f98dd49.
- PATCH starts: 2026-09-05 23:53:21.377 through 23:56:28.961, log-local time, 187.584 seconds.
- 29,785 unique PATCH requests: 29,714 HTTP 200 and 71 HTTP 409.
- Average 158.78 PATCH starts/second; peak 186 in one wall-clock second.
- This Session also has 20,477 POST /chat requests: three HTTP 200 and 20,474 HTTP 409. The first two start at 23:52:50.763/23:52:51.047, before the chapter switch; the later burst begins at 23:56:29.081 and ends at 23:57:55.818.
- Thus the log shows a second HTTP 409 chat-request storm after the PATCH storm. It does not show 20,477 provider executions; admission rejections must not be described as model calls or billable usage.
- The global controller's automatic prelude path is an independently visible source-level retry-loop risk: use-learning-workspace-controller.ts:2010-2026 re-runs on isBusy changes; runSessionPrelude :1552 sets busy true and :1581-1583 unconditionally removes the in-flight key and sets busy false after failure. An unprepared Session and immediate HTTP 409 can therefore retrigger indefinitely, including on another route because the controller lives in the root Provider. Logs contain no POST bodies, so attribution of every observed chat POST to this path remains code-supported rather than body-verified.

## Source mechanism

1. apps/web/components/study-dialog-page.tsx:129-141 calls handleSwitchSection directly during navigateToSchedule. The page also has a second automatic synchronization path at :339-349 whenever currentStudyUnitId differs from the persisted Session unit.
2. A normal selection already creates a client/server unit mismatch while the request is in flight, which is sufficient to trigger the synchronization effect. Separately, the URL effect at :247-260 retains requestedScheduleId indefinitely: on a schedule-1 deep link it also restores schedule-1 after selecting schedule-2.
3. The synchronization effect includes handleSwitchSection in its dependencies (:345). apps/web/hooks/use-learning-workspace-controller.ts:1496 defines that callback as a fresh async function on every render, rather than a stable callback.
4. Each invocation synchronously dispatches busy_started (:1498). The reducer always creates a new state object for that action, even when isBusy is already true (apps/web/lib/learning-workspace-reducer.ts:121-125). This produces another render, another callback identity, and another synchronization effect while the unit mismatch remains.
5. No single-flight/in-flight guard or busy guard exists in the synchronization effect or handleSwitchSection. The same Session target is repeatedly PATCHed at use-learning-workspace-controller.ts:1357-1361.
6. Repeated ensureSessionForSection calls invoke transitionStudyView (:1324-1333) while the persisted ref still has the old unit. StudyAsyncViewFence.transition increments viewRevision unconditionally (apps/web/lib/async-result-fence.ts:160-165). The previous PATCH result is then rejected by the viewRevision equality check (:1364-1368) before activateStudySessionView/study_session_set. This can keep the client mismatch alive even after the server has accepted updates.
7. finally dispatches busy_finished (:1527-1528), producing further renders. The boolean busy state is not a concurrency counter and cannot prevent overlap.

The primary failure is an unbounded effect/request feedback loop during ordinary chapter synchronization. Deep-link pinning is a separate issue; memoizing only the callback would not by itself resolve contradictory URL state or duplicate synchronization paths. The post-switch automatic-prelude failure path also requires bounded admission recovery.

## Evidence limits

The backend log does not include PATCH bodies. It proves request counts, timing, status codes, and the secondary Chat exception; it cannot independently establish the exact sequence of study_unit_id values or prove why the browser showed Cannot reach AI service. That text was observed by the root agent, and browser transport failure should not be represented as a server outage based on this log.

Recommended closure evidence: a browser test enters a real plan deep link, switches chapters while responses are delayed, and asserts bounded requests, the requested final chapter, persisted read-back, no automatic replay storm, and no unexpected Chat uncertainty.
