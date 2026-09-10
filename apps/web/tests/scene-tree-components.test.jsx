import { dom } from "./support/dom.js";
import assert from "node:assert/strict";
import { after, afterEach, test } from "node:test";
import { cleanup, fireEvent, render, within } from "@testing-library/react";
import { SceneLayerCard } from "../components/scene/scene-tree-components.tsx";
import { INITIAL_SCENE } from "../lib/scene-editor-model.ts";

afterEach(cleanup);
after(() => dom.window.close());
function fixture(overrides = {}) {
  const calls = [];
  const layer = INITIAL_SCENE[0];
  const props = {
    layer, index: 0, selectedLayerId: "", selectedObjectId: "", reusableActionPendingId: "",
    onSelect: id => calls.push(["select", id]), onToggleEditor: id => calls.push(["toggle", id]),
    onAddChild: id => calls.push(["add", id]), onAddObject() {}, onSaveToReusable() {},
    onSelectObject() {}, onSaveObjectToReusable() {}, onRemoveObject() {},
    onRequestDelete: id => calls.push(["delete", id]), canDeleteLayerForId: () => true,
    editorContent: <p>Selected editor</p>, renderObjectEditor: () => null, ...overrides,
  };
  const view = render(<SceneLayerCard {...props} />);
  const card = within(view.getByRole("heading", { name: layer.title, exact: true }).closest("article"));
  return { ...view, getByRole: card.getByRole, calls, layer };
}

test("tree action controls do not bubble into selecting another editor", () => {
  const h = fixture();
  fireEvent.click(h.getByRole("button", { name: "添加子层", exact: true }));
  fireEvent.click(h.getByRole("button", { name: "删除当前层级", exact: true }));
  assert.deepEqual(h.calls, [["add", h.layer.id], ["delete", h.layer.id]]);
  fireEvent.click(h.getByRole("heading", { name: h.layer.title, exact: true }));
  assert.deepEqual(h.calls.at(-1), ["select", h.layer.id]);
});

test("protected root deletion and pending reusable save remain disabled in the extracted view", () => {
  const h = fixture({ canDeleteLayerForId: () => false, reusableActionPendingId: INITIAL_SCENE[0].id, selectedLayerId: INITIAL_SCENE[0].id });
  assert.equal(h.getByRole("button", { name: "删除当前层级", exact: true }).disabled, true);
  assert.equal(h.getByRole("button", { name: "加入节点库", exact: true }).disabled, true);
  assert.ok(h.getByText("Selected editor"));
  h.getByRole("button", { name: "删除当前层级", exact: true }).click();
  assert.deepEqual(h.calls, []);
});
