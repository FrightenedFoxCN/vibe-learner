import { dom } from "./support/dom.js";
import assert from "node:assert/strict";
import { after, test } from "node:test";
import { initializeDesktopVault, unlockDesktopVault, lockDesktopVault, loadDesktopVaultSecrets, saveDesktopVaultSecrets, clearDesktopVaultSecrets } from "../lib/desktop-vault.ts";
import { diagnosticSnapshot } from "../lib/diagnostics.ts";

after(() => dom.window.close());
test("all Vault entrypoints record locked/unavailable outcomes without passwords or credentials", async () => {
  for (const [name, invoke] of [
    ["vault_create", () => initializeDesktopVault("PRIVATE_PASSWORD_SENTINEL")],
    ["vault_unlock", () => unlockDesktopVault("PRIVATE_PASSWORD_SENTINEL")],
    ["vault_load_secrets", () => loadDesktopVaultSecrets()],
    ["vault_save_secrets", () => saveDesktopVaultSecrets({ openaiApiKey: "PRIVATE_APIKEY_SENTINEL" })],
    ["vault_clear_secrets", () => clearDesktopVaultSecrets()],
  ]) {
    await assert.rejects(invoke());
    const events = diagnosticSnapshot().events.filter(item => item.action_name === name);
    assert.deepEqual(events.map(item => item.name), ["action_started", "action_failed"]);
  }
  await lockDesktopVault();
  assert.equal(diagnosticSnapshot().events.at(-1)?.action_name, "vault_lock");
  assert.equal(diagnosticSnapshot().events.at(-1)?.name, "action_finished");
  assert.ok(!JSON.stringify(diagnosticSnapshot()).includes("PRIVATE"));
});
