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
    just shot "..."     # screenshot over CDP, phone viewport unless --width says wider
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
- **`current_location` is the on-view filter** for `catalogue.json`. No `current_location`
  means the museum publishes no room; it does not mean the work is in storage, and for the
  Milkmaid and a dozen others it plainly is not. A curated work does not need one — see
  *Off the line* below.
- Gallery code `HG-2.31` → building HG, floor 2, room 2.31. `AK-1-23` (Asian Pavilion)
  carries no readable storey, so those works get `floor: null` and cannot be routed. The
  place names itself twice, once for the room and once for the building; `gallery()` reads
  both, so a work outside the main building can still say where it is.
- **Height and width are only ever read from one run of measurements.** A record may
  measure the object, then its frame, then the case it travels in, naming each run in the
  `identified_by` of its own nodes. Pairing across runs states a size the object has never
  had, so `dimensions()` takes the run the record leaves unnamed, or calls the whole
  (`geheel`, `overall`), or the only one measured both ways — and otherwise reports no
  numbers and lets the sheet fall back to the museum's own dimensions sentence.
- Images: object → `shows` → VisualItem → `digitally_shown_by` → IIIF level 2 on
  `iiif.micr.io`, Public Domain Mark. `fetch_images.py` writes 480/960/1600/2400px AVIF,
  WebP and JPEG under `assets/works/` for curated works only. 2400 is for the detail sheet
  on a retina desktop; the smallest source photograph is 3168px wide, so none is enlarged.
- English curatorial prose is largely absent from the API; the Dutch `description`
  statement usually exists. The museum's own object page (`web_page`) has English text —
  fetch it when writing prose.
- Photographs are not all cropped to the work: some are shot in the frame, some show the
  unpainted edge of a panel. `detect_crops.py` measures the box that is the work and
  writes `data/crops.json`; the guide clips its plates to it and the files stay whole.

Current state: 1237 on-view works, 244 rooms, 102 curated works of which 84 are on the
line, 131 rooms located on the plan. A second `just build` must produce byte-identical
JSON; that is the reproducibility check.

### Off the line

A curated work does not have to be walkable. Two things put one out of reach: the museum
publishes no `current_location` for it, or it hangs in a building the route does not enter
— the Asian Pavilion, the KPN Wing. Either way it is written up, photographed, tiled on
the contact sheet and readable in full; it is only never a stop.

- `build_catalogue.py` normalises every harvested record. `catalogue.json` keeps the
  on-view part; `tour.json` joins the curated prose to whichever of them it names, with no
  `gallery` key at all when the museum gives none.
- `route.js` exports `onTheLine`, and it is the one place the rule lives: main building,
  and a floor read out of the room code. `rankWorks` filters on it; the contact-sheet tile
  says `off the line` instead of `not in this plan`; the detail sheet says which of the two
  reasons applies, in the provenance note where the guide shows its working.
- `fetch_records.py` follows the imagery hop for on-view objects **and** for anything named
  in `data/curated`. Following it for all nine thousand candidates would cost twenty
  thousand requests to photograph a collection nobody is being shown.
- `common.harvested()` indexes object number → record URI over the whole harvest, cached in
  `cache/by-object-number.json`, so `just describe SK-A-2344` and `just articles` reach a
  work the catalogue does not hold.

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
run deeper than the limit. Those are hand-measured into `data/crops-extra.json` and merged
over the detected boxes. A hand-read box is exempt from the depth limit — Van Gogh's
Riverbank is photographed in a carved frame that takes a seventh off every side — and is
held to the museum's stated height and width instead, within 3%. `verify.py` does that
arithmetic: a box cut in the right place has the work's own proportions, and one cut in
the wrong place cannot have them by accident.

Read the result with `just crops "--review sheet.png"` and look at the PNG. Judging a cut
means looking at the edge magnified, not at the thumbnail; a band 12px wide at the 960px
analysis size is what the whole argument is about.

## Writing a curated work

`data/curated/<objectNumber>.md`: YAML front matter (objectNumber, displayTitle, priority
1–3, stayMinutes, tags, sources) then `## timeline / closer / detail / look / kids`.
Hard-wrapped lines join into paragraphs; blank lines separate them.

A `region:` line closes the block above it and says which part of the work that block is
about — the timeline, any `detail` paragraph, any `look` item. It carries four fractions
**of the photograph**, the same space the crops are measured in and the space you are in
when you look at the file; the build restates them in the plate's own space, so re-reading
a border moves the regions with it. Blocks without one are the normal case.

    ## look
    1. The pearl hanging from the gold chain on the turban.
    region: 0.6550 0.1780 0.0750 0.1150
    2. The hard division between the lit and shadowed halves of the face.

A quoted phrase narrows the anchor from the whole block to those words, so a sentence
naming two places can point at both. The phrase is matched against the block's finished
text — written as it reads, not as it is wrapped — and must occur exactly once, which is
what stops a reworded sentence from silently lighting the wrong words. What ships is the
offsets, not a second copy of the prose. A block points either whole or by phrase.

    1. The captain's hand and the shadow it throws onto the lieutenant's coat.
    region: "The captain's hand" 0.4480 0.5900 0.0650 0.0640
    region: "the shadow it throws onto the lieutenant's coat" 0.5500 0.5950 0.0740 0.1080

Measure by eye against the photograph and check the result on the plate, magnified:
`just shot "/ --width 1440 --click '.tile[data-object=\"<n>\"]' --hover '.look li:nth-child(1)'"`.
A box that cannot be placed confidently is left out — the monogram on SK-A-3066 is not
legible in the photograph, so that look point ships without one. The `closer` and `kids`
are not on the sheet, and a region there is an error rather than a silent drop.

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
- every curated file must reach `tour.json`; a work that was never harvested, or carries no
  public-domain photograph, is a file that ships nothing
- a work in building HG must have a floor — the room code names one, so a work there that
  reports none was parsed wrong. Being outside HG, or having no gallery at all, is allowed
  and costs the work its place on the line, not its entry
- every curated work must have all three image widths
- a hand-read crop must match the record's stated proportions within 3%; a detected one
  must still keep 70% of every side
- a region must be a box inside the work, and a *part* of it: `KEPT` does not apply, but a
  box over 80% of a side points at the whole picture and one under 2% cannot be found
- a phrase's offsets must lie inside its own block's text and not overlap another's — they
  are offsets rather than copies, so nothing in the file shows when one has slipped

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
- The line runs inside the column on a phone and survives in the gaps between entries; from
  640px up it straightens into a continuous rail to the left of the text. Marker geometry is
  CSS (`.row-<kind>`, `--axis`, `--mark-y`), never inline styles — a media query has to
  reach it.
- The axis stands 26px off the right edge of the column, the mirror of the rail above the
  breakpoint: everything that shares a line with a marker — a stop's label against its
  minutes, a walk's sentence — is one run of text to the left of it. `--text-limit` is how
  far that text may run, and `.stop-head`, `.entry-walk`, `.entry-break` and `.entry-floor`
  are held to it.
- Each marker stands level with the first line of its entry. **The line breaks where a
  painting hangs**: the entries between artworks — walk, break, floor header — carry a rail
  the whole height of their row with their marker on it, while a stop's plate runs to the
  column's edge and its rail ends on the marker above. The termini end the line, where the
  visit ends. The floor plan is centred inside its own `max-width`, so holding that card to
  `--text-limit` leaves the schematic its size.
- Where the rail runs past a marker that dims, the opaque `.mark-back` goes behind it — so
  break and floor carry one on a phone too. A walk is never dimmed and masks the rail with
  its own fill.
- The plate is a window, not an image: `.plate-wrap` holds the proportions of the work and
  the photograph is laid inside it, absolutely positioned and scaled so the content box
  fills the opening. `plate.js` sets `--crop-x/y/w/h` and `--crop-ratio` per work and the
  stylesheet does the arithmetic, so it holds at every width the plate is drawn at. Works
  with no border carry `0 0 1 1` and come out at their plain size. The tile grid hangs the
  window, not the image, on the band floor — hence `.plate-band` around it in `setup.js`.
- The detail sheet is the one place the work is looked at rather than walked past. From
  1160px up it leaves the reading column: `.sheet-plate` takes a column of its own and is
  sticky, standing the height of the window under the head, and `.sheet-text` runs beside
  it at its usual measure, so the description scrolls past a work that stays in view. The
  plate is height-led there — `width: min(100%, var(--plate-height) * var(--crop-ratio))`,
  the same reading the contact-sheet tiles use. That plate is drawn at up to 840px, which
  is what its `sizes` declares and what pulls the widest derivative on a retina desktop.
  `.plate-frame` wraps the picture there and is what sticks, so the hotspots travel with it.
- On that sheet a block of prose — or a marked phrase inside one — and the part of the work
  it names carry the same `data-region`, and `regions.js` lights either from the other with
  one delegated listener. It re-reads the marked nodes on every hover, because justif
  rebuilds a paragraph line by line and clones the phrases it holds: one that runs over a
  line break is several elements by the time it is hovered. Everything anchored carries a
  dotted gold rule, so it can be found without hovering the page to look for it.
  Hovering the text veils the rest of the work behind a soft-edged hole cut in
  `.plate-frame::after`; hovering the work only golds the text, because you are already
  looking at the painting. Gated to 1160px and `hover: hover` — below that the plate is
  above the description rather than beside it. `screenshot.py` tells Blink which pointer it
  is being driven with, or a capture would report `hover: none` and see none of this.
- The whole of that is switched by `.sheet-regions` in the sheet head — rules, hotspots and
  veil, off one `data-regions` attribute on `.sheet` that gates every rule in the block.
  `paintRegions` flips it in place rather than re-rendering, which would cost the reader
  their place. The switch is drawn only on a work that has regions, and only where the
  feature runs. Its value persists with the rest of the state.
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

- Fifteen curated works return no `current_location` — the Milkmaid, the Jewish Bride, the
  Syndics, the Feast of St Nicholas among them. They are written up and shown off the line.
  The museum's *own object pages* do give a display location for several of them, so the
  gap is in the Linked Art records rather than in the hang. Reading those pages into a
  hand-written location file would put them back on the route, at the cost of a mapping
  that goes stale silently; that trade has not been taken.
- SK-C-1845, Van Gogh's Wheatfield, is filed with its height and width the wrong way round
  — the record and the dimensions sentence both make a landscape canvas portrait. It is not
  curated for that reason. Nothing in the pipeline can catch this without measuring the
  photograph, which would be deriving a fact from a picture.
- Asian Pavilion: 52 on-view works, floor not derivable from `AK-*` codes. Three are
  curated and shown off the line; the other 49 are uncurated like most of the catalogue.
- Prints and drawings are not harvested (424k records, essentially all in storage), so
  Rembrandt's etchings are invisible here even if they are hanging.
- A single-artist focus can run short of the requested time — there are only two Vermeers
  and twelve Rembrandt paintings on view. That is a content ceiling, not a routing bug.
- Eighteen curated works show a Dutch medium statement, because the record carries no
  English one. The museum's own words in the museum's own language beat a translation the
  guide would have had to invent.

## Working here

- Version control is **jj** (`.jj/` exists) — never git directly.
- `just shot` needs a server: start one, take the shot, then stop it. Chrome must be given
  `--no-proxy-server` or a system proxy refuses `127.0.0.1`.
- Never `pkill -f` a pattern that also appears in the same command line; it kills the
  shell (exit 144). Build the pattern with `printf` or match on something narrower.
- Screenshots are the review: read the PNG, do not assume the CSS did what you meant.
