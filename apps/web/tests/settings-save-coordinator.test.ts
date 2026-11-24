import assert from "node:assert/strict";
import { setImmediate } from "node:timers/promises";
import test from "node:test";

import {
  SettingsSaveCoordinator,
  type SavePhase,
  type SaveScheduler,
} from "../lib/settings-save-coordinator.ts";

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: Error) => void;
  const promise = new Promise<T>((yes, no) => {
    resolve = yes;
    reject = no;
  });
  return { promise, resolve, reject };
}

function fixture() {
  const timers = new Map<number, () => void>();
  let schedules = 0;
  const clock: SaveScheduler = {
    schedule: (callback) => {
      timers.set(++schedules, callback);
      return schedules;
    },
    cancel: (id) => timers.delete(Number(id)),
  };
  const persisted: string[] = [];
  const responses: ReturnType<typeof deferred<string>>[] = [];
  const saved: [string, string][] = [];
  const statuses: [SavePhase, string][] = [];
  const coordinator = new SettingsSaveCoordinator<string>(
    {
      serialize: (snapshot) => snapshot,
      persist: (snapshot) => {
        persisted.push(snapshot);
        const response = deferred<string>();
        responses.push(response);
        return response.promise;
      },
      saved: (snapshot, key) => saved.push([snapshot, key]),
      status: (phase, error) => statuses.push([phase, error]),
    },
    900,
    clock,
  );
  coordinator.acceptSaved("original");
  return {
    coordinator,
    timers,
    persisted,
    responses,
    saved,
    statuses,
    get schedules() {
      return schedules;
    },
    fire() {
      assert.equal(timers.size, 1);
      const [[key, callback]] = [...timers.entries()];
      timers.delete(key);
      callback();
    },
  };
}

test("debounces to the latest edit and does not reschedule identical input", async () => {
  const f = fixture();
  f.coordinator.edit("first");
  f.coordinator.edit("second");
  f.coordinator.edit("second");
  assert.equal(f.schedules, 2);
  assert.equal(f.persisted.length, 0);
  f.fire();
  assert.deepEqual(f.persisted, ["second"]);
  f.responses[0].resolve("canonical second");
  await setImmediate();
  assert.deepEqual(f.saved, [["canonical second", "second"]]);
  f.coordinator.edit("canonical second");
  assert.equal(f.timers.size, 0);
  assert.deepEqual(f.statuses.at(-1), ["saved", ""]);
});

test("navigation flush starts pending work and drains the latest queued edit in order", async () => {
  const f = fixture();
  f.coordinator.edit("first");
  f.coordinator.flush();
  f.coordinator.edit("intermediate");
  f.coordinator.edit("latest");
  f.coordinator.flush();
  assert.equal(f.timers.size, 0);
  assert.deepEqual(f.persisted, ["first"]);
  f.responses[0].resolve("first");
  await setImmediate();
  assert.deepEqual(f.persisted, ["first", "latest"]);
  f.responses[1].resolve("latest");
  await setImmediate();
  assert.deepEqual(f.saved, [
    ["first", "first"],
    ["latest", "latest"],
  ]);
  assert.equal(f.timers.size, 0);
});

test("a failed snapshot stays blocked until an explicit retry", async () => {
  const f = fixture();
  f.coordinator.edit("retry me");
  f.fire();
  f.responses[0].reject(new Error("fake persistence failure"));
  await setImmediate();
  assert.deepEqual(f.statuses.at(-1), ["error", "Error: fake persistence failure"]);
  f.coordinator.edit("retry me");
  f.coordinator.flush();
  assert.equal(f.timers.size, 0);
  assert.deepEqual(f.persisted, ["retry me"]);
  f.coordinator.retry("retry me");
  f.responses[1].resolve("retry me");
  await setImmediate();
  assert.deepEqual(f.persisted, ["retry me", "retry me"]);
  assert.deepEqual(f.statuses.at(-1), ["saved", ""]);
});

test("reverting to the running edit does not resend its unnormalized payload", async () => {
  const f = fixture();
  f.coordinator.edit("  in flight  ");
  f.fire();
  f.coordinator.edit("newer edit");
  f.coordinator.edit("  in flight  ");
  f.coordinator.flush();
  f.responses[0].resolve("in flight");
  await setImmediate();
  assert.deepEqual(f.persisted, ["  in flight  "]);
});

test("reverting to the previous baseline during a save queues an undo write", async () => {
  const f = fixture();
  f.coordinator.edit("in flight");
  f.fire();
  f.coordinator.edit("original");
  f.responses[0].resolve("in flight");
  await setImmediate();
  f.fire();
  assert.deepEqual(f.persisted, ["in flight", "original"]);
  f.responses[1].resolve("original");
  await setImmediate();
});

test("Vault transition may discard queued edits without interrupting the running save", async () => {
  const f = fixture();
  f.coordinator.edit("in flight");
  f.fire();
  f.coordinator.edit("abandoned");
  f.coordinator.discardPending();
  f.responses[0].resolve("in flight");
  await setImmediate();
  f.coordinator.acceptSaved("Vault readback");
  f.coordinator.edit("Vault readback");
  assert.equal(f.timers.size, 0);
  assert.deepEqual(f.persisted, ["in flight"]);
});
