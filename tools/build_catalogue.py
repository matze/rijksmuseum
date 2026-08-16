# /// script
# requires-python = ">=3.11"
# dependencies = ["requests>=2.31", "pyyaml>=6.0"]
# ///
"""Turn cached Linked Art records into the two files the guide reads.

`data/catalogue.json`  every on-view work with a public-domain image, facts only
`data/galleries.json`  the rooms those works hang in, grouped by floor
`data/tour.json`       the curated works, prose joined to the museum's own facts

A curated work does not have to be on view. The museum reports no
`current_location` for the Milkmaid or the Jewish Bride; both are still in the
collection and worth reading about. Where its own object page says where the
work hangs, `data/locations.json` carries those words and the work goes back on
the line, marked as placed by the page. Where nothing says, it ships in
`tour.json` with no gallery at all rather than with a guessed one.

Nothing here invents a value. A field that the museum does not publish is absent
from the output, and `verify.py` decides whether that absence is tolerable.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from enum import StrEnum
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import (CACHE, DATA, Fetcher, creator, dimensions, gallery,  # noqa: E402
                    image_services, object_number, production_date, statements,
                    titles, visual_item_uri, web_page, write_json)

IMAGE_WIDTHS = [480, 960, 1600, 2400]
CURATED_SECTIONS = ("timeline", "closer", "detail", "look", "kids")
REQUIRED_SECTIONS = ("timeline", "closer", "detail", "look")

#: A `region:` line closes the block above it and says which part of the work
#: that block is about. Four fractions of the photograph — the space the crops
#: are measured in, and the space you are in when you look at the file. The
#: build restates them in the plate's own space; see `in_work`.
#:
#: A quoted phrase narrows it from the whole block to those words, wherever they
#: fall in it. The phrase is matched against the block's finished text, so it is
#: written as it reads rather than as it is wrapped.
REGION = re.compile(r'^region:\s+(?:"([^"]+)"\s+)?([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)$')

#: `look` is authored as a numbered list and rendered as one, so the figures the
#: author typed would otherwise be shown twice.
NUMBERING = re.compile(r"^\d+\.\s*")


class Grouping(StrEnum):
    """How a section's lines fall into blocks.

    `paragraph` reads markdown's own rule, where a blank line starts a block and
    a line ending does not. `line` gives every line a block of its own, which is
    what a numbered list is.
    """

    paragraph = "paragraph"
    line = "line"


def aspect_ratio(measured: dict) -> str | None:
    """A CSS `aspect-ratio` for the plate, reduced from the work's own dimensions."""
    height, width = measured.get("height_cm"), measured.get("width_cm")

    if not height or not width:
        return None

    return f"{round(width / height, 3)}"


def searched_as(by_type: dict[str, list[str]]) -> dict[str, list[str]]:
    """Object URI → the museum's own search types for it.

    The harvest asks the search API for the types that are actually exhibited, so
    the museum has already said of every candidate whether it is a painting or a
    ship model. That is worth keeping: a painting is a flat thing photographed
    face-on, and it is the only kind of object whose stated height and width can
    be checked against its own photograph.
    """
    found: dict[str, list[str]] = {}

    for name, uris in sorted(by_type.items()):
        for uri in uris:
            found.setdefault(uri, []).append(name)

    return found


def normalise(record: dict, images: dict[str, dict], types: dict[str, list[str]],
              retrieved: str) -> dict | None:
    where = gallery(record)
    number = object_number(record)
    visual_uri = visual_item_uri(record)

    if not number or not visual_uri:
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
        "gallery": where.as_json() if where else None,
        "types": types.get(record["id"], []),
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


def load_locations() -> dict[str, dict]:
    """What the museum's own object page says, for works whose record says nothing.

    `fetch_locations.py` reads the page's badge; the place here is the one it
    names, in the museum's own words, and the date is the day it was read — a
    location taken off a web page is only as good as the day it was taken. A work
    whose page carries no badge is in the file with a null and drops out here.
    """
    path = DATA / "locations.json"

    if not path.exists():
        return {}

    stated = json.loads(path.read_text())

    return {number: {"place": found["location"], "read": stated["retrieved"]}
            for number, found in stated["works"].items() if found.get("location")}


def shared_room(rooms: list[str]) -> str | None:
    """The room several rooms are parts of: 2.30.1 and 2.30.8 are both 2.30."""
    shared: list[str] = []

    for level in zip(*(room.split(".") for room in rooms)):
        if len(set(level)) != 1:
            break

        shared.append(level[0])

    return ".".join(shared) or None


def named_gallery(place: str, galleries: dict, plan: dict) -> dict | None:
    """The gallery the museum's page means when it says a work is *there*.

    The page names a hall — "Gallery of Honour" — and the records name seven bays
    HG-2.30.1 to HG-2.30.8 "Gallery of Honour". The hall is the room those bays
    are parts of, and its floor and building are theirs. A page that names a room
    number instead is matched against the room numbers themselves.

    Nothing is invented: a place the museum's own gallery names do not answer to,
    or one whose galleries disagree about which floor or building they are on,
    resolves to nothing and leaves the work off the line.
    """
    named = [room for room in galleries.values()
             if place in (room["room"], room["code"]) or place in room["name"].values()]
    houses = {(room["building"], room["floor"]) for room in named}

    if not named or len(houses) != 1:
        return None

    room = shared_room([found["room"] for found in named])
    building, floor = houses.pop()

    if not room:
        return None

    where = {"code": f"{building}-{room}", "building": building, "room": room, "floor": floor,
             "name": named[0]["name"], "house": named[0]["house"], "source": "page"}

    if position := plan_position(plan, where):
        where["position"] = position

    return where


#: The museum's attribution line sometimes ends in a note about the evidence for
#: it — "(signed by artist)", "(mentioned on object)". That belongs in the facts,
#: not under a title. Qualifiers that change who made the thing, such as
#: "workshop of Rembrandt", are not parenthesised and survive this.
EVIDENCE_NOTE = re.compile(r"\s*\([^()]*\)\s*$")


def billed_as(attribution: str | None) -> str | None:
    return EVIDENCE_NOTE.sub("", attribution) if attribution else attribution


def anchor(block: dict, phrase: str | None, box: list[float]) -> None:
    """Point a block, or some words inside it, at a part of the work.

    A phrase is recorded as where it falls in the block's own text rather than as
    a copy of it, so the prose stays one string and the guide has nothing to
    reassemble. Requiring the phrase to occur exactly once is what keeps the
    offsets honest as the prose is edited: a phrase that has moved is still
    found, and one that has been reworded stops the build.
    """
    if phrase is None:
        if block.get("spans"):
            raise ValueError(f"'{block['text'][:48]}…' is already pointed at by phrase")

        if "region" in block:
            raise ValueError(f"two regions on '{block['text'][:48]}…'")

        block["region"] = box

        return

    if "region" in block:
        raise ValueError(f"'{block['text'][:48]}…' is already pointed at whole")

    found = block["text"].count(phrase)

    if found != 1:
        raise ValueError(f"'{phrase}' occurs {found} times in '{block['text'][:48]}…'")

    start = block["text"].index(phrase)
    spans = block.setdefault("spans", [])

    if any(start < span["end"] and span["start"] < start + len(phrase) for span in spans):
        raise ValueError(f"'{phrase}' overlaps another phrase already pointed at")

    spans.append({"start": start, "end": start + len(phrase), "region": box})
    spans.sort(key=lambda span: span["start"])


def blocks(lines: list[str], grouping: Grouping) -> list[dict]:
    """Group a section's lines into blocks, each with the region it points at.

    A block that carries no `region:` line is prose that points nowhere in
    particular, and carries neither key at all — which is most of them.
    """
    grouped: list[dict] = []
    run: list[str] = []

    def close() -> None:
        if run:
            grouped.append({"text": " ".join(run)})
            run.clear()

    for raw in lines:
        line = raw.strip()

        if found := REGION.match(line):
            close()

            if not grouped:
                raise ValueError("a region: line has nothing above it to point from")

            phrase, *box = found.groups()
            anchor(grouped[-1], phrase, [float(number) for number in box])
        elif not line:
            close()
        elif grouping is Grouping.line:
            grouped.append({"text": NUMBERING.sub("", line)})
        else:
            run.append(line)

    close()

    return grouped


def in_work(box: list[float], crop: list[float] | None) -> list[float]:
    """A region measured on the photograph, restated in the space the plate draws in.

    The plate is a window onto the work: it holds the work's own proportions and
    the photograph is laid behind it, so 0–1 across that window is 0–1 across the
    work and not across the photograph. Regions are authored in the photograph's
    space, which is the one they are measured in, so re-reading a border moves
    the regions with it rather than leaving them behind.
    """
    if not crop:
        return box

    x, y, width, height = box
    left, top, kept_width, kept_height = crop

    return [round(value, 4) for value in ((x - left) / kept_width, (y - top) / kept_height,
                                          width / kept_width, height / kept_height)]


def placed(work: dict, crop: list[float] | None) -> dict:
    """The curated prose with every region restated in the plate's own space."""
    def convert(block: dict) -> dict:
        if "region" in block:
            return {**block, "region": in_work(block["region"], crop)}

        if "spans" in block:
            return {**block, "spans": [{**span, "region": in_work(span["region"], crop)}
                                       for span in block["spans"]]}

        return block

    return {**work,
            "timeline": convert(work["timeline"]),
            "detail": [convert(block) for block in work["detail"]],
            "look": [convert(block) for block in work["look"]]}


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

            # A second heading of the same name used to start the section again,
            # which silently dropped everything written under the first one.
            if current in sections:
                raise SystemExit(f"{path}: '{current}' appears twice — one section holds "
                                 f"as many paragraphs as it needs")

            sections[current] = []
        elif current:
            sections[current].append(line)

    try:
        prose = {name: blocks(lines, Grouping.line if name == "look" else Grouping.paragraph)
                 for name, lines in sections.items()}
    except ValueError as problem:
        raise SystemExit(f"{path}: {problem}") from problem

    missing = [s for s in REQUIRED_SECTIONS if not prose.get(s)]

    if missing:
        raise SystemExit(f"{path}: missing sections {', '.join(missing)}")

    if not front.get("sources"):
        raise SystemExit(f"{path}: every curated work needs at least one source")

    # One paragraph, so that the region it carries is the region of all of it.
    if len(prose["timeline"]) > 1:
        raise SystemExit(f"{path}: the timeline is one paragraph, not {len(prose['timeline'])}")

    # The sheet is the only place a region has a plate to light, and these two
    # are not on it: the closer belongs to the line, the question to a child.
    for name in ("closer", "kids"):
        if any("region" in block for block in prose.get(name, [])):
            raise SystemExit(f"{path}: the {name} is not shown beside the plate, so a "
                             f"region there would have nothing to point at")

    return {
        "objectNumber": front["objectNumber"],
        "priority": front["priority"],
        "stayMinutes": front["stayMinutes"],
        "tags": front.get("tags", []),
        "sources": front["sources"],
        "displayTitle": front.get("displayTitle"),
        "dimensionsSwapped": front.get("dimensionsSwapped"),
        "timeline": prose["timeline"][0],
        "closer": " ".join(block["text"] for block in prose["closer"]),
        "detail": prose["detail"],
        "look": prose["look"],
        "kids": " ".join(block["text"] for block in prose["kids"]) if prose.get("kids") else None,
    }


def load_crops() -> dict[str, list[float]]:
    """The measured content boxes, with the hand-read ones merged over them."""
    crops: dict[str, list[float]] = {}

    for name in ("crops.json", "crops-extra.json"):
        path = DATA / name

        if path.exists():
            crops.update({number: box for number, box in json.loads(path.read_text()).items()
                          if not number.startswith("_")})

    return crops


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

    searched = json.loads((CACHE / "candidates.json").read_text())
    candidates = searched["uris"]
    types = searched_as(searched["byType"])
    fetcher = Fetcher("records")

    records = [fetcher.get_json(uri) for uri in candidates
               if fetcher.path_for(uri).exists()]

    if len(records) < len(candidates):
        print(f"warning: {len(candidates) - len(records)} candidates not yet harvested",
              file=sys.stderr)

    images = image_services(records, fetcher)

    # Everything harvested that has a public-domain photograph, on view or not.
    # The catalogue proper is the on-view part of it; the rest is only reachable
    # by being written up, and reaches the guide through data/curated.
    harvested = [entry for record in records
                 if (entry := normalise(record, images, types, args.retrieved))]

    catalogue = sorted(
        (entry for entry in harvested if entry.get("gallery")),
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
    crops = load_crops()
    plan = load_plan()
    locations = load_locations()
    curated = [parse_curated(path) for path in sorted((DATA / "curated").glob("*.md"))]
    by_number = {entry["objectNumber"]: entry for entry in harvested}
    tour = []

    for work in curated:
        facts = by_number.get(work["objectNumber"])

        if not facts:
            print(f"warning: curated {work['objectNumber']} was never harvested, or has "
                  f"no public-domain photograph", file=sys.stderr)
            continue

        entry = with_image_shape(facts, iiif)

        # The record names no room and the museum's own page does. That is the
        # museum in a second voice rather than a guess, so the work goes back on
        # the line — and says on its sheet where the location came from.
        if not entry.get("gallery") and (stated := locations.get(work["objectNumber"])):
            if where := named_gallery(stated["place"], galleries, plan):
                entry = {**entry, "gallery": {**where, "read": stated["read"]}}
            else:
                print(f"warning: {work['objectNumber']} is on display in "
                      f"{stated['place']!r}, which no gallery the museum names answers to",
                      file=sys.stderr)

        crop = crops.get(work["objectNumber"])

        if crop:
            entry["image"] = {**entry["image"], "crop": crop}

        prose = placed(work, crop)

        tour.append({**entry, **{k: v for k, v in prose.items() if v is not None}})

    write_json(DATA / "tour.json", tour)
    unplaced = sum(1 for work in tour if not work.get("gallery"))
    by_page = sum(1 for work in tour if work.get("gallery", {}).get("source") == "page")
    print(f"{len(catalogue)} on-view works across {len(galleries)} rooms, "
          f"{len(tour)}/{len(curated)} curated works written up "
          f"({unplaced} of them with no location the museum publishes anywhere, "
          f"{by_page} placed by the museum's object page)", file=sys.stderr)


if __name__ == "__main__":
    main()
