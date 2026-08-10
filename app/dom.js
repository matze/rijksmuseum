/** Minimal element construction. The views are small enough that building DOM
 *  directly is shorter than any templating we would have to ship to the phone. */

/** Custom properties are the one thing `style` will not take by assignment. */
const setStyle = (node, declarations) => {
  for (const [property, value] of Object.entries(declarations)) {
    if (property.startsWith('--')) node.style.setProperty(property, String(value));
    else node.style[property] = value;
  }
};

/**
 * @param {string} tag
 * @param {Object<string, *>} [props] attributes; `class`, `style`, `on*` handlers,
 *   `text` for a text child. A null or undefined value omits the attribute.
 * @param {...(Node|string|null|undefined|Array)} children
 */
export function el(tag, props = {}, ...children) {
  const node = document.createElement(tag);

  for (const [key, value] of Object.entries(props)) {
    if (value === null || value === undefined || value === false) continue;

    if (key === 'text') node.textContent = value;
    else if (key.startsWith('on')) node.addEventListener(key.slice(2).toLowerCase(), value);
    else if (key === 'style' && typeof value === 'object') setStyle(node, value);
    else node.setAttribute(key, value === true ? '' : String(value));
  }

  node.append(...children.flat(Infinity).filter((child) => child !== null && child !== undefined));

  return node;
}

export function svg(tag, props = {}, ...children) {
  const node = document.createElementNS('http://www.w3.org/2000/svg', tag);

  for (const [key, value] of Object.entries(props)) {
    if (value === null || value === undefined) continue;

    node.setAttribute(key, String(value));
  }

  node.append(...children.flat(Infinity).filter(Boolean));

  return node;
}

export const clear = (node) => { node.replaceChildren(); return node; };
