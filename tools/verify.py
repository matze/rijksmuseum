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
from datetime import date
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import ASSETS, DATA, ROOT  # noqa: E402

IMAGE_WIDTHS = [480, 960, 1600, 2400]
IMAGE_FORMATS = ["avif", "webp", "jpg"]
KEPT = 0.7  # of each side of a photograph, at least, once a *detected* border is clipped
PROPORTIONS = 0.03  # how far a hand-read box may sit from the work's stated shape
MOST_OF_A_SIDE = 0.8  # of the work, which is as wide as a region may point
LEAST_OF_A_SIDE = 0.02  # of the work, below which the dimming lights nothing
STALE_AFTER_DAYS = 180  # after which a location read off a web page is worth reading again
FLAT = "painting"  # the one kind of object whose size its photograph can be checked against
SHAPE = 0.2  # how far a painting's stated shape may sit from the shape of its photograph
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


def read_by_hand() -> set[str]:
    """The works whose content box is measured in `data/crops-extra.json`."""
    path = DATA / "crops-extra.json"
    boxes = json.loads(path.read_text()) if path.exists() else {}

    return {number for number in boxes if not number.startswith("_")}


def check_curated(tour: list[dict], report: Report) -> None:
    known = selectable_tags() | INTERNAL_TAGS
    written_up = {work["objectNumber"]: work for work in tour}
    by_hand = read_by_hand()

    for path in sorted((DATA / "curated").glob("*.md")):
        front = yaml.safe_load(path.read_text().split("---")[1])
        number = front["objectNumber"]

        if path.stem != number:
            report.fail(f"{path.name}: filename does not match objectNumber {number}")

        entry = written_up.get(number)

        if not entry:
            report.fail(f"{path.name}: {number} did not reach the tour — it was never "
                        f"harvested, or carries no public-domain photograph")
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
        where = work.get("gallery")

        # The main building numbers the floor into the room code, so a work there
        # that reports none was parsed wrong rather than hung somewhere unusual.
        if where and where["building"] == MAIN_BUILDING and where["floor"] is None:
            report.fail(f"{number}: in {where['code']}, which names no floor the route "
                        f"can read")

        for width in IMAGE_WIDTHS:
            for suffix in IMAGE_FORMATS:
                image = ASSETS / "works" / f"{number}-{width}.{suffix}"

                if not image.exists():
                    report.fail(f"{number}: missing {image.relative_to(ASSETS.parent)}")

        if not work["image"].get("aspectRatio"):
            report.fail(f"{number}: no aspect ratio, so the plate cannot reserve space")

        check_crop(work, by_hand, report)
        check_shape(work, report)

        check_spans(number, work, report)

        for where, region in anchored(work):
            check_region(f"{number} {where}", region, report)


def check_crop(work: dict, by_hand: set[str], report: Report) -> None:
    """A content box the guide clips its plate to.

    The box is what the visitor sees of the work, so a box that leaves the
    photograph, inverts, or takes a third of the picture away is a reading gone
    wrong rather than a border: it would hide the work and no test but this one
    would notice.

    A box read by hand is held to a different rule. It is allowed to be deep,
    because a work photographed in its frame really has lost a third of its
    photograph to moulding — and in exchange it has to have the work's own
    proportions, which a box cut in the wrong place cannot have by accident.
    """
    number = work["objectNumber"]
    crop = work["image"].get("crop")

    if crop is None:
        return

    x, y, width, height = crop

    if not (0 <= x and 0 <= y and width > 0 and height > 0
            and x + width <= 1.0001 and y + height <= 1.0001):
        report.fail(f"{number}: crop {crop} is not a box inside the photograph")

    if number not in by_hand:
        if min(width, height) < KEPT:
            report.fail(f"{number}: crop keeps {min(width, height):.0%} of a side, which "
                        f"is more than a border")

        return

    pixels = work["image"].get("pixels")
    stated = shape_stated(work)

    if not pixels or not all(stated):
        report.fail(f"{number}: read by hand, but the record gives no size to check the "
                    f"reading against")
        return

    box = (width * pixels[0]) / (height * pixels[1])
    off = abs(box - stated[0] / stated[1]) / (stated[0] / stated[1])

    if off > PROPORTIONS:
        report.fail(f"{number}: the hand-read box is {box:.3f} wide to high, against the "
                    f"record's {stated[0]}x{stated[1]} cm — off by {off:.1%}")


def shape_stated(work: dict) -> tuple[float | None, float | None]:
    """The width and height the record states, turned round where it has them
    the wrong way round — which is a claim the work has to make in writing, and
    which `check_shape` makes it prove against its own photograph."""
    measured = work.get("dimensions", {})
    stated = measured.get("width_cm"), measured.get("height_cm")

    return stated[::-1] if work.get("dimensionsSwapped") else stated


def check_shape(work: dict, report: Report) -> None:
    """A painting's stated size against the shape of its own photograph.

    A painting is flat and is photographed face-on, so the museum's height and
    width and the museum's picture of it are two statements about one rectangle
    and have to agree. Where they do not, one of them is wrong: Van Gogh's
    Wheatfield is filed 61 x 50 cm, taller than wide, and photographed wider than
    tall. Such a work has to carry a `dimensionsSwapped` note saying so, and the
    sheet then states no size at all — and turning the pair round has to give the
    shape the photograph has, or the note is a story rather than a reading.

    The tolerance is loose on purpose. This is looking for a contradiction — a
    canvas filed on its side — not for a millimetre: a photograph may keep a
    little of the wall around a work no border reading would cut.
    """
    number = work["objectNumber"]
    measured = work.get("dimensions", {})
    stated = measured.get("width_cm"), measured.get("height_cm")
    pixels = work["image"].get("pixels")
    swapped = work.get("dimensionsSwapped")

    if FLAT not in work.get("types", []) or not pixels or not all(stated):
        if swapped:
            report.fail(f"{number}: says its size is the wrong way round, but nothing here "
                        f"can check that — it is searched as "
                        f"{', '.join(work.get('types', [])) or 'no type at all'} and "
                        f"measured {stated[1]}x{stated[0]}")

        return

    x, y, width, height = work["image"].get("crop") or [0, 0, 1, 1]
    box = (width * pixels[0]) / (height * pixels[1])
    off = abs(box - stated[0] / stated[1]) / (stated[0] / stated[1])

    if off > SHAPE and not swapped:
        report.fail(f"{number}: the record says {stated[1]}x{stated[0]} cm and its own "
                    f"photograph is {box:.3f} wide to high — off by {off:.0%}")

    if not swapped:
        return

    if off <= SHAPE:
        report.fail(f"{number}: says its size is the wrong way round, but the record and "
                    f"the photograph agree to within {off:.0%} as they stand")

    turned = abs(box - stated[1] / stated[0]) / (stated[1] / stated[0])

    if turned > SHAPE:
        report.fail(f"{number}: says its size is the wrong way round, but turning it round "
                    f"gives {stated[0]}x{stated[1]} against a photograph {box:.3f} wide to "
                    f"high — still off by {turned:.0%}")


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


def check_locations(tour: list[dict], report: Report) -> None:
    """The display locations read off the museum's own object pages.

    That file supplements the records and has to stay a supplement: an entry for
    a work whose record has since named a gallery is stale, and the build would
    quietly ignore it. A location taken off a web page also ages, so the day it
    was read travels with it and is said out loud here.
    """
    path = DATA / "locations.json"

    if not path.exists():
        report.note("no data/locations.json: no work is placed by the museum's own page")
        return

    stated = json.loads(path.read_text())
    written_up = {work["objectNumber"]: work for work in tour}
    placed = [work for work in tour if (work.get("gallery") or {}).get("source") == "page"]

    for number, found in stated["works"].items():
        work = written_up.get(number)

        if not work:
            report.fail(f"locations.json: {number} is not a curated work")
            continue

        where = work.get("gallery") or {}

        if where.get("source") != "page" and where:
            report.fail(f"locations.json: {number} is in {where['code']} in the record "
                        f"now — the entry is stale and the build is ignoring it")

        if found["location"] and not where:
            report.note(f"{number}: its page says {found['location']!r}, which no gallery "
                        f"the museum names answers to, so it stays off the line")

    for work in placed:
        number = work["objectNumber"]

        if number not in stated["works"]:
            report.fail(f"{number}: placed by a page that data/locations.json does not hold")

        if not work["gallery"].get("read"):
            report.fail(f"{number}: placed by a page with no date of reading")

    if placed:
        days = (date.today() - date.fromisoformat(stated["retrieved"])).days
        report.note(f"{len(placed)} curated works are placed by the museum's own object "
                    f"page, read {days} days ago: "
                    f"{', '.join(work['objectNumber'] for work in placed)}")

        if days > STALE_AFTER_DAYS:
            report.note(f"those readings are over {STALE_AFTER_DAYS} days old — "
                        f"re-run `just harvest` before trusting them")


def on_the_line(work: dict) -> bool:
    """Whether the walking route can reach a work.

    The same rule `app/route.js` applies: the main building, and a floor read out
    of the room code. A work the museum reports no location for fails it, and so
    does the Asian Pavilion, whose `AK-1-23` names no storey.
    """
    where = work.get("gallery")

    return bool(where) and where["building"] == MAIN_BUILDING and where["floor"] is not None


def check_route_coverage(tour: list[dict], galleries: dict, report: Report) -> None:
    walkable = [work for work in tour if on_the_line(work)]
    floors = sorted({work["gallery"]["floor"] for work in walkable})
    report.note(f"{len(walkable)} curated works on the line, across floors {floors}")

    elsewhere = [work["objectNumber"] for work in tour if not on_the_line(work)]

    if elsewhere:
        report.note(f"{len(elsewhere)} curated works the route cannot reach, shown on the "
                    f"contact sheet only: {', '.join(elsewhere)}")

    # A work placed by the museum's own page carries its position itself: its
    # room holds no on-view work, so galleries.json has never heard of it.
    unplaced = [work["objectNumber"] for work in walkable
                if "position" not in work["gallery"]
                and "position" not in galleries.get(work["gallery"]["code"], {})]

    if unplaced:
        report.note(f"{len(unplaced)} curated works are in rooms the published plan does "
                    f"not label: {', '.join(unplaced)}")


def main() -> None:
    catalogue = json.loads((DATA / "catalogue.json").read_text())
    galleries = json.loads((DATA / "galleries.json").read_text())
    tour = json.loads((DATA / "tour.json").read_text())

    report = Report()
    check_catalogue(catalogue, report)
    check_curated(tour, report)
    check_locations(tour, report)
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
