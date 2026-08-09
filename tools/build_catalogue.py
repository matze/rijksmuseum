# /// script
# requires-python = ">=3.11"
# dependencies = ["requests>=2.31", "pyyaml>=6.0"]
# ///
"""Turn cached Linked Art records into the two files the guide reads.

`data/catalogue.json`  every on-view work with a public-domain image, facts only
`data/galleries.json`  the rooms those works hang in, grouped by floor
`data/tour.json`       catalogue entries joined to the curated prose in data/curated

Nothing here invents a value. A field that the museum does not publish is absent
from the output, and `verify.py` decides whether that absence is tolerable.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import (CACHE, DATA, Fetcher, creator, digital_object_uris,  # noqa: E402
                    dimensions, gallery, image_service, object_number,
                    production_date, statements, titles, visual_item_uri,
                    web_page, write_json)

IMAGE_WIDTHS = [480, 960, 1600]
CURATED_SECTIONS = ("timeline", "closer", "detail", "look", "kids")
REQUIRED_SECTIONS = ("timeline", "closer", "detail", "look")


def aspect_ratio(measured: dict) -> str | None:
    """A CSS `aspect-ratio` for the plate, reduced from the work's own dimensions."""
    height, width = measured.get("height_cm"), measured.get("width_cm")

    if not height or not width:
        return None

    return f"{round(width / height, 3)}"


def normalise(record: dict, images: dict[str, dict], retrieved: str) -> dict | None:
    where = gallery(record)
    number = object_number(record)
    visual_uri = visual_item_uri(record)

    if not where or not number or not visual_uri:
        return None

    image = images.get(visual_uri)

    if not image:
        return None

    display_date, earliest, latest = production_date(record)
    measured = dimensions(record)
    maker = creator(record)

    entry = {
        "objectNumber": number,
        "uri": record["id"],
        "title": titles(record),
        "artist": billed_as(maker["display"]),
        "attribution": maker["display"],
        "artistUri": maker["uri"],
        "date": display_date,
        "dateEarliest": earliest,
        "dateLatest": latest,
        "medium": statements(record, "medium_statement"),
        "credit": statements(record, "credit_line"),
        "dimensions": {k: v for k, v in measured.items() if v is not None},
        "gallery": where.as_json(),
        "image": {**image, "widths": IMAGE_WIDTHS, "aspectRatio": aspect_ratio(measured)},
        "page": web_page(record),
        "retrieved": retrieved,
    }

    return {k: v for k, v in entry.items() if v not in (None, {}, [])}


def room_order(room: str) -> tuple[int, ...]:
    """Sort key putting rooms in the museum's own numbering, 2.9 before 2.10.

    The numbering runs along the visitor circuit — verified against the published
    plan, where consecutive numbers sit next to each other around the ring — so
    this ordering is also the walking order within a floor.
    """
    return tuple(int(part) for part in re.findall(r"\d+", room))


def load_plan() -> dict:
    """The extracted plan, with the hand-read hall positions merged over it."""
    plan = json.loads((DATA / "floorplan.json").read_text())
    extra_path = DATA / "floorplan-extra.json"

    if not extra_path.exists():
        return plan

    for floor, addition in json.loads(extra_path.read_text())["floors"].items():
        plan["floors"].setdefault(floor, {"rooms": {}})["rooms"].update(addition["rooms"])

    return plan


def plan_position(plan: dict, where: dict) -> list[float] | None:
    """Where a room sits on the published plan.

    The Gallery of Honour is subdivided into bays — `2.30.3` — that the plan
    labels only by their parent room, so a sub-room falls back to the room that
    contains it.
    """
    rooms = plan["floors"].get(str(where["floor"]), {}).get("rooms", {})
    parts = where["room"].split(".")

    return next((rooms[candidate] for length in range(len(parts), 1, -1)
                 if (candidate := ".".join(parts[:length])) in rooms), None)


def build_galleries(catalogue: list[dict]) -> dict:
    """Every room that holds an on-view work, with its position on the plan."""
    plan = load_plan()
    galleries: dict[str, dict] = {}

    for entry in catalogue:
        where = entry["gallery"]
        room = galleries.setdefault(where["code"], {**where, "works": 0})
        room["works"] += 1

        if position := plan_position(plan, where):
            room["position"] = position

    placed = sum(1 for room in galleries.values() if "position" in room)
    print(f"{placed}/{len(galleries)} rooms located on the published plan", file=sys.stderr)

    return dict(sorted(galleries.items(),
                       key=lambda kv: (kv[1]["floor"] is None, kv[1]["floor"] or 0,
                                       room_order(kv[1]["room"]), kv[0])))


#: The museum's attribution line sometimes ends in a note about the evidence for
#: it — "(signed by artist)", "(mentioned on object)". That belongs in the facts,
#: not under a title. Qualifiers that change who made the thing, such as
#: "workshop of Rembrandt", are not parenthesised and survive this.
EVIDENCE_NOTE = re.compile(r"\s*\([^()]*\)\s*$")


def billed_as(attribution: str | None) -> str | None:
    return EVIDENCE_NOTE.sub("", attribution) if attribution else attribution


def paragraphs(lines: list[str]) -> list[str]:
    """Group hard-wrapped lines into paragraphs the way markdown reads them:
    a blank line starts a new paragraph, a line ending does not."""
    grouped: list[list[str]] = [[]]

    for line in lines:
        if line.strip():
            grouped[-1].append(line.strip())
        elif grouped[-1]:
            grouped.append([])

    return [" ".join(group) for group in grouped if group]


def parse_curated(path: Path) -> dict:
    """Read a curated markdown file: YAML front matter plus `## section` bodies."""
    raw = path.read_text()
    match = re.match(r"^---\n(.*?)\n---\n(.*)$", raw, re.S)

    if not match:
        raise SystemExit(f"{path}: missing YAML front matter")

    front = yaml.safe_load(match.group(1)) or {}
    sections: dict[str, list[str]] = {}
    current = None

    for line in match.group(2).splitlines():
        if heading := re.match(r"^##\s+(\w+)\s*$", line):
            current = heading.group(1)

            if current not in CURATED_SECTIONS:
                raise SystemExit(f"{path}: unknown section '{current}'")

            sections[current] = []
        elif current:
            sections[current].append(line)

    prose = {name: paragraphs(lines) for name, lines in sections.items()}
    missing = [s for s in REQUIRED_SECTIONS if not prose.get(s)]

    if missing:
        raise SystemExit(f"{path}: missing sections {', '.join(missing)}")

    if not front.get("sources"):
        raise SystemExit(f"{path}: every curated work needs at least one source")

    return {
        "objectNumber": front["objectNumber"],
        "priority": front["priority"],
        "stayMinutes": front["stayMinutes"],
        "tags": front.get("tags", []),
        "sources": front["sources"],
        "displayTitle": front.get("displayTitle"),
        "timeline": " ".join(prose["timeline"]),
        "closer": " ".join(prose["closer"]),
        "detail": prose["detail"],
        "look": [re.sub(r"^\d+\.\s*", "", line.strip())
                 for line in sections["look"] if line.strip()],
        "kids": " ".join(prose["kids"]) if prose.get("kids") else None,
    }


def with_image_shape(entry: dict, fetcher: Fetcher) -> dict:
    """Replace the plate's aspect ratio with the photograph's own proportions.

    Deriving it from the object's height and width works for paintings and fails
    for everything else — a sculpture's measurements describe the sculpture, not
    the picture of it. The IIIF service states the image's real pixel size.
    """
    info = fetcher.get_json(f"{entry['image']['service']}/info.json",
                            accept="application/json", optional=True)

    if not info or not info.get("width") or not info.get("height"):
        return entry

    return {**entry, "image": {**entry["image"], "pixels": [info["width"], info["height"]],
                               "aspectRatio": f"{round(info['width'] / info['height'], 3)}"}}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--retrieved", default=date.today().isoformat(),
                        help="stamp written onto every entry")
    args = parser.parse_args()

    candidates = json.loads((CACHE / "candidates.json").read_text())["uris"]
    fetcher = Fetcher("records")

    records = [fetcher.get_json(uri) for uri in candidates
               if fetcher.path_for(uri).exists()]

    if len(records) < len(candidates):
        print(f"warning: {len(candidates) - len(records)} candidates not yet harvested",
              file=sys.stderr)

    # Resolve the imagery hop entirely from cache: visual item → digital object → IIIF.
    images: dict[str, dict] = {}

    for record in records:
        visual_uri = visual_item_uri(record)

        if not visual_uri or not fetcher.path_for(visual_uri).exists():
            continue

        visual = fetcher.get_json(visual_uri)
        digitals = [fetcher.get_json(uri) for uri in digital_object_uris(visual)
                    if fetcher.path_for(uri).exists()]

        if service := image_service(visual, digitals):
            images[visual_uri] = service

    catalogue = sorted(
        (entry for record in records
         if (entry := normalise(record, images, args.retrieved))),
        key=lambda e: (e["gallery"]["floor"] is None, e["gallery"]["floor"] or 0,
                       room_order(e["gallery"]["room"]), e["objectNumber"]),
    )

    write_json(DATA / "catalogue.json", catalogue)

    galleries = build_galleries(catalogue)
    write_json(DATA / "galleries.json", galleries)

    # The route draws each floor's schematic from the works themselves, so the
    # room's position has to travel with the work rather than only with the room.
    for entry in catalogue:
        if position := galleries[entry["gallery"]["code"]].get("position"):
            entry["gallery"]["position"] = position

    write_json(DATA / "catalogue.json", catalogue)

    iiif = Fetcher("iiif")
    curated = [parse_curated(path) for path in sorted((DATA / "curated").glob("*.md"))]
    by_number = {entry["objectNumber"]: entry for entry in catalogue}
    tour = []

    for work in curated:
        facts = by_number.get(work["objectNumber"])

        if not facts:
            print(f"warning: curated {work['objectNumber']} is not in the on-view "
                  f"catalogue — it has moved or come off display", file=sys.stderr)
            continue

        tour.append({**with_image_shape(facts, iiif),
                     **{k: v for k, v in work.items() if v is not None}})

    write_json(DATA / "tour.json", tour)
    print(f"{len(catalogue)} on-view works across {len(galleries)} rooms, "
          f"{len(tour)}/{len(curated)} curated works placed", file=sys.stderr)


if __name__ == "__main__":
    main()
