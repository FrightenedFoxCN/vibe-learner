import { dom } from "./support/dom.js";
import assert from "node:assert/strict";
import { after, afterEach, test } from "node:test";
import { cleanup, fireEvent, render } from "@testing-library/react";
import { PersonaCardView, PersonaProfileCard } from "../components/persona/persona-library-cards.tsx";

afterEach(cleanup);
after(() => dom.window.close());

test("card insertion and dragging report the selected card without deleting it", () => {
  const card = { id: "card-1", title: "Patient", kind: "personality", label: "Personality", tags: [], content: "Explain patiently" };
  const calls = [];
  const view = render(<PersonaCardView card={card} dragging={false} deletePending={false}
    onInsert={value => calls.push(["insert", value])} onDelete={id => calls.push(["delete", id])}
    onDragStart={id => calls.push(["drag", id])} onDragEnd={() => calls.push(["end"])} />);
  fireEvent.click(view.getByRole("button", { name: "插入当前人格", exact: true }));
  const drag = view.getByRole("button", { name: "拖拽插入到左侧人格插槽", exact: true });
  fireEvent.dragStart(drag);
  fireEvent.dragEnd(drag);
  assert.deepEqual(calls, [["insert", card], ["drag", card.id], ["end"]]);
});

test("built-in profiles cannot be deleted and pending user deletion cannot repeat", () => {
  const persona = { id: "mentor", name: "Mentor", source: "builtin", summary: "Teacher", slots: [] };
  const calls = [];
  const props = { persona, isSelected: false, deletePending: false,
    onActivate: value => calls.push(["activate", value]), onDelete: value => calls.push(["delete", value]) };
  const view = render(<PersonaProfileCard {...props} />);
  assert.equal(view.queryByRole("button", { name: "删除", exact: true }), null);
  fireEvent.click(view.getByRole("button", { name: "载入", exact: true }));
  assert.deepEqual(calls, [["activate", persona]]);
  view.rerender(<PersonaProfileCard {...props} persona={{ ...persona, source: "user" }} deletePending />);
  const pending = view.getByRole("button", { name: "删除中", exact: true });
  assert.equal(pending.disabled, true);
  pending.click();
  assert.equal(calls.length, 1);
});
