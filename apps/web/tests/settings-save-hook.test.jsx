import { dom } from "./support/dom.js";
import assert from "node:assert/strict";
import { after, afterEach, test } from "node:test";
import { useEffect } from "react";
import { act, cleanup, renderHook } from "@testing-library/react";
import { useSettingsSave } from "../hooks/use-settings-save.ts";
import { saveClock, saveRequests, settleSave } from "./support/save-clock.js";

afterEach(cleanup);
after(() => dom.window.close());
function fixture() {
  const clock = saveClock(), transport = saveRequests(), statuses = [], saved = [];
  const view = renderHook(({ value }) => {
    const coordinator = useSettingsSave({ value }, true, {
      serialize: JSON.stringify, persist: transport.persist,
      saved: value => saved.push(value), status: phase => statuses.push(phase),
    }, 900, clock);
    useEffect(() => { coordinator.acceptSaved({ value: "initial" }); }, [coordinator]);
    return coordinator;
  }, { initialProps: { value: "initial" } });
  return { ...view, clock, ...transport, statuses, saved };
}

test("real Hook rerenders preserve debounce and pagehide flushes the latest snapshot", () => {
  const h = fixture();
  h.rerender({ value: "A" }); h.clock.tick(400); h.rerender({ value: "A" });
  h.clock.tick(499); assert.equal(h.requests.length, 0);
  act(() => { window.dispatchEvent(new window.Event("pagehide")); });
  assert.deepEqual(h.requests.map(r => r.snapshot.value), ["A"]);
});

test("unmount drains latest pending save and suppresses local status updates", async () => {
  const h = fixture(); h.rerender({ value: "A" }); h.clock.tick(900);
  h.rerender({ value: "B" }); h.unmount();
  const statuses = [...h.statuses];
  await act(async () => { h.requests[0].resolve(); await settleSave(); });
  assert.deepEqual(h.requests.map(r => r.snapshot.value), ["A", "B"]);
  await act(async () => { h.requests[1].resolve(); await settleSave(); });
  assert.deepEqual(h.statuses, statuses);
  assert.deepEqual(h.saved.map(item => item.value), ["A", "B"]);
});
