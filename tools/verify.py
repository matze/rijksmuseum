# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml>=6.0", "requests>=2.31"]
# ///
"""Assert the invariants the generated data has to satisfy before it ships.

`DESIGN.md` asks that nothing be guessed. Most of that discipline lives in the
retrieval scripts, which only ever copy values the museum publishes; this script
covers the seam where hand-written prose meets retrieved fact, and fails the
build when the two disagree.
"""

from __future__ import annotations

import json
import re
import sys
from collections.abc import Iterator
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import ASSETS, DATA, ROOT  # noqa: E402

IMAGE_WIDTHS = [480, 960, 1600, 2400]
IMAGE_FORMATS = ["avif", "webp", "jpg"]
KEPT = 0.7  # of each side of a photograph, at least, once its border is clipped
MOST_OF_A_SIDE = 0.8  # of the work, which is as wide as a region may point
LEAST_OF_A_SIDE = 0.02  # of the work, below which the dimming lights nothing
MAIN_BUILDING = "HG"
RECORD_URI = re.compile(r"^https://id\.rijksmuseum\.nl/\d+$")
ARTICLE_URI = re.compile(r"^https://en\.wikipedia\.org/wiki/[^\s?#]+$")


#: Tags that carry meaning in the app without appearing on the setup screen.
INTERNAL_TAGS = {"kidsfav"}


def selectable_tags() -> set[str]:
    """The focus tags the setup screen offers, read from the app's own vocabulary.

    A tag that is not in it can never be chosen, so a work carrying one is
    unreachable by any route the visitor can ask for.
    """
    source = (ROOT / "app" / "route.js").read_text()
    block = re.search(r"ARTIST_TAGS = \[(.*?)\];.*?THEME_TAGS = \[(.*?)\];", source, re.S)

    if not block:
        raise SystemExit("app/route.js: cannot find the tag vocabulary")

    return set(re.findall(r"\['([\w-]+)'", block.group(1) + block.group(2)))


class Report:
    def __init__(self) -> None:
        self.problems: list[str] = []
        self.notes: list[str] = []

    def fail(self, message: str) -> None:
        self.problems.append(message)

    def note(self, message: str) -> None:
        self.notes.append(message)


def check_catalogue(catalogue: list[dict], report: Report) -> None:
    for entry in catalogue:
        where = f"{entry['objectNumber']}"

        if not entry.get("title"):
            report.fail(f"{where}: no title in any language")

        if not entry["gallery"].get("code"):
            report.fail(f"{where}: on view but no gallery code")

        if not entry["image"].get("service"):
            report.fail(f"{where}: no IIIF image service")

        if not entry.get("retrieved"):
            report.fail(f"{where}: no retrieval date")

    undated = [e["objectNumber"] for e in catalogue if not e.get("date")]

    if undated:
        report.note(f"{len(undated)} catalogue entries carry no production date")


def check_curated(tour: list[dict], catalogue: dict[str, dict], report: Report) -> None:
    known = selectable_tags() | INTERNAL_TAGS

    for path in sorted((DATA / "curated").glob("*.md")):
        front = yaml.safe_load(path.read_text().split("---")[1])
        number = front["objectNumber"]

        if path.stem != number:
            report.fail(f"{path.name}: filename does not match objectNumber {number}")

        entry = catalogue.get(number)

        if not entry:
            report.fail(f"{path.name}: {number} is not in the on-view catalogue")
            continue

        # A source pointing at the museum's own record must point at *this* record,
        # or the prose is cited against a different object than the facts.
        for source in front["sources"]:
            if RECORD_URI.match(source) and source != entry["uri"]:
                report.fail(f"{path.name}: cites {source}, but {number} is {entry['uri']}")

            # Object pages carry an opaque hash, which is exactly the kind of thing
            # that gets typed from memory instead of copied from the record.
            if (source.startswith("https://www.rijksmuseum.nl/") and entry.get("page")
                    and source != entry["page"]):
                report.fail(f"{path.name}: cites {source}, but the museum's page for "
                            f"{number} is {entry['page']}")

        for tag in set(front.get("tags", [])) - known:
            report.fail(f"{path.name}: tag '{tag}' is not one the setup screen offers")

        if not any(source.startswith("https://www.rijksmuseum.nl/")
                   for source in front["sources"]):
            report.note(f"{path.name}: no museum object page among the sources")

        # The detail sheet offers the encyclopaedia entry as a link, so a
        # half-written one would ship as a dead end rather than a citation.
        for source in front["sources"]:
            if "wikipedia.org" in source and not ARTICLE_URI.match(source):
                report.fail(f"{path.name}: {source} is not an English Wikipedia article URL")

    for work in tour:
        number = work["objectNumber"]

        if work["gallery"]["building"] != MAIN_BUILDING:
            report.fail(f"{number}: in building {work['gallery']['building']}, which the "
                        f"main-building route cannot reach")

        if work["gallery"]["floor"] is None:
            report.fail(f"{number}: no floor, so it cannot be placed on the route")

        for width in IMAGE_WIDTHS:
            for suffix in IMAGE_FORMATS:
                image = ASSETS / "works" / f"{number}-{width}.{suffix}"

                if not image.exists():
                    report.fail(f"{number}: missing {image.relative_to(ASSETS.parent)}")

        if not work["image"].get("aspectRatio"):
            report.fail(f"{number}: no aspect ratio, so the plate cannot reserve space")

        check_crop(number, work["image"].get("crop"), report)

        check_spans(number, work, report)

        for where, region in anchored(work):
            check_region(f"{number} {where}", region, report)


def check_crop(number: str, crop: list[float] | None, report: Report) -> None:
    """A content box the guide clips its plate to.

    The box is what the visitor sees of the work, so a box that leaves the
    photograph, inverts, or takes a third of the picture away is a reading gone
    wrong rather than a border: it would hide the work and no test but this one
    would notice.
    """
    if crop is None:
        return

    x, y, width, height = crop

    if not (0 <= x and 0 <= y and width > 0 and height > 0
            and x + width <= 1.0001 and y + height <= 1.0001):
        report.fail(f"{number}: crop {crop} is not a box inside the photograph")

    if min(width, height) < KEPT:
        report.fail(f"{number}: crop keeps {min(width, height):.0%} of a side, which is "
                    f"more than a border")


def anchored(work: dict) -> Iterator[tuple[str, dict]]:
    """Every region a work's prose points at, and the words that point at it.

    A block either points whole or points by phrase; the phrases carry offsets
    into the block's own text, so a slice that has drifted off the end of it
    would render as the wrong words under the right box.
    """
    numbered = [(f"{name} {index + 1}", block)
                for name in ("detail", "look")
                for index, block in enumerate(work[name])]

    for where, block in [("timeline", work["timeline"]), *numbered]:
        if "region" in block:
            yield where, block["region"]

        for span in block.get("spans", []):
            phrase = block["text"][span["start"]:span["end"]]

            yield f"{where} '{phrase[:32]}'", span["region"]


def check_spans(number: str, work: dict, report: Report) -> None:
    """The slices of prose that point at a part of the work.

    They are offsets rather than copies of the words, so nothing in the file
    itself shows when one has slipped: the guide would quietly light the wrong
    phrase. A block also points either whole or by phrase, never both, or two
    regions would answer to the same cursor.
    """
    for name, block in [("timeline", work["timeline"]),
                        *((name, block) for name in ("detail", "look")
                          for block in work[name])]:
        spans = block.get("spans", [])

        if spans and "region" in block:
            report.fail(f"{number} {name}: points both whole and by phrase")

        for span, following in zip(spans, spans[1:] + [None]):
            if not 0 <= span["start"] < span["end"] <= len(block["text"]):
                report.fail(f"{number} {name}: phrase {span['start']}–{span['end']} is not "
                            f"inside its own text of {len(block['text'])} characters")

            if following and span["end"] > following["start"]:
                report.fail(f"{number} {name}: phrases {span['start']}–{span['end']} and "
                            f"{following['start']}–{following['end']} overlap")


def check_region(where: str, region: list[float], report: Report) -> None:
    """A box on the plate that a block of prose points at.

    Unlike a crop this is meant to be small — it names a hand, or a chicken on a
    belt — so `KEPT` does not apply and the bounds run the other way. What it
    must be is a part: a region the size of the work says nothing that the plate
    beside it was not already saying, and one a few pixels across is a typo.
    """
    x, y, width, height = region

    if not (0 <= x and 0 <= y and width > 0 and height > 0
            and x + width <= 1.0001 and y + height <= 1.0001):
        report.fail(f"{where}: region {region} is not a box inside the work")

    if min(width, height) > MOST_OF_A_SIDE:
        report.fail(f"{where}: region covers {min(width, height):.0%} of a side, which "
                    f"points at the whole work rather than at a part of it")

    if min(width, height) < LEAST_OF_A_SIDE:
        report.fail(f"{where}: region is {min(width, height):.1%} of a side, too small to "
                    f"find on the plate")


def check_route_coverage(tour: list[dict], galleries: dict, report: Report) -> None:
    floors = sorted({work["gallery"]["floor"] for work in tour})
    report.note(f"{len(tour)} curated works across floors {floors}")

    unplaced = [work["objectNumber"] for work in tour
                if "position" not in galleries.get(work["gallery"]["code"], {})]

    if unplaced:
        report.note(f"{len(unplaced)} curated works are in rooms the published plan does "
                    f"not label: {', '.join(unplaced)}")


def main() -> None:
    catalogue = json.loads((DATA / "catalogue.json").read_text())
    galleries = json.loads((DATA / "galleries.json").read_text())
    tour = json.loads((DATA / "tour.json").read_text())
    by_number = {entry["objectNumber"]: entry for entry in catalogue}

    report = Report()
    check_catalogue(catalogue, report)
    check_curated(tour, by_number, report)
    check_route_coverage(tour, galleries, report)

    for note in report.notes:
        print(f"note: {note}")

    for problem in report.problems:
        print(f"FAIL: {problem}", file=sys.stderr)

    if report.problems:
        raise SystemExit(f"{len(report.problems)} problems")

    print(f"ok — {len(catalogue)} catalogue entries, {len(tour)} curated works, "
          f"{len(galleries)} rooms")


if __name__ == "__main__":
    main()
