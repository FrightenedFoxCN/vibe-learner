import { dom } from "./support/dom.js";
import React from "react";
import assert from "node:assert/strict";
import { after, afterEach, test } from "node:test";
import { act, cleanup, fireEvent, render } from "@testing-library/react";
import {
  InteractionComposer,
  ParticipantRoster,
  TavernSessionPanel,
  TavernConversationPanel,
} from "../components/tavern-workspace-panels.tsx";
import { deferred, detail, environment, message } from "./support/tavern-controller.js";

afterEach(cleanup);
after(() => dom.window.close());
const frames = new Map();
let frame = 0;
window.requestAnimationFrame = (callback) => {
  const id = ++frame;
  frames.set(id, callback);
  return id;
};
window.cancelAnimationFrame = (id) => frames.delete(id);
afterEach(() => frames.clear());
function flushFrames() {
  for (const [id, callback] of frames) {
    frames.delete(id);
    callback(0);
  }
}
function composer(overrides = {}) {
  const env = environment();
  return {
    roomId: "room-a",
    roomAvailable: true,
    roomActive: true,
    participants: detail().participants,
    selectedIds: ["p2", "p1"],
    latestMessage: message("room-a", 4),
    recovery: null,
    busy: false,
    recoveryBusy: false,
    retrying: false,
    canCancel: false,
    canceling: false,
    storage: env.storage,
    onTurn: async () => false,
    onCancel: async () => false,
    onRetry: () => {},
    ...overrides,
  };
}

test("Composer uses roster order and respects Enter, Shift+Enter and composition trailing events", async () => {
  const writes = [],
    props = composer({
      onTurn: async (...args) => {
        writes.push(args);
        return false;
      },
    });
  const view = render(<InteractionComposer {...props} />);
  assert.match(view.container.textContent, /本轮回应：p1 → p2/);
  const input = view.getByRole("textbox", { name: "你的消息", exact: true });
  fireEvent.change(input, { target: { value: "hello" } });
  fireEvent.keyDown(input, { key: "Enter", shiftKey: true });
  fireEvent.compositionStart(input);
  fireEvent.keyDown(input, { key: "Enter", isComposing: true });
  fireEvent.compositionEnd(input);
  fireEvent.keyDown(input, { key: "Enter" });
  fireEvent.keyDown(input, { key: "Enter", keyCode: 229 });
  assert.equal(writes.length, 0);
  await act(async () => {
    fireEvent.keyDown(input, { key: "Enter" });
  });
  assert.equal(writes.length, 1);
  assert.equal(writes[0][0].content, "hello");
  assert.equal(input.value, "hello");
});

test("active retry recipients override next-round selection and clear back to that selection after completion", () => {
  const props = composer({
    selectedIds: ["p1"],
    activeReplyIds: ["p2"],
    busy: true,
    retrying: true,
  });
  const view = render(<InteractionComposer {...props} />);
  assert.match(view.container.textContent, /本轮回应：p2/);
  view.rerender(
    <InteractionComposer
      {...props}
      activeReplyIds={[]}
      busy={false}
      retrying={false}
    />,
  );
  assert.match(view.container.textContent, /本轮回应：p1/);
});

test("Roster labels a selected actor outside the in-flight retry as a next-round target", () => {
  const participants = detail().participants;
  const view = render(
    <ParticipantRoster
      states={participants.map((participant, index) => ({
        participant,
        state: index ? "generating" : "idle",
      }))}
      selectedIds={["p1"]}
      activeReplyIds={["p2"]}
      disabled
      onToggle={() => assert.fail("disabled selection")}
    />,
  );
  const next = view.getByRole("checkbox", { name: /p1/ });
  assert.match(next.closest("label").textContent, /下轮目标/);
  assert.equal(next.disabled, true);
});

test("Composer focuses cleared input only after confirmation settles and cancels focus on unmount", async () => {
  const pending = deferred();
  const props = composer({ onTurn: () => pending.promise });
  const view = render(<InteractionComposer {...props} />);
  const input = view.getByRole("textbox", { name: "你的消息", exact: true });
  fireEvent.change(input, { target: { value: "hello" } });
  fireEvent.click(view.getByRole("button", { name: /发送并回应/ }));
  view.rerender(<InteractionComposer {...props} busy />);
  await act(async () => pending.resolve(true));
  assert.equal(input.value, "");
  assert.equal(frames.size, 0);
  view.rerender(<InteractionComposer {...props} />);
  act(flushFrames);
  assert.equal(document.activeElement, input);
  assert.equal(props.storage.readTavernRoomDraft("room-a").message, "");
  fireEvent.change(input, { target: { value: "again" } });
  await act(async () =>
    fireEvent.click(view.getByRole("button", { name: /发送并回应/ })),
  );
  assert.ok(frames.size);
  view.unmount();
  assert.equal(frames.size, 0);
});

test("Session Panel exposes paging errors, disables pending pagination and preserves room identity", () => {
  const opened = [],
    props = {
      rooms: [{ ...detail().room, participantNames: ["p1"], messageCount: 4 }],
      activeRoomId: "room-a",
      busy: false,
      hasMore: true,
      loadingMore: true,
      historyTruncated: false,
      pageError: "retry the page",
      onOpen: (id) => opened.push(id),
      onLoadMore: () => assert.fail("disabled pagination"),
    };
  const view = render(<TavernSessionPanel {...props} />);
  assert.equal(view.getByRole("alert").textContent, "retry the page");
  assert.equal(view.getByRole("button", { name: /正在载入/ }).disabled, true);
  fireEvent.click(view.getByRole("button", { name: /room-a/ }));
  assert.deepEqual(opened, ["room-a"]);
  view.rerender(
    <TavernSessionPanel
      {...props}
      hasMore={false}
      loadingMore={false}
      historyTruncated
    />,
  );
  assert.match(view.container.textContent, /已显示最近 100 个房间/);
});

test("empty Conversation names the next action without referring to desktop placement", () => {
  const view = render(
    <TavernConversationPanel
      room={null}
      participants={[]}
      messages={[]}
      messageCount={0}
      hasOlder={false}
      loading={false}
      loadingOlder={false}
      olderDisabled={false}
      onLoadOlder={async () => false}
    />,
  );
  assert.match(view.container.textContent, /先创建或打开一个酒馆，然后开始对话/);
  assert.doesNotMatch(view.container.textContent, /左侧/);
});
