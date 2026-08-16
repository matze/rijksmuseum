/** The full catalogue entry, over the line.
 *
 *  Every fact in the table comes from the museum's own record; the closing note
 *  says where, because a guide that insists nothing is guessed should be willing
 *  to show its working. */

import { el } from './dom.js';
import { plate, plateVars } from './plate.js';
import { onTheLine } from './route.js';
import { PHASE, REGIONS } from './state.js';

/** Above the two-column breakpoint the plate has a column of its own and is
 *  drawn at up to 840px; the stylesheet holds it to the height of the window,
 *  so a portrait work asks for more file than it shows. That is the trade the
 *  sheet is for. */
const SHEET_SIZES = '(min-width: 1160px) 840px, (min-width: 656px) 584px, calc(100vw - 36px)';

/** Cited sources are also offered as links, so the reading behind the text is
 *  one tap away. The article is whichever source is an encyclopaedia entry. */
const WIKIPEDIA = /^https:\/\/en\.wikipedia\.org\/wiki\//;

const link = (href, text) => href
  ? el('div', {}, el('a', { href, target: '_blank', rel: 'noreferrer', text }))
  : null;

const fact = (key, value) => value
  ? el('div', { class: 'fact' },
    el('span', { class: 'kicker k', text: key }),
    el('span', { class: 'v', text: value }))
  : null;

/** Where the museum says the work is, in the head of the sheet.
 *
 *  A room and a floor is what the line walks to. Outside the main building
 *  there is no floor to climb to, so the place names itself instead — and for
 *  the works the museum publishes no location for at all, saying so is the only
 *  honest line, and the reason the work is not on the line. */
const whereabouts = (where) => {
  if (!where) return 'Location not published';

  if (where.building === 'HG' && where.floor !== null) {
    return `Room ${where.room} · Floor ${where.floor}`;
  }

  return [where.house?.en, where.name?.en ?? `Room ${where.room}`].filter(Boolean).join(' · ');
};

/** Why a work is missing from every plan, said on the work's own sheet.
 *
 *  The visitor meets these in the contact sheet, permanently dimmed, and is
 *  owed the reason. Neither of the two is that the work is unimportant. */
const whyNotWalked = (work) => {
  if (onTheLine(work)) return null;

  if (!work.gallery) {
    return 'The museum publishes no gallery for this object, so the guide has nowhere to '
      + 'put it on the line. That is a gap in the data rather than a statement about the '
      + 'work — check the museum’s own entry for where it is hanging today.';
  }

  return `It stands in the ${work.gallery.house?.en ?? work.gallery.building}, which the `
    + 'line through the main building does not enter. Worth its own walk.';
};

/** Everything in a work's prose that names a place on it, in reading order.
 *
 *  A block either points whole or points by phrase, so an anchor is a block or
 *  one of its spans. The number is all that ties the words to their part of the
 *  painting: they and the hotspot lying over the work carry the same one, which
 *  is what lets one listener light either from the other. */
const anchors = (work) => new Map([work.timeline, ...work.detail, ...work.look]
  .flatMap((source) => (source.region ? [source] : source.spans ?? []))
  .map((source, index) => [source, index]));

/** A block of prose, with its anchored phrases marked.
 *
 *  The spans carry offsets into the block's own text, so the words between them
 *  stay plain text nodes and nothing empty is ever appended. */
function block(tag, source, ids) {
  if (!source.spans) return el(tag, { text: source.text, 'data-region': ids.get(source) });

  const parts = [];
  let read = 0;

  for (const span of source.spans) {
    if (span.start > read) parts.push(source.text.slice(read, span.start));

    parts.push(el('span', {
      'data-region': ids.get(span),
      text: source.text.slice(span.start, span.end),
    }));
    read = span.end;
  }

  if (read < source.text.length) parts.push(source.text.slice(read));

  return el(tag, {}, parts);
}

/** The transparent hit area over the part of the work a block names. Nothing is
 *  drawn here — the dimming is the frame's own, and this only has to be hovered. */
const hotspot = ([anchored, id]) => el('div', {
  class: 'plate-region', 'data-region': id, 'aria-hidden': 'true',
  style: {
    '--region-x': anchored.region[0],
    '--region-y': anchored.region[1],
    '--region-w': anchored.region[2],
    '--region-h': anchored.region[3],
  },
});

/** The switch for the links between the prose and the work.
 *
 *  Anchored prose is ruled underneath so it can be found without hovering for it,
 *  and on a work with much to say that is a lot of rule. This turns the whole of
 *  it off — rules, hotspots and veil — and the stylesheet does the turning, off
 *  one attribute on the sheet. It is drawn only where the feature runs. */
const regionSwitch = (state, actions) => el('button', {
  type: 'button', class: 'btn btn-ghost sheet-regions',
  'aria-pressed': String(state.regions === REGIONS.on),
  onClick: actions.toggleRegions,
},
el('span', { text: 'Highlight' }),
el('span', { class: 'switch', 'aria-hidden': 'true' }));

export function renderDetail(work, state, actions) {
  const title = work.displayTitle ?? work.title.en ?? work.title.nl;
  const byline = [work.artist, work.date].filter(Boolean).join(', ');
  const dimensions = work.dimensions?.height_cm && work.dimensions?.width_cm
    ? `${work.dimensions.height_cm} × ${work.dimensions.width_cm} cm`
    : work.dimensions?.display;
  // The sheet is reachable from the contact sheet on the setup screen too, where
  // there is no line to go back to.
  const back = state.phase === PHASE.setup ? 'Back to the plan' : 'Back to the line';
  const ids = anchors(work);

  return el('div', {
    class: 'sheet', role: 'dialog', 'aria-modal': 'true', 'aria-label': title,
    'data-regions': state.regions,
  },
  el('div', { class: 'sheet-head' },
    el('div', {},
      el('span', { class: 'kicker', text: whereabouts(work.gallery) }),
      el('div', { class: 'sheet-head-end' },
        ids.size
          ? [regionSwitch(state, actions),
            el('span', { class: 'sheet-head-dot', 'aria-hidden': 'true', text: '·' })]
          : null,
        el('button', {
          type: 'button', class: 'btn btn-ghost',
          style: { padding: '0' },
          onClick: actions.closeDetail, text: back,
        })))),

  el('div', { class: 'sheet-body' },
    el('div', { class: 'sheet-plate' },
      el('div', { class: 'plate-frame', style: plateVars(work) },
        plate(work, SHEET_SIZES),
        ids.size
          ? el('div', { class: 'plate-regions' }, [...ids].map(hotspot))
          : null)),
    el('div', { class: 'sheet-text' },
      el('h2', { text: title }),
      byline ? el('div', { class: 'byline muted', text: byline }) : null,
      block('p', work.timeline, ids),
      work.detail.map((paragraph) => block('p', paragraph, ids)),

      el('div', { class: 'section-label', style: { color: 'var(--color-accent-700)' } },
        'What to look for'),
      el('ol', { class: 'look' },
        work.look.map((point) => block('li', point, ids))),

      el('div', { class: 'facts' },
        fact('Attribution', work.attribution !== work.artist ? work.attribution : null),
        fact('Medium', work.medium?.en ?? work.medium?.nl),
        fact('Dimensions', dimensions),
        fact('Where', work.gallery
          ? `${work.gallery.name?.en ?? 'Room ' + work.gallery.room}, `
            + `Room ${work.gallery.room}`
          : null),
        fact('Planned stay', onTheLine(work) ? `${work.stayMinutes} minutes` : null),
        fact('Credit', work.credit?.en ?? work.credit?.nl)),

      state.kids && work.kids
        ? el('div', { class: 'ask' },
          el('span', { class: 'kicker label', text: 'Ask them' }),
          el('span', { class: 'text', text: work.kids }))
        : null,

      el('div', { class: 'provenance quiet' },
        whyNotWalked(work) ? el('div', { text: whyNotWalked(work) }) : null,
        el('div', { text: `Object ${work.objectNumber}. Facts retrieved from the `
          + `Rijksmuseum collection data on ${work.retrieved}. Image public domain.` }),
        link(work.page, 'The museum’s own entry for this work'),
        link(work.sources.find((source) => WIKIPEDIA.test(source)),
          'Further reading on Wikipedia')),

      el('button', {
        type: 'button', class: 'btn btn-primary btn-block',
        onClick: actions.closeDetail, text: back,
      }))));
}

/** Flip the links on or off in place. Nothing about the sheet changes but one
 *  attribute the stylesheet reads, and re-rendering would cost the reader their
 *  place in a description they are in the middle of. */
export function paintRegions(mode) {
  const sheet = document.querySelector('.sheet');

  if (!sheet) return;

  sheet.dataset.regions = mode;
  sheet.querySelector('.sheet-regions')
    ?.setAttribute('aria-pressed', String(mode === REGIONS.on));
}
