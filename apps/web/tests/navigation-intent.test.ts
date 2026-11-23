import assert from "node:assert/strict";
import { test } from "node:test";
import { classifyAppLink } from "../lib/navigation-intent.ts";

const source = "https://example.test/persona-spectrum/";
const click = {
  button: 0,
  defaultPrevented: false,
  metaKey: false,
  altKey: false,
  ctrlKey: false,
  shiftKey: false,
};
const link = (href: string, target = "", download = false) => ({
  href,
  target,
  hasAttribute: (name: string) => name === "download" && download,
});

test("ordinary same-tab app links retain query and fragment", () => {
  assert.deepEqual(
    classifyAppLink(click, link("/plan/?id=4#history", "_SELF"), source),
    {
      path: "/plan",
      suffix: "?id=4#history",
      samePage: false,
    },
  );
  assert.equal(classifyAppLink(click, link("?mode=edit"), source)?.samePage, false);
});

test("same route and hash changes do not leave the workspace", () => {
  assert.equal(
    classifyAppLink(click, link("/persona-spectrum"), source)?.samePage,
    true,
  );
  assert.equal(classifyAppLink(click, link("#section"), source)?.samePage, true);
});

test("cancelled, modified, other-tab, download and external links stay native", () => {
  for (const modifier of [
    "metaKey",
    "altKey",
    "ctrlKey",
    "shiftKey",
    "defaultPrevented",
  ] as const) {
    assert.equal(
      classifyAppLink({ ...click, [modifier]: true }, link("/plan"), source),
      null,
    );
  }
  assert.equal(classifyAppLink({ ...click, button: 1 }, link("/plan"), source), null);
  assert.equal(classifyAppLink(click, link("/plan", "_blank"), source), null);
  assert.equal(classifyAppLink(click, link("/plan", "", true), source), null);
  assert.equal(classifyAppLink(click, link("https://other.test/plan"), source), null);
  assert.equal(classifyAppLink(click, link("mailto:a@example.test"), source), null);
});
