/** Application state and its one localStorage key.
 *
 *  A visit that has started survives a reload — the phone will lock, the browser
 *  will be closed, and the clock has to keep meaning what it meant. */

const KEY = 'rijks-guide-v1';

export const PHASE = Object.freeze({ setup: 'setup', tour: 'tour' });

/** Whether the detail sheet joins its prose to the parts of the work it names.
 *  The stylesheet reads this off the sheet, so it is a word rather than a flag. */
export const REGIONS = Object.freeze({ on: 'on', off: 'off' });

/** The four budgets offered on the setup screen, in minutes. */
export const BUDGETS = [60, 90, 120, 180];

const defaults = () => ({
  phase: PHASE.setup,
  minutes: 120,
  focus: [],
  kids: false,
  stepFree: false,
  started: 0,
  open: null,
  active: 1,
  regions: REGIONS.on,
});

const PERSISTED = ['minutes', 'focus', 'kids', 'stepFree', 'started', 'regions'];

export function load() {
  const state = defaults();

  try {
    const saved = JSON.parse(localStorage.getItem(KEY) || '{}');

    for (const key of PERSISTED) {
      if (saved[key] !== undefined) state[key] = saved[key];
    }
  } catch {
    // A corrupt or unavailable store is not worth failing the visit over.
  }

  state.phase = state.started ? PHASE.tour : PHASE.setup;

  return state;
}

export function persist(state) {
  try {
    localStorage.setItem(KEY, JSON.stringify(
      Object.fromEntries(PERSISTED.map((key) => [key, state[key]]))));
  } catch {
    // Private browsing refuses writes; the visit still works, it just will not resume.
  }
}
