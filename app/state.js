/** Application state, its one localStorage key, and the theme.
 *
 *  A visit that has started survives a reload — the phone will lock, the browser
 *  will be closed, and the clock has to keep meaning what it meant. */

const KEY = 'rijks-guide-v1';

export const PHASE = Object.freeze({ setup: 'setup', tour: 'tour' });
export const THEME = Object.freeze({ auto: 'auto', light: 'light', dark: 'dark' });

/** The four budgets offered on the setup screen, in minutes. */
export const BUDGETS = [60, 90, 120, 180];

const defaults = () => ({
  phase: PHASE.setup,
  minutes: 120,
  focus: [],
  kids: false,
  stepFree: false,
  started: 0,
  theme: THEME.auto,
  open: null,
  active: 1,
});

const PERSISTED = ['minutes', 'focus', 'kids', 'stepFree', 'started', 'theme'];

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

export const prefersDark = () =>
  window.matchMedia?.('(prefers-color-scheme: dark)').matches ?? false;

export const resolveTheme = (theme) =>
  theme === THEME.auto ? (prefersDark() ? THEME.dark : THEME.light) : theme;

export function applyTheme(state) {
  document.documentElement.dataset.theme = resolveTheme(state.theme);
}

/** The label of the theme button, which names the theme it switches *to*. */
export const themeLabel = (state) =>
  resolveTheme(state.theme) === THEME.dark ? 'Light' : 'Dark';

export const nextTheme = (state) =>
  resolveTheme(state.theme) === THEME.dark ? THEME.light : THEME.dark;
