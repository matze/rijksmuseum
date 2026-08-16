# /// script
# requires-python = ">=3.11"
# dependencies = ["requests>=2.31", "pillow>=11.3", "pyyaml>=6.0"]
# ///
"""Download and transcode the artwork imagery for the curated works.

The museum serves public-domain images through a IIIF endpoint. The guide has to
work with no network, so each work is pulled once at four widths and written
into `assets/works/` as AVIF, WebP and JPEG. Only curated works are fetched —
the catalogue's other twelve hundred entries never appear on the timeline.

The widest file is for the detail sheet on a desktop, where the plate leaves the
reading column and stands the height of the window; the smallest source
photograph is 3168px wide, so none of them is enlarged to reach 2400.
"""

from __future__ import annotations

import argparse
import io
import json
import sys
from pathlib import Path

import yaml
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import ASSETS, DATA, Fetcher, in_parallel  # noqa: E402

WIDTHS = [480, 960, 1600, 2400]
FORMATS = {"avif": {"quality": 55}, "webp": {"quality": 78, "method": 5},
           "jpg": {"quality": 82, "progressive": True, "optimize": True}}
WORKS = ASSETS / "works"


def curated_numbers() -> list[str]:
    return [yaml.safe_load(path.read_text().split("---")[1])["objectNumber"]
            for path in sorted((DATA / "curated").glob("*.md"))]


def derivatives(entry: dict, fetcher: Fetcher, force: bool) -> tuple[str, int]:
    """Fetch one work at every width and write every format. Returns files written."""
    number, service = entry["objectNumber"], entry["image"]["service"]
    written = 0

    for width in WIDTHS:
        targets = {suffix: WORKS / f"{number}-{width}.{suffix}" for suffix in FORMATS}

        if all(path.exists() for path in targets.values()) and not force:
            continue

        source = fetcher.get_bytes(f"{service}/full/{width},/0/default.jpg", suffix=".jpg")
        image = Image.open(io.BytesIO(source)).convert("RGB")

        for suffix, options in FORMATS.items():
            image.save(targets[suffix], **options)
            written += 1

    return number, written


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="re-encode existing files")
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()

    # The tour, not the catalogue: a curated work does not have to be on view,
    # and `build_catalogue.py` has already joined every one of them to its facts.
    written_up = {entry["objectNumber"]: entry
                  for entry in json.loads((DATA / "tour.json").read_text())}
    wanted = curated_numbers()
    missing = [number for number in wanted if number not in written_up]

    if missing:
        print(f"warning: {', '.join(missing)} never reached the tour, so no image is "
              f"fetched", file=sys.stderr)

    WORKS.mkdir(parents=True, exist_ok=True)
    fetcher = Fetcher("images", force=args.force)
    entries = [written_up[number] for number in wanted if number in written_up]

    total = 0

    for number, written in in_parallel(entries, lambda e: derivatives(e, fetcher, args.force),
                                       workers=args.workers, label="images"):
        total += written

    size = sum(path.stat().st_size for path in WORKS.iterdir())
    print(f"{len(entries)} works, {total} files written, "
          f"{size / 1e6:.1f} MB in {WORKS.relative_to(ASSETS.parent)}", file=sys.stderr)


if __name__ == "__main__":
    main()
