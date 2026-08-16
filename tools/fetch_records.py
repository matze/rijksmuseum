# /// script
# requires-python = ">=3.11"
# dependencies = ["requests>=2.31"]
# ///
"""Resolve candidate object identifiers to full Linked Art records.

Records land in the HTTP cache, so a second run costs nothing and a harvest can
be interrupted and resumed. Objects that turn out to be on view are followed one
hop further, to the visual item and digital object that carry the IIIF service —
and so are the works written up in `data/curated`, which do not all report a
location: the museum publishes none for the Milkmaid, and the guide still shows
it. Following the hop for all nine thousand candidates would cost twenty thousand
requests to photograph a collection nobody is being shown.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import (CACHE, DATA, Fetcher, digital_object_uris, gallery,  # noqa: E402
                    in_parallel, object_number, visual_item_uri)


def curated_numbers() -> set[str]:
    """The object numbers `data/curated` writes about, read without a YAML parser.

    This runs before the catalogue exists, so the front matter is all there is to
    read, and one line of it is all that is wanted.
    """
    return {match.group(1)
            for path in (DATA / "curated").glob("*.md")
            if (match := re.search(r"^objectNumber:\s*(\S+)", path.read_text(), re.M))}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="ignore the HTTP cache")
    parser.add_argument("--limit", type=int, help="resolve only the first n candidates")
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()

    candidates = json.loads((CACHE / "candidates.json").read_text())["uris"]

    if args.limit:
        candidates = candidates[: args.limit]

    fetcher = Fetcher("records", force=args.force)
    resolve = lambda uri: fetcher.get_json(uri, optional=True)  # noqa: E731
    written_up = curated_numbers()
    shown: list[dict] = []

    for record in in_parallel(candidates, resolve, workers=args.workers, label="records"):
        if record and (gallery(record) or object_number(record) in written_up):
            shown.append(record)

    print(f"{len(shown)}/{len(candidates)} on view or written up "
          f"(cache {fetcher.hits} hit / {fetcher.misses} miss)", file=sys.stderr)

    # Second hop: only the objects the guide can show need their imagery resolved.
    visual_uris = [uri for record in shown if (uri := visual_item_uri(record))]
    visual_items = [item for item in in_parallel(visual_uris, resolve, workers=args.workers,
                                                 label="visual items") if item]

    digital_uris = sorted({uri for item in visual_items for uri in digital_object_uris(item)})
    list(in_parallel(digital_uris, resolve, workers=args.workers, label="digital objects"))

    print(f"{len(visual_uris)} visual items, {len(digital_uris)} digital objects "
          f"(cache {fetcher.hits} hit / {fetcher.misses} miss, "
          f"{len(fetcher.failures)} unresolvable)", file=sys.stderr)


if __name__ == "__main__":
    main()
