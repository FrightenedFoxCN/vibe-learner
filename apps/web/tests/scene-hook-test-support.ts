import assert from "node:assert/strict";
import { createElement, act } from "react";
import { createRoot } from "react-dom/client";

// The harness renders no DOM nodes: only the React root, hooks and effects run.
export async function mountSceneHook<T>(useValue: () => T) {
  const view = new EventTarget();
  const document = Object.assign(new EventTarget(), { nodeType: 9, defaultView: view });
  Object.assign(view, { document, HTMLIFrameElement: class {}, innerWidth: 1440 });
  const container = Object.assign(new EventTarget(), {
    nodeType: 1,
    tagName: "DIV",
    ownerDocument: document,
    textContent: "",
  });
  const globals = { window: view, document, IS_REACT_ACT_ENVIRONMENT: true };
  const descriptors = Object.keys(globals).map(
    (key) => [key, Object.getOwnPropertyDescriptor(globalThis, key)] as const,
  );
  for (const [key, value] of Object.entries(globals))
    Object.defineProperty(globalThis, key, { configurable: true, value });
  const root = createRoot(container as unknown as HTMLElement);
  let current: { value: T } | undefined;
  function Probe() {
    current = { value: useValue() };
    return null;
  }
  async function unmount() {
    try {
      await act(() => root.unmount());
    } finally {
      for (const [key, descriptor] of descriptors) {
        if (descriptor) Object.defineProperty(globalThis, key, descriptor);
        else Reflect.deleteProperty(globalThis, key);
      }
    }
  }
  try {
    await act(async () => root.render(createElement(Probe)));
  } catch (error) {
    await unmount();
    throw error;
  }
  return {
    current: () => {
      assert.ok(current);
      return current.value;
    },
    unmount,
  };
}
