set shell := ["bash", "-uc"]

run := "uv run --quiet"
port := "8137"

default:
    @just --list

# Vendor third-party runtime assets (justif, fonts) into the tree.
setup:
    {{run}} tools/vendor.py

# Retrieve object identifiers and Linked Art records from the museum.
harvest *ARGS:
    {{run}} tools/fetch_candidates.py {{ARGS}}
    {{run}} tools/fetch_records.py {{ARGS}}

# Regenerate the catalogue, the tour pool and the artwork imagery.
build:
    {{run}} tools/detect_crops.py
    {{run}} tools/build_catalogue.py
    {{run}} tools/fetch_images.py

# Measure the border each curated photograph carries, for the guide to clip away.
#   just crops "--review crops.png"
crops *ARGS:
    {{run}} tools/detect_crops.py {{ARGS}}

# Read room positions out of the museum's published floor plan.
floorplan:
    {{run}} tools/fetch_floorplan.py

# Everything the museum's record says about an object, for writing curated prose.
#   just describe SK-C-5
#   just describe "--room 2.30 --list --uncurated"
describe *ARGS:
    {{run}} tools/describe.py {{ARGS}}

# Find and read the English Wikipedia article for a work, for the same purpose.
#   just articles "--for SK-A-4"
#   just articles "--search 'Saint Elizabeth flood painting'"
articles *ARGS:
    {{run}} tools/articles.py {{ARGS}}

# Assert the invariants the generated data has to satisfy.
check:
    {{run}} tools/verify.py

# Route composition and pacing, against the real tour data.
test:
    node --test tests/

serve:
    python3 -m http.server {{port}}

# Screenshot the guide at a phone viewport. Needs `just serve` running.
#   just shot "/ --click .btn-primary --out tour.png"
shot *ARGS:
    {{run}} tools/screenshot.py --base http://localhost:{{port}} {{ARGS}}

all: harvest build check test
