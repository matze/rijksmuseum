/** The line itself: one row per timeline entry, all on a single rail.
 *
 *  Each row carries its own marker, drawn as two layers so the rail is masked
 *  behind an opaque backing while only the coloured mark dims with its card. */

import { el } from './dom.js';
import { floorPlan, planCaption } from './floorplan.js';
import { plate } from './plate.js';
import { focusLabel, overBy } from './route.js';
import { MODE } from './state.js';

const PLATE_SIZES = '(min-width: 640px) 538px, calc(100vw - 36px)';

/** Kinds whose marker needs an opaque backing to mask the rail behind it when
 *  the marker dims. */
const BACKED = new Set(['stop', 'break', 'terminus', 'floor', 'walk']);

/** Marker geometry is CSS, per `.row-<kind>`: it differs between the connector
 *  inside the column on a phone and the left rail above the breakpoint, and
 *  inline styles are out of a media query's reach. */
const marker = (kind) => [
  BACKED.has(kind) ? el('div', { class: 'mark-back' }) : null,
  el('div', { class: 'mark', 'data-lit': 'true' }),
];

const row = (kind, ...content) =>
  el('div', { class: `row row-${kind}` }, el('div', { class: 'rail' }), marker(kind), content);

function stopEntry(item, state, route, actions) {
  const { work } = item;
  const title = work.displayTitle ?? work.title.en ?? work.title.nl;
  const byline = [work.artist, work.date].filter(Boolean).join(', ');

  return row('stop', el('button', {
    type: 'button',
    class: 'card entry-stop',
    'data-lit': 'true',
    'data-stop-number': item.number,
    onClick: () => actions.openDetail(work.objectNumber),
  },
  el('div', { class: 'stop-head kicker' },
    el('span', { class: 'where', text: `Stop ${item.number} · Room ${work.gallery.room}` }),
    el('span', { class: 'stay', text: `${item.stay} min` })),
  plate(work, PLATE_SIZES),
  el('h2', { text: title }),
  byline ? el('div', { class: 'byline muted', text: byline }) : null,
  el('p', { class: 'body-text', text: work.timeline.text }),
  el('div', { class: 'aside' },
    el('span', { class: 'kicker label', text: 'Look closer' }),
    el('span', { class: 'text', text: work.closer })),
  state.kids && work.kids
    ? el('div', { class: 'ask' },
      el('span', { class: 'kicker label', text: 'Ask them' }),
      el('span', { class: 'text', text: work.kids }))
    : null,
  el('div', { class: 'kicker affordance', text: 'Tap for the full entry' })));
}

const walkEntry = (item) => row('walk', el('div', { class: 'entry-walk', 'data-lit': 'true' },
  el('div', { class: 'walk-line muted' },
    el('span', { class: 'kicker mins', text: `${item.minutes} min` }),
    el('span', { class: 'what', text: item.text }))));

const floorEntry = (item) => row('floor', el('div', { class: 'card entry-floor', 'data-lit': 'true' },
  el('div', { class: 'kicker', text: item.kicker }),
  el('div', { class: 'floor-title', text: item.title }),
  el('div', { class: 'plan' },
    floorPlan(item.stops),
    el('div', { class: 'plan-caption muted', text: planCaption(item.stops) }))));

const breakEntry = (item) => row('break', el('div', { class: 'card entry-break', 'data-lit': 'true' },
  el('div', { class: 'kicker', text: item.kicker }),
  el('div', { class: 'break-title', text: item.title }),
  el('div', { class: 'break-text muted', text: item.text })));

/** What made this line, said at the top of it.
 *
 *  In the guided flow that is the constraints the visitor set. In the picking
 *  flow the works themselves are the answer, so the recap names neither a focus
 *  nor the two constraints that flow does not offer — and it owns up to a walk
 *  that runs past the time asked for, because nothing was dropped to prevent
 *  that. */
function recap(state, route) {
  if (state.mode !== MODE.picked) {
    return [[`${state.minutes} min`, focusLabel(state.focus)]
      .concat(state.kids ? ['with children'] : [])
      .concat(state.stepFree ? ['step-free'] : [])
      .join(' · ')];
  }

  const over = overBy(route, state.minutes);
  const counted = `${route.stopCount} ${route.stopCount === 1 ? 'work' : 'works'}`;

  return [`Hand-picked · ${counted} · ${route.plannedMinutes} min`]
    .concat(over > 0 ? [`${over} min over the ${state.minutes} min you asked for`] : []);
}

function terminusEntry(item, state, route, actions) {
  return row('terminus', el('div', { class: 'card entry-term', 'data-lit': 'true' },
    el('div', { class: 'kicker', text: item.kicker }),
    el('div', { class: 'term-title', text: item.title }),
    el('div', { class: 'term-text muted', text: item.text }),
    item.at === 'start'
      ? el('div', { class: 'selection muted' },
        recap(state, route).map((text) => el('div', { text })))
      : el('div', { class: 'actions' },
        el('button', {
          type: 'button', class: 'btn btn-secondary',
          onClick: actions.restart, text: 'Plan another visit',
        }))));
}

const ENTRIES = {
  stop: stopEntry,
  walk: walkEntry,
  floor: floorEntry,
  break: breakEntry,
  terminus: terminusEntry,
};

export function renderTour(state, route, actions) {
  const chrome = el('div', { class: 'chrome', 'data-hidden': 'false' },
    el('div', { class: 'chrome-row kicker' },
      el('span', { class: 'chrome-at' }),
      el('span', { class: 'chrome-nudge' }),
      el('span', { class: 'chrome-clock' }),
      el('button', {
        type: 'button', class: 'btn btn-ghost chrome-edit',
        onClick: actions.edit, text: 'Change plan',
      })),
    el('div', { class: 'progress' }, el('i')));

  const line = el('div', { class: 'line' },
    route.items.map((item) => ENTRIES[item.kind](item, state, route, actions)));

  return el('div', {}, chrome, line);
}

/** Update the header in place. Called every tick and on every focus change. */
export function paintChrome({ at, nudge, clock, progress }) {
  const chrome = document.querySelector('.chrome');

  if (!chrome) return;

  chrome.querySelector('.chrome-at').textContent = at;

  const nudgeNode = chrome.querySelector('.chrome-nudge');
  nudgeNode.textContent = nudge.text;
  nudgeNode.dataset.behind = String(nudge.behind);

  chrome.querySelector('.chrome-clock').textContent = clock;
  chrome.querySelector('.progress > i').style.width = `${progress}%`;
}
