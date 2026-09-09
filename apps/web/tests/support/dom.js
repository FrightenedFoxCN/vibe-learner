import { JSDOM } from "jsdom";

// Each node:test file runs in its own process; no browser/API service is needed.
export function installDOM() {
  const dom = new JSDOM("<!doctype html><html><body></body></html>", { url: "http://localhost/" });
  for (const name of ["window", "document", "navigator", "HTMLElement", "Node", "Event", "MouseEvent"]) {
    Object.defineProperty(globalThis, name, { configurable: true, value: dom.window[name] });
  }
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  return dom;
}

export const dom = installDOM();
