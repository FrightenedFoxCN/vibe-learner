# Study operation recovery UX

The browser preserves the existing durable Study admission rules. Recovery reads
the original Session/request identity and never replays a POST or invents a new
key to resolve an ambiguous outcome. Strict receipt decoding and the server's
same-key payload/revision mismatch rejection remain authoritative.

## Wait and query bounds

- A learner or automatic Study POST has a 60-second browser wait limit, including
  response-body decoding. Expiry aborts local transport and moves the UI into
  query-only recovery. It does not cancel or prove failure of server/provider work.
- One operation GET or explicit Session refresh waits at most 15 seconds. A
  query timeout/network/decode error retains identity and pauses background reads;
  it cannot authorize resending. A late response cannot update the expired view.
- After a receipt reports `admitted` or `running`, the mounted view performs at
  most six background GETs, with 2, 4, 8, 15, 30 and 30-second delays between
  completed reads. Reads never overlap. Manual/restore queries are separate.
  Reaching the limit displays a pause explanation and leaves manual query
  available; elapsed time is not evidence that a Turn was not committed.
- `uncertain` is never background-polled or automatically resent. Its text states
  that waiting/reloading cannot prove absence of effects. Manual read-back still
  uses the same operation identity.
- The browser's offline signal pauses reads and explains that the result remains
  unconfirmed. A later online event attempts one GET of the retained identity;
  repeated events/clicks share an in-flight read. Online is a connectivity hint,
  not proof of backend reachability.

The six-query budget belongs to one operation in one mounted recovery view.
Explicitly leaving/re-entering or reloading starts a new bounded recovery visit.
Session transitions and controller unmount cancel timers and fence late results;
navigation that keeps the learning controller mounted retains its bounded
recovery. Neither cancels server work. The local deadline also handles transports that ignore abort by
discarding their late result, without claiming their resources were released.

## Terminal refresh and persistence

Only identity metadata is stored in browser local storage: Session ID, client
request ID, expected revision, message kind and Study Unit ID. No learner message,
attachment bytes, hidden prefix or grading data is added to recovery storage.

An unconfirmed identity uses the existing
`vibe-learner:pending-study-chat-operation:v1` record. A confirmed `not_committed`
outcome retains its identity separately as
`vibe-learner:last-not-committed-study-chat:v1`. On a later visit the browser queries
that operation once to restore the terminal explanation; it does not trust a
locally cached outcome as permission to resend. The new marker is replaced when
a new operation starts, and cannot erase/replace a different pending identity.

For `committed`, the exact pending identity is cleared and the persisted Session
is rendered. An older receipt cannot roll back a newer Session projection. For
`not_committed`, resending is offered only for an explicitly safe receipt and a
retained in-memory learner draft; the resend uses a fresh identity with the same
draft/language choice. After reload, an identity-only record cannot supply the
message or attachments. The UI asks the learner to check the composer and reselect
files. Existing page draft caching remains separate from operation recovery.

An exact operation-not-found 404 or a definite pre-admission rejection requires
Session refresh before a new send. A failed refresh leaves the draft and refresh
action available. Generic network/HTTP/decode errors never count as this proof.
The recovery heading distinguishes a waiting reply, a confirmed unsaved reply and
an unconfirmed result; controls remain keyboard accessible with polite status
announcements.

## Focused verification

`npm --workspace @vibe-learner/web run test:workspace:recovery` covers identity-only
storage, stale response fencing, bounded background queries, offline restoration,
non-overlap, terminal reload and local transport/body deadlines. It uses virtual
timers instead of waiting minutes. Existing Study message tests cover safe fresh
key resend and preservation of the original draft/language.

`npm --workspace @vibe-learner/web run test:workspace:recovery:live` starts a real
temporary SQLite/FastAPI mock backend and the development frontend. Test-only
loopback controls hold one provider callback, reject a complete reply, or inject
an ambiguous outcome. The browser clock advances independently of the backend
clock. The adversarial paths check:

- browser POST timeout while the actual operation is still `running`;
- six-query pause, later real commit, manual read-back and terminal reload;
- offline/reconnect and uncertain reload with one original learner POST/provider
  callback, plus actual same-key changed-payload HTTP 409;
- confirmed `not_committed` reload with no automatic resend.

Fault routes exist only in the disposable acceptance server under `tests/`.
They are absent from the production router. These cases do not call a real model,
run a production Web build, or certify native/offline cold-load behavior. Device
and live-provider acceptance remains tracked in the corresponding TODO items.
