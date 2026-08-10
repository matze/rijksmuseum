# /// script
# requires-python = ">=3.11"
# dependencies = ["requests>=2.31", "pillow>=11.3", "pyyaml>=6.0", "numpy>=2.0"]
# ///
"""Measure the part of each curated photograph that is the work itself.

Some works are photographed inside their frame, and some are painted on a panel
that carries an unpainted edge. Either way the plate arrives with a band around
it that the visitor did not come to look at — the KNIL soldier's panel shows a
pale strip of hardboard down two sides, the Van der Helst militia piece is shot
with its whole dark frame.

Each side is read on its own, along the outer twentieth of the photograph. A
border ends in an edge — a hard change of colour running the length of the side —
and the picture inside it does not: it shifts a little at every line and nowhere
much more than that. Finding the hardest change, and asking that it be several
times harder than the strip's own restlessness, is what separates the two.

The reading is deliberately timid, because a border left in place costs the
visitor nothing and a picture cut into is gone. It will not cut deeper than a
fiftieth of a side, the band it cuts off has to be even in itself, and a side
where nothing stands out is left whole — which is why a ship model photographed
against a gallery wall, and the lit floor at the foot of the Night Watch, both
keep every pixel they came with.

Frames are past what it will read: their own browns and golds are the painting's,
and they run deeper than the limit. Those are hand-measured in
`data/crops-extra.json`, which is merged over this file's output at build time.

The pixels are not touched. `data/crops.json` records the box as fractions of
the photograph and the guide clips to it in CSS.
"""

from __future__ import annotations

import argparse
import io
import json
import sys
from pathlib import Path
from typing import NamedTuple

import numpy as np
import yaml
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import (CACHE, DATA, Fetcher, image_services, in_parallel,  # noqa: E402
                    object_number, visual_item_uri, write_json)

ANALYSIS_WIDTH = 960  # the derivative `fetch_images.py` caches anyway
WINDOW = 0.05         # of a side, the strip a border is read within
DEEPEST = 0.02        # of a side, the deepest cut that will be read automatically
CLOSE = 3             # lines either side of a boundary, for the change across it
MARK = 0.03           # the colour change a boundary has to make, of the 0–1 range
SHARP = 3.0           # and that much more than the strip's own line-to-line change
QUIET = 0.004         # below which line-to-line change is the camera, not the work
EVEN = 0.5            # of that change, the most a border may vary within itself
FADED = 0.5           # of that change, by which the crossing has finished
BAND = 0.5            # nearer the border than the picture, and it is still border


class Border(NamedTuple):
    depth: int           # lines of border, counting in from the side
    tone: np.ndarray     # the colour the border itself is


def spread(colours: np.ndarray) -> np.ndarray:
    """Root-mean-square distance in RGB, which is the whole colour sense here."""
    return np.sqrt((colours ** 2).mean(axis=-1))


def curated_numbers() -> list[str]:
    return [yaml.safe_load(path.read_text().split("---")[1])["objectNumber"]
            for path in sorted((DATA / "curated").glob("*.md"))]


def border(lines: np.ndarray) -> Border:
    """The border on the side `lines` starts at.

    Every line of the outer strip is taken at its median colour, so that a line
    speaks for whatever covers most of it, and the strip is read for the one
    place where that colour changes hardest over three lines. A border ends in
    exactly such an edge — pale hardboard against paint, a lit frame lip against
    a dark ground — and a picture, however it shades from its own edge, does not:
    it moves a little at every line and nowhere much more than that. Measuring
    the change against the strip's own restlessness is what tells the two apart,
    and it is why the lit floor at the foot of the Night Watch stays where it is.

    An edge on the photograph is a few lines wide, not one: a panel's ragged rim
    and the softness of the scan spread it out. So the sharpest line only says
    where the edge is, and the cut falls at the first line past it where the
    changing has died down and the colour has stopped being the band's — the
    whole of the crossing, however wide, and no further into the picture.

    Then it looks again. A frame shows its dark outer face and its lit lip one
    behind the other, and each is a band in its own right, so bands are taken off
    one at a time until what is left no longer reads as one. The band also has to
    be even in itself: a stretch that varies as much as the edge it ends at is a
    piece of picture that happens to end sharply — the sitter's shoulder, not a
    margin.

    Nothing deeper than a fiftieth of the side is read here. Past that a wrong
    reading starts to cost real picture, and what lies out there is usually a
    whole frame — measured by hand, in `data/crops-extra.json`.
    """
    window = max(8, round(WINDOW * len(lines)))
    limit = max(2, round(DEEPEST * len(lines)))
    median = np.median(lines[:window], axis=1)
    change = np.array([spread(median[max(0, line - CLOSE):line].mean(axis=0)
                              - median[line:line + CLOSE].mean(axis=0))
                       for line in range(1, window - CLOSE)])
    threshold = max(MARK, SHARP * max(np.median(change), QUIET))
    picture = median[limit:window].mean(axis=0)
    depth = 0

    while depth < limit:
        edge = depth + 1 + int(np.argmax(change[depth:limit]))
        peak = change[edge - 1]
        band = median[depth:edge].mean(axis=0)

        if peak < threshold or spread(median[depth:edge] - band).mean() > EVEN * peak:
            break

        cut = next((line for line in range(edge, limit + 1)
                    if change[line - 1] <= FADED * peak
                    and spread(median[line] - band) >= BAND * spread(median[line] - picture)), 0)

        if not cut:
            break

        depth = cut

    return Border(depth, median[:depth].mean(axis=0) if depth else median[0])


def content_box(image: Image.Image) -> list[float] | None:
    """The work's own box within the photograph, as [x, y, width, height] fractions.

    Each side is read on its own. A border is often only on one side — a panel
    photographed square shows its unpainted edge where the plank was cut, and
    nowhere else — so nothing here asks the four readings to agree.
    """
    rows = np.asarray(image.convert("RGB"), dtype=np.float32) / 255
    columns = rows.transpose(1, 0, 2)
    sides = [border(lines).depth for lines in (columns, rows, columns[::-1], rows[::-1])]

    if not any(sides):
        return None

    height, width = rows.shape[:2]
    left, top, right, bottom = (round(depth / side, 4) for depth, side in
                                zip(sides, (width, height, width, height)))

    return [left, top, round(1 - left - right, 4), round(1 - top - bottom, 4)]


def photograph(service: str, fetcher: Fetcher) -> Image.Image:
    source = fetcher.get_bytes(f"{service}/full/{ANALYSIS_WIDTH},/0/default.jpg", suffix=".jpg")

    return Image.open(io.BytesIO(source))


def review(found: dict[str, tuple[Image.Image, list[float] | None]], path: Path) -> None:
    """A contact sheet with every box drawn on its photograph, for reading by eye."""
    cell, columns = 220, 6
    rows = -(-len(found) // columns)
    sheet = Image.new("RGB", (columns * cell, rows * (cell + 18)), (24, 24, 26))
    draw = ImageDraw.Draw(sheet)

    for index, (number, (image, box)) in enumerate(sorted(found.items())):
        thumb = image.copy()
        thumb.thumbnail((cell - 10, cell - 10))
        left, top = (index % columns) * cell + 5, (index // columns) * (cell + 18) + 5
        sheet.paste(thumb, (left, top))

        if box:
            x, y, width, height = box
            draw.rectangle([left + x * thumb.width, top + y * thumb.height,
                            left + (x + width) * thumb.width - 1,
                            top + (y + height) * thumb.height - 1], outline=(255, 90, 60))

        draw.text((left, top + cell - 8), f"{number} {'crop' if box else '—'}", fill=(200, 200, 200))

    sheet.save(path)
    print(f"wrote {path}", file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--review", type=Path, help="write a contact sheet of the boxes here")
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()

    wanted = set(curated_numbers())
    records = Fetcher("records")
    candidates = json.loads((CACHE / "candidates.json").read_text())["uris"]
    curated = [record for uri in candidates if records.path_for(uri).exists()
               if (record := records.get_json(uri)) and object_number(record) in wanted]
    services = image_services(curated, records)

    images = Fetcher("images")
    found: dict[str, tuple[Image.Image, list[float] | None]] = {}

    def measure(record: dict) -> tuple[str, Image.Image, list[float] | None]:
        service = services[visual_item_uri(record)]["service"]
        image = photograph(service, images)

        return object_number(record), image, content_box(image)

    measurable = [record for record in curated if services.get(visual_item_uri(record))]

    for number, image, box in in_parallel(measurable, measure, workers=args.workers,
                                          label="crops"):
        found[number] = (image, box)

    crops = {number: box for number, (_, box) in sorted(found.items()) if box}
    write_json(DATA / "crops.json", crops)
    print(f"{len(crops)}/{len(found)} curated works carry a border", file=sys.stderr)

    if args.review:
        review(found, args.review)


if __name__ == "__main__":
    main()
