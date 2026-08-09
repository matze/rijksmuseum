# /// script
# requires-python = ">=3.11"
# dependencies = ["requests>=2.31"]
# ///
"""Page the museum's search API for the object types that are actually exhibited.

The full collection is 838k objects, almost all of it works on paper kept in
storage. The types below are the ones that hang in galleries; the on-view filter
proper happens in `build_catalogue.py`, which drops anything the museum does not
report a current location for.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import CACHE, SEARCH_ENDPOINT, Fetcher, write_json  # noqa: E402

EXHIBITED_TYPES = [
    "painting",
    "sculpture",
    "furniture",
    "ship model",
    "delftware",
    "silver",
    "glass",
    "porcelain",
    "dolls' house",
    "tapestry",
    "costume",
    "weapon",
]


def page_through(fetcher: Fetcher, object_type: str, limit: int | None) -> list[str]:
    url = f"{SEARCH_ENDPOINT}?type={object_type.replace(' ', '+')}"
    found: list[str] = []

    while url:
        page = fetcher.get_json(url, accept="application/json")
        found.extend(item["id"] for item in page.get("orderedItems", []))
        url = page.get("next", {}).get("id") if isinstance(page.get("next"), dict) else page.get("next")

        if limit and len(found) >= limit:
            return found[:limit]

    return found


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="ignore the HTTP cache")
    parser.add_argument("--limit", type=int, help="stop after this many ids per type")
    parser.add_argument("--type", action="append", dest="types", help="restrict to one type")
    args = parser.parse_args()

    fetcher = Fetcher("search", force=args.force)
    by_type: dict[str, list[str]] = {}

    for object_type in args.types or EXHIBITED_TYPES:
        by_type[object_type] = page_through(fetcher, object_type, args.limit)
        print(f"{object_type:16} {len(by_type[object_type]):6}", file=sys.stderr)

    unique = sorted({uri for uris in by_type.values() for uri in uris})
    write_json(CACHE / "candidates.json", {"byType": by_type, "uris": unique})
    print(f"{len(unique)} unique candidates "
          f"(cache {fetcher.hits} hit / {fetcher.misses} miss)", file=sys.stderr)


if __name__ == "__main__":
    main()
