/** The constraint screen. Everything the route needs is chosen here, once. */

import { el } from './dom.js';
import { BUDGETS } from './state.js';
import { ARTIST_TAGS, THEME_TAGS, buildRoute, focusLabel } from './route.js';

const BUDGET_LABELS = new Map([[60, '1 h'], [90, '1½ h'], [120, '2 h'], [180, '3 h']]);

const chip = (label, pressed, onClick, extraClass = '') =>
  el('button', {
    type: 'button',
    class: `chip ${extraClass}`.trim(),
    'aria-pressed': String(pressed),
    onClick,
  }, label);

const wideChip = (label, note, pressed, onClick) =>
  el('button', {
    type: 'button',
    class: 'chip chip-wide',
    'aria-pressed': String(pressed),
    onClick,
  }, el('span', { text: label }), el('span', { class: 'chip-note', text: note }));

export function renderSetup(state, works, actions) {
  const toggleTag = (tag) => () => actions.update((next) => {
    next.focus = next.focus.includes(tag)
      ? next.focus.filter((each) => each !== tag)
      : [...next.focus, tag];
  });

  // The preview counts the route as it will actually be walked, trimming included.
  const { stopCount } = buildRoute(works, state);
  const preview = `${stopCount} ${stopCount === 1 ? 'work' : 'works'} · `
    + `${state.minutes} minutes · ${focusLabel(state.focus).toLowerCase()}`;

  return el('div', { class: 'setup' },
    el('div', { class: 'setup-head' },
      el('div', {
        class: 'kicker',
        style: { color: 'var(--color-accent-700)', letterSpacing: '.16em' },
        text: 'Rijksmuseum',
      }),
      el('button', {
        type: 'button', class: 'btn btn-ghost',
        onClick: actions.toggleTheme, text: actions.themeLabel,
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
        'chip-centred'))),

    el('div', { class: 'section-label' }, 'Artists & highlights'),
    el('div', { class: 'wrap' },
      ARTIST_TAGS.map(([tag, label]) =>
        chip(label, state.focus.includes(tag), toggleTag(tag)))),

    el('div', { class: 'section-label' }, 'Periods & themes'),
    el('div', { class: 'wrap' },
      THEME_TAGS.map(([tag, label]) =>
        chip(label, state.focus.includes(tag), toggleTag(tag)))),
    el('p', { class: 'hint quiet' },
      'Leave both empty for the greatest hits.'),

    el('div', { class: 'section-label' }, 'Walking with'),
    el('div', { class: 'stack' },
      wideChip('Children along', 'shorter stops, a question at each', state.kids,
        () => actions.update((next) => { next.kids = !next.kids; })),
      wideChip('Lifts only, no stairs', 'step-free route', state.stepFree,
        () => actions.update((next) => { next.stepFree = !next.stepFree; }))),

    el('button', {
      type: 'button', class: 'btn btn-primary btn-block',
      onClick: actions.start, text: 'Lay out the route',
    }),
    el('p', { class: 'preview quiet', text: preview }));
}
