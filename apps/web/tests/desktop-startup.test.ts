import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { requiresDesktopVaultCreation } from "../lib/desktop-startup.ts";

const appNavigationSource = readFileSync(
  new URL("../lib/app-navigation.tsx", import.meta.url),
  "utf8",
);
const topNavSource = readFileSync(
  new URL("../components/top-nav.tsx", import.meta.url),
  "utf8",
);

test("desktop navigation remains locked until the first Vault is created", () => {
  assert.equal(requiresDesktopVaultCreation({
    isDesktop: true,
    vaultState: "unconfigured",
    vaultUnlocked: false,
  }), true);
  assert.equal(requiresDesktopVaultCreation({
    isDesktop: true,
    vaultState: "unconfigured",
    vaultUnlocked: true,
  }), false);
  assert.equal(requiresDesktopVaultCreation({
    isDesktop: true,
    vaultState: "locked",
    vaultUnlocked: false,
  }), false);
  assert.equal(requiresDesktopVaultCreation({
    isDesktop: false,
    vaultState: "unconfigured",
    vaultUnlocked: false,
  }), false);
});

test("desktop vault gate blocks both app links and side navigation", () => {
  assert.match(appNavigationSource, /vaultCreationRequired && path !== "\/settings"/);
  assert.match(topNavSource, /vaultCreationRequired && item\.href !== "\/settings"/);
  assert.match(topNavSource, /aria-disabled="true"/);
});

test("desktop navigation preserves the root workspace provider during route changes", () => {
  assert.doesNotMatch(appNavigationSource, /window\.location\.(assign|replace)/);
  assert.match(appNavigationSource, /router\.push\(href as Route\)/);
  assert.match(appNavigationSource, /router\.replace\(href as Route\)/);
});
