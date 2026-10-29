import { dom } from "./support/dom.js";
import assert from "node:assert/strict";
import { after, afterEach, test } from "node:test";
import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { useTavernWorkspaceController } from "../hooks/use-tavern-workspace-controller.ts";
import {
  deferred,
  detail,
  environment,
  message,
  run,
  turnResult,
} from "./support/tavern-controller.js";

afterEach(cleanup);
after(() => dom.window.close());
async function fixture(env = environment()) {
  const view = renderHook(() => useTavernWorkspaceController(env.ports));
  await waitFor(() => assert.equal(view.result.current.activeRoom?.id, "room-a"));
  await waitFor(() => assert.equal(view.result.current.busyAction, null));
  return { ...view, ...env };
}

test("bootstrap reads libraries once and switching rooms fences late room loads", async () => {
  const h = await fixture();
  assert.equal(h.calls.filter((c) => c.name === "listPersonas").length, 1);
  assert.equal(h.calls.filter((c) => c.name === "listSceneLibrary").length, 1);
  const pending = deferred();
  h.handlers.getTavernRoom = ({ roomId }) =>
    roomId === "room-b" ? pending.promise : h.data.rooms.get(roomId);
  let old;
  act(() => {
    old = h.result.current.openRoom("room-b");
  });
  await act(async () => {
    await h.result.current.openRoom("room-a");
  });
  await act(async () => {
    pending.resolve(detail("room-b"));
    await old;
  });
  assert.equal(h.result.current.activeRoom.id, "room-a");
  assert.equal(h.remembered.at(-1), "room-a");
});

test("history paging deduplicates one cursor and ignores its response after refresh", async () => {
  const env = environment();
  env.data.cursor = "next";
  const h = await fixture(env),
    pending = deferred();
  h.handlers.listTavernRooms = (args) =>
    args.cursor ? pending.promise : { items: [], nextCursor: null };
  let loading;
  act(() => {
    loading = h.result.current.loadMoreRooms();
  });
  await act(async () => {
    await h.result.current.loadMoreRooms();
  });
  assert.equal(
    h.calls.filter((c) => c.name === "listTavernRooms" && c.args[0].cursor).length,
    1,
  );
  await act(async () => {
    await h.result.current.refreshRoom();
  });
  await act(async () => {
    pending.resolve({
      items: [{ ...h.data.rooms.get("room-b").room }],
      nextCursor: "later",
    });
    await loading;
  });
  assert.deepEqual(h.result.current.rooms, []);
  assert.equal(h.result.current.nextRoomCursor, null);
  assert.equal(h.result.current.loadingMoreRooms, false);
});

test("older messages block a competing submit and preserve the latest tail", async () => {
  const h = await fixture(),
    pending = deferred();
  h.handlers.getTavernRoom = (args) =>
    args.beforeSequence ? pending.promise : h.data.rooms.get(args.roomId);
  let load;
  act(() => {
    load = h.result.current.handleLoadOlder();
  });
  await act(async () => {
    assert.equal(
      await h.result.current.handleTurn(
        { kind: "user_message", content: "blocked" },
        "",
      ),
      false,
    );
  });
  assert.equal(h.calls.filter((c) => c.name === "runTavernTurn").length, 0);
  await act(async () => {
    pending.resolve({
      ...detail(),
      messages: [message("room-a", 1), message("room-a", 2)],
      nextBeforeSequence: null,
    });
    await load;
  });
  assert.deepEqual(
    h.result.current.messages.map((m) => m.sequence),
    [1, 2, 3, 4],
  );
});

test("an uncertain turn retains its original key and revision until read-back finds it", async () => {
  const h = await fixture();
  h.handlers.runTavernTurn = () => {
    throw new Error("response lost");
  };
  await act(async () => {
    assert.equal(
      await h.result.current.handleTurn(
        { kind: "user_message", content: "hello" },
        "guide",
      ),
      false,
    );
  });
  const draft = h.storage.readTavernRoomDraft("room-a");
  await act(async () => {
    await h.result.current.handleTurn(
      { kind: "user_message", content: "hello" },
      "guide",
    );
  });
  const writes = h.calls.filter((c) => c.name === "runTavernTurn");
  assert.equal(writes.length, 2);
  assert.equal(writes[0].args[1].idempotencyKey, writes[1].args[1].idempotencyKey);
  assert.equal(
    writes[0].args[1].expectedRoomRevision,
    draft.pendingTurn.expectedRoomRevision,
  );
  assert.ok(h.storage.readTavernRoomDraft("room-a").pendingTurn);
});

test("switching rooms fences late mutations and preserves the old room recovery draft", async () => {
  const h = await fixture(),
    pending = deferred();
  h.handlers.runTavernTurn = () => pending.promise;
  let turn;
  act(() => {
    turn = h.result.current.handleTurn({ kind: "user_message", content: "hello" }, "");
  });
  await act(async () => {
    await h.result.current.openRoom("room-b");
  });
  await act(async () => {
    pending.resolve(turnResult(detail()));
    await turn;
  });
  assert.equal(h.result.current.activeRoom.id, "room-b");
  assert.equal(h.storage.readTavernRoomDraft("room-a").message, "hello");
  assert.ok(h.result.current.messages.every((m) => m.roomId === "room-b"));
  assert.equal(h.clock.pending, 0);
});

test("cancel supersedes an in-flight turn and rejects its late completed response", async () => {
  const h = await fixture(),
    pending = deferred();
  h.handlers.runTavernTurn = () => pending.promise;
  h.handlers.listTavernRuns = () => [run("room-a")];
  let turn;
  act(() => {
    turn = h.result.current.handleTurn({ kind: "user_message", content: "hello" }, "");
  });
  await waitFor(() => assert.equal(h.result.current.runPending, true));
  const canceled = turnResult(detail(), "canceled");
  h.handlers.cancelTavernRun = () => canceled;
  h.handlers.getTavernRoom = () => ({ ...detail(), room: canceled.roomState });
  h.handlers.listTavernRuns = () => [canceled.run];
  await act(async () => {
    assert.equal(await h.result.current.handleCancelRun(), true);
  });
  await act(async () => {
    pending.resolve(turnResult(detail(), "completed"));
    await turn;
  });
  assert.equal(h.result.current.runs[0].status, "canceled");
  assert.equal(h.result.current.busyAction, null);
  assert.equal(h.clock.pending, 0);
  assert.equal(h.storage.readTavernRoomDraft("room-a").message, "");
});

test("poll intervals stop on unmount and pending auto-resume uses bounded backoff", async () => {
  const env = environment();
  env.data.runs.set("room-a", [run("room-a")]);
  const h = await fixture(env);
  h.handlers.resumeTavernRun = () => turnResult(detail());
  assert.equal(h.clock.pending, 1);
  await act(async () => {
    h.clock.tick(2499);
  });
  assert.equal(h.calls.filter((c) => c.name === "resumeTavernRun").length, 0);
  h.unmount();
  await act(async () => {
    h.clock.tick(10000);
  });
  assert.equal(h.clock.pending, 0);
  assert.equal(h.calls.filter((c) => c.name === "resumeTavernRun").length, 0);
});

test("a refresh begun before a turn commit cannot roll room revision or transcript backward", async () => {
  const h = await fixture(),
    late = deferred(),
    turn = deferred();
  h.handlers.runTavernTurn = () => turn.promise;
  let sending, refreshing;
  act(() => {
    sending = h.result.current.handleTurn(
      { kind: "user_message", content: "hello" },
      "",
    );
  });
  h.handlers.getTavernRoom = () => late.promise;
  act(() => {
    refreshing = h.result.current.refreshRoom();
  });
  await act(async () => {
    turn.resolve(turnResult(detail()));
    await sending;
  });
  assert.equal(h.result.current.activeRoom.revision, 1);
  await act(async () => {
    late.resolve(detail());
    await refreshing;
  });
  assert.equal(h.result.current.activeRoom.revision, 1);
  assert.equal(h.result.current.activeRoom.lastSequence, 5);
  assert.equal(h.result.current.runs[0].status, "completed");
});

test("returning to the same room does not let an earlier older-page request release the new page lock", async () => {
  const h = await fixture(),
    first = deferred(),
    second = deferred();
  let reads = 0;
  h.handlers.getTavernRoom = (args) =>
    args.beforeSequence
      ? ++reads === 1
        ? first.promise
        : second.promise
      : h.data.rooms.get(args.roomId);
  let oldPage, newPage;
  act(() => {
    oldPage = h.result.current.handleLoadOlder();
  });
  await act(async () => {
    await h.result.current.openRoom("room-b");
  });
  await act(async () => {
    await h.result.current.openRoom("room-a");
  });
  act(() => {
    newPage = h.result.current.handleLoadOlder();
  });
  await act(async () => {
    first.resolve({
      ...detail(),
      messages: [message("room-a", 1)],
      nextBeforeSequence: null,
    });
    await oldPage;
  });
  assert.equal(h.result.current.loadingOlder, true);
  assert.deepEqual(
    h.result.current.messages.map((m) => m.sequence),
    [3, 4],
  );
  await act(async () => {
    second.resolve({
      ...detail(),
      messages: [message("room-a", 2)],
      nextBeforeSequence: 2,
    });
    await newPage;
  });
  assert.deepEqual(
    h.result.current.messages.map((m) => m.sequence),
    [2, 3, 4],
  );
});

test("starting cancel suppresses the already scheduled automatic resume", async () => {
  const env = environment();
  env.data.runs.set("room-a", [run("room-a")]);
  const h = await fixture(env),
    pending = deferred();
  h.handlers.cancelTavernRun = () => pending.promise;
  h.handlers.resumeTavernRun = () => turnResult(detail());
  let canceling;
  act(() => {
    canceling = h.result.current.handleCancelRun();
  });
  await act(async () => {
    h.clock.tick(2500);
  });
  assert.equal(h.calls.filter((c) => c.name === "resumeTavernRun").length, 0);
  h.handlers.listTavernRuns = () => [run("room-a", "canceled")];
  await act(async () => {
    pending.resolve(turnResult(detail(), "canceled"));
    await canceling;
  });
});

test("run-in-progress resumes back off to a maximum ten second delay", async () => {
  const { ApiHttpError } = await import("../lib/http-error.ts");
  const env = environment();
  env.data.runs.set("room-a", [run("room-a")]);
  const h = await fixture(env);
  h.handlers.resumeTavernRun = () => {
    throw new ApiHttpError({
      status: 409,
      message: "busy",
      payload: {
        detail: {
          code: "tavern_run_in_progress",
          run_id: "room-a-run",
          child_run_id: "",
          current_revision: 0,
          recovery_action: "wait_and_resume",
        },
      },
    });
  };
  for (const [index, delay] of [2500, 5000, 10000, 10000].entries()) {
    await act(async () => {
      h.clock.tick(delay - 1);
    });
    assert.equal(h.calls.filter((c) => c.name === "resumeTavernRun").length, index);
    await act(async () => {
      h.clock.tick(1);
    });
    assert.equal(h.calls.filter((c) => c.name === "resumeTavernRun").length, index + 1);
  }
});

test("unmount cancels foreground polling and its late response cannot start recovery", async () => {
  const h = await fixture(),
    write = deferred(),
    poll = deferred();
  h.handlers.runTavernTurn = () => write.promise;
  h.handlers.listTavernRuns = () => poll.promise;
  let pending;
  act(() => {
    pending = h.result.current.handleTurn(
      { kind: "user_message", content: "in-flight" },
      "",
    );
  });
  assert.equal(h.clock.pending, 1);
  const reads = h.calls.filter((c) => c.name === "listTavernRuns").length;
  h.unmount();
  await act(async () => {
    h.clock.tick(5000);
    poll.resolve([run("room-a")]);
    write.resolve(turnResult(detail()));
    await pending;
  });
  assert.equal(h.clock.pending, 0);
  assert.equal(h.calls.filter((c) => c.name === "listTavernRuns").length, reads);
  assert.equal(h.calls.filter((c) => c.name === "resumeTavernRun").length, 0);
  assert.equal(h.storage.readTavernRoomDraft("room-a").message, "in-flight");
});

test("child retry uses server unfinished steps and leaves current recipient selection independent", async () => {
  const env = environment();
  const failed = run("room-a", "partial", {
    mode: "facilitated",
    speakerSteps: [
      { personaId: "p1", status: "completed" },
      { personaId: "p2", status: "failed" },
      { personaId: "p3", status: "blocked" },
    ],
  });
  env.data.runs.set("room-a", [failed]);
  const h = await fixture(env),
    pending = deferred();
  h.handlers.retryTavernRun = () => pending.promise;
  act(() => {
    h.result.current.handleTargetToggle("p2");
  });
  let retry;
  act(() => {
    retry = h.result.current.handleRetry(failed);
  });
  assert.deepEqual(h.result.current.generatingPersonaIds, ["p2", "p3"]);
  const request = h.calls.find((c) => c.name === "retryTavernRun").args;
  assert.equal(request[1], failed.id);
  assert.equal(request[2].targetPersonaIds, undefined);
  assert.deepEqual(h.result.current.targetPersonaIds, ["p1", "p2"]);
  await act(async () => {
    pending.resolve(
      turnResult(detail(), "completed", {
        id: "child",
        parentRunId: failed.id,
        mode: "facilitated",
      }),
    );
    await retry;
  });
  assert.equal(h.result.current.runs[0].id, "child");
});

test("late resume after completed cancellation cannot overwrite its notice or terminal state", async () => {
  const env = environment();
  env.data.runs.set("room-a", [run("room-a")]);
  const h = await fixture(env),
    resuming = deferred();
  h.handlers.resumeTavernRun = () => resuming.promise;
  await act(async () => h.clock.tick(2500));
  const canceled = turnResult(detail(), "canceled");
  h.handlers.cancelTavernRun = () => canceled;
  h.handlers.getTavernRoom = () => ({ ...detail(), room: canceled.roomState });
  h.handlers.listTavernRuns = () => [canceled.run];
  await act(async () => {
    await h.result.current.handleCancelRun();
  });
  const notice = h.result.current.notice;
  await act(async () => {
    resuming.resolve(turnResult(detail(), "completed"));
  });
  assert.equal(h.result.current.notice, notice);
  assert.equal(h.result.current.runs[0].status, "canceled");
});

test("slow foreground polling retains a single outstanding read", async () => {
  const h = await fixture(),
    posting = deferred(),
    polling = deferred();
  h.handlers.runTavernTurn = () => posting.promise;
  h.handlers.listTavernRuns = () => polling.promise;
  let pending;
  act(() => {
    pending = h.result.current.handleTurn(
      { kind: "user_message", content: "slow" },
      "",
    );
  });
  const reads = h.calls.filter((c) => c.name === "listTavernRuns").length;
  await act(async () => h.clock.tick(9000));
  assert.equal(h.calls.filter((c) => c.name === "listTavernRuns").length, reads);
  h.unmount();
  await act(async () => {
    polling.resolve([]);
    posting.resolve(turnResult(detail()));
    await pending;
  });
  assert.equal(h.clock.pending, 0);
});

test("ambiguous response hands off to one fresh read-back and prevents more foreground polls", async () => {
  const h = await fixture(),
    write = deferred(),
    polling = deferred(),
    readBack = deferred();
  let readCount = 0;
  h.handlers.runTavernTurn = () => write.promise;
  h.handlers.listTavernRuns = () =>
    ++readCount === 1 ? polling.promise : readBack.promise;
  let sending;
  act(() => {
    sending = h.result.current.handleTurn(
      { kind: "user_message", content: "read-back" },
      "",
    );
  });
  assert.equal(readCount, 1);
  await act(async () => write.reject(new Error("lost response")));
  assert.equal(readCount, 2);
  await act(async () => {
    polling.resolve([]);
    h.clock.tick(5000);
  });
  assert.equal(readCount, 2);
  await act(async () => {
    readBack.resolve([]);
    await sending;
  });
  assert.equal(h.calls.filter((call) => call.name === "runTavernTurn").length, 1);
});

test("an old page with a reused cursor cannot clear the new page request guard", async () => {
  const env = environment();
  env.data.cursor = "same";
  const h = await fixture(env),
    old = deferred(),
    latest = deferred();
  let calls = 0;
  h.handlers.listTavernRooms = (args) =>
    args.cursor
      ? ++calls === 1
        ? old.promise
        : latest.promise
      : { items: [], nextCursor: "same" };
  let first, second;
  act(() => {
    first = h.result.current.loadMoreRooms();
  });
  await act(async () => {
    await h.result.current.refreshRoom();
  });
  act(() => {
    second = h.result.current.loadMoreRooms();
  });
  await act(async () => {
    old.resolve({ items: [], nextCursor: null });
    await first;
  });
  assert.equal(h.result.current.loadingMoreRooms, true);
  await act(async () => {
    latest.resolve({ items: [], nextCursor: null });
    await second;
  });
  assert.equal(h.result.current.loadingMoreRooms, false);
});

test("creation reuses the persisted request identity and rejects a concurrent create", async () => {
  const h = await fixture(),
    pending = deferred();
  h.handlers.createTavernRoom = () => pending.promise;
  const input = {
    title: "New room",
    personaIds: ["p1", "p2"],
    sceneId: "",
    openingPrompt: "Welcome",
  };
  let first;
  act(() => {
    first = h.result.current.handleCreateRoom(input);
  });
  await act(async () => {
    await h.result.current.handleCreateRoom(input);
  });
  assert.equal(h.calls.filter((c) => c.name === "createTavernRoom").length, 1);
  const key = h.storage.readTavernCreationDraft().key;
  await act(async () => {
    pending.reject(new Error("unknown outcome"));
    await first;
  });
  assert.equal(h.storage.readTavernCreationDraft().key, key);
  h.handlers.createTavernRoom = () => detail("new-room");
  await act(async () => {
    await h.result.current.handleCreateRoom(input);
  });
  assert.equal(
    h.calls.filter((c) => c.name === "createTavernRoom")[1].args[0].idempotencyKey,
    key,
  );
  assert.equal(h.result.current.activeRoom.id, "new-room");
  assert.equal(h.storage.readTavernCreationDraft(), null);
});

test("a room switch rejects a submit from the still-visible previous Composer", async () => {
  const h = await fixture(),
    pending = deferred();
  h.handlers.getTavernRoom = ({ roomId }) =>
    roomId === "room-b" ? pending.promise : h.data.rooms.get(roomId);
  let opening;
  act(() => {
    opening = h.result.current.openRoom("room-b");
  });
  await act(async () => {
    assert.equal(
      await h.result.current.handleTurn(
        { kind: "user_message", content: "wrong room" },
        "",
      ),
      false,
    );
  });
  assert.equal(h.calls.filter((c) => c.name === "runTavernTurn").length, 0);
  await act(async () => {
    pending.resolve(detail("room-b"));
    await opening;
  });
  assert.equal(h.result.current.activeRoom.id, "room-b");
});
