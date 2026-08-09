# /// script
# requires-python = ">=3.11"
# dependencies = ["requests>=2.31", "pypdf[image]>=5.1", "pillow>=11.3"]
# ///
"""Read room positions out of the museum's own visitor floor plan.

The collection API knows which room a work hangs in but nothing about where that
room is. The published plattegrond carries both: a drawing of each floor, and a
text layer placing every room number on it. Those label positions are the only
geometry in this project that is measured rather than drawn by hand.

Writes `data/floorplan.json` and, for visual checking, the plan images the
coordinates were taken from into `docs/reference/`.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from pypdf import PdfReader

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import DATA, ROOT, Fetcher, write_json  # noqa: E402

PLAN_URL = ("https://www.rijksmuseum.nl/assets/6d50aec4-8feb-4d9e-aa40-a4b772190697"
            "?c=394feaa68540fae3ffc6e057f76ba56abc6107deee57d30888976d3147400f6d")
PLAN_PAGE = "https://www.rijksmuseum.nl/en/about-us/rijksmuseum-downloads"
REFERENCE = ROOT / "docs" / "reference"

ROOM_LABEL = re.compile(r"^(\d)\.(\d{1,2})$")
# A page carrying the plan itself, rather than the highlights list, has the
# drawing behind it as one large raster and several room numbers placed on it.
MAP_RASTER_PIXELS = 1_000_000
MAP_MIN_LABELS = 4

# The schematic in the guide keeps the design's proportions; plan coordinates are
# normalised into this box, with the y axis flipped from PDF space into SVG space.
VIEW_WIDTH, VIEW_HEIGHT = 200.0, 104.0
MARGIN = 14.0


def labelled_rooms(page) -> list[tuple[str, float, float]]:
    found: list[tuple[str, float, float]] = []

    def visit(text, _cm, tm, _font, _size):
        if ROOM_LABEL.match(stripped := text.strip()):
            found.append((stripped, tm[4], tm[5]))

    page.extract_text(visitor_text=visit)

    return found


def normalise(rooms: list[tuple[str, float, float]]) -> dict[str, list[float]]:
    """Fit the measured label positions into the schematic's view box."""
    xs = [x for _, x, _ in rooms]
    ys = [y for _, _, y in rooms]
    span_x, span_y = max(xs) - min(xs) or 1.0, max(ys) - min(ys) or 1.0
    inner_w, inner_h = VIEW_WIDTH - 2 * MARGIN, VIEW_HEIGHT - 2 * MARGIN

    placed: dict[str, list[float]] = {}

    for room, x, y in rooms:
        placed.setdefault(room, [
            round(MARGIN + (x - min(xs)) / span_x * inner_w, 1),
            round(MARGIN + (max(ys) - y) / span_y * inner_h, 1),
        ])

    return placed


def largest_raster(page):
    rasters = [image.image for image in page.images
               if image.image.size[0] * image.image.size[1] > MAP_RASTER_PIXELS]

    return max(rasters, key=lambda i: i.size[0] * i.size[1], default=None)


def save_plan_image(drawing, floor: int) -> str:
    drawing.thumbnail((1800, 1800))
    REFERENCE.mkdir(parents=True, exist_ok=True)
    name = f"floor-{floor}.png"
    drawing.convert("RGB").save(REFERENCE / name)

    return name


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="ignore the HTTP cache")
    args = parser.parse_args()

    fetcher = Fetcher("floorplan", force=args.force)
    REFERENCE.mkdir(parents=True, exist_ok=True)
    pdf_path = REFERENCE / "rijksmuseum-plattegrond.pdf"
    pdf_path.write_bytes(fetcher.get_bytes(PLAN_URL, suffix=".pdf"))

    # Each floor appears twice: once as a highlights list, once as the plan. Both
    # repeat the room numbers, so the plan is picked out by its far larger drawing.
    best: dict[int, tuple] = {}

    for number, page in enumerate(PdfReader(pdf_path).pages, start=1):
        rooms = labelled_rooms(page)
        drawing = largest_raster(page)

        if len(rooms) < MAP_MIN_LABELS or drawing is None:
            continue

        floor = int(rooms[0][0].split(".")[0])
        pixels = drawing.size[0] * drawing.size[1]

        if pixels > best.get(floor, (0,))[0]:
            best[floor] = (pixels, number, rooms, drawing)

    floors: dict[str, dict] = {}

    for floor, (_, number, rooms, drawing) in sorted(best.items()):
        image = save_plan_image(drawing, floor)
        floors[str(floor)] = {
            "rooms": normalise(rooms),
            "source": {"page": number, "image": f"docs/reference/{image}"},
        }
        print(f"floor {floor}: {len(rooms)} labels on page {number}", file=sys.stderr)

    write_json(DATA / "floorplan.json", {
        "viewBox": f"0 0 {VIEW_WIDTH:.0f} {VIEW_HEIGHT:.0f}",
        "source": {"url": PLAN_URL, "page": PLAN_PAGE,
                   "file": str(pdf_path.relative_to(ROOT))},
        "floors": floors,
    })


if __name__ == "__main__":
    main()
