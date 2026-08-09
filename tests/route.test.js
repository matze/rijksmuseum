/** Route composition and pacing, checked against the real tour data.
 *
 *  These are the two modules with no DOM in them and all of the arithmetic, so
 *  they are worth testing directly: a route that quietly overruns the visitor's
 *  budget is the one failure the guide must not have.
 *
 *  Run with: just test
 */

import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import assert from 'node:assert/strict';
import test from 'node:test';

import { buildRoute, focusLabel, stayFor } from '../app/route.js';
import { formatClock, pacing } from '../app/clock.js';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const works = JSON.parse(readFileSync(join(root, 'data/tour.json')));

const FLOOR_ORDER = [0, 1, 3, 2];
const BUDGETS = [60, 90, 120, 180];

const permutations = BUDGETS.flatMap((minutes) =>
  [false, true].flatMap((kids) =>
    [false, true].map((stepFree) => ({ minutes, focus: [], kids, stepFree }))));

test('the data is present', () => {
  assert.ok(works.length > 0, 'data/tour.json is empty — run `just build`');
});

for (const state of permutations) {
  const label = `${state.minutes} min${state.kids ? ' kids' : ''}${state.stepFree ? ' step-free' : ''}`;

  test(`${label}: the plan fits the time asked for`, () => {
    const route = buildRoute(works, state);
    assert.ok(route.plannedMinutes <= state.minutes,
      `planned ${route.plannedMinutes} > budget ${state.minutes}`);
  });

  test(`${label}: the line runs one way, Atrium to exit`, () => {
    const route = buildRoute(works, state);
    const stops = route.items.filter((item) => item.kind === 'stop');

    assert.equal(route.items.at(0).title, 'Atrium');
    assert.equal(route.items.at(-1).title, 'Exit');
    assert.ok(stops.length > 0);

    const ranks = stops.map((stop) => FLOOR_ORDER.indexOf(stop.work.gallery.floor));
    assert.deepEqual([...ranks].sort((a, b) => a - b), ranks,
      `floors revisited: ${stops.map((s) => s.work.gallery.floor)}`);
  });

  test(`${label}: one floor header per floor entered`, () => {
    const route = buildRoute(works, state);
    const headers = route.items.filter((item) => item.kind === 'floor');
    const floors = new Set(route.items
      .filter((item) => item.kind === 'stop')
      .map((stop) => stop.work.gallery.floor));

    assert.equal(headers.length, floors.size);
  });

  test(`${label}: a break only in the long plans`, () => {
    const route = buildRoute(works, state);
    const breaks = route.items.filter((item) => item.kind === 'break');

    assert.equal(breaks.length, state.minutes >= 150 ? 1 : 0);
  });

  test(`${label}: stop numbering is contiguous from one`, () => {
    const stops = buildRoute(works, state).items.filter((item) => item.kind === 'stop');

    assert.deepEqual(stops.map((stop) => stop.number),
      stops.map((_, index) => index + 1));
  });
}

test('children shorten every stop but never below three minutes', () => {
  for (const work of works) {
    const stay = stayFor(work, true);
    assert.ok(stay >= 3 && stay <= work.stayMinutes);
  }
});

test('step-free costs more minutes than the stairs', () => {
  const base = buildRoute(works, { minutes: 180, focus: [], kids: false, stepFree: false });
  const lift = buildRoute(works, { minutes: 180, focus: [], kids: false, stepFree: true });

  assert.ok(lift.plannedMinutes > base.plannedMinutes);
});

test('a focus keeps its own works and the unmissable ones', () => {
  const route = buildRoute(works, { minutes: 120, focus: ['vermeer'], kids: false, stepFree: false });
  const chosen = route.items.filter((item) => item.kind === 'stop').map((s) => s.work);

  assert.ok(chosen.some((work) => work.tags.includes('vermeer')));
  assert.ok(chosen.every((work) => work.priority === 1 || work.tags.includes('vermeer')));
});

test('the focus line names the tags, or the default', () => {
  assert.equal(focusLabel([]), 'Greatest hits');
  assert.equal(focusLabel(['vermeer', 'golden']), 'Vermeer, Dutch Golden Age');
});

test('pacing speaks to where the visitor actually is', () => {
  const started = Date.UTC(2026, 0, 1, 10, 0, 0);
  const route = buildRoute(works, { minutes: 120, focus: [], kids: false, stepFree: false });
  const stops = route.items.filter((item) => item.kind === 'stop');
  const early = stops[1];

  assert.match(pacing({ started, now: started + 20_000 }, early, route).text, /^finish about/);
  assert.match(pacing({ started, now: started + 60_000 }, early, route).text, /in hand$/);

  const late = pacing({ started, now: started + (early.plannedAt + 30) * 60_000 }, early, route);
  assert.ok(late.behind);
  assert.match(late.text, /behind$/);

  assert.equal(pacing({ started, now: started + 60_000 }, stops.at(-1), route).text,
    'take as long as you like');
});

test('the clock is zero-padded', () => {
  assert.equal(formatClock(new Date(2026, 0, 1, 9, 5)), '09:05');
});
