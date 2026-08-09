# /// script
# requires-python = ">=3.11"
# dependencies = ["requests>=2.31"]
# ///
"""Print everything the museum's record says about an object.

The source sheet for curation. Prose in data/curated/ is written against what
this prints plus the pages listed under `sources`, so the reading that produced
a paragraph can be repeated later by running the same command.

    uv run tools/describe.py SK-C-5
    uv run tools/describe.py --room 2.30 --list
    uv run tools/describe.py --floor 1 --list --uncurated
"""

from __future__ import annotations

import argparse
import json
import sys
import textwrap
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import (AAT, DATA, Fetcher, as_list, classifications, creator,  # noqa: E402
                    dimensions, gallery, language_of, production_date, statements,
                    titles, web_page)

STATEMENT_KINDS = ("description", "attribution", "medium_statement", "credit_line",
                   "inscription", "provenance", "dimensions_statement")

#: Ownership history and the repeated dimension line: long, and rarely what the
#: prose is written from.
VERBOSE_KINDS = ("provenance", "dimensions_statement")

WRAP = textwrap.TextWrapper(width=88, initial_indent="    ", subsequent_indent="    ")


def catalogue() -> dict[str, dict]:
    return {entry["objectNumber"]: entry
            for entry in json.loads((DATA / "catalogue.json").read_text())}


def curated() -> set[str]:
    return {path.stem for path in (DATA / "curated").glob("*.md")}


def summarise(entry: dict) -> str:
    where = entry["gallery"]
    return (f"{where['room']:<8} {entry['objectNumber']:<11} "
            f"{(entry['title'].get('en') or entry['title'].get('nl') or '')[:44]:<45} "
            f"{(entry.get('artist') or '')[:30]}")


def describe(number: str, entry: dict, fetcher: Fetcher, *, brief: bool = False) -> None:
    record = fetcher.get_json(entry["uri"])
    date, earliest, latest = production_date(record)
    where = gallery(record)

    print(f"\n{'=' * 88}\n{number}  {entry['uri']}")
    print(f"  titles     {titles(record)}")
    print(f"  creator    {creator(record)}")
    print(f"  date       {date}  ({earliest}–{latest})")
    print(f"  where      {where.code if where else None} — "
          f"{where.name.get('en') if where else ''}")
    print(f"  dimensions {dimensions(record)}")
    print(f"  page       {web_page(record)}")

    kinds = [k for k in STATEMENT_KINDS if not (brief and k in VERBOSE_KINDS)]

    for kind in kinds:
        for language, content in statements(record, kind).items():
            print(f"  {kind} [{language}]")
            print(WRAP.fill(content))

    types = {node.get("_label") for node in as_list(record.get("classified_as"))
             if AAT["primary_name"] not in classifications(node)}
    print(f"  classified {sorted(filter(None, types))}")

    subjects = {node.get("_label") for node in as_list(record.get("about"))}

    if subjects := sorted(filter(None, subjects)):
        print(f"  about      {subjects}")

    for node in as_list(record.get("referred_to_by")):
        kinds = classifications(node)

        if node.get("content") and not kinds & {AAT[k] for k in STATEMENT_KINDS}:
            print(f"  other [{language_of(node) or 'und'}] {sorted(kinds)}")
            print(WRAP.fill(node["content"]))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("numbers", nargs="*", help="object numbers, e.g. SK-C-5")
    parser.add_argument("--room", help="restrict to one room, e.g. 2.30")
    parser.add_argument("--floor", type=int, help="restrict to one floor")
    parser.add_argument("--list", action="store_true", help="one line each, no record detail")
    parser.add_argument("--brief", action="store_true", help="skip provenance and dimension statements")
    parser.add_argument("--uncurated", action="store_true", help="skip works already written up")
    args = parser.parse_args()

    entries = catalogue()
    written = curated()
    chosen = args.numbers or [
        number for number, entry in entries.items()
        if (args.room is None or entry["gallery"]["room"].startswith(args.room))
        and (args.floor is None or entry["gallery"]["floor"] == args.floor)
        and not (args.uncurated and number in written)]

    missing = [number for number in chosen if number not in entries]

    if missing:
        raise SystemExit(f"not in the catalogue (not on view?): {', '.join(missing)}")

    chosen.sort(key=lambda number: (entries[number]["gallery"]["floor"] or 0,
                                    entries[number]["gallery"]["room"], number))

    if args.list:
        for number in chosen:
            print(summarise(entries[number]))

        print(f"\n{len(chosen)} works", file=sys.stderr)
        return

    fetcher = Fetcher("records")

    for number in chosen:
        describe(number, entries[number], fetcher, brief=args.brief)


if __name__ == "__main__":
    main()
