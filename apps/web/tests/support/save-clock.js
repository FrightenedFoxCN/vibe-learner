export function saveClock() {
  let now = 0, next = 0;
  const timers = new Map();
  return {
    schedule(callback, delay) { const id = ++next; timers.set(id, { at: now + delay, callback }); return id; },
    cancel(id) { timers.delete(id); },
    tick(ms) {
      now += ms;
      for (const [id, timer] of timers) if (timer.at <= now) { timers.delete(id); timer.callback(); }
    },
  };
}
export function saveRequests() {
  const requests = [];
  return {
    requests,
    persist: snapshot => new Promise((resolve, reject) => {
      requests.push({ snapshot, resolve: (value = snapshot) => resolve(value), reject });
    }),
  };
}
export const settleSave = () => new Promise(resolve => setImmediate(resolve));
