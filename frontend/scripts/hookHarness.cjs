// Minimal effect/state runner for data hooks, without new test dependencies.
// The caller renders again after async work; React exports are always restored.
const React = require('react');

exports.withHookHarness = async function withHookHarness(run) {
  const original = {};
  const slots = [];
  let cursor = 0;
  let effects = [];
  const changed = (a, b) => !a || !b || a.length !== b.length || a.some((v, i) => !Object.is(v, b[i]));
  const replacements = {
    useState(initial) {
      const index = cursor++;
      if (!slots[index]) slots[index] = { value: typeof initial === 'function' ? initial() : initial };
      return [slots[index].value, value => {
        slots[index].value = typeof value === 'function' ? value(slots[index].value) : value;
      }];
    },
    useRef(initial) {
      const index = cursor++;
      if (!slots[index]) slots[index] = { current: initial };
      return slots[index];
    },
    useCallback(callback, deps) {
      const index = cursor++;
      if (!slots[index] || changed(slots[index].deps, deps)) slots[index] = { value: callback, deps };
      return slots[index].value;
    },
    useEffect(effect, deps) {
      const index = cursor++;
      if (!slots[index] || changed(slots[index].deps, deps)) {
        slots[index]?.cleanup?.();
        slots[index] = { deps };
        effects.push(() => { slots[index].cleanup = effect(); });
      }
    },
  };
  for (const [key, value] of Object.entries(replacements)) {
    original[key] = React[key];
    React[key] = value;
  }
  try {
    await run({
      render(hook) {
        cursor = 0;
        effects = [];
        const result = hook();
        effects.forEach(effect => effect());
        return result;
      },
      settle: () => new Promise(resolve => setImmediate(resolve)),
      unmount() { slots.forEach(slot => slot?.cleanup?.()); },
    });
  } finally {
    slots.forEach(slot => slot?.cleanup?.());
    Object.assign(React, original);
  }
};
