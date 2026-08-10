/** The full catalogue entry, over the line.
 *
 *  Every fact in the table comes from the museum's own record; the closing note
 *  says where, because a guide that insists nothing is guessed should be willing
 *  to show its working. */

import { el } from './dom.js';
import { plate } from './plate.js';

const SHEET_SIZES = '(min-width: 656px) 584px, calc(100vw - 36px)';

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

export function renderDetail(work, state, actions) {
  const title = work.displayTitle ?? work.title.en ?? work.title.nl;
  const byline = [work.artist, work.date].filter(Boolean).join(', ');
  const dimensions = work.dimensions?.height_cm && work.dimensions?.width_cm
    ? `${work.dimensions.height_cm} × ${work.dimensions.width_cm} cm`
    : work.dimensions?.display;

  return el('div', {
    class: 'sheet', role: 'dialog', 'aria-modal': 'true', 'aria-label': title,
  },
  el('div', { class: 'sheet-head' },
    el('div', {},
      el('span', {
        class: 'kicker',
        text: `Room ${work.gallery.room} · Floor ${work.gallery.floor}`,
      }),
      el('button', {
        type: 'button', class: 'btn btn-ghost',
        style: { padding: '0' },
        onClick: actions.closeDetail, text: 'Back to the line',
      }))),

  el('div', { class: 'sheet-body' },
    plate(work, SHEET_SIZES),
    el('h2', { text: title }),
    byline ? el('div', { class: 'byline muted', text: byline }) : null,
    el('p', { text: work.timeline }),
    work.detail.map((paragraph) => el('p', { text: paragraph })),

    el('div', { class: 'section-label', style: { color: 'var(--color-accent-700)' } },
      'What to look for'),
    el('ol', { class: 'look' },
      work.look.map((point) => el('li', { text: point }))),

    el('div', { class: 'facts' },
      fact('Attribution', work.attribution !== work.artist ? work.attribution : null),
      fact('Medium', work.medium?.en ?? work.medium?.nl),
      fact('Dimensions', dimensions),
      fact('Where', `${work.gallery.name?.en ?? 'Room ' + work.gallery.room}, `
        + `Room ${work.gallery.room}`),
      fact('Planned stay', `${work.stayMinutes} minutes`),
      fact('Credit', work.credit?.en ?? work.credit?.nl)),

    state.kids && work.kids
      ? el('div', { class: 'ask' },
        el('span', { class: 'kicker label', text: 'Ask them' }),
        el('span', { class: 'text', text: work.kids }))
      : null,

    el('div', { class: 'provenance quiet' },
      el('div', { text: `Object ${work.objectNumber}. Facts retrieved from the `
        + `Rijksmuseum collection data on ${work.retrieved}. Image public domain.` }),
      link(work.page, 'The museum’s own entry for this work'),
      link(work.sources.find((source) => WIKIPEDIA.test(source)),
        'Further reading on Wikipedia')),

    el('button', {
      type: 'button', class: 'btn btn-primary btn-block',
      onClick: actions.closeDetail, text: 'Back to the line',
    })));
}
