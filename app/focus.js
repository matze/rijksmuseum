/** Focus, dimming, and the self-hiding header.
 *
 *  Exactly one element on the line is lit. Which one is decided on scroll, by
 *  proximity to a line across the upper third of the screen — the place a
 *  walking visitor's eye actually rests. All of it is attribute writes on
 *  existing nodes: nothing re-renders while the page is moving. */

/** Where the reading line sits, as a fraction of viewport height. */
const READING_LINE = 0.42;
/** Scroll distance before the header commits to hiding or returning. */
const HYSTERESIS = 6;
/** Above this point the header is always shown, so the top never feels broken. */
const ALWAYS_SHOWN_ABOVE = 120;

/** Where the eye rests, in viewport coordinates.
 *
 *  Normally a fixed line across the upper third. At the two ends of the page
 *  that line is unreachable — nothing can be scrolled above the Atrium or below
 *  the exit — so a fixed line would light the wrong entry while the page sits
 *  still. There the line meets the stranded terminus instead, and eases back to
 *  its resting place over the first and last screen of scrolling. */
function readingLine(first, last) {
  const height = window.innerHeight;
  const rest = height * READING_LINE;
  const scrolled = window.scrollY || 0;
  const toGo = document.documentElement.scrollHeight - height - scrolled;

  // Each end pulls the line onto its terminus while the page is at rest there,
  // and releases it a pixel for every pixel scrolled away from that end.
  const fromStart = first.top + 2 * scrolled;
  const fromEnd = last.bottom - 2 * toGo;

  return Math.min(Math.max(rest, fromEnd), fromStart);
}

/**
 * @param {HTMLElement} root the timeline container
 * @param {(stopNumber: number) => void} onFocusStop called when the lit stop changes
 * @returns {() => void} detach
 */
export function trackFocus(root, onFocusStop) {
  let frame = 0;
  let lastY = null;
  let hidden = false;
  let litStop = null;

  const update = () => {
    frame = 0;

    // Every entry on the line — a card or a walk — competes for the light; its
    // marker follows whichever wins.
    const entries = [...root.querySelectorAll('.card[data-lit], .entry-walk[data-lit]')];

    if (!entries.length) return;

    const line = readingLine(entries[0].getBoundingClientRect(),
      entries.at(-1).getBoundingClientRect());
    let best = entries[0];
    let bestDistance = Infinity;

    for (const entry of entries) {
      const box = entry.getBoundingClientRect();
      const distance = box.top > line ? box.top - line
        : box.bottom < line ? line - box.bottom
        : 0;

      if (distance < bestDistance) {
        bestDistance = distance;
        best = entry;
      }
    }

    for (const entry of entries) {
      const lit = entry === best;
      entry.dataset.lit = String(lit);

      const mark = entry.parentElement?.querySelector('.mark');

      if (mark) mark.dataset.lit = String(lit);
    }

    const number = Number(best.dataset.stopNumber);

    if (number && number !== litStop) {
      litStop = number;
      onFocusStop(number);
    }

    const chrome = document.querySelector('.chrome');

    if (chrome) {
      const y = window.scrollY || 0;
      const previous = lastY ?? y;

      if (y < ALWAYS_SHOWN_ABOVE) hidden = false;
      else if (y - previous > HYSTERESIS) hidden = true;
      else if (previous - y > HYSTERESIS) hidden = false;

      lastY = y;
      chrome.dataset.hidden = String(hidden);
    }
  };

  const onScroll = () => {
    if (frame) return;

    frame = requestAnimationFrame(update);
  };

  window.addEventListener('scroll', onScroll, { passive: true });
  window.addEventListener('resize', onScroll);
  update();

  return () => {
    window.removeEventListener('scroll', onScroll);
    window.removeEventListener('resize', onScroll);

    if (frame) cancelAnimationFrame(frame);
  };
}
