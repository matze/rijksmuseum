# /// script
# requires-python = ">=3.11"
# dependencies = ["requests>=2.31"]
# ///
"""Shared plumbing for the retrieval scripts: an on-disk HTTP cache and the
accessors that pull single fields out of a Rijksmuseum Linked Art record.

Every fact the guide displays passes through one of the accessors below, so the
mapping from museum data to rendered text is auditable in one file.
"""

from __future__ import annotations

import concurrent.futures
import hashlib
import json
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator, Sequence

import requests

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "cache"
DATA = ROOT / "data"
ASSETS = ROOT / "assets"

SEARCH_ENDPOINT = "https://data.rijksmuseum.nl/search/collection"
USER_AGENT = "rijksmuseum-guide/0.1 (static visitor guide; reproducible build)"

# Getty AAT vocabulary identifiers, spelled out once so call sites read as prose.
AAT = {
    "english": "http://vocab.getty.edu/aat/300388277",
    "dutch": "http://vocab.getty.edu/aat/300388256",
    "description": "http://vocab.getty.edu/aat/300435452",
    "attribution": "http://vocab.getty.edu/aat/300435416",
    "medium_statement": "http://vocab.getty.edu/aat/300435429",
    "dimensions_statement": "http://vocab.getty.edu/aat/300435430",
    "credit_line": "http://vocab.getty.edu/aat/300026687",
    "inscription": "http://vocab.getty.edu/aat/300435414",
    "provenance": "http://vocab.getty.edu/aat/300444174",
    "primary_name": "http://vocab.getty.edu/aat/300404670",
    "gallery_name": "http://vocab.getty.edu/aat/300260522",
    "building_name": "http://vocab.getty.edu/aat/300004188",
    "web_page": "http://vocab.getty.edu/aat/300264578",
    "height": "http://vocab.getty.edu/aat/300055644",
    "width": "http://vocab.getty.edu/aat/300055647",
    "availability": "http://vocab.getty.edu/aat/300435434",
    "centimetres": "http://vocab.getty.edu/aat/300379098",
}

LANGUAGE_OF = {AAT["english"]: "en", AAT["dutch"]: "nl"}

PUBLIC_DOMAIN_RIGHTS = (
    "https://creativecommons.org/publicdomain/mark/1.0/",
    "https://creativecommons.org/publicdomain/zero/1.0/",
)


# ── HTTP ──────────────────────────────────────────────────────────────────────


class Fetcher:
    """A requests session with a content-addressed cache on disk.

    Re-runs of a harvest hit the cache and cost nothing, which is what makes the
    pipeline cheap to repeat and therefore worth trusting.
    """

    def __init__(self, subdir: str, *, force: bool = False, delay: float = 0.0):
        self.dir = CACHE / subdir
        self.dir.mkdir(parents=True, exist_ok=True)
        self.force = force
        self.delay = delay
        self.session = requests.Session()
        self.session.headers["User-Agent"] = USER_AGENT
        self.hits = 0
        self.misses = 0
        self.failures: list[str] = []

    def path_for(self, url: str, suffix: str = ".json") -> Path:
        return self.dir / (hashlib.sha256(url.encode()).hexdigest()[:32] + suffix)

    def get_json(self, url: str, *, accept: str = "application/ld+json",
                 optional: bool = False) -> Any:
        """Fetch and cache a JSON document.

        With `optional`, a document the museum will not serve yields None instead
        of aborting: a nine-thousand-object harvest should not be lost to one
        unresolvable identifier.
        """
        path = self.path_for(url)

        if path.exists() and not self.force:
            self.hits += 1
            return json.loads(path.read_text())

        try:
            payload = self._get(url, accept).json()
        except (RuntimeError, ValueError) as error:
            if not optional:
                raise

            self.failures.append(url)
            print(f"\nskipping {url}: {error}", file=sys.stderr)
            return None
        path.write_text(json.dumps(payload, ensure_ascii=False))
        self.misses += 1
        return payload

    def get_bytes(self, url: str, *, suffix: str) -> bytes:
        path = self.path_for(url, suffix)

        if path.exists() and not self.force:
            self.hits += 1
            return path.read_bytes()

        payload = self._get(url, "*/*").content
        path.write_bytes(payload)
        self.misses += 1
        return payload

    def _get(self, url: str, accept: str) -> requests.Response:
        last: Exception | None = None

        for attempt in range(4):
            try:
                response = self.session.get(url, headers={"Accept": accept}, timeout=60)
                response.raise_for_status()

                if self.delay:
                    time.sleep(self.delay)

                return response
            except requests.RequestException as error:
                last = error
                time.sleep(1.5 * (attempt + 1))

        raise RuntimeError(f"giving up on {url}") from last


def in_parallel(items: Sequence[Any], work: Callable[[Any], Any], *, workers: int = 8,
                label: str = "") -> Iterator[Any]:
    """Map `work` over `items`, yielding results as they land, with a progress line."""
    done = 0

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        for result in pool.map(work, items):
            done += 1

            if label and (done % 50 == 0 or done == len(items)):
                print(f"\r{label}: {done}/{len(items)}", end="", file=sys.stderr, flush=True)

            yield result

    if label:
        print(file=sys.stderr)


# ── Linked Art accessors ──────────────────────────────────────────────────────


def as_list(value: Any) -> list:
    """Every node the records reach for, normalised to a list of dicts.

    Linked Art properties come back as a bare object, a list, or — where the
    serialiser compacted a node to its identifier — a plain string. Only the
    object forms carry anything the accessors below can read.
    """
    if value is None:
        return []

    items = value if isinstance(value, list) else [value]

    return [item for item in items if isinstance(item, dict)]


def language_of(node: dict) -> str | None:
    for language in as_list(node.get("language")):
        if code := LANGUAGE_OF.get(language.get("id", "")):
            return code

    return None


def classifications(node: dict) -> set[str]:
    return {c.get("id", "") for c in as_list(node.get("classified_as"))}


def statements(record: dict, kind: str) -> dict[str, str]:
    """Every `referred_to_by` statement of one AAT kind, keyed by language."""
    wanted = AAT[kind]
    found: dict[str, str] = {}

    for node in as_list(record.get("referred_to_by")):
        if wanted not in classifications(node) or not node.get("content"):
            continue

        found.setdefault(language_of(node) or "und", node["content"])

    return found


def titles(record: dict) -> dict[str, str]:
    """Object titles by language, preferring the name marked as primary."""
    found: dict[str, str] = {}

    for name in as_list(record.get("identified_by")):
        if name.get("type") != "Name":
            continue

        for part in as_list(name.get("part")) or [name]:
            content, language = part.get("content"), language_of(part) or language_of(name)

            if not content or not language:
                continue

            if AAT["primary_name"] in classifications(part) or language not in found:
                found[language] = content

    return found


def object_number(record: dict) -> str | None:
    for identifier in as_list(record.get("identified_by")):
        if identifier.get("type") == "Identifier" and identifier.get("content"):
            content = identifier["content"]

            if re.fullmatch(r"[A-Z]{2}(-[A-Za-z0-9.]+)+", content):
                return content

    return None


def harvested(fetcher: Fetcher) -> dict[str, str]:
    """Object number → record URI, over everything the harvest reached.

    `data/catalogue.json` holds only what is on view, and a curated work need not
    be: the museum publishes no location for the Milkmaid. The tools that gather
    source material therefore cannot go through the catalogue. Reading nine
    thousand records to answer one question is slow, so the index is written
    beside them in the cache and rebuilt whenever the candidate list moves.
    """
    candidates = CACHE / "candidates.json"
    index = CACHE / "by-object-number.json"

    if index.exists() and index.stat().st_mtime >= candidates.stat().st_mtime:
        return json.loads(index.read_text())

    found: dict[str, str] = {}

    for uri in json.loads(candidates.read_text())["uris"]:
        path = fetcher.path_for(uri)

        if path.exists() and (number := object_number(json.loads(path.read_text()))):
            found.setdefault(number, uri)

    index.write_text(json.dumps(found, ensure_ascii=False, sort_keys=True))

    return found


@dataclass(frozen=True)
class Gallery:
    code: str
    building: str
    room: str
    floor: int | None
    name: dict[str, str]
    house: dict[str, str]

    def as_json(self) -> dict:
        return {"code": self.code, "building": self.building, "room": self.room,
                "floor": self.floor, "name": self.name, "house": self.house}


# Main-building codes name the floor in the room number: `HG-2.31` is floor 2,
# room 31. Other buildings number their rooms flat — the Asian Pavilion's
# `AK-1-23` says nothing this parser can read as a storey, so it reports none
# rather than inventing one.
MAIN_BUILDING = "HG"
DOTTED_ROOM = re.compile(r"^(?P<floor>-?\d+)\.[\w.]+$")


def gallery(record: dict) -> Gallery | None:
    """The gallery an object is currently hung in, or None when it is not on view.

    Codes look like `HG-2.31`, or `HG-0.7-Z2.01` for a showcase inside a room.
    The floor is the leading component of the first room segment.

    The place is named twice over, once for the room and once for the building
    that holds it. Both are read: a work in a building the route does not enter
    has only its building's name to say where it is.
    """
    location = record.get("current_location")

    if not location:
        return None

    code, name, house = None, {}, {}

    for identity in as_list(location.get("identified_by")):
        if identity.get("type") == "Identifier" and identity.get("content"):
            code = identity["content"]
            continue

        language = language_of(identity)

        if not language:
            continue

        for part in as_list(identity.get("part")):
            kinds = classifications(part)

            if not part.get("content"):
                continue

            if AAT["gallery_name"] in kinds:
                name.setdefault(language, part["content"])
            elif AAT["building_name"] in kinds:
                house.setdefault(language, part["content"])

    if not code:
        return None

    building, *segments = code.split("-")

    if not segments:
        return None

    dotted = next((DOTTED_ROOM.match(s) for s in segments if DOTTED_ROOM.match(s)), None)
    room = dotted.group(0) if dotted else "-".join(segments)

    return Gallery(code=code, building=building, room=room,
                   floor=int(dotted["floor"]) if dotted else None, name=name, house=house)


def notations(node: dict) -> dict[str, str]:
    """A node's `notation` values keyed by language tag."""
    return {n["@language"]: n["@value"] for n in as_list(node.get("notation"))
            if n.get("@language") and n.get("@value")}


def creator(record: dict) -> dict:
    """Who made it: the museum's own attribution line plus the actor's identity.

    The attribution statement is preferred for display because it carries the
    qualifiers — "workshop of", "attributed to" — that a bare actor name drops.
    """
    attribution: dict[str, str] = {}
    name, uri = None, None

    for production in as_list(record.get("produced_by")):
        attribution = attribution or statements(production, "attribution")

        for part in as_list(production.get("part")) or [production]:
            for actor in as_list(part.get("carried_out_by")):
                labels = notations(actor) or titles(actor)

                if not name and (labels.get("en") or labels.get("nl")):
                    name, uri = labels.get("en") or labels.get("nl"), actor.get("id")

    display = attribution.get("en") or attribution.get("nl") or name

    return {"display": display, "name": name, "uri": uri}


def production_date(record: dict) -> tuple[str | None, int | None, int | None]:
    """Display date plus the machine-readable range, when the record carries one."""
    for production in as_list(record.get("produced_by")):
        for span in as_list(production.get("timespan")):
            names = titles(span)
            display = names.get("en") or names.get("nl")
            begin, end = span.get("begin_of_the_begin"), span.get("end_of_the_end")
            years = tuple(int(v[:4]) if isinstance(v, str) and len(v) >= 4 else None
                          for v in (begin, end))

            if display or any(years):
                return display, years[0], years[1]

    return None, None, None


AXES = {"height": "height_cm", "width": "width_cm"}

#: What a record calls the run of measurements that is of the whole object,
#: rather than of its plinth, its frame or the case it travels in. Naming no run
#: at all is the ordinary way of saying it. Both languages, because a run does
#: not always carry an English name.
THE_WHOLE = ("", "geheel", "overall", "total")


def measurement_run(dimension: dict) -> str:
    """Which run of measurements a dimension belongs to.

    A record may measure the same object several times over — the support, the
    painted surface, the frame — and names each run in the `identified_by` of
    every node in it. The names come in both languages and in either order, so
    one language has to be chosen or the same run answers to two keys.
    """
    names = as_list(dimension.get("identified_by"))
    english = [name["content"] for name in names if language_of(name) == "en" and name.get("content")]

    return (english or [name["content"] for name in names if name.get("content")] or [""])[0]


def dimensions(record: dict) -> dict:
    """Height and width in centimetres, plus the museum's own display string.

    Reading the first height and the first width would pair a framed height with
    a bare canvas width — Vermeer's letter-reader is filed both ways — and report
    a size the object has never had. So a pair is only ever taken from one run,
    and only when there is no doubt which run is the work: the run the record
    leaves unnamed, or the only one measured both ways. Where a record measures
    its object and its plinth and says nothing about which is which, the guide
    states no size and shows the museum's own sentence instead.
    """
    runs: dict[str, dict[str, float]] = {}

    for dimension in as_list(record.get("dimension")):
        equivalents = {e.get("id") for classifier in as_list(dimension.get("classified_as"))
                       for e in as_list(classifier.get("equivalent"))}
        axis = next((field for name, field in AXES.items() if AAT[name] in equivalents), None)
        in_centimetres = any(u.get("id") == AAT["centimetres"]
                             for u in as_list(dimension.get("unit")))

        if not axis or not in_centimetres or dimension.get("value") is None:
            continue

        run = measurement_run(dimension)
        runs.setdefault(run, {}).setdefault(axis, []).append(float(dimension["value"]))

    # A run that measures one axis twice is two runs the record forgot to name —
    # the Standard Bearer is 102.6 or 118.8 cm high depending on which of its two
    # unnamed heights goes with which width — and is no more usable than none.
    complete = {name: {axis: values[0] for axis, values in run.items()}
                for name, run in runs.items()
                if run.keys() == set(AXES.values()) and all(len(v) == 1 for v in run.values())}

    measured = next((complete[name] for name in THE_WHOLE if name in complete),
                    next(iter(complete.values())) if len(complete) == 1 else {})

    display = statements(record, "dimensions_statement")

    return {**measured, "display": display.get("en") or display.get("nl")}


def web_page(record: dict) -> str | None:
    """The museum's public object page, in English.

    Only the Dutch URL is published in the record; the English one is the same
    path with the two localised segments swapped, which the site itself serves.
    """
    for subject in as_list(record.get("subject_of")):
        for carrier in as_list(subject.get("digitally_carried_by")):
            if AAT["web_page"] not in classifications(carrier):
                continue

            for point in as_list(carrier.get("access_point")):
                url = point.get("id", "")

                if url.startswith("https://www.rijksmuseum.nl/"):
                    return url.replace("/nl/collectie/object/", "/en/collection/object/")

    return None


def visual_item_uri(record: dict) -> str | None:
    for shown in as_list(record.get("shows")):
        if shown.get("id"):
            return shown["id"]

    return None


def image_service(visual_item: dict, digital_objects: Iterable[dict]) -> dict | None:
    """The IIIF image service for a visual item, if it is public domain.

    Returns the service base (no `/full/...` suffix) so callers can request any
    derivative size they like.
    """
    rights = {c.get("id") for right in as_list(visual_item.get("subject_to"))
              for c in as_list(right.get("classified_as"))}

    if not rights & set(PUBLIC_DOMAIN_RIGHTS):
        return None

    for digital in digital_objects:
        for point in as_list(digital.get("access_point")):
            url = point.get("id", "")

            if "/full/" not in url:
                continue

            return {"service": url.split("/full/")[0],
                    "rights": next(iter(rights & set(PUBLIC_DOMAIN_RIGHTS)))}

    return None


def digital_object_uris(visual_item: dict) -> list[str]:
    return [d["id"] for d in as_list(visual_item.get("digitally_shown_by")) if d.get("id")]


def image_services(records: Iterable[dict], fetcher: Fetcher) -> dict[str, dict]:
    """Visual item URI → IIIF service, for the records whose imagery is in the cache.

    The hop is object → visual item → digital object → IIIF, and each step is a
    record of its own that a harvest may not have reached.
    """
    services: dict[str, dict] = {}

    for record in records:
        visual_uri = visual_item_uri(record)

        if not visual_uri or not fetcher.path_for(visual_uri).exists():
            continue

        visual = fetcher.get_json(visual_uri)
        digitals = [fetcher.get_json(uri) for uri in digital_object_uris(visual)
                    if fetcher.path_for(uri).exists()]

        if service := image_service(visual, digitals):
            services[visual_uri] = service

    return services


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    print(f"wrote {path.relative_to(ROOT)}", file=sys.stderr)
