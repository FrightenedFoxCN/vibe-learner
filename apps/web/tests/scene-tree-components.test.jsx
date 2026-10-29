import { dom } from "./support/dom.js";
import assert from "node:assert/strict";
import { after, afterEach, test } from "node:test";
import { cleanup, fireEvent, render, within } from "@testing-library/react";
import { SceneProposalPreview } from "../components/scene/scene-proposal-preview.tsx";
import { SceneLayerCard } from "../components/scene/scene-tree-components.tsx";
import { INITIAL_SCENE } from "../lib/scene-editor-model.ts";

afterEach(cleanup);
after(() => dom.window.close());
function fixture(overrides = {}) {
  const calls = [];
  const layer = INITIAL_SCENE[0];
  const props = {
    layer,
    index: 0,
    selectedLayerId: "",
    selectedObjectId: "",
    reusableActionPendingId: "",
    onSelect: (id) => calls.push(["select", id]),
    onToggleEditor: (id) => calls.push(["toggle", id]),
    onAddChild: (id) => calls.push(["add", id]),
    onAddObject() {},
    onSaveToReusable() {},
    onSelectObject() {},
    onSaveObjectToReusable() {},
    onRemoveObject() {},
    onRequestDelete: (id) => calls.push(["delete", id]),
    canDeleteLayerForId: () => true,
    editorContent: <p>Selected editor</p>,
    renderObjectEditor: () => null,
    ...overrides,
  };
  const view = render(<SceneLayerCard {...props} />);
  const card = within(
    view.getByRole("heading", { name: layer.title, exact: true }).closest("article"),
  );
  return { ...view, getByRole: card.getByRole, calls, layer, props };
}

test("tree action controls do not bubble into selecting another editor", () => {
  const h = fixture();
  fireEvent.click(h.getByRole("button", { name: "添加子层", exact: true }));
  fireEvent.click(h.getByRole("button", { name: "删除当前层级", exact: true }));
  assert.deepEqual(h.calls, [
    ["add", h.layer.id],
    ["delete", h.layer.id],
  ]);
  fireEvent.click(h.getByRole("heading", { name: h.layer.title, exact: true }));
  assert.deepEqual(h.calls.at(-1), ["select", h.layer.id]);
});

test("protected root deletion and pending reusable save remain disabled in the extracted view", () => {
  const h = fixture({
    canDeleteLayerForId: () => false,
    reusableActionPendingId: INITIAL_SCENE[0].id,
    selectedLayerId: INITIAL_SCENE[0].id,
  });
  assert.equal(
    h.getByRole("button", { name: "删除当前层级", exact: true }).disabled,
    true,
  );
  assert.equal(
    h.getByRole("button", { name: "加入节点库", exact: true }).disabled,
    true,
  );
  assert.ok(h.getByText("Selected editor"));
  h.getByRole("button", { name: "删除当前层级", exact: true }).click();
  assert.deepEqual(h.calls, []);
});

test("controlled tree disclosure hides descendants without selecting or deleting the node", () => {
  const toggled = [];
  const layer = INITIAL_SCENE[0];
  const h = fixture({
    collapsedLayerIds: [layer.id],
    onToggleChildren: (id) => toggled.push(id),
  });
  assert.equal(
    h.queryByRole("heading", { name: layer.children[0].title, exact: true }),
    null,
  );
  const toggle = h.getByRole("button", {
    name: `展开${layer.title}的子层和物体`,
    exact: true,
  });
  assert.equal(toggle.getAttribute("aria-expanded"), "false");
  fireEvent.click(toggle);
  assert.deepEqual(toggled, [layer.id]);
  assert.deepEqual(h.calls, []);
  h.rerender(<SceneLayerCard {...h.props} collapsedLayerIds={[]} />);
  assert.ok(h.queryByRole("heading", { name: layer.children[0].title, exact: true }));
});

test("scene proposal review exposes removed hierarchy, rule changes and added objects without equating generated IDs", () => {
  const current = [
    {
      ...INITIAL_SCENE[0],
      id: "old",
      title: "教室",
      rules: "保持安静",
      children: [],
      objects: [],
    },
  ];
  const proposed = [
    {
      ...current[0],
      id: "new",
      rules: "允许讨论",
      objects: [
        {
          id: "desk",
          name: "实验桌",
          description: "耐热桌面",
          interaction: "放置试管",
        },
      ],
    },
    { ...current[0], id: "hall", title: "走廊" },
  ];
  const view = render(<SceneProposalPreview current={current} proposed={proposed} />);
  assert.match(view.container.textContent, /层级：1 → 2；物体：0 → 1/);
  assert.match(view.container.textContent, /保留路径：1. 教室/);
  assert.match(view.container.textContent, /新增层级：2. 走廊/);
  assert.match(view.container.textContent, /保持安静.*允许讨论/);
  assert.match(view.container.textContent, /实验桌：耐热桌面；交互：放置试管/);
  view.rerender(<SceneProposalPreview current={proposed} proposed={current} />);
  assert.match(view.container.textContent, /移除：2. 走廊/);
});

test("scene proposal review exposes full fields and deterministic structural conflicts", () => {
  const current = [
    {
      ...INITIAL_SCENE[0],
      id: "old",
      reuseId: "layer-a",
      title: "教室",
      atmosphere: "安静",
      objects: [
        {
          id: "old-object",
          name: "讲台",
          description: "木质",
          interaction: "查看",
          tags: "教学",
          reuseId: "object-a",
          reuseHint: "",
        },
      ],
      children: [],
    },
  ];
  const proposed = [
    {
      ...current[0],
      id: "new",
      reuseId: "layer-a",
      atmosphere: "嘈杂",
      objects: [
        {
          ...current[0].objects[0],
          id: "new-object",
          description: "金属",
          interaction: "移动",
          tags: "实验",
          reuseId: "object-a",
        },
        {
          ...current[0].objects[0],
          id: "duplicate-object",
          name: "讲台",
          reuseId: "object-b",
        },
      ],
      children: [],
    },
    {
      ...current[0],
      id: "other",
      title: "走廊",
      reuseId: "layer-a",
      objects: [],
      children: [],
    },
  ];
  const view = render(<SceneProposalPreview current={current} proposed={proposed} />);
  assert.match(view.container.textContent, /发现 2 个结构约束冲突候选/);
  assert.match(view.container.textContent, /复用引用 layer-a/);
  assert.match(view.container.textContent, /重复物体名称/);
  assert.match(view.container.textContent, /氛围：安静.*嘈杂/);
  assert.match(view.container.textContent, /描述：木质.*金属/);
  assert.match(view.container.textContent, /交互：查看.*移动/);
  assert.match(view.container.textContent, /标签：教学.*实验/);
});

test("scene proposal review flags explicit parent and child rule polarity conflicts", () => {
  const layers = [
    {
      ...INITIAL_SCENE[0],
      rules: "实验室禁止进入",
      children: [{ ...INITIAL_SCENE[0].children[0], rules: "实验室允许进入" }],
    },
  ];
  const view = render(<SceneProposalPreview current={[]} proposed={layers} />);
  assert.match(view.container.textContent, /规则“实验室 进入”与父级/);
  assert.match(view.container.textContent, /禁止约束冲突/);
});
