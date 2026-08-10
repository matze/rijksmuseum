# Rijksmuseum visitor guide

A single-page, mobile-first browser guide. The visitor picks constraints (time, artists
and periods, children, step-free); the app composes one unbroken walkable line from the
Atrium to the exit, with no backtracking, and a live clock says whether they are ahead or
behind. Spec: `DESIGN.md`. Design reference only: `docs/design_handoff_rijksmuseum_guide/`.

## The rule that governs everything

**Nothing is guessed.** Every fact shown comes from the museum's own data or from a source
cited in the work's front matter. Prose is written from those sources, never copied from
the handoff and never recalled from memory. If a fact cannot be sourced, it does not ship
— say so instead, in the text or to the user.

The handoff prototype is placeholder content (its own README admits invented room
numbers). Treat it as layout, type and colour reference; take no facts from it.

## Commands

    just harvest        # search API → candidate ids → Linked Art records (cached)
    just build          # records → data/*.json, then IIIF derivatives for curated works
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
    data/       generated catalogue.json, galleries.json, tour.json;
                hand-written curated/*.md and floorplan-extra.json
    app/        plain ES modules, loaded directly by index.html
    css/        ds-classical.css (vendored design system, unmodified) + app.css
    vendor/     justif; assets/fonts/ self-hosted woff2
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
- Nothing may leave the page at runtime — fonts, images and justif are all local. Grep for
  external URLs in shipped files before claiming otherwise.

### Type

Seven sizes across the whole app, and no more: **37 · 29 · 22 · 16.5 · 14.5 · 12.5 · 11.5**.
Titles 37 (page) and 29 (stop, terminus); 22 for structure (floor headers, breaks); 16.5
running prose; 14.5 secondary text, chips and buttons; 12.5 small text and ghost buttons;
11.5 every uppercase label (`.kicker`, `.section-label`). Button sizes live in `.btn` /
`.btn-ghost`, not in inline styles at the call sites — that is how the ladder drifted to
seventeen sizes the first time.

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
