/** Composing one unbroken line from the Atrium to the exit.
 *
 *  Two steps: choose which works fit the time available, then lay them out in an
 *  order that never doubles back. */

/** Tag vocabulary offered on the setup screen, in the order it is shown. */
export const ARTIST_TAGS = [
  ['rembrandt', 'Rembrandt'],
  ['vermeer', 'Vermeer'],
  ['portrait', 'Portraits'],
  ['vangogh', 'Van Gogh'],
  ['hits', 'Greatest hits'],
];

export const THEME_TAGS = [
  ['golden', 'Dutch Golden Age'],
  ['middle', 'Middle Ages'],
  ['19c', '18th–19th century'],
  ['20c', '20th century'],
  ['decorative', 'Decorative arts'],
  ['landscape', 'Landscape'],
];

export const TAG_LABELS = new Map([...ARTIST_TAGS, ...THEME_TAGS]);

/** Floors in the order the route visits them.
 *
 *  Physically the building stacks 0–3, but the Night Watch hangs on floor 2 and
 *  is where a visit should end, so floor 3 is taken on the way up and floor 2 on
 *  the way back down. */
const FLOOR_ORDER = [0, 1, 3, 2];

const FLOOR_NAMES = new Map([
  [0, 'Special Collections, 1100–1600'],
  [1, '1700–1900'],
  [2, 'The Golden Age'],
  [3, '1900–2000'],
]);

/** Walking-time estimates, in minutes.
 *
 *  These are estimates, not measurements: the published plan carries no scale,
 *  so the guide states minutes and never metres. They are deliberately generous
 *  — a visitor who arrives early is better served than one who arrives late. */
const WALK = {
  sameRoom: 1,
  sameWing: 2,
  acrossFloor: 3,
  changeFloor: 4,
  changeFloorStepFree: 5,
  fromAtrium: 3,
  fromAtriumStepFree: 4,
  toExit: 4,
  toExitStepFree: 5,
};

/** Minutes held back from the budget for arriving, queueing and leaving. */
const OVERHEAD = 10;
/** Longer visits get a sit-down, and the budget pays for it. */
const BREAK_MINUTES = 12;
const BREAK_THRESHOLD = 150;
/** Rooms this far apart on the plan count as opposite wings of the building. */
const WING_DISTANCE = 60;

const floorRank = (floor) => {
  const rank = FLOOR_ORDER.indexOf(floor);

  return rank === -1 ? FLOOR_ORDER.length : rank;
};

/** Sort key following the museum's own room numbering, so 2.9 precedes 2.10. */
export const roomOrder = (room) =>
  (room.match(/\d+/g) ?? []).map(Number);

function compareRooms(a, b) {
  const left = roomOrder(a);
  const right = roomOrder(b);

  for (let i = 0; i < Math.max(left.length, right.length); i += 1) {
    const difference = (left[i] ?? -1) - (right[i] ?? -1);

    if (difference) return difference;
  }

  return 0;
}

const inRouteOrder = (a, b) =>
  floorRank(a.gallery.floor) - floorRank(b.gallery.floor)
  || compareRooms(a.gallery.room, b.gallery.room)
  || a.objectNumber.localeCompare(b.objectNumber);

/** How long the visitor stands in front of a work, in minutes. */
export function stayFor(work, kids) {
  return kids ? Math.max(3, work.stayMinutes - 1) : work.stayMinutes;
}

function score(work, focus, kids) {
  let value = work.priority;

  if (focus.length && work.tags.some((tag) => focus.includes(tag))) value -= 2;
  if (kids && work.tags.includes('kidsfav')) value -= 1;

  return value;
}

/** The candidate works, best first — the order stops are added and dropped in. */
function rankWorks(works, { focus, kids }) {
  const pool = works.filter((work) =>
    !focus.length || work.priority === 1 || work.tags.some((tag) => focus.includes(tag)));

  return [...pool].sort((a, b) =>
    score(a, focus, kids) - score(b, focus, kids) || inRouteOrder(a, b));
}

/** Which works fit, given the constraints. Returns them in route order.
 *
 *  The greedy pass prices every stop at one short walk, which understates a
 *  route that changes floors, so `buildRoute` costs the real thing afterwards
 *  and drops the weakest stops until the plan honours the time asked for. */
export function selectWorks(works, state) {
  const takesBreak = state.minutes >= BREAK_THRESHOLD;
  const budget = state.minutes - OVERHEAD - (takesBreak ? BREAK_MINUTES : 0);
  const ranked = rankWorks(works, state);

  const chosen = [];
  let spent = 0;

  for (const work of ranked) {
    const cost = stayFor(work, state.kids) + WALK.sameWing;

    if (spent + cost > budget) continue;

    spent += cost;
    chosen.push(work);
  }

  return { works: chosen.sort(inRouteOrder), ranked, takesBreak };
}

const distanceBetween = (a, b) => {
  const from = a.gallery.position;
  const to = b.gallery.position;

  return from && to ? Math.hypot(from[0] - to[0], from[1] - to[1]) : null;
};

function walkBetween(previous, work, stepFree) {
  if (!previous) {
    return {
      minutes: stepFree ? WALK.fromAtriumStepFree : WALK.fromAtrium,
      text: `From the Atrium, ${stepFree ? 'take the lift' : 'take the stairs'} `
        + `to Floor ${work.gallery.floor}.`,
    };
  }

  if (previous.gallery.floor !== work.gallery.floor) {
    const climbing = work.gallery.floor > previous.gallery.floor;

    return {
      minutes: stepFree ? WALK.changeFloorStepFree : WALK.changeFloor,
      text: `Take the ${stepFree ? 'lift' : 'stairs'} ${climbing ? 'up' : 'down'} `
        + `to Floor ${work.gallery.floor}.`,
    };
  }

  if (previous.gallery.room === work.gallery.room) {
    return { minutes: WALK.sameRoom, text: 'Same room — turn around.' };
  }

  const distance = distanceBetween(previous, work);

  if (distance !== null && distance > WING_DISTANCE) {
    return {
      minutes: WALK.acrossFloor,
      text: `Back through the central hall and into Room ${work.gallery.room}, `
        + 'on the other side of the building.',
    };
  }

  return { minutes: WALK.sameWing, text: `Through to Room ${work.gallery.room}.` };
}

/**
 * Build the timeline: termini, floor headers, walks, stops and the break.
 * @returns {{items: Array, plannedMinutes: number, stopCount: number}}
 */
export function buildRoute(works, state) {
  const selection = selectWorks(works, state);
  let chosen = selection.works;
  let route = layOut(chosen, selection.takesBreak, state);

  // Drop the weakest stop until the plan fits the time the visitor actually has.
  while (route.plannedMinutes > state.minutes && chosen.length > 1) {
    const weakest = [...selection.ranked].reverse().find((work) => chosen.includes(work));
    chosen = chosen.filter((work) => work !== weakest);
    route = layOut(chosen, selection.takesBreak, state);
  }

  return route;
}

function layOut(works, takesBreak, { kids, stepFree }) {
  const items = [];

  let planned = 0;
  let stopNumber = 0;
  let previous = null;
  let breakTaken = false;

  items.push({
    kind: 'terminus',
    at: 'start',
    kicker: 'Start · Floor 0',
    title: 'Atrium',
    text: 'Coats and bags down first — you will not want them upstairs. The line below '
      + 'runs one way only; when it ends you are standing at the doors.',
  });

  for (const work of works) {
    const changingFloor = !previous || previous.gallery.floor !== work.gallery.floor;

    if (changingFloor && takesBreak && !breakTaken && previous
        && floorRank(work.gallery.floor) >= FLOOR_ORDER.indexOf(2)) {
      breakTaken = true;
      planned += BREAK_MINUTES;
      items.push({
        kind: 'break',
        kicker: `Pause · ${BREAK_MINUTES} min`,
        title: 'Coffee in the Atrium',
        text: 'Halfway. Sit down before the Golden Age rooms rather than after — '
          + 'attention is the thing you are actually spending today.',
      });
    }

    const walk = walkBetween(previous, work, stepFree);
    planned += walk.minutes;
    items.push({ kind: 'walk', ...walk });

    if (changingFloor) {
      const onThisFloor = works.filter((w) => w.gallery.floor === work.gallery.floor);
      items.push({
        kind: 'floor',
        floor: work.gallery.floor,
        kicker: `Floor ${work.gallery.floor}`,
        title: FLOOR_NAMES.get(work.gallery.floor) ?? `Floor ${work.gallery.floor}`,
        stops: onThisFloor,
      });
    }

    stopNumber += 1;
    const stay = stayFor(work, kids);
    planned += stay;

    items.push({
      kind: 'stop',
      number: stopNumber,
      work,
      stay,
      plannedAt: planned,
    });

    previous = work;
  }

  const out = stepFree ? WALK.toExitStepFree : WALK.toExit;
  planned += out;
  items.push({
    kind: 'walk',
    minutes: out,
    text: `Down ${stepFree ? 'by lift' : 'the stairs'} to the Atrium and straight out — `
      + 'the shop is on your left if you want it.',
  });

  items.push({
    kind: 'terminus',
    at: 'end',
    kicker: 'End · Floor 0',
    title: 'Exit',
    text: `${stopNumber} works in ${planned} minutes. You saw a fraction of one percent `
      + 'of what is here, which is the correct amount.',
  });

  return { items, plannedMinutes: planned, stopCount: stopNumber };
}

export const focusLabel = (focus) =>
  focus.length ? focus.map((tag) => TAG_LABELS.get(tag) ?? tag).join(', ') : 'Greatest hits';
