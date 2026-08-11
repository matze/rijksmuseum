/** The matted photograph. One <picture> for the whole guide.
 *
 *  Sizes are declared so the browser picks the narrow file on a phone. The
 *  <picture> is the window: it holds the proportions of the work itself, and the
 *  image is laid inside it at whatever size puts the work in the opening. For
 *  most works that is the whole photograph; for the ones shot in their frame, or
 *  painted on a panel that is not painted to its edge, `image.crop` says which
 *  part of it is the work, and the border falls outside the window.
 *
 *  The window is set here rather than in the stylesheet because it is a fact
 *  about one work, and it is set as custom properties rather than as finished
 *  lengths because the arithmetic has to run again at every width the plate is
 *  drawn at. */

import { el } from './dom.js';

const FORMATS = [['avif', 'image/avif'], ['webp', 'image/webp'], ['jpg', 'image/jpeg']];

const srcset = (number, widths, suffix) =>
  widths.map((width) => `assets/works/${number}-${width}.${suffix} ${width}w`).join(', ');

/** The window, as custom properties: where the work sits in the photograph and
 *  what proportions it stands in.
 *
 *  Exported because the detail sheet wraps the plate in a frame it has to size
 *  the same way, and custom properties inherit down rather than up.
 *
 * @param {object} work a tour entry
 */
export function plateVars(work) {
  const { image } = work;
  const [x, y, width, height] = image.crop ?? [0, 0, 1, 1];
  const photograph = image.pixels
    ? image.pixels[0] / image.pixels[1]
    : Number(image.aspectRatio) || 1;

  return {
    '--crop-x': x,
    '--crop-y': y,
    '--crop-w': width,
    '--crop-h': height,
    '--crop-ratio': (photograph * width / height).toFixed(4),
  };
}

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
  });

  return el('picture', { class: 'plate-wrap', style: plateVars(work) }, sources, img);
}
