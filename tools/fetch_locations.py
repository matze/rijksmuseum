# /// script
# requires-python = ">=3.11"
# dependencies = ["requests>=2.31"]
# ///
"""Read a display location off the museum's own object page.

Fifteen of the works this guide writes up carry no `current_location` in their
Linked Art record — the Milkmaid, the Jewish Bride, the Syndics among them — and
so have nowhere to stand on a walking line. The museum's own object page carries
a badge for some of them: *On display in Gallery of Honour*. That is the museum
saying where the work hangs, in a second voice, and it is worth asking for.

So this asks, for every curated work whose record gives no location, and writes
what came back to `data/locations.json` verbatim. A page that says nothing is
written down too, as `null`: the file is then a record of what was asked as well
as of what was answered, and the day a work gains or loses a badge it shows up
as a change to a committed file rather than as silence.

Nothing here decides where a hall is. `build_catalogue.py` matches the badge
against the museum's own gallery names and routes the work only where the two
agree.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import (DATA, Fetcher, curated_numbers, gallery,  # noqa: E402
                    harvested, web_page, write_json)

#: The object's own location badge, in the page head. There is exactly one on a
#: page — the related works further down carry their locations in the data
#: payload only — so this cannot pick up a neighbour's room by accident.
BADGE = re.compile(r'class="badge location-badge"[^>]*>(?:<!--\[-->)?\s*([^<]+?)\s*<')

#: What the badge puts in front of the place. Read off the same payload the badge
#: is rendered from, where it is a field of its own next to the place itself.
LEAD_IN = "On display in "

COMMENT = [
    "Where the museum's own object page says a work is, for the curated works",
    "whose Linked Art record names no current_location. `badge` is the page's",
    "words; `location` is the place alone, and is what build_catalogue.py",
    "matches against the museum's own gallery names. A null location means the",
    "page was read and showed no badge.",
    "Regenerate with: just harvest",
]


def read_badge(html: str) -> tuple[str, str | None] | None:
    """The page's location badge, and the place it names."""
    found = BADGE.search(html)

    if not found:
        return None

    badge = found.group(1)

    return badge, badge[len(LEAD_IN):] if badge.startswith(LEAD_IN) else None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="ignore the HTTP cache")
    args = parser.parse_args()

    records = Fetcher("records")
    pages = Fetcher("pages", force=args.force, delay=1.0)
    index = harvested(records)
    found: dict[str, dict] = {}

    for number in sorted(curated_numbers()):
        uri = index.get(number)
        record = records.get_json(uri) if uri and records.path_for(uri).exists() else None

        if not record or gallery(record):
            continue

        page = web_page(record)

        if not page:
            print(f"warning: {number} publishes no object page", file=sys.stderr)
            continue

        badge = read_badge(pages.get_bytes(page, suffix=".html").decode())

        if badge and not badge[1]:
            print(f"warning: {number} reads {badge[0]!r}, which does not start "
                  f"{LEAD_IN!r} — location not taken", file=sys.stderr)

        found[number] = {"page": page,
                         "badge": badge[0] if badge else None,
                         "location": badge[1] if badge else None}

    write_json(DATA / "locations.json",
               {"_comment": COMMENT, "retrieved": date.today().isoformat(), "works": found})

    stated = sum(1 for entry in found.values() if entry["location"])
    print(f"{stated}/{len(found)} works with no location in the record are placed by "
          f"the museum's own page (cache {pages.hits} hit / {pages.misses} miss)",
          file=sys.stderr)


if __name__ == "__main__":
    main()
