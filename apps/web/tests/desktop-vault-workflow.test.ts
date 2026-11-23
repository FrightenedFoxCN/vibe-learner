import assert from "node:assert/strict";
import test from "node:test";
import { createVaultQueue, saveWithVault } from "../lib/desktop-vault-workflow.ts";

for (const failure of ["store", "apply", "commit"]) {
  test(`failed ${failure} restores synthetic vault and runtime credentials`, async () => {
    let disk = "before";
    let session = "before";
    await assert.rejects(
      saveWithVault(
        {
          read: async () => disk,
          store: async (value) => {
            disk = value;
            if (failure === "store" && value === "after")
              throw new Error("fake store failure");
          },
          apply: async (value) => {
            session = value;
            if (failure === "apply" && value === "after")
              throw new Error("fake apply failure");
          },
          commit: async () => {
            if (failure === "commit") throw new Error("fake PATCH failure");
            assert.fail("commit after failed preceding step");
          },
        },
        "after",
      ),
      /密钥已恢复/,
    );
    assert.deepEqual([disk, session], ["before", "before"]);
  });
}

test("uncertain rollback is reported rather than claiming success", async () => {
  await assert.rejects(
    saveWithVault(
      {
        read: async () => "old",
        store: async () => {},
        apply: async () => {
          throw new Error("fake network failure");
        },
        commit: async () => assert.fail(),
      },
      "new",
    ),
    /无法确认运行时密钥已恢复/,
  );
});

test("vault lock waits for the pending save even when the save rejects", async () => {
  const enqueue = createVaultQueue();
  let release = () => {};
  const gate = new Promise<void>((resolve) => {
    release = resolve;
  });
  const events: string[] = [];
  const save = enqueue(async () => {
    events.push("saving");
    await gate;
    throw new Error("fake failure");
  });
  const lock = enqueue(async () => events.push("locked"));
  await Promise.resolve();
  assert.deepEqual(events, ["saving"]);
  release();
  await assert.rejects(save);
  await lock;
  assert.deepEqual(events, ["saving", "locked"]);
});
