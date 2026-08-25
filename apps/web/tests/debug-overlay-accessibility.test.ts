import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const source = readFileSync(
  new URL("../components/debug-overlay.tsx", import.meta.url),
  "utf8"
);

test("Debug Overlay exposes a labelled modal and focuses its collapse control", () => {
  assert.match(source, /role="dialog"/);
  assert.match(source, /aria-modal="true"/);
  assert.match(source, /aria-labelledby=\{titleId\}/);
  assert.match(source, /<span id=\{titleId\} style=\{styles\.title\}>\{title\}<\/span>/);
  assert.match(source, /collapseButtonRef\.current\?\.focus\(\{ preventScroll: true \}\)/);
  assert.match(source, /ref=\{collapseButtonRef\}[\s\S]*?>[\s\n]*收起/);
  assert.match(source, /fab: \{[\s\S]*?minHeight: 44/);
  assert.match(source, /primaryButton: \{[\s\S]*?minWidth: 44,[\s\S]*?minHeight: 44/);
  assert.match(source, /secondaryButton: \{[\s\S]*?minWidth: 44,[\s\S]*?minHeight: 44/);
});

test("Debug Overlay isolates main content and restores page state exactly", () => {
  assert.match(source, /document\.querySelectorAll<HTMLElement>\("main"\)/);
  assert.match(source, /ariaHidden: element\.getAttribute\("aria-hidden"\)/);
  assert.match(source, /inertAttribute: element\.getAttribute\("inert"\)/);
  assert.match(source, /inertProperty: element\.inert/);
  assert.match(source, /mainElement\.inert = true/);
  assert.match(source, /mainElement\.setAttribute\("inert", ""\)/);
  assert.match(source, /mainElement\.setAttribute\("aria-hidden", "true"\)/);
  assert.match(source, /const previousBodyOverflow = document\.body\.style\.overflow/);
  assert.match(source, /document\.body\.style\.overflow = "hidden"/);
  assert.match(source, /document\.body\.style\.overflow = previousBodyOverflow/);
  assert.match(source, /restoreAttribute\(element, "aria-hidden", ariaHidden\)/);
  assert.match(source, /restoreAttribute\(element, "inert", inertAttribute\)/);
});

test("Debug Overlay traps focus and routes every close interaction through one path", () => {
  assert.match(source, /if \(event\.key === "Escape"\)[\s\S]*?closeOverlay\(\)/);
  assert.match(source, /if \(event\.key !== "Tab"\)/);
  assert.match(source, /event\.shiftKey \? lastFocusable : firstFocusable/);
  assert.match(source, /event\.shiftKey && activeElement === firstFocusable/);
  assert.match(source, /!event\.shiftKey && activeElement === lastFocusable/);
  assert.equal(source.match(/onClick=\{closeOverlay\}/g)?.length, 2);
  assert.match(source, /restoreFocusRef\.current = trigger \?\?/);
  assert.match(source, /restoreTarget\?\.isConnected/);
  assert.match(source, /restoreTarget\.focus\(\{ preventScroll: true \}\)/);
  assert.match(source, /style=\{open \? \{ \.\.\.styles\.fab, \.\.\.styles\.hiddenFab \} : styles\.fab\}/);
});
