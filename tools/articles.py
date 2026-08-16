# /// script
# requires-python = ">=3.11"
# dependencies = ["requests>=2.31"]
# ///
"""Find and read the English Wikipedia article for a work, without guessing URLs.

Curated prose cites an encyclopaedia article alongside the museum's own record,
and the detail sheet links to it. Article titles cannot be derived from object
titles — `The Windmill at Wijk bij Duurstede` is filed under another name — so
they are resolved through the search API and the canonical URL is printed for
the `sources` list. Responses go through the same cache as everything else.

    uv run tools/articles.py --for SK-A-4
    uv run tools/articles.py --search "Saint Elizabeth's Day Flood painting"
    uv run tools/articles.py --title "The Night Watch" --full
"""

from __future__ import annotations

import argparse
import json
import sys
import textwrap
from pathlib import Path
from urllib.parse import quote, urlencode

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import DATA, Fetcher, creator, harvested, titles  # noqa: E402

API = "https://en.wikipedia.org/w/api.php"
ARTICLE = "https://en.wikipedia.org/wiki/"
WRAP = textwrap.TextWrapper(width=88)


def api(fetcher: Fetcher, **params) -> dict:
    query = {"format": "json", "formatversion": "2", **params}

    return fetcher.get_json(f"{API}?{urlencode(query)}", accept="application/json")


def search(fetcher: Fetcher, terms: str, limit: int) -> list[dict]:
    result = api(fetcher, action="query", list="search", srsearch=terms, srlimit=limit)

    return result["query"]["search"]


def extract(fetcher: Fetcher, title: str) -> dict | None:
    result = api(fetcher, action="query", prop="extracts", explaintext="1",
                 redirects="1", titles=title)
    pages = result["query"]["pages"]

    return pages[0] if pages and not pages[0].get("missing") else None


def url_for(title: str) -> str:
    return ARTICLE + quote(title.replace(" ", "_"), safe="(),'-_.!~*")


def show(page: dict, *, full: bool, limit: int) -> None:
    text = page["extract"]
    body = text if full else text[:limit]

    print(f"\n{'=' * 88}\n{page['title']}\n{url_for(page['title'])}\n")

    for paragraph in body.split("\n"):
        print(WRAP.fill(paragraph) if paragraph.strip() else "")

    if not full and len(text) > limit:
        print(f"\n… {len(text) - limit} more characters, pass --full")


def terms_for(number: str) -> str:
    """Title and artist, to search on. The catalogue first, then the harvest —
    a work the museum reports no location for is missing from the one and
    present in the other, and is exactly as worth reading about."""
    catalogue = {entry["objectNumber"]: entry
                 for entry in json.loads((DATA / "catalogue.json").read_text())}
    entry = catalogue.get(number)

    if entry:
        title = entry["title"].get("en") or entry["title"].get("nl") or ""

        return f"{title} {entry.get('artist') or ''}".strip()

    records = Fetcher("records")
    uri = harvested(records).get(number)

    if not uri:
        raise SystemExit(f"{number} was never harvested")

    record = records.get_json(uri)
    names = titles(record)

    return f"{names.get('en') or names.get('nl') or ''} {creator(record)['display'] or ''}".strip()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--for", dest="number", help="object number: search on title and artist")
    source.add_argument("--search", help="free-text search")
    source.add_argument("--title", help="exact article title, no search")
    parser.add_argument("--results", type=int, default=3, help="how many hits to read")
    parser.add_argument("--full", action="store_true", help="print the whole article")
    parser.add_argument("--chars", type=int, default=2600, help="characters per article")
    args = parser.parse_args()

    # Wikipedia asks unregistered clients to keep well under a request a second.
    fetcher = Fetcher("wikipedia", delay=0.6)

    if args.title:
        page = extract(fetcher, args.title)

        if not page:
            raise SystemExit(f"no article titled {args.title!r}")

        show(page, full=args.full, limit=args.chars)
        return

    terms = args.search or terms_for(args.number)
    hits = search(fetcher, terms, args.results)

    if not hits:
        raise SystemExit(f"nothing found for {terms!r}")

    print(f"search: {terms}", file=sys.stderr)

    for hit in hits:
        if page := extract(fetcher, hit["title"]):
            show(page, full=args.full, limit=args.chars)


if __name__ == "__main__":
    main()
