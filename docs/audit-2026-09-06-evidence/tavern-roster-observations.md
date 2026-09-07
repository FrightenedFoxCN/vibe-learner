# Tavern roster audit evidence — 2026-09-05

This directory summarizes two independently executed reproductions from the
audit session. The Python snippets were run inline and were not saved at the
time. This is a transcription of the steps and observed results, **not a raw
log file**. No test has been rerun to create this evidence document.

## Isolation and verification method

- Working directory: `/Users/ffox/vibe-learner/services/ai`.
- Execution: `UV_CACHE_DIR=/tmp/vibe-learner-uv-cache uv run python -` with inline Python.
- Fixture: `tests.test_tavern_api.TavernApiTests`; `setUp()` creates a new
  `TemporaryDirectory`, SQLite database, storage, Persona engine, Tavern
  service, and FastAPI `TestClient`.
- Provider: repository `MockModelProvider`.
- Every fixture was disposed with `tearDown()` in `finally`.
- No user database or actual model provider was used. No source files were edited.
- Fixture import printed an incidental LiteLLM price-map download warning;
  LiteLLM used its bundled fallback. The Tavern generation itself used Mock.

## Reproduction A: a successful roster update invalidates historical commit read-back

1. Instantiate `TavernApiTests`, call `setUp()`.
2. Create a Room containing fixture Persona A via
   `case._create_room(creation_key='audit-roster-change-1')`.
3. POST `/tavern/rooms/{room_id}/turns`:

   ```json
   {
     "input": {"kind": "user_message", "content": "你好"},
     "mode": "direct",
     "target_persona_ids": ["<Persona A ID>"],
     "guidance": "",
     "idempotency_key": "audit-turn-roster-1",
     "expected_room_revision": 0
   }
   ```

4. Read the generated Message using
   `case.repository.get_actor_commit_read_back(message_id=message_id)`.
   Pass its Message, Run, Step, Participants, and anchor into
   `build_tavern_persona_message_committed_projection`. This passes.
5. Create replacement Persona B using `case.persona_engine.create_persona`
   and `CreatePersonaRequest(name='新角色', summary='审计替换角色',
   relationship='同行者', learner_address='你', system_prompt='正常对话', slots=[])`.
6. PATCH `/tavern/rooms/{room_id}`:

   ```json
   {"persona_ids": ["<Persona B ID>"], "expected_revision": 1}
   ```

7. GET the Room; repeat step 4 against the original Message.

Observed result lines from the successful inline execution:

```text
turn_status 200 completed
before_roster_update_commit_projection valid
roster_update_status 200
messages_remain 2
after_roster_update_commit_projection tavern_commit_persona_not_in_room
```

The process exited successfully; the final `ValueError` was caught to print
its exact message. The legitimate roster mutation retained historical
Messages but removed the Participant snapshot required to validate them.

## Reproduction B: Continue after the roster replacement returns HTTP 500

1. Set up a fresh fixture and create a one-Persona Room using creation key
   `audit-continue-creation-2`.
2. POST a direct `你好` user turn to Persona A with idempotency key
   `audit-continue-turn-3` and expected revision `0`; save the returned
   generated Message ID as `anchor`.
3. Create Persona B with the same fields described in reproduction A.
4. PATCH the Room to `[B]`, expected revision `1`.
5. Use `TestClient(case.client.app, raise_server_exceptions=False)` to POST
   `/tavern/rooms/{room_id}/turns`:

   ```json
   {
     "input": {"kind": "continue", "anchor_message_id": "<anchor>"},
     "mode": "direct",
     "target_persona_ids": ["<Persona B ID>"],
     "idempotency_key": "audit-continue-turn-4",
     "expected_room_revision": 2
   }
   ```

6. Inspect the latest persisted Run via `case.service.list_runs(room_id)[0]`.

Observed result lines from the successful inline execution:

```text
roster_update_status 200
continue_status 500 Internal Server Error
latest_run_status failed
latest_run_error tavern_commit_addressed_participant_not_in_room
new_messages 0
```

An earlier execution with the default TestClient exception behavior raised
the same `ValueError` through `TavernService._execute_run` →
`TavernRepository.complete_step` → `commit_runtime` →
`build_tavern_persona_message_committed_projection`. The second execution
above made the external HTTP response explicit and verified the persisted
failure outcome.

## Relevant implementation locations

- `/Users/ffox/vibe-learner/services/ai/app/persistence/tavern_repository.py:1324`
  deletes all current Room Participant rows, then reinserts the updated roster.
- `/Users/ffox/vibe-learner/services/ai/app/persistence/tavern_repository.py:1230`
  reads current Room Participants to validate a historical actor commit.
- `/Users/ffox/vibe-learner/services/ai/app/models/tavern.py:283`
  requires the historical Message's Persona in that current Participant map.
- `/Users/ffox/vibe-learner/services/ai/app/services/tavern.py:730`
  derives Continue's required target from the old anchor's Persona, even when
  that Persona has been removed from the Room.
- `/Users/ffox/vibe-learner/services/ai/app/models/tavern.py:344`
  rejects the generated Message's addressed participant when it is absent
  from the Room.

## Scope and interpretation

This verifies the exposed roster PATCH API and the authoritative commit
boundary. It does not claim that the browser currently exposes a roster
replacement control; broader Room management remains backlog work. The
historical-evidence failure and Continue failure share the destructive roster
replacement root cause and should be reported as one finding.
