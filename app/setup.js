/** The screen the visit is composed on, in either of the two flows.
 *
 *  In the guided flow the visitor states constraints and the guide chooses the
 *  works; in the picking flow the visitor chooses the works and the guide only
 *  walks them. One of the two is on the screen and the other is not on it at
 *  all: the switch swaps the body of the form, and the contact sheet below
 *  changes what a tap on a work means.
 *
 *  Below both, every work the guide knows — lit or dimmed by whether the plan
 *  as it stands reaches it, or marked by whether the visitor has picked it. */

import { clear, el } from './dom.js';
import { plate } from './plate.js';
import { BUDGETS, MODE } from './state.js';
import {
  ARTIST_TAGS, THEME_TAGS, focusLabel, inRouteOrder, onTheLine, overBy, routeFor,
} from './route.js';

const BUDGET_LABELS = new Map([[60, '1 h'], [90, '1½ h'], [120, '2 h'], [180, '3 h']]);

/** Three tiles to the row on a phone; from 720px up the sheet widens instead. */
const TILE_SIZES = '(min-width: 720px) 176px, 31vw';

const MODES = [
  [MODE.guided, 'Let the guide choose', 'time, artists, themes'],
  [MODE.picked, 'Choose the works yourself', 'pick from the whole collection'],
];

const chip = (label, pressed, onClick, extra = {}) =>
  el('button', {
    type: 'button',
    class: 'chip',
    'aria-pressed': String(pressed),
    onClick,
    ...extra,
  }, label);

const wideChip = (label, note, flag, pressed, onClick) =>
  el('button', {
    type: 'button',
    class: 'chip chip-wide',
    'aria-pressed': String(pressed),
    'data-flag': flag,
    onClick,
  }, el('span', { text: label }), el('span', { class: 'chip-note', text: note }));

const previewLine = (state, stopCount) =>
  `${stopCount} ${stopCount === 1 ? 'work' : 'works'} · ${state.minutes} minutes · `
  + focusLabel(state.focus).toLowerCase();

/** What the picked line costs, said where the time is chosen.
 *
 *  The budget is advice in this flow and nothing is ever dropped to meet it, so
 *  the only honest thing to do with an overrun is name it — and it belongs
 *  beside the chips that set the time rather than in the bar that counts. */
const budgetLine = (state, route) => {
  const budget = BUDGET_LABELS.get(state.minutes) ?? `${state.minutes} min`;

  if (!route.stopCount) return `Nothing picked yet — your ${budget} is untouched.`;

  const over = overBy(route, state.minutes);
  const walk = `${route.stopCount === 1 ? 'One work' : `${route.stopCount} works`}, `
    + `${route.plannedMinutes} minutes with the walking`;

  if (over > 0) {
    return `${walk} — ${over} minutes over the ${budget} you asked for, `
      + 'and nothing dropped for it.';
  }

  if (over === 0) return `${walk} — exactly the ${budget} you asked for.`;

  return `${walk} — ${-over} minutes inside the ${budget} you asked for.`;
};

const runsOver = (state, route) => route.stopCount > 0 && overBy(route, state.minutes) > 0;

/** The running count, kept in reach of the thumb. Short, because it stands in a
 *  bar beside two controls on a phone. */
const pickLine = (route) => (route.stopCount
  ? `${route.stopCount} picked · ${route.plannedMinutes} min`
  : 'Nothing picked yet');

const startLabel = (route) => (route.stopCount
  ? `Lay out these ${route.stopCount}`
  : 'Lay out the line');

const plannedWorks = (items) => new Set(items
  .filter((item) => item.kind === 'stop')
  .map((item) => item.work.objectNumber));

/** The plan first, then everything it leaves out. The sort is stable, so both
 *  groups keep the walking order they came in. */
const planFirst = (entries, lit) => [...entries].sort((a, b) => Number(lit(b)) - Number(lit(a)));

const byWalkingOrder = (a, b) => Number(a.dataset.order) - Number(b.dataset.order);

/** Everything the sheet needs to know about the state of the wall, read once
 *  and used by both the first render and every repaint after it. */
function wallView(state, works) {
  const route = routeFor(works, state);
  const picked = new Set(state.picked);

  return {
    route,
    picked,
    chosen: state.mode === MODE.picked ? picked : plannedWorks(route.items),
  };
}

/** What a tile says about itself.
 *
 *  A work the line cannot reach was not left out of this plan — no plan would
 *  ever hold it, and it cannot be picked either — and the tile is the only
 *  place the visitor is told so. */
const tileState = (work, mode, chosen) => {
  if (!onTheLine(work)) return 'off the line';

  if (mode === MODE.picked) return chosen ? 'picked' : 'not picked';

  return chosen ? 'in this plan' : 'not in this plan';
};

/** One work in the contact sheet.
 *
 *  Whether the plan reaches it, or the visitor has picked it, is said in the
 *  tile's own text and not only in its marking, so the sheet reads the same to
 *  a screen reader as it does to an eye. `data-order` is its place in the
 *  walking order, which the tiles keep once the plan has pulled some of them
 *  forward.
 *
 *  Two controls, because the picking flow has two verbs and a button cannot hold
 *  another one — but nothing is drawn for the second. The picture is the tile's
 *  own verb, read or pick; the caption under it always opens the entry. In the
 *  guided flow both do the one thing, so the caption leaves the tab order and
 *  the tile is the single stop it has always been. */
function tile(work, order, state, view, actions) {
  const title = work.displayTitle ?? work.title.en ?? work.title.nl;
  const byline = [work.artist, work.date].filter(Boolean).join(', ');
  const picking = state.mode === MODE.picked;
  const chosen = view.chosen.has(work.objectNumber);
  const reachable = onTheLine(work);

  return el('div', {
    class: 'tile',
    'data-object': work.objectNumber,
    'data-order': order,
    'data-lit': String(chosen),
    'data-picked': String(view.picked.has(work.objectNumber)),
    'data-reachable': String(reachable),
  },
  el('button', {
    type: 'button',
    class: 'tile-face',
    disabled: picking && !reachable,
    // A pick is a toggle, and says so where it is one.
    'aria-pressed': picking ? String(chosen) : null,
    onClick: () => actions.tapWork(work.objectNumber),
  },
  el('span', { class: 'plate-band' }, plate(work, TILE_SIZES)),
  el('span', { class: 'tile-state', text: tileState(work, state.mode, chosen) })),
  el('button', {
    type: 'button',
    class: 'tile-caption',
    tabindex: picking ? '0' : '-1',
    onClick: () => actions.openDetail(work.objectNumber),
  },
  el('span', { class: 'tile-title', text: title }),
  el('span', { class: 'tile-by muted', text: byline })),
  // The outline round the plate is a mark and not a word. The screen reader has
  // `.tile-state` and does not need both.
  el('span', { class: 'tile-check', 'aria-hidden': 'true', text: '✓ Picked' }));
}

/** The two flows, named. Only one body is ever on the screen. */
const modeSwitch = (state, actions) => el('div', { class: 'mode-switch', role: 'group' },
  MODES.map(([mode, label, note]) => el('button', {
    type: 'button',
    class: 'chip chip-mode',
    'aria-pressed': String(state.mode === mode),
    'data-mode': mode,
    onClick: () => actions.setMode(mode),
  },
  el('span', { text: label }),
  el('span', { class: 'chip-note', text: note }))));

const budgetChips = (state, actions) => el('div', { class: 'grid-4' },
  BUDGETS.map((minutes) => chip(
    BUDGET_LABELS.get(minutes),
    state.minutes === minutes,
    () => actions.update((next) => { next.minutes = minutes; }),
    { class: 'chip chip-centred', 'data-minutes': minutes })));

/** The constraint flow: everything the route needs is chosen here, once. */
function guidedBody(state, view, actions) {
  const toggleTag = (tag) => () => actions.update((next) => {
    next.focus = next.focus.includes(tag)
      ? next.focus.filter((each) => each !== tag)
      : [...next.focus, tag];
  });

  return [
    el('p', { class: 'setup-intro' },
      'Tell the guide what you have and what you love. It lays one unbroken line from the '
      + 'Atrium to the exit — no backtracking, most of your minutes spent standing still '
      + 'in front of paintings.'),
    el('hr', { class: 'hr' }),

    el('div', { class: 'section-label', style: { marginTop: '0' } }, 'How long do you have?'),
    budgetChips(state, actions),

    el('div', { class: 'section-label' }, 'Artists & highlights'),
    el('div', { class: 'wrap' },
      ARTIST_TAGS.map(([tag, label]) =>
        chip(label, state.focus.includes(tag), toggleTag(tag), { 'data-tag': tag }))),

    el('div', { class: 'section-label' }, 'Periods & themes'),
    el('div', { class: 'wrap' },
      THEME_TAGS.map(([tag, label]) =>
        chip(label, state.focus.includes(tag), toggleTag(tag), { 'data-tag': tag }))),
    el('p', { class: 'hint quiet' },
      'Leave both empty for the greatest hits.'),

    el('div', { class: 'section-label' }, 'Walking with'),
    el('div', { class: 'stack' },
      wideChip('Children along', 'shorter stops, a question at each', 'kids', state.kids,
        () => actions.update((next) => { next.kids = !next.kids; })),
      wideChip('Lifts only, no stairs', 'step-free route', 'stepFree', state.stepFree,
        () => actions.update((next) => { next.stepFree = !next.stepFree; }))),

    el('button', {
      type: 'button', class: 'btn btn-primary btn-block',
      onClick: actions.start, text: 'Lay out the route',
    }),
    el('p', { class: 'preview quiet', text: previewLine(state, view.route.stopCount) }),
  ];
}

/** The picking flow: the works are the constraint, and the guide does the
 *  walking arithmetic. The time is still asked for, but only so the count below
 *  the wall has something to measure the walk against. */
const pickedBody = (state, view, actions) => [
  el('p', { class: 'setup-intro' },
    'Pick the works you want to see. The guide puts them in walking order — one unbroken '
    + 'line from the Atrium, no backtracking — and tells you what that costs. Nothing you '
    + 'pick is ever dropped.'),
  el('hr', { class: 'hr' }),

  el('div', { class: 'section-label', style: { marginTop: '0' } }, 'How long do you have?'),
  budgetChips(state, actions),
  el('p', {
    class: 'pick-against',
    'data-over': String(runsOver(state, view.route)),
    text: budgetLine(state, view.route),
  }),
  el('p', { class: 'hint quiet' },
    'Time is advice here, not a limit. This line walks the stairs and stands the full time '
    + 'at every work — for lifts, or shorter stops with a question for children, let the '
    + 'guide choose instead.'),
];

const modeBody = (state, view, actions) => (state.mode === MODE.picked
  ? pickedBody(state, view, actions)
  : guidedBody(state, view, actions));

/** The heading over the wall, which says what a tap on it does. */
const sheetIntro = (state, works) => {
  const strays = works.filter((work) => !onTheLine(work)).length;

  if (state.mode === MODE.picked) {
    return [
      el('div', { class: 'section-label' }, 'Pick your works'),
      el('p', { class: 'hint quiet' },
        `All ${works.length} are written up in full and stand here in walking order. Tap a `
        + 'picture to put it on your line, tap it again to take it off; tap its title to '
        + `read the entry first. The ${strays} dimmed ones cannot be walked to at all — the `
        + 'museum publishes no room for them, or they hang where the route does not go.'),
    ];
  }

  return [
    el('div', { class: 'section-label' }, 'Everything the guide can show you'),
    el('p', { class: 'hint quiet' },
      `All ${works.length} works are written up in full. The plan comes first, in walking `
      + 'order; the dimmed ones fall outside it. Tap any of them to read its entry. '
      + `The last ${strays} are off the line whatever you ask for — the museum publishes `
      + 'no room for them, or they hang where the route does not go.'),
  ];
};

/** The count and the way out of the picking flow, held at the foot of the
 *  window because picking happens while scrolling a wall of a hundred plates.
 *  It is the mirror of the tour's own bar at the top of that screen. */
const pickBar = (state, view, actions) => el('div', { class: 'pick-bar' },
  el('div', { class: 'pick-row' },
    el('span', { class: 'kicker pick-count', text: pickLine(view.route) }),
    el('div', { class: 'pick-actions' },
      el('button', {
        type: 'button', class: 'btn btn-ghost pick-clear',
        onClick: actions.clearPicks, text: 'Clear',
      }),
      el('button', {
        type: 'button', class: 'btn btn-primary pick-start',
        disabled: !view.route.stopCount,
        onClick: actions.start,
        text: startLabel(view.route),
      }))));

export function renderSetup(state, works, actions) {
  const view = wallView(state, works);
  const walkingOrder = new Map([...works].sort(inRouteOrder).map((work, index) => [work, index]));
  const ordered = state.mode === MODE.picked
    ? [...walkingOrder.keys()]
    : planFirst([...walkingOrder.keys()], (work) => view.chosen.has(work.objectNumber));

  const form = el('div', { class: 'setup' },
    el('div', { class: 'setup-head' },
      el('div', {
        class: 'kicker',
        style: { color: 'var(--color-accent-700)' },
        text: 'Rijksmuseum',
      })),

    el('h1', { text: 'A walk through the collection' }),
    modeSwitch(state, actions),
    el('div', { class: 'mode-body' }, modeBody(state, view, actions)));

  // Its own block, not part of the constraint column: a hundred plates want more
  // width than a form does, and get it as soon as the window has any to give.
  const sheet = el('div', { class: 'collection-block' },
    el('hr', { class: 'hr collection-rule' }),
    el('div', { class: 'collection-intro' }, sheetIntro(state, works)),
    el('div', { class: 'collection' },
      ordered.map((work) => tile(work, walkingOrder.get(work), state, view, actions))));

  return el('div', { class: 'screen', 'data-mode': state.mode },
    form, sheet, pickBar(state, view, actions));
}

const press = (node, pressed) => node.setAttribute('aria-pressed', String(pressed));

/** Repaint the screen in place after a constraint, a pick or the mode changes.
 *
 *  Rebuilding it would replace a hundred plates the browser has already
 *  decoded, and the whole sheet blinks. A change of mode swaps the body of the
 *  form and the heading over the wall; everything else here is attributes the
 *  transitions run on, so the pressed chip keeps its focus and the tiles keep
 *  their pictures. */
export function paintSetup(state, works, actions) {
  const screen = document.querySelector('.screen');

  if (!screen) return;

  const all = (selector) => [...screen.querySelectorAll(selector)];
  const changedMode = screen.dataset.mode !== state.mode;

  screen.dataset.mode = state.mode;

  const view = wallView(state, works);

  if (changedMode) {
    clear(screen.querySelector('.mode-body')).append(...modeBody(state, view, actions));
    clear(screen.querySelector('.collection-intro')).append(...sheetIntro(state, works));
  }

  all('.chip[data-mode]').forEach((node) => press(node, node.dataset.mode === state.mode));
  all('.chip[data-minutes]').forEach((node) =>
    press(node, Number(node.dataset.minutes) === state.minutes));
  all('.chip[data-tag]').forEach((node) => press(node, state.focus.includes(node.dataset.tag)));
  all('.chip[data-flag]').forEach((node) => press(node, Boolean(state[node.dataset.flag])));

  const byNumber = new Map(works.map((work) => [work.objectNumber, work]));
  const tiles = all('.tile');

  const picking = state.mode === MODE.picked;

  tiles.forEach((node) => {
    const work = byNumber.get(node.dataset.object);
    const chosen = view.chosen.has(node.dataset.object);
    const face = node.querySelector('.tile-face');

    node.dataset.lit = String(chosen);
    node.dataset.picked = String(view.picked.has(node.dataset.object));
    node.querySelector('.tile-state').textContent = tileState(work, state.mode, chosen);
    node.querySelector('.tile-caption').tabIndex = picking ? 0 : -1;
    face.disabled = picking && !onTheLine(work);

    if (picking) face.setAttribute('aria-pressed', String(chosen));
    else face.removeAttribute('aria-pressed');
  });

  // Appending nodes that are already in the grid moves them, so the plates keep
  // the decoding they have. Moving them rather than reordering them in CSS is
  // what keeps the tab order and the reading order the one on the screen.
  const grid = screen.querySelector('.collection');

  if (picking) {
    // The wall stays in walking order while it is being picked from: a tile that
    // jumped forward as it was tapped would move the next one under the finger.
    if (changedMode) grid.append(...tiles.sort(byWalkingOrder));

    const bar = screen.querySelector('.pick-bar');
    const start = bar.querySelector('.pick-start');

    const against = screen.querySelector('.pick-against');

    against.textContent = budgetLine(state, view.route);
    against.dataset.over = String(runsOver(state, view.route));
    bar.querySelector('.pick-count').textContent = pickLine(view.route);
    start.textContent = startLabel(view.route);
    start.disabled = !view.route.stopCount;

    return;
  }

  screen.querySelector('.preview').textContent = previewLine(state, view.route.stopCount);
  grid.append(...planFirst(tiles.sort(byWalkingOrder), (node) => node.dataset.lit === 'true'));
}
