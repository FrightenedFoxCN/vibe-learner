const assert = require('node:assert/strict');
const test = require('node:test');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const ts = require('typescript');

// Execute the production save/effect bodies with a controlled effect lifecycle
// and transport. No copied save algorithm; full browser coverage stays separate.
const source = fs.readFileSync(path.join(__dirname, '../components/settings/use-settings-controller.ts'), 'utf8');
const start = source.indexOf('  const persistSnapshot = useEffectEvent(');
const end = source.indexOf('\n  function setSettingField', start);
assert.ok(start > 0 && end > start);
const code = ts.transpileModule(`(() => {${source.slice(start, end)}\n})()`, {
  compilerOptions: { target: ts.ScriptTarget.ES2022 },
}).outputText;

function harness() {
  let now = 0;
  let timerId = 0;
  const timers = new Map();
  let effects = [];
  let nextEffects = [];
  const requests = [];
  const ctx = {
    useEffectEvent: callback => (...args) => callback(...args),
    useEffect: (create, deps) => nextEffects.push({create, deps}),
    savingRef: {current: false}, flushRequestedRef: {current: false},
    pendingSaveRef: {current: null}, initializedRef: {current: true},
    desktopSecurityRef: {current: {enabled: false}},
    lastSavedSerializedRef: {current: JSON.stringify({value: 'initial'})},
    blockedSerializedRef: {current: ''}, settingsRef: {current: null},
    settings: {value: 'initial'}, isSaving: false,
    setIsSaving: value => { ctx.isSaving = value; },
    setSavePhase: () => {}, setSaveError: () => {}, setLastSavedAt: () => {},
    setSettings: value => {ctx.settings = value;}, setNumericDrafts: () => {},
    runtimeSettings: {loading: false, replaceSettings: () => {}},
    serializeSettings: JSON.stringify, buildNumericDrafts: x => x,
    buildRuntimeSettingsPatch: x => x,
    updateRuntimeSettings: snapshot => new Promise((resolve, reject) => {
      requests.push({snapshot, resolve: () => resolve(snapshot), reject});
    }),
    AUTO_SAVE_DELAY_MS: 900,
    window: {
      addEventListener: () => {}, removeEventListener: () => {},
      setTimeout: (callback, delay) => {timers.set(++timerId, {at: now + delay, callback}); return timerId;},
      clearTimeout: id => timers.delete(id),
    },
  };
  vm.createContext(ctx);
  function render(value) {
    if (value !== undefined) ctx.settings = {value};
    ctx.settingsRef.current = ctx.settings;
    nextEffects = [];
    vm.runInContext(code, ctx);
    const changed = nextEffects.map((e, i) => !effects[i] ||
      e.deps.length !== effects[i].deps.length || e.deps.some((d, j) => !Object.is(d, effects[i].deps[j])));
    effects.forEach((e, i) => { if (changed[i]) e.cleanup?.(); });
    effects = nextEffects.map((e, i) => changed[i] ? {...e, cleanup: e.create()} : effects[i]);
  }
  function tick(ms) {
    now += ms;
    for (const [id, timer] of timers) if (timer.at <= now) {
      timers.delete(id); timer.callback();
    }
  }
  render();
  return {ctx, render, tick, requests, unmount: () => effects.forEach(e => e.cleanup?.())};
}
const settle = () => new Promise(resolve => setImmediate(resolve));

test('settings preserve 900ms debounce across unrelated renders and rapid edits', () => {
  const h = harness();
  h.render('A');
  h.render(); // same settings, fresh Effect Event wrappers
  h.tick(899);
  assert.equal(h.requests.length, 0);
  h.render('B');
  h.tick(899);
  assert.equal(h.requests.length, 0);
  h.tick(1);
  assert.deepEqual(h.requests.map(r => r.snapshot.value), ['B']);
});

test('settings navigation flush saves the latest edit after an in-flight save', async () => {
  const h = harness();
  h.render('A'); h.tick(900);
  h.render('B'); h.render('C'); h.unmount();
  assert.deepEqual(h.requests.map(r => r.snapshot.value), ['A']);
  h.requests[0].resolve(); await settle();
  assert.deepEqual(h.requests.map(r => r.snapshot.value), ['A', 'C']);
  h.requests[1].resolve(); await settle();
  assert.equal(h.ctx.pendingSaveRef.current, null);
  assert.equal(h.ctx.savingRef.current, false);
});

test('settings navigation flush continues after older request fails without retrying it', async () => {
  const h = harness();
  h.render('A'); h.tick(900); h.render('B'); h.unmount();
  h.requests[0].reject(new Error('offline')); await settle();
  assert.deepEqual(h.requests.map(r => r.snapshot.value), ['A', 'B']);
  h.requests[1].reject(new Error('offline')); await settle();
  assert.equal(h.requests.length, 2);
});

test('reverting to the saved value clears an unsent edit before navigation', () => {
  const h = harness();
  h.render('A'); h.render('initial'); h.unmount();
  assert.equal(h.requests.length, 0);
});

test('reverting while saving still restores the original value after navigation', async () => {
  const h = harness();
  h.render('A'); h.tick(900); h.render('initial'); h.unmount();
  h.requests[0].resolve(); await settle();
  assert.deepEqual(h.requests.map(r => r.snapshot.value), ['A', 'initial']);
});
