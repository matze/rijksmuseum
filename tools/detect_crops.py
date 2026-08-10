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

Each side is read on its own. The outermost line of the photograph states what
tone the border is, and the border runs until a line has left that tone behind
along most of its length. A side that never leaves it is a work photographed
against a room — a ship model, a dolls' house — and keeps all of its picture.

The reading is deliberately timid, because a border left in place costs the
visitor nothing and a picture cut into is gone. Anything deeper than a hairline
has to be a tone the work itself does not use, and every side has to be
corroborated by another side of the same tone.

Works it will not read are hand-measured in `data/crops-extra.json`, which is
merged over this file's output at build time.

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
LIMIT = 0.12          # how far in from an edge a border may reach
APART = 0.12          # brightness away from the border's tone to be the work
MOSTLY = 0.85         # of a line, before that line counts as the work
SLIVER = 0.01         # of a side, the depth a border may reach on its own word
RARE = 0.05           # of the work may carry the border's tone, past that depth
TOGETHER = 0.15       # brightness within which two sides are the same border
LUMINANCE = np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)


class Border(NamedTuple):
    depth: int    # lines of border, counting in from the side
    tone: float   # the brightness the border itself is


def curated_numbers() -> list[str]:
    return [yaml.safe_load(path.read_text().split("---")[1])["objectNumber"]
            for path in sorted((DATA / "curated").glob("*.md"))]


def border(lines: np.ndarray, work: np.ndarray) -> Border:
    """The border on the side `lines` starts at, given the middle of the work.

    Read from the outside in. The outermost line states the border's own tone;
    every line after it is scored on how much of its length has left that tone
    behind, and the border ends at the first line that is mostly the work. A
    ragged panel edge is therefore cut where the paint takes the line over
    rather than where it first appears, which loses a hair of paint at the
    corners and takes the whole of the pale strip along the sides — the trade
    the eye wants.

    Two readings mean there is no border: a side that is the work from its first
    line was photographed to its edge, and a side that never becomes the work at
    all is a work photographed against a room, where the wall goes on past the
    limit and there is no edge to find.

    What a wrong reading costs grows with how deep it cuts, so past a hairline a
    border has to be a tone the work itself does not use. Without that, a
    picture that opens on an even stretch of sky, or on its own dark ground,
    reads as a margin and loses a tenth of its height.
    """
    limit = max(2, round(LIMIT * len(lines)))
    brightness = lines @ LUMINANCE
    tone = np.median(brightness[0])
    theirs = (abs(brightness - tone) >= APART).mean(axis=1)
    depth = next((line for line in range(limit) if theirs[line] >= MOSTLY), 0)
    familiar = (abs(work - tone) < APART).mean()

    if depth > max(2, round(SLIVER * len(lines))) and familiar > RARE:
        return Border(0, tone)

    return Border(depth, tone)


def content_box(image: Image.Image) -> list[float] | None:
    """The work's own box within the photograph, as [x, y, width, height] fractions.

    A border runs around a work rather than along one side of it, so a reading
    no other side agrees with is dropped.
    """
    rows = np.asarray(image.convert("RGB"), dtype=np.float32) / 255
    columns = rows.transpose(1, 0, 2)
    inset = [max(2, round(LIMIT * length)) for length in rows.shape[:2]]
    middle = (rows[inset[0]:-inset[0], inset[1]:-inset[1]] @ LUMINANCE)
    sides = [border(lines, middle) for lines in (columns, rows, columns[::-1], rows[::-1])]
    corroborated = [side.depth if any(other.depth and other is not side
                                      and abs(other.tone - side.tone) <= TOGETHER
                                      for other in sides) else 0
                    for side in sides]

    if not any(corroborated):
        return None

    height, width = rows.shape[:2]
    left, top, right, bottom = (round(depth / side, 4) for depth, side in
                                zip(corroborated, (width, height, width, height)))

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
