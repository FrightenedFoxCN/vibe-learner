import assert from "node:assert/strict";
import test from "node:test";
import {
  requiresDesktopVaultCreation,
  resolveDesktopStartupRequirement,
} from "../lib/desktop-startup.ts";
import { createDesktopVaultSession } from "../lib/desktop-vault-state.ts";
import { resolvePlanGenerationBlockedReason } from "../lib/learning-workspace-model.ts";
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

function syntheticSession() {
  return { stronghold: { save: async () => {}, unload: async () => {} } };
}

const noPlanKey = {
  planProvider: "litellm",
  openaiPlanApiKeyConfigured: false,
  openaiApiKeyConfigured: false,
} as const;

test("create, lock and reopen publish current state behind stale WebView bootstrap", async () => {
  const vault = createDesktopVaultSession(() => "unconfigured");
  const transitions: Array<string | null> = [];
  const unsubscribe = vault.subscribe(() => transitions.push(vault.getSnapshot()));
  const creationRequired = () => requiresDesktopVaultCreation(vault.getSnapshot());
  const planBlockedReason = () =>
    resolvePlanGenerationBlockedReason({
      runtimeSettings: noPlanKey,
      runtimeSettingsLoading: false,
      desktopVaultState: vault.getSnapshot(),
    });

  assert.equal(creationRequired(), true);
  assert.match(planBlockedReason(), /尚未创建/);
  await vault.activate(syntheticSession(), "initialize");
  assert.equal(creationRequired(), false);
  assert.match(planBlockedReason(), /还没有可用的计划模型密钥/);
  await vault.lock();
  assert.equal(vault.getSession(), null);
  assert.equal(creationRequired(), false);
  assert.match(planBlockedReason(), /尚未解锁/);
  assert.equal(
    resolveDesktopStartupRequirement({
      isDesktop: true,
      vaultState: "locked",
      settings: null,
    })?.title,
    "先解锁桌面 Vault",
  );
  await vault.activate(syntheticSession(), "unlock");
  unsubscribe();
  await vault.lock();
  assert.deepEqual(transitions, ["unlocked", "locked", "unlocked"]);
});

test("failed initial persistence never publishes the Vault as configured", async () => {
  const vault = createDesktopVaultSession(() => "unconfigured");
  vault.subscribe(() => assert.fail("failed creation must not publish an unlock"));
  let unloaded = false;
  await assert.rejects(
    vault.activate(
      {
        stronghold: {
          save: async () => {
            throw new Error("synthetic save failure");
          },
          unload: async () => {
            unloaded = true;
          },
        },
      },
      "initialize",
    ),
    /synthetic save failure/,
  );
  assert.equal(unloaded, true);
  assert.equal(requiresDesktopVaultCreation(vault.getSnapshot()), true);
});

test("a failed unload still revokes local access without requiring a new Vault", async () => {
  const vault = createDesktopVaultSession(() => "unconfigured");
  await vault.activate(
    {
      stronghold: {
        save: async () => {},
        unload: async () => {
          throw new Error("synthetic unload failure");
        },
      },
    },
    "initialize",
  );
  await assert.rejects(vault.lock(), /synthetic unload failure/);
  assert.equal(vault.getSession(), null);
  assert.equal(vault.getSnapshot(), "locked");
  assert.equal(requiresDesktopVaultCreation(vault.getSnapshot()), false);
});

test("web has no Vault and native bootstrap cannot manufacture a live unlock", () => {
  assert.equal(createDesktopVaultSession(() => null).getSnapshot(), null);
  assert.equal(createDesktopVaultSession(() => "unlocked").getSnapshot(), "locked");
  assert.equal(requiresDesktopVaultCreation(null), false);
});
