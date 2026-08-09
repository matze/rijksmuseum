/** The matted photograph. One <picture> for the whole guide.
 *
 *  Sizes are declared so the browser picks the narrow file on a phone, and the
 *  aspect ratio is set from the image's real pixel dimensions so the line does
 *  not jump while the plate loads. */

import { el } from './dom.js';

const FORMATS = [['avif', 'image/avif'], ['webp', 'image/webp'], ['jpg', 'image/jpeg']];

const srcset = (number, widths, suffix) =>
  widths.map((width) => `assets/works/${number}-${width}.${suffix} ${width}w`).join(', ');

/**
 * @param {object} work a tour entry
 * @param {string} sizes the CSS `sizes` attribute for this context
 */
export function plate(work, sizes) {
  const { objectNumber, image } = work;
  const widths = image.widths ?? [480, 960, 1600];
  const title = work.displayTitle ?? work.title.en ?? work.title.nl ?? objectNumber;

  const sources = FORMATS.slice(0, -1).map(([suffix, type]) =>
    el('source', { type, sizes, srcset: srcset(objectNumber, widths, suffix) }));

  const img = el('img', {
    class: 'plate',
    src: `assets/works/${objectNumber}-${widths[1] ?? widths[0]}.jpg`,
    srcset: srcset(objectNumber, widths, 'jpg'),
    sizes,
    width: image.pixels?.[0],
    height: image.pixels?.[1],
    loading: 'lazy',
    decoding: 'async',
    alt: `${title}${work.artist ? `, ${work.artist}` : ''}`,
    style: image.aspectRatio ? { aspectRatio: image.aspectRatio } : {},
  });

  return el('picture', { class: 'plate-wrap' }, sources, img);
}
