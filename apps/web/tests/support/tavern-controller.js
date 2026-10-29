export function deferred() {
  let resolve, reject;
  const promise = new Promise((yes, no) => {
    resolve = yes;
    reject = no;
  });
  return { promise, resolve, reject };
}
const timestamp = "2026-10-29T00:00:00Z";
export function message(roomId, sequence) {
  return {
    id: `${roomId}-m${sequence}`,
    roomId,
    sequence,
    authorKind: "user",
    content: `message ${sequence}`,
    emotion: "calm",
    addressedParticipantIds: [],
    createdAt: timestamp,
  };
}
export function detail(id = "room-a", revision = 0, sequences = [3, 4]) {
  return {
    room: {
      id,
      title: id,
      status: "active",
      revision,
      lastSequence: sequences.at(-1) ?? 0,
      createdAt: timestamp,
      updatedAt: timestamp,
    },
    participants: ["p1", "p2", "p3"].map((personaId, displayOrder) => ({
      roomId: id,
      personaId,
      displayOrder,
      displayName: personaId,
      personaSnapshot: { id: personaId },
      promptHash: `hash-${personaId}`,
      joinedAt: timestamp,
    })),
    messages: sequences.map((sequence) => message(id, sequence)),
    messageCount: sequences.at(-1) ?? 0,
    nextAfterSequence: null,
    nextBeforeSequence: sequences[0] > 1 ? sequences[0] : null,
  };
}
export function run(roomId, status = "pending", extra = {}) {
  return {
    id: `${roomId}-run`,
    roomId,
    idempotencyKey: "original-key",
    mode: "direct",
    triggerKind: "user_message",
    inputMessageId: null,
    scheduledParticipantIds: ["p1"],
    speakerSteps: [],
    guidance: "",
    status,
    expectedRoomRevision: 0,
    generatedMessageIds: [],
    harnessTrace: [],
    terminalSequence: 4,
    createdAt: timestamp,
    ...extra,
  };
}
export function turnResult(room, status = "completed", extraRun = {}) {
  const inputMessage = message(room.room.id, room.room.lastSequence + 1);
  return {
    run: run(room.room.id, status, {
      terminalSequence: inputMessage.sequence,
      ...extraRun,
    }),
    inputMessage,
    generatedMessages: [],
    roomState: {
      ...room.room,
      revision: room.room.revision + 1,
      lastSequence: inputMessage.sequence,
    },
  };
}
export function fakeClock() {
  let now = 0,
    sequence = 0;
  const timers = new Map();
  const schedule = (callback, delay, repeat) => {
    const id = ++sequence;
    timers.set(id, { callback, at: now + delay, repeat });
    return id;
  };
  return {
    setTimeout: (callback, delay) => schedule(callback, delay, 0),
    clearTimeout: (id) => timers.delete(id),
    setInterval: (callback, delay) => schedule(callback, delay, delay),
    clearInterval: (id) => timers.delete(id),
    tick(delay) {
      const end = now + delay;
      for (;;) {
        const [id, timer] =
          [...timers]
            .filter(([, value]) => value.at <= end)
            .sort((a, b) => a[1].at - b[1].at)[0] ?? [];
        if (!timer) break;
        now = timer.at;
        if (timer.repeat) timer.at += timer.repeat;
        else timers.delete(id);
        timer.callback();
      }
      now = end;
    },
    get pending() {
      return timers.size;
    },
  };
}
export function environment() {
  const roomDrafts = new Map(),
    remembered = [],
    calls = [],
    handlers = {};
  let creation = null,
    key = 0;
  const data = {
    rooms: new Map([
      ["room-a", detail()],
      ["room-b", detail("room-b")],
    ]),
    runs: new Map(),
    chains: new Map(),
    cursor: null,
  };
  const clock = fakeClock();
  const storage = {
    readActiveTavernRoomId: () => "",
    rememberActiveTavernRoomId: (id) => remembered.push(id),
    readTavernCreationDraft: () => structuredClone(creation),
    writeTavernCreationDraft: (value) => {
      creation = structuredClone(value);
    },
    readTavernRoomDraft: (id) =>
      structuredClone(roomDrafts.get(id) ?? { message: "", guidance: "" }),
    writeTavernRoomDraft: (id, draft) =>
      roomDrafts.set(id, structuredClone(draft)),
  };
  const names = [
    "getTavernRoom",
    "getTavernRunRecovery",
    "listTavernRooms",
    "listTavernRuns",
    "listPersonas",
    "listSceneLibrary",
    "runTavernTurn",
    "retryTavernRun",
    "resumeTavernRun",
    "cancelTavernRun",
    "createTavernRoom",
    "updateTavernRoom",
  ];
  const api = Object.fromEntries(
    names.map((name) => [
      name,
      async (...args) => {
        calls.push({ name, args });
        if (handlers[name]) return handlers[name](...args);
        if (name === "getTavernRoom")
          return structuredClone(data.rooms.get(args[0].roomId));
        if (name === "listTavernRuns")
          return structuredClone(data.runs.get(args[0]) ?? []);
        if (name === "getTavernRunRecovery")
          return structuredClone(data.chains.get(args[0]) ?? []);
        if (name === "listPersonas")
          return ["p1", "p2", "p3"].map((id) => ({ id, name: id }));
        if (name === "listSceneLibrary") return [];
        if (name === "listTavernRooms")
          return {
            nextCursor: data.cursor,
            items: [...data.rooms.values()].map(
              ({ room, participants, messageCount }) => ({
                ...room,
                participantPersonaIds: participants.map((p) => p.personaId),
                participantNames: participants.map((p) => p.displayName),
                messageCount,
              }),
            ),
          };
        throw new Error(`unconfigured mutation ${name}`);
      },
    ]),
  );
  return {
    data,
    calls,
    handlers,
    remembered,
    roomDrafts,
    clock,
    storage,
    ports: {
      api,
      clock,
      storage,
      makeRequestKey: (scope) => `${scope}-test-${++key}`,
    },
  };
}
