import assert from "node:assert/strict";
import test from "node:test";
import { planRevisionRecovery } from "../lib/plan-revision-recovery.ts";

function memoryStorage() {
  const data = new Map<string, string>();
  return {
    get length() {
      return data.size;
    },
    key: (index: number) => [...data.keys()][index] ?? null,
    getItem: (key: string) => data.get(key) ?? null,
    setItem: (key: string, value: string) => void data.set(key, value),
    removeItem: (key: string) => void data.delete(key),
  };
}

const legacyKey = "vibe-learner:plan-revision:v1:plan";

test("two tabs retain and reload their own request IDs and clear only the target", () => {
  const shared = memoryStorage();
  const tabA = memoryStorage();
  const tabB = memoryStorage();
  const inA = planRevisionRecovery("plan", shared, tabA);
  const inB = planRevisionRecovery("plan", shared, tabB);
  inA.remember("request-a");
  assert.equal(inB.current(), "");
  inB.remember("request-b");

  const reloadA = planRevisionRecovery("plan", shared, tabA);
  const reloadB = planRevisionRecovery("plan", shared, tabB);
  assert.equal(reloadA.current(), "request-a");
  assert.equal(reloadB.current(), "request-b");
  assert.deepEqual(reloadA.list(), ["request-a", "request-b"]);

  reloadA.clear("request-a");
  assert.equal(reloadA.current(), "");
  assert.equal(reloadB.current(), "request-b");
  assert.deepEqual(reloadA.list(), ["request-b"]);
});

test("clearing a shared selection cannot remove the original tab's reload pointer", () => {
  const shared = memoryStorage();
  const tabA = memoryStorage();
  const inA = planRevisionRecovery("plan", shared, tabA);
  const inB = planRevisionRecovery("plan", shared, memoryStorage());
  inA.remember("request-a");
  assert.equal(inB.select("request-a"), true);
  inB.clear("request-a");
  assert.equal(inB.current(), "");
  assert.equal(planRevisionRecovery("plan", shared, tabA).current(), "request-a");
});

test("late cleanup for the previous request cannot erase the latest tab selection", () => {
  const shared = memoryStorage();
  const tab = memoryStorage();
  const recovery = planRevisionRecovery("plan", shared, tab);
  recovery.remember("previous");
  recovery.remember("latest");
  recovery.clear("previous");
  assert.equal(planRevisionRecovery("plan", shared, tab).current(), "latest");
  assert.deepEqual(recovery.list(), ["latest"]);
});

test("the old shared slot is explicitly adopted and scoped migration survives slot replacement", () => {
  const shared = memoryStorage();
  const tab = memoryStorage();
  shared.setItem(legacyKey, "old:id");
  const recovery = planRevisionRecovery("plan", shared, tab);
  assert.equal(recovery.current(), "");
  assert.deepEqual(recovery.list(), ["old:id"]);
  assert.equal(recovery.select("old:id"), true);
  shared.setItem(legacyKey, "other-legacy");
  assert.equal(planRevisionRecovery("plan", shared, tab).current(), "old:id");
  assert.deepEqual(recovery.list(), ["old:id", "other-legacy"]);

  recovery.clear("old:id");
  assert.equal(recovery.current(), "");
  assert.equal(shared.getItem(legacyKey), "other-legacy");
  assert.deepEqual(recovery.list(), ["other-legacy"]);
  shared.setItem(legacyKey, "old:id");
  assert.deepEqual(recovery.list(), []);
  assert.equal(recovery.select("old:id"), false);
});

test("clearing a migrated ID leaves the old slot intact but cannot resurrect the request", () => {
  const shared = memoryStorage();
  shared.setItem(legacyKey, "legacy-id");
  const recovery = planRevisionRecovery("plan", shared, memoryStorage());
  assert.equal(recovery.select("legacy-id"), true);
  recovery.clear("legacy-id");
  assert.equal(shared.getItem(legacyKey), "legacy-id");
  assert.deepEqual(recovery.list(), []);
  assert.equal(recovery.select("legacy-id"), false);
});

test("a concurrent legacy import cannot restore a request another tab just cleared", () => {
  const shared = memoryStorage();
  shared.setItem(legacyKey, "legacy-id");
  const inA = planRevisionRecovery("plan", shared, memoryStorage());
  const storageInB = Object.create(shared) as typeof shared;
  storageInB.setItem = (key, value) => {
    inA.clear("legacy-id");
    shared.setItem(key, value);
  };
  const inB = planRevisionRecovery("plan", storageInB, memoryStorage());
  assert.equal(inB.select("legacy-id"), false);
  assert.equal(inB.current(), "");
  assert.deepEqual(inB.list(), []);
});

test("invalid and other-plan entries cannot be selected or collide with request IDs", () => {
  const shared = memoryStorage();
  const tab = memoryStorage();
  const recovery = planRevisionRecovery("plan", shared, tab);
  const another = planRevisionRecovery("plan:one", shared, tab);
  shared.setItem(legacyKey, "bad id");
  another.remember("nested");
  recovery.remember("one:nested");
  assert.deepEqual(recovery.list(), ["one:nested"]);
  assert.equal(recovery.select("nested"), false);
  assert.equal(recovery.select("bad id"), false);
  assert.equal(recovery.current(), "one:nested");
  assert.equal(another.current(), "nested");
});

test("a failed tab write leaves no new recoverable ID or damage to another request", () => {
  const shared = memoryStorage();
  const inA = planRevisionRecovery("plan", shared, memoryStorage());
  inA.remember("request-a");
  const inB = planRevisionRecovery("plan", shared, {
    ...memoryStorage(),
    setItem() {
      throw new Error("storage denied");
    },
  });
  assert.throws(() => inB.remember("request-b"), /storage denied/);
  assert.throws(() => inB.remember("request-a"), /already saved/);
  assert.equal(inA.current(), "request-a");
  assert.deepEqual(inB.list(), ["request-a"]);
});
