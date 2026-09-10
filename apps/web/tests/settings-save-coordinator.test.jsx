import assert from "node:assert/strict";
import { test } from "node:test";
import { SettingsSaveCoordinator } from "../lib/settings-save-coordinator.ts";
import { saveClock, saveRequests, settleSave } from "./support/save-clock.js";

function fixture() {
  const clock = saveClock(), transport = saveRequests(), statuses = [], saved = [];
  const coordinator = new SettingsSaveCoordinator({
    serialize: JSON.stringify, persist: transport.persist,
    saved: (value, key) => saved.push({ value, key }),
    status: (phase, error) => statuses.push({ phase, error }),
  }, 900, clock);
  coordinator.acceptSaved({ value: "initial" });
  return { coordinator, clock, ...transport, statuses, saved, edit: value => coordinator.edit({ value }) };
}

test("900ms debounce survives identical snapshots and restarts only on changed edits", () => {
  const h = fixture(); h.edit("A"); h.clock.tick(400); h.edit("A");
  h.clock.tick(499); assert.equal(h.requests.length, 0);
  h.edit("B"); h.clock.tick(899); assert.equal(h.requests.length, 0);
  h.clock.tick(1); assert.deepEqual(h.requests.map(r => r.snapshot.value), ["B"]);
});

for (const fails of [false, true]) test(`navigation drains latest edit after older ${fails ? "failure" : "success"}`, async () => {
  const h = fixture(); h.edit("A"); h.clock.tick(900); h.edit("B"); h.edit("C"); h.coordinator.flush();
  assert.equal(h.requests.length, 1);
  fails ? h.requests[0].reject(new Error("offline")) : h.requests[0].resolve();
  await settleSave();
  assert.deepEqual(h.requests.map(r => r.snapshot.value), ["A", "C"]);
  h.requests[1].reject(new Error("offline")); await settleSave();
  h.clock.tick(5000); h.coordinator.flush();
  assert.equal(h.requests.length, 2);
});

test("reverting an unsent edit clears it; reverting an in-flight edit queues restoration", async () => {
  const h = fixture(); h.edit("A"); h.edit("initial"); h.coordinator.flush();
  assert.equal(h.requests.length, 0);
  h.edit("A"); h.clock.tick(900); h.edit("initial"); h.coordinator.flush();
  h.requests[0].resolve(); await settleSave();
  assert.deepEqual(h.requests.map(r => r.snapshot.value), ["A", "initial"]);
});

test("failed snapshot requires explicit retry and successful normalization avoids redundant writes", async () => {
  const h = fixture(); h.edit("A"); h.clock.tick(900);
  h.requests[0].reject(new Error("offline")); await settleSave();
  h.edit("A"); h.clock.tick(5000); assert.equal(h.requests.length, 1);
  h.coordinator.retry({ value: "A" }); assert.equal(h.requests.length, 2);
  h.requests[1].resolve({ value: "normalized" }); await settleSave();
  h.edit("normalized"); h.clock.tick(900); assert.equal(h.requests.length, 2);
  assert.equal(h.saved[0].key, JSON.stringify({ value: "A" }));
});

test("newer edits during normal save receive their own debounce without concurrent writes", async () => {
  const h = fixture(); h.edit("A"); h.clock.tick(900); h.edit("B");
  h.clock.tick(5000); assert.equal(h.requests.length, 1);
  h.requests[0].resolve(); await settleSave();
  h.clock.tick(899); assert.equal(h.requests.length, 1);
  h.clock.tick(1); assert.equal(h.requests.length, 2);
});
