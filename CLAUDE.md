# Rijksmuseum visitor guide

A single-page, mobile-first browser guide. The visitor picks constraints (time, artists
and periods, children, step-free); the app composes one unbroken walkable line from the
Atrium to the exit, with no backtracking, and a live clock says whether they are ahead or
behind.

## The rule that governs everything

**Nothing is guessed.** Every fact shown comes from the museum's own data or from a source
cited in the work's front matter. Prose is written from those sources, never copied from
the handoff and never recalled from memory. If a fact cannot be sourced, it does not ship
— say so instead, in the text or to the user.

## Commands

    just setup          # vendor the typefaces and justif — assets/ is not committed
    just harvest        # search API → candidate ids → Linked Art records (cached)
    just build          # borders → records → data/*.json, then IIIF derivatives
    just crops "..."    # detect_crops.py alone; "--review sheet.png" draws every box
    just floorplan      # read room coordinates out of the museum's published plan PDF
    just check          # verify.py — the invariants; fails the build
    just test           # node --test tests/ — routing and pacing, no DOM
    just serve          # python3 -m http.server 8137
    just shot "..."     # phone-viewport screenshot over CDP; needs a server running
    just describe SK-C-5              # everything the record says about an object
    just articles "--for SK-A-4"      # find and read the Wikipedia article

Python tools carry PEP 723 inline dependencies and run under `uv run`; there is no venv.
No npm, no bundler, no frontend build step — `package.json` exists only so `node --test`
treats `app/*.js` as ES modules.

## Layout

    tools/      retrieval and generation (Python). common.py holds one accessor per
                Linked Art field — the auditable seam between museum data and rendered text
    data/       generated catalogue.json, galleries.json, tour.json, crops.json;
                hand-written curated/*.md, floorplan-extra.json and crops-extra.json
    app/        plain ES modules, loaded directly by index.html
    css/        ds-classical.css (vendored design system, unmodified) + app.css
    vendor/     justif, committed
    assets/     gitignored and generated: fonts/ self-hosted woff2 from `just setup`,
                works/ the IIIF derivatives from `just build`. A fresh checkout has
                neither, so the page renders unstyled and imageless until both have run
    cache/      gitignored, content-addressed HTTP cache; makes harvests resumable

## Data

`https://data.rijksmuseum.nl` — Linked Art / JSON-LD, no API key, metadata CC0.

- `GET /search/collection?type=painting` pages object ids via `next`.
- `GET https://id.rijksmuseum.nl/{id}` with `Accept: application/ld+json` resolves a record.
- **`current_location` is the on-view filter.** No `current_location` means not on display.
- Gallery code `HG-2.31` → building HG, floor 2, room 2.31. `AK-1-23` (Asian Pavilion)
  carries no readable storey, so those works get `floor: null` and cannot be routed.
- Images: object → `shows` → VisualItem → `digitally_shown_by` → IIIF level 2 on
  `iiif.micr.io`, Public Domain Mark. `fetch_images.py` writes 480/960/1600px AVIF, WebP
  and JPEG under `assets/works/` for curated works only.
- English curatorial prose is largely absent from the API; the Dutch `description`
  statement usually exists. The museum's own object page (`web_page`) has English text —
  fetch it when writing prose.
- Photographs are not all cropped to the work: some are shot in the frame, some show the
  unpainted edge of a panel. `detect_crops.py` measures the box that is the work and
  writes `data/crops.json`; the guide clips its plates to it and the files stay whole.

Current state: 1237 on-view works, 244 rooms, 40 curated works, 131 rooms located on the
plan. A second `just build` must produce byte-identical JSON; that is the reproducibility
check.

### Floor plan

The API has room codes but no geometry. `fetch_floorplan.py` downloads the official
plattegrond PDF and reads room numbers out of its text layer at real map coordinates,
normalised into a 200×104 viewBox. Halls the plan names in words rather than numbers are
hand-read into `data/floorplan-extra.json`, with the derivation written in `_comment`.
Rooms the plan does not label carry no dot, and the caption says so — room 2.8, which
holds eleven Rembrandts, is one of them.

There is no verified scale, so the guide states minutes and never metres. Walking times
are named constants in `app/route.js` (`WALK`) and are estimates.

### Content boxes

`detect_crops.py` runs first in `just build`, before the catalogue, so one build takes a
new curated work all the way through. Each side is read on its own, along the outer
twentieth of the photograph, at one median colour per line. A border ends in an edge — a
hard change of colour running the length of the side — and the picture inside it does not,
so the reading is the hardest change in the strip, required to be several times harder
than the strip's own line-to-line restlessness. The cut then falls past the whole
crossing, which on a ragged panel edge is several lines wide, and bands are peeled one at
a time: a frame's dark outer face and its lit lip are two bands, not one.

It is built to under-read — a border left in place costs nothing, a cut into the picture
is gone. It will not cut deeper than 2% of a side, the band it takes has to be even in
itself, and a side where nothing stands out is left whole. That is what keeps the gallery
wall behind the ship model and the lit floor at the foot of the Night Watch — both of
which read as margins under every simpler rule tried here — out of the crops.

Frames are past what it will read: their browns and golds are the painting's own and they
run deeper than the limit. Those are hand-measured into `data/crops-extra.json`, merged
over the detected boxes, and both readings there are checked against the museum's stated
height and width — a box cut in the right place has the work's own proportions.

Read the result with `just crops "--review sheet.png"` and look at the PNG. Judging a cut
means looking at the edge magnified, not at the thumbnail; a band 12px wide at the 960px
analysis size is what the whole argument is about.

## Writing a curated work

`data/curated/<objectNumber>.md`: YAML front matter (objectNumber, displayTitle, priority
1–3, stayMinutes, tags, sources) then `## timeline / closer / detail / look / kids`.
Hard-wrapped lines join into paragraphs; blank lines separate them.

Workflow: `just describe <n>` for the record → `just articles "--for <n>"` for the
encyclopaedia article → WebFetch the museum object page for English curatorial text →
check visual claims against the actual image (fetch `<iiif service>/full/700,/0/default.jpg`
and look at it) → write → `just build && just check`.

Rules `verify.py` enforces, each written after nearly shipping the mistake:

- a source pointing at `id.rijksmuseum.nl` must be *this* object's URI
- a source pointing at `rijksmuseum.nl` must equal the record's own `page` (the hash is
  opaque and gets typed from memory — copy it from `just describe`)
- Wikipedia sources must be `https://en.wikipedia.org/wiki/...` article URLs
- tags must exist in the setup screen's vocabulary, read out of `app/route.js`
- curated works must be in building HG with a floor, and have all three image widths

Wikipedia coverage of individual works is patchy; when only an artist or sitter article
exists, cite it — the detail sheet labels the link "Further reading on Wikipedia".

## Frontend

State is one plain object in `app/main.js`; each view module exports a render function and
the app re-renders on transitions. No framework, no vdom. The expensive path — focus and
dimming on scroll — is attribute mutation in a rAF callback and re-renders nothing.

- Every view change is a history entry, so Back closes the detail sheet and steps out of
  the timeline. Scroll position rides on the entry; `history.scrollRestoration` is manual.
- `focus.js` lights exactly one `.card`, chosen by proximity to a reading line at 42% of
  the viewport. The line slides to meet the first and last entries so the termini can win
  at the ends of the page, where nothing can reach a fixed line.
- Route: floors in order `[0, 1, 3, 2]` so the visit ends on the Night Watch. Selection
  then layout; if the plan overruns the budget, drop the weakest stop and lay out again.
- Persistence: one localStorage key. A started visit resumes on the timeline.
- Dark only. There is no theme switch and no `prefers-color-scheme` branch; the tokens in
  `app.css` sit on bare `:root` and override the design system's light ones.
- The line is centred on a phone and survives only in the gaps between entries; from 640px
  up it straightens into a continuous rail to the left of the text. Marker geometry is CSS
  (`.row-<kind>`, `--axis`, `--mark-y`), never inline styles — a media query has to reach it.
- Each marker stands level with the first line of its entry, and the rail ends on the
  marker's edge rather than under it, so the line meets every marker without a gap. On a
  phone that puts the marker in the middle of a label's line: `.stop-head .where` is capped
  at `50% - 10px` so a long room code wraps instead of colliding. A walk is the exception —
  its text runs the full width, so its ring stays up in the gap.
- The plate is a window, not an image: `.plate-wrap` holds the proportions of the work and
  the photograph is laid inside it, absolutely positioned and scaled so the content box
  fills the opening. `plate.js` sets `--crop-x/y/w/h` and `--crop-ratio` per work and the
  stylesheet does the arithmetic, so it holds at every width the plate is drawn at. Works
  with no border carry `0 0 1 1` and come out at their plain size. The tile grid hangs the
  window, not the image, on the band floor — hence `.plate-band` around it in `setup.js`.
- Nothing may leave the page at runtime — fonts, images and justif are all local. Grep for
  external URLs in shipped files before claiming otherwise.

### Type

Six sizes across the whole app, and no more: **37 · 29 · 22 · 16.5 · 14.5 · 12.5**.
Titles 37 (page) and 29 (stop, terminus); 22 for structure (floor headers, breaks); 16.5
running prose; 14.5 secondary text, chips, buttons and every label (`.kicker`,
`.section-label`); 12.5 small text and ghost buttons. Button sizes live in `.btn` /
`.btn-ghost`, not in inline styles at the call sites — that is how the ladder drifted to
seventeen sizes the first time.

Labels are real small capitals from Cormorant SC, not `text-transform`. Its
small caps stand at 468/1000 against a cap height of 625 — set at the 11.5 the
transformed capitals used, the capital opening each label towers over the rest
of it, which is why labels sit two rungs up the ladder at 14.5 and are tracked
at .09em rather than .15em.

Every entry on the line opens on a label or on the walk line, so `--label-line` (14.5 on
the body's 1.55 leading) is what the timeline markers align to. Changing the label size
moves every marker.

Numbers are old-style figures (Cormorant Garamond); list markers hang in the page margin.

## Known and deliberate

- The Milkmaid (SK-A-2344), The Jewish Bride (SK-C-216) and The Syndics (SK-C-6) return no
  `current_location`, so the guide omits them. Surprising for three permanent highlights;
  worth a human check against the live hang before release.
- Asian Pavilion: 52 on-view works excluded, floor not derivable from `AK-*` codes.
- Prints and drawings are not harvested (424k records, essentially all in storage), so
  Rembrandt's etchings are invisible here even if they are hanging.
- A single-artist focus can run short of the requested time — there are only two Vermeers
  and twelve Rembrandt paintings on view. That is a content ceiling, not a routing bug.

## Working here

- Version control is **jj** (`.jj/` exists) — never git directly.
- `just shot` needs a server: start one, take the shot, then stop it. Chrome must be given
  `--no-proxy-server` or a system proxy refuses `127.0.0.1`.
- Never `pkill -f` a pattern that also appears in the same command line; it kills the
  shell (exit 144). Build the pattern with `printf` or match on something narrower.
- Screenshots are the review: read the PNG, do not assume the CSS did what you meant.
