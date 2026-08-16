/** The constraint screen. Everything the route needs is chosen here, once —
 *  and below the constraints, every work the guide knows, lit or dimmed by
 *  whether the plan as it stands reaches it. */

import { el } from './dom.js';
import { plate } from './plate.js';
import { BUDGETS } from './state.js';
import { ARTIST_TAGS, THEME_TAGS, buildRoute, focusLabel, inRouteOrder, onTheLine } from './route.js';

const BUDGET_LABELS = new Map([[60, '1 h'], [90, '1½ h'], [120, '2 h'], [180, '3 h']]);

/** Three tiles to the row on a phone; from 720px up the sheet widens instead. */
const TILE_SIZES = '(min-width: 720px) 176px, 31vw';

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

const plannedWorks = (items) => new Set(items
  .filter((item) => item.kind === 'stop')
  .map((item) => item.work.objectNumber));

/** The plan first, then everything it leaves out. The sort is stable, so both
 *  groups keep the walking order they came in. */
const planFirst = (entries, lit) => [...entries].sort((a, b) => Number(lit(b)) - Number(lit(a)));

/** What a tile says about itself.
 *
 *  A work the line cannot reach was not left out of this plan — no plan would
 *  ever hold it — and the tile is the only place the visitor is told so. */
const tileState = (work, planned) => {
  if (!onTheLine(work)) return 'off the line';

  return planned ? 'in this plan' : 'not in this plan';
};

/** One work in the contact sheet. Whether the plan reaches it is said in the
 *  tile's own text, not only in its dimming, so the sheet reads the same to a
 *  screen reader as it does to an eye. `data-order` is its place in the walking
 *  order, which the tiles keep once the plan has pulled some of them forward. */
function tile(work, planned, order, actions) {
  const title = work.displayTitle ?? work.title.en ?? work.title.nl;
  const byline = [work.artist, work.date].filter(Boolean).join(', ');

  return el('button', {
    type: 'button',
    class: 'tile',
    'data-lit': String(planned),
    'data-object': work.objectNumber,
    'data-order': order,
    onClick: () => actions.openDetail(work.objectNumber),
  },
  el('span', { class: 'plate-band' }, plate(work, TILE_SIZES)),
  el('span', { class: 'tile-title', text: title }),
  el('span', { class: 'tile-by muted', text: byline }),
  el('span', { class: 'tile-state', text: tileState(work, planned) }));
}

export function renderSetup(state, works, actions) {
  const toggleTag = (tag) => () => actions.update((next) => {
    next.focus = next.focus.includes(tag)
      ? next.focus.filter((each) => each !== tag)
      : [...next.focus, tag];
  });

  // The preview counts the route as it will actually be walked, trimming included.
  const { items, stopCount } = buildRoute(works, state);
  const planned = plannedWorks(items);
  const walkingOrder = new Map([...works].sort(inRouteOrder).map((work, index) => [work, index]));

  const form = el('div', { class: 'setup' },
    el('div', { class: 'setup-head' },
      el('div', {
        class: 'kicker',
        style: { color: 'var(--color-accent-700)' },
        text: 'Rijksmuseum',
      })),

    el('h1', { text: 'A walk through the collection' }),
    el('p', { class: 'setup-intro' },
      'Tell the guide what you have and what you love. It lays one unbroken line from the '
      + 'Atrium to the exit — no backtracking, most of your minutes spent standing still '
      + 'in front of paintings.'),
    el('hr', { class: 'hr' }),

    el('div', { class: 'section-label', style: { marginTop: '0' } }, 'How long do you have?'),
    el('div', { class: 'grid-4' },
      BUDGETS.map((minutes) => chip(
        BUDGET_LABELS.get(minutes),
        state.minutes === minutes,
        () => actions.update((next) => { next.minutes = minutes; }),
        { class: 'chip chip-centred', 'data-minutes': minutes }))),

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
    el('p', { class: 'preview quiet', text: previewLine(state, stopCount) }));

  const strays = works.filter((work) => !onTheLine(work)).length;

  // Its own block, not part of the constraint column: a hundred plates want more
  // width than a form does, and get it as soon as the window has any to give.
  const sheet = el('div', { class: 'collection-block' },
    el('hr', { class: 'hr collection-rule' }),
    el('div', { class: 'section-label' }, 'Everything the guide can show you'),
    el('p', { class: 'hint quiet' },
      `All ${works.length} works are written up in full. The plan comes first, in walking `
      + 'order; the dimmed ones fall outside it. Tap any of them to read its entry. '
      + `The last ${strays} are off the line whatever you ask for — the museum publishes `
      + 'no room for them, or they hang where the route does not go.'),
    el('div', { class: 'collection' },
      planFirst([...walkingOrder.keys()], (work) => planned.has(work.objectNumber))
        .map((work) => tile(work, planned.has(work.objectNumber),
          walkingOrder.get(work), actions))));

  return el('div', {}, form, sheet);
}

const press = (node, pressed) => node.setAttribute('aria-pressed', String(pressed));

/** Repaint the screen in place after a constraint changes.
 *
 *  Rebuilding it would replace forty plates the browser has already decoded, and
 *  the whole sheet blinks; this touches the attributes the dimming transition
 *  runs on, moves the tiles the plan has pulled forward, and leaves the pressed
 *  chip holding focus. */
export function paintSetup(state, works) {
  const screen = document.querySelector('.setup')?.parentElement;

  if (!screen) return;

  const all = (selector) => [...screen.querySelectorAll(selector)];

  all('.chip[data-minutes]').forEach((node) =>
    press(node, Number(node.dataset.minutes) === state.minutes));
  all('.chip[data-tag]').forEach((node) => press(node, state.focus.includes(node.dataset.tag)));
  all('.chip[data-flag]').forEach((node) => press(node, Boolean(state[node.dataset.flag])));

  const { items, stopCount } = buildRoute(works, state);
  const planned = plannedWorks(items);

  screen.querySelector('.preview').textContent = previewLine(state, stopCount);

  const tiles = all('.tile');

  const byNumber = new Map(works.map((work) => [work.objectNumber, work]));

  tiles.forEach((node) => {
    const lit = planned.has(node.dataset.object);

    node.setAttribute('data-lit', String(lit));
    node.querySelector('.tile-state').textContent =
      tileState(byNumber.get(node.dataset.object), lit);
  });

  // Appending nodes that are already in the grid moves them, so the plates keep
  // the decoding they have. Moving them rather than reordering them in CSS is
  // what keeps the tab order and the reading order the one on the screen.
  screen.querySelector('.collection').append(...planFirst(
    tiles.sort((a, b) => Number(a.dataset.order) - Number(b.dataset.order)),
    (node) => node.dataset.lit === 'true'));
}
