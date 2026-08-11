/** Wiring: state in, views out, plus the two things that keep running — the
 *  five-second clock tick and the scroll listener that decides what is lit. */

import { clear, el } from './dom.js';
import { formatClock, pacing } from './clock.js';
import { paintRegions, renderDetail } from './detail.js';
import { trackFocus } from './focus.js';
import { linkRegions } from './regions.js';
import { buildRoute } from './route.js';
import { paintSetup, renderSetup } from './setup.js';
import { PHASE, REGIONS, load, persist } from './state.js';
import { paintChrome, renderTour } from './tour.js';

/** How often the header re-reads the clock. A minute display needs no more. */
const TICK_MS = 5000;

const root = document.getElementById('app');
const state = load();

let works = [];
let route = null;
let detachFocus = null;
let justify = null;

/** Every view change is a history entry, so Back closes the detail sheet and
 *  steps out of the timeline the way it would on any other page. Scroll is
 *  carried on the entry too: the line is rebuilt on the way back, and a rebuilt
 *  document would otherwise drop the visitor at the top of it. */
function show(view, { replace = false } = {}) {
  const entry = { ...view, scroll: window.scrollY || 0 };

  history.replaceState({ ...history.state, scroll: entry.scroll }, '');
  Object.assign(state, view);
  persist(state);
  history[replace ? 'replaceState' : 'pushState'](entry, '');
  render();
}

const actions = {
  /** Constraints only ever change on the setup screen, and that screen repaints
   *  itself rather than being rebuilt — see `paintSetup`. */
  update(mutate) {
    mutate(state);
    persist(state);
    paintSetup(state, works);
  },

  start() {
    state.started = Date.now();
    state.active = 1;
    show({ phase: PHASE.tour, open: null });
    window.scrollTo(0, 0);
  },

  edit() {
    show({ phase: PHASE.setup, open: null });
    window.scrollTo(0, 0);
  },

  restart() {
    state.started = 0;
    show({ phase: PHASE.setup, open: null });
    window.scrollTo(0, 0);
  },

  openDetail(objectNumber) {
    show({ phase: state.phase, open: objectNumber });
  },

  closeDetail() {
    if (history.state?.open) history.back();
    else show({ phase: state.phase, open: null }, { replace: true });
  },

  /** Not a view change and not a history entry: the sheet stays exactly where it
   *  is and the stylesheet reads the new value off it. */
  toggleRegions() {
    state.regions = state.regions === REGIONS.on ? REGIONS.off : REGIONS.on;
    persist(state);
    paintRegions(state.regions);
  },
};

function focusedStop() {
  const stops = route.items.filter((item) => item.kind === 'stop');

  return stops.find((stop) => stop.number === state.active) ?? stops[0] ?? null;
}

function tick() {
  if (state.phase !== PHASE.tour || !route) return;

  const stop = focusedStop();
  const now = Date.now();

  paintChrome({
    here: stop
      ? `${stop.number}/${route.stopCount} · Room ${stop.work.gallery.room}`
      : 'Atrium',
    nudge: pacing({ started: state.started, now }, stop, route),
    clock: formatClock(new Date(now)),
    progress: Math.round(((stop?.number ?? 0) / Math.max(1, route.stopCount)) * 100),
  });
}

/** Knuth–Plass justification over the running prose, once the DOM settles. */
async function applyJustification() {
  justify?.destroy();
  justify = null;

  const paragraphs = root.querySelectorAll('.body-text, .sheet-body p');

  if (!paragraphs.length) return;

  try {
    const [{ justify: run }, { hyphenateEnUS }] = await Promise.all([
      import('../vendor/justif/index.js'),
      import('../vendor/justif/hyphenate/en-us.js'),
    ]);

    justify = run(paragraphs, { hyphenate: hyphenateEnUS });
  } catch (error) {
    // Justification is an enhancement over the browser's own; losing it is survivable.
    console.warn('justif unavailable', error);
  }
}

function render() {
  detachFocus?.();
  detachFocus = null;

  clear(root);

  const open = state.open && works.find((work) => work.objectNumber === state.open);

  if (state.phase === PHASE.setup) {
    root.append(renderSetup(state, works, actions));
  } else {
    route = buildRoute(works, state);
    root.append(renderTour(state, route, actions));
  }

  // The sheet's own listeners go with it when the next render clears the root,
  // so unlike the focus tracker below there is nothing to detach.
  if (open) {
    const sheet = renderDetail(open, state, actions);

    root.append(sheet);
    linkRegions(sheet);
  }

  document.body.style.overflow = open ? 'hidden' : '';

  if (state.phase === PHASE.tour && !open) {
    detachFocus = trackFocus(root, (number) => {
      state.active = number;
      tick();
    });
  }

  tick();
  applyJustification();
}

window.addEventListener('keydown', (event) => {
  if (event.key === 'Escape' && state.open) actions.closeDetail();
});

window.addEventListener('popstate', (event) => {
  Object.assign(state, event.state ?? { phase: state.phase, open: null });
  persist(state);
  render();
  window.scrollTo(0, event.state?.scroll ?? 0);
});

setInterval(tick, TICK_MS);

// Scroll is restored from the history entry, not by the browser, because the
// view is rebuilt on every entry and the document is briefly empty.
history.scrollRestoration = 'manual';
history.replaceState({ phase: state.phase, open: state.open, scroll: 0 }, '');

fetch('data/tour.json')
  .then((response) => response.json())
  .then((loaded) => {
    works = loaded;
    render();
  })
  .catch(() => {
    root.append(el('div', { class: 'setup' },
      el('h1', { text: 'The guide could not load its data' }),
      el('p', { class: 'setup-intro' },
        'data/tour.json is missing. Run ', el('code', { text: 'just build' }),
        ' to regenerate it.')));
  });
