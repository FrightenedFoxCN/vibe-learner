import assert from "node:assert/strict";
import test from "node:test";
import { advanceStudySchedule } from "../lib/study-schedule-advance.ts";

const advance = { planId: "plan", currentId: "one", nextId: "two" };

function fixture(results: boolean[]) {
  const events: unknown[] = [];
  const actions: Parameters<typeof advanceStudySchedule>[1] = {
    update: async ({ scheduleIds, status }) => {
      events.push([scheduleIds[0], status]);
      return results.shift() ?? false;
    },
    isCurrent: () => true,
    navigate: async (id) => {
      events.push(["navigate", id]);
    },
    onPartial: (pending) => {
      events.push(pending);
    },
  };
  return { events, actions };
}

test("a failed next update keeps the selection; retry only writes the next item", async () => {
  const { events, actions } = fixture([true, false, true]);
  await advanceStudySchedule(advance, actions);
  assert.deepEqual(events, [["one", "completed"], ["two", "in_progress"], advance]);
  await advanceStudySchedule(advance, actions, true);
  assert.deepEqual(events.slice(3), [
    ["two", "in_progress"],
    null,
    ["navigate", "two"],
  ]);
});

test("last item or rejected completion does not start or navigate to another item", async () => {
  for (const [nextId, success] of [
    ["", true],
    ["two", false],
  ] as const) {
    const { events, actions } = fixture([success]);
    await advanceStudySchedule({ ...advance, nextId }, actions);
    assert.deepEqual(events, [["one", "completed"]]);
  }
});

test("a late completion cannot advance after the selection changes", async () => {
  const { events, actions } = fixture([true]);
  actions.isCurrent = () => events.length === 0;
  await advanceStudySchedule(advance, actions);
  assert.deepEqual(events, [["one", "completed"]]);
});
