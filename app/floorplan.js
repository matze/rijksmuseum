/** The schematic shown under each floor header.
 *
 *  Room positions come from the museum's published plan (see
 *  tools/fetch_floorplan.py). The drawing is an abstraction of that plan, not a
 *  survey: an outline, the two courtyards, a dashed line through the rooms this
 *  visit actually enters, and one dot per stop. Rooms the plan does not label
 *  carry no dot, and the caption says so rather than inventing a position. */

import { svg } from './dom.js';

const VIEW = '0 0 200 104';

/** The courtyards, as the design draws them: two voids inside the ring. */
const COURTYARDS = [[52, 30, 44, 44], [104, 30, 44, 44]];

/** One point per place on the plan, not one per stop.
 *
 *  Stops often share a coordinate: the Gallery of Honour is a single labelled
 *  hall split into bays, so four stops there resolve to one position. Stacking
 *  four dots on it would draw one blob and imply it was one stop. */
function positionsOf(stops) {
  const seen = new Map();

  for (const work of stops) {
    const position = work.gallery.position;

    if (position) seen.set(position.join(','), position);
  }

  return [...seen.values()];
}

export function floorPlan(stops) {
  const points = positionsOf(stops);

  const outline = svg('rect', {
    x: 8, y: 8, width: 184, height: 88, rx: 3,
    fill: 'none', stroke: 'var(--color-divider)', 'stroke-width': 1,
  });

  const courtyards = COURTYARDS.map(([x, y, width, height]) => svg('rect', {
    x, y, width, height, fill: 'none', stroke: 'var(--color-divider)', 'stroke-width': 1,
  }));

  const route = points.length > 1
    ? svg('polyline', {
      points: points.map(([x, y]) => `${x},${y}`).join(' '),
      fill: 'none',
      stroke: 'var(--color-accent)',
      'stroke-width': 1.25,
      'stroke-dasharray': '3 3',
      'stroke-linejoin': 'round',
    })
    : null;

  const dots = points.map(([x, y]) => svg('circle', {
    cx: x, cy: y, r: 4.4,
    fill: 'var(--color-bg)', stroke: 'var(--color-accent)', 'stroke-width': 1,
  }));

  return svg('svg', { viewBox: VIEW, role: 'img', 'aria-label': planCaption(stops) },
    outline, courtyards, route, dots);
}

export function planCaption(stops) {
  const dots = positionsOf(stops).length;
  const unplaced = stops.filter((work) => !work.gallery.position).length;
  const count = stops.length === 1 ? 'One stop' : `${stops.length} stops`;

  if (!dots) {
    return `${count} on this floor, in rooms the published plan does not number, `
      + 'so the outline below is the floor without them.';
  }

  const spread = dots === stops.length - unplaced ? ''
    : `, ${dots === 1 ? 'all in one hall' : `gathered in ${dots} places`}`;

  const tail = unplaced
    ? unplaced === 1
      ? ' One of them is in a room the plan does not number, and so carries no dot.'
      : ` ${unplaced} of them are in rooms the plan does not number, and so carry no dot.`
    : '';

  return 'The galleries ring the two courtyards, and the numbers run with the walk. '
    + `${count} on this floor${spread}, then the stairs again.${tail}`;
}
