/** The sentence and the place it names.
 *
 *  On the wide sheet the work stands beside its description and stays there
 *  while the text scrolls past. This is what joins the two: a block of prose
 *  that names a part of the painting and the part itself carry the same number,
 *  so a single listener can light either from the other.
 *
 *  The two directions are not symmetrical. Hovering the text dims the rest of
 *  the work, because the sentence is asking you to look at one place. Hovering
 *  the work dims nothing — you are already looking at it — and only lights the
 *  sentence that is about it.
 *
 *  All of it is attribute writes on nodes that already exist, in the manner of
 *  `focus.js`: nothing here re-renders. */

/** Which side of the sheet the pointer is on. Only the text dims the plate. */
const FROM = { text: 'text', plate: 'plate' };

/** The four numbers the veil is cut from. They are read off the hotspot, which
 *  already carries them to stand where it does, so the box is written down once. */
const GEOMETRY = ['--region-x', '--region-y', '--region-w', '--region-h'];

/**
 * @param {HTMLElement} sheet the rendered detail sheet
 */
export function linkRegions(sheet) {
  const frame = sheet.querySelector('.plate-frame');
  const text = sheet.querySelector('.sheet-text');

  if (!frame || !sheet.querySelector('[data-region]')) return;

  const light = (id, source) => {
    // Read afresh: justification rebuilds a paragraph line by line, cloning the
    // marked phrases it holds, so a phrase that runs over a line break is
    // several elements by now and none of them existed when this was wired up.
    for (const node of sheet.querySelectorAll('[data-region]')) {
      node.dataset.lit = String(node.dataset.region === id);
    }

    frame.dataset.lit = String(id !== null && source === FROM.text);

    const hotspot = sheet.querySelector(`.plate-region[data-region="${id}"]`);

    if (!hotspot) return;

    for (const property of GEOMETRY) {
      frame.style.setProperty(property, hotspot.style.getPropertyValue(property));
    }
  };

  // Every move into a new element reports here, so leaving a marked block for
  // the space around it lands on an unmarked one and puts the light out.
  sheet.addEventListener('pointerover', ({ target }) => {
    const anchor = target.closest('[data-region]');

    if (!anchor) {
      light(null, FROM.plate);

      return;
    }

    light(anchor.dataset.region, text?.contains(anchor) ? FROM.text : FROM.plate);
  });

  sheet.addEventListener('pointerleave', () => light(null, FROM.plate));
}
