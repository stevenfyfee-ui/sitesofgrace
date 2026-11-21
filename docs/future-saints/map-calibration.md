# Future Saints: California missions map calibration

The missions hub map is an SVG in one fixed viewBox. The state outline and the 21 pins go through the
same function, `future_saints.geo.to_viewbox(lat, lng)`: the outline once, when
`tools/build_california_outline.py` builds it, and the pins on every request, from each canonical
Mission Trail page's own latitude/longitude. Nothing is placed by hand. Comp 02 is the layout and
style target only, never a source of positions.

## Geography source

- **US Census Bureau, 2023 Cartographic Boundary File, States, 1:500,000 (KML)**:
  https://www2.census.gov/geo/tiger/GENZ2023/kml/cb_2023_us_state_500k.zip
- Licence: public domain (a US government work).
- Built with `python tools/build_california_outline.py <zip>`. It uses only the standard library, and
  the zip isn't committed.
- Output: California (STATEFP 06), the mainland plus the islands larger than 4 square units (the
  Channel Islands). Each ring is simplified with Douglas-Peucker at **0.2 units (about 220 m)**,
  giving 7 rings and 1,409 points.
  - The mission closest to the coast is San Buenaventura, 0.8 units (about 0.9 km) inside the
    simplified coastline.
- Files written:
  - `future_saints/data/california_outline.json` (the rings and the SVG path)
  - `docs/future-saints/map-art-template.svg` (the outline and viewBox only, for an illustrator to
    paint a basemap on)

## Projection

EPSG:3310, "NAD83 / California Albers":
- Albers equal-area conic on the GRS80 ellipsoid (a = 6,378,137 m, e² = 0.0066943800229).
- Standard parallels 34°N and 40.5°N.
- Latitude of origin 0°, central meridian 120°W.
- False easting 0, false northing −4,000,000 m.

The formulas are Snyder's, from *Map Projections: A Working Manual* (USGS Professional Paper 1395,
eqs. 14-1 to 14-19 and 3-12), in plain Python with no new dependency. When written, the code was
checked against PROJ (pyproj, EPSG:4269 → EPSG:3310). It matched to better than 1e-7 m at nine
points across the state. Three of those reference values are in the tests.

## viewBox

```
viewBox = "0 0 1000 1100"     preserveAspectRatio = "xMidYMid meet"
x_view = (x_3310 − (−440,000)) / 1,100
y_view = (480,000 − y_3310) / 1,100          (SVG y grows downward)
```

- 1 unit is 1.1 km.
- The state outline spans x 60.1–890.9 and y 27.2–985.9, leaving ocean margin on the west and
  south. The compass rose (around 110, 990) and the "California Mission Trail" scroll (box 52–308 ×
  773–847) sit in the ocean.
- The map box has the viewBox's aspect ratio (CSS `aspect-ratio: 1000 / 1100`), so "meet" fills it
  exactly. A pin's `left` / `top` percentages are therefore x/1000 and y/1100.
- `MissionHubEntry.map_offset_x/y` move a pin's Founding # badge, in screen pixels. They never move
  the pin (see "Founding # badges" below).

## Ocean and neighbouring land

Only the Pacific is drawn as water. The build writes an `ocean` ring:
- California's own coast, from the mainland's northernmost vertex (the Oregon border at the sea) south
  to its southernmost vertex (the Mexico border at the sea);
- short neighbour coasts, decorative only and never used for pins:
  - Oregon: Brookings (42.05, −124.28) and Cape Ferrelo (42.10, −124.35);
  - Baja California: Rosarito (32.36, −117.06), Ensenada (31.86, −116.63) and Punta Banda (31.75, −116.75);
- the map's west and south edges.

Everything else outside California (Oregon, Nevada, Arizona, Mexico) is plain, unlabelled parchment
land. A test checks that Reno, Las Vegas, Yuma, Medford and Tecate fall outside the ocean.

## City labels

There are four parchment ribbons: San Francisco (on two lines), Monterey, Los Angeles and San Diego.
There's no Sonoma ribbon.
- Each ribbon sits in the Pacific. A thin leader line runs from it to a dot at the city's real position:
  the city-centre latitude/longitude, through the same projection.
- The boxes are in `future_saints/missions.py` (`CITY_LABELS`). They were chosen by a search that keeps
  each ribbon:
  - clear of the coast and the islands (6-unit margin), the compass, the scroll and the other ribbons;
  - clear of every bell and Founding # badge at every QA width where the ribbons show;
  - within 70 units of its city's latitude, in north-to-south order.
- **Ribbon text is never under 11 px.** It is 22 units tall, so it reaches 11 px once the map is
  500 px wide (`CITY_LABEL_MIN_MAP_PX`). On a narrower map, a CSS container query on `.fs-map`
  hides the ribbons, their dots and their leaders.
  - Shown at 1440 (15.2 px), 1024 (12.0 px) and 768 (15.5 px).
  - Hidden at 430, 390 and 360.
- Tests check all of this in viewBox units. The browser QA checks the rendered boxes.

## Trail line

A dotted gold line joins the pins in the Mission Trail page's stop order (south to north along the
coast), from the same canonical positions as the pins.

## Founding # badges

Each badge sits up and to the right of its bell, at a fixed size in screen pixels. The pins themselves
scale with the map, at 0.328–0.707 px per unit across the QA widths (`MAP_WIDTHS_PX`, measured with
`tools/measure_mission_map.py`).
- The reviewed offsets in `BADGE_OFFSETS` keep every pair of badges apart at 1440, 1024, 768, 430,
  390 and 360. The largest is 36 px; 16 of the 21 missions have one.
- `seed_mission_hub` writes them where a mission has no offset yet, marked reviewed. An editor's own
  offset is kept.

## Control points

| point | lat, lng | EPSG:3310 (m) | viewBox |
|---|---|---|---|
| Mission San Diego de Alcalá (#1, southernmost pin) | 32.784267, −117.106283 | 271,406, −576,777 | 646.7, 960.7 |
| Mission San Francisco Solano, Sonoma (#21, northernmost pin) | 38.293667, −122.455917 | −214,509, 33,605 | 205.0, 405.8 |
| California–Mexico border at the Pacific (state's southern extreme) | 32.5343, −117.1235 | 270,632, −604,493 | 646.0, 985.9 |
| California–Oregon border at the Pacific (northwest corner) | 41.9983, −124.2125 | −349,582, 450,008 | 82.2, 27.3 |

The last two rows are an independent check on the outline. Projected on their own, they land on the
outline's southernmost vertex (646.01, 985.89) and its northwest corner (82.27, 27.25), both within
0.1 unit.

## What the tests check (`future_saints/tests/test_missions.py`)

- All 21 pins fall inside the state polygon.
- The southernmost pin is San Diego (#1) and the northernmost is Sonoma (#21).
- North-to-south order by projected y matches latitude order.
- The Monterey cluster (#2, #13, #15) and the SF Bay cluster (#6, #8, #12, #14, #20, #21):
  - every pair's map distance is within 3% (plus 0.5 km) of its great-circle distance;
  - each pin is within 80 units of its cluster's centre.
- A pin moves when its canonical latitude/longitude changes.
- The compass rose, the scroll and the four city ribbons stay in the Pacific. Only the Pacific is water.
- No two Founding # badges intersect at any QA width, and no ribbon touches a bell or a badge.
- The trail line follows the trail's stop order.
- The border control points match the outline's extremes.
- The `albers()` reference values match PROJ.

---

# World Discovery Map (Phase 4)

The world map at `/future-saints/map/` uses the same approach as the California map. The land outline
and every pin go through one function, `future_saints.geo.world_viewbox(lat, lng)`: the outline once,
when `tools/build_world_outline.py` builds it, and the pins on every request from each story's own
canonical coordinates. Comp 01's map hero is the style target only.

## Geography source

- **Natural Earth, 1:110m Physical Vectors, Land (`ne_110m_land`), version 5.1.2.**
  https://www.naturalearthdata.com/downloads/110m-physical-vectors/110m-land/
- Licence: public domain (Natural Earth terms of use, "All versions of Natural Earth raster + vector
  map data … are in the public domain").
- The build used the GeoJSON copy at
  https://raw.githubusercontent.com/nvkelso/natural-earth-vector/v5.1.2/geojson/ne_110m_land.geojson.
  That download isn't committed.
- The build:
  - leaves out **Antarctica**: any land wholly south of 60°S (8 rings), to save space;
  - simplifies each ring with Douglas-Peucker at **0.4 units** (about 15 km at the equator);
  - drops islands smaller than 2 square units.
- The result is 109 polygons, 1 hole and 3,104 points.
- Files written:
  - `sitesofgrace/static/future_saints/svg/world-outline.svg`, 43 KB: one `<path id="fs-world-land">`.
    The map and the homepage preview both `<use>` it, so browsers fetch it once. In production it's
    served with a hashed, cache-forever name.
  - `future_saints/data/world_outline.json`: the same rings, for the tests and the staff checks.

## Projection

**Equal Earth** (Šavrič, Patterson & Jenny, 2018, *International Journal of Geographical Information
Science* 33(3)):
- on a sphere, central meridian 0°;
- coefficients A1 = 1.340264, A2 = −0.081106, A3 = 0.000893, A4 = 0.003796;
- in plain Python (`geo.equal_earth`).

When written, it was checked against PROJ (`+proj=eqearth +R=1`) at nine points, and the difference
was 0.

## viewBox

```
viewBox = "0 0 1000 445"     preserveAspectRatio = "xMidYMid meet"
x_view = 500 + x_EE × 500 / x_EE(0°, 180°)
y_view = (y_EE(90°N) − y_EE) × 500 / x_EE(0°, 180°)        (SVG y grows downward)
```

- 90°N is at y 0. 60°S is at y 444.4, the bottom edge.
- The map box keeps the viewBox's aspect ratio, so a pin's `left` / `top` percentages are x/1000 and
  y/445.
- The compass rose is in the South Pacific, around (70, 370). A test checks it's clear of land.

## Control points

| point | lat, lng | viewBox |
|---|---|---|
| Mexico City | 19.4326, −99.1332 | 232.2, 171.4 |
| Fátima | 39.6317, −8.6724 | 478.6, 101.5 |
| Lourdes | 43.0967, −0.0558 | 499.9, 90.4 |
| Rome | 41.9028, 12.4964 | 530.4, 94.2 |
| Jerusalem | 31.7784, 35.2296 | 590.8, 127.7 |

All five are on land.
- West to east: Mexico City, Fátima, Lourdes, Rome, Jerusalem.
- North to south: Lourdes, Rome, Fátima, Jerusalem, Mexico City.

## Pins

Only **published** stories appear.

| Story type | Where its pin goes |
|---|---|
| Marian, Eucharistic, Holy Land | the canonical page's coordinates |
| Saint | `map_place` if set; otherwise the saint's one live principal site (`SacredSitePage.associated_saint`) |
| California missions | one callout at 37.2°N, 119.6°W, with the count of published mission pages |

A saint with no principal site, or with two or more, is listed but not pinned, and staff see it as
needing a map place.

**Offsets.** Markers are 34 px discs. At 1440 the whole world is 1,184 px wide (691 px before the
map was enlarged; see "Country borders and names"). Where markers would overlap
there, a reviewed offset in `worldmap.WORLD_MARKER_OFFSETS` moves the marker on desktop (1024 and
wider) only. A thin line and a dot anchor it to its true spot.

**Spreading (with JavaScript), since the map card fix.** The fixed offsets only suited the 1440 map.
Assisi and Lanciano are about 5 map units apart:

- at 1440 the selected Carlo disc (scaled 1.12) left about 2 px to Lanciano;
- at 1024 the discs overlapped;
- at 390 (no offsets) they sat 1.9 px apart;
- the offsets faded out by 2× zoom, while these two only separate on their own near 9×.

`future-saints.js` now spreads the markers that would touch, for the map as it is drawn. It reruns
after every layout, zoom, resize and filter change.

- **Spacing:** each pair ends at least 39 px apart, centre to centre. That is a 2 px gap between
  the selected disc and another, plus 1 px for rounding.
- **True spots:** each moved marker keeps a dot and a thin line to its true spot, which never moves.
- **Without JavaScript:** the reviewed offsets below still apply on the desktop map.

`tools/future_saints_card_screens.py` checks that no two discs touch at 1440, 1024 and 390, at
1×, 1.5×, 2×, 3× and 6×, and that every true spot is unchanged.

| Story | Offset (px) |
|---|---|
| Lourdes | (−16, 0) |
| Saint Carlo Acutis (Assisi) | (0, −8) |
| Lanciano | (0, 28) |

These are the smallest offsets that clear every marker. Staff see any new overlap on the map page.

---

# Map art, textures and zoom (both maps)

## Steven's map art

Steven supplied ten pieces. `tools/build_map_art.py <folder>` reads the source folder without
changing it, picks each file by the number at the end of its name, and writes the results to
`static/future_saints/map-art/`.

**Textures (1–2).**
- `land-texture.jpg` and `ocean-texture.jpg`, kept at their own 1254 px.
- They're JPEG quality 82, about 200 KB each. The source PNGs were about 2.3 MB each, and the
  textures have no transparency.

**Pieces (3–10).**
- Mountain range, tall mountain, oak, redwoods, palm, poppies, sailing ship, whale.
- Each is resized to 2× its largest display size: its width in map units × 0.707 px per unit on the
  widest map × 4 for California's 4× zoom × 2 for high-density screens.
- They're saved as 256-colour PNG with transparency, 14–70 KB each.
- Only the sailing ship and the whale are used. Steven decided before #28 merged to keep land
  pieces off the maps. The other six files stay in `map-art/` unused, in case they come back; the
  build script still makes all ten.

**Tiling.** The textures aren't seamless, so each is tiled as a mirrored 2 × 2 pattern: every edge
meets its own reflection. One tile is 300 map units on California and 250 on the world map, so at
maximum zoom the texture is upscaled 1.35× and 1.65× respectively: soft, not blocky.

**California.** The land texture is clipped to the outline and the ocean texture to the Pacific; the
neighbouring states stay plain parchment. Only two pieces, both in open Pacific
(`missions.CALIFORNIA_ART`):

| Piece | Where | Width (units) |
|---|---|---|
| Sailing ship | open Pacific (60, 680) | 90 |
| Whale | open Pacific, 32.3°N 120.3°W | 120 |

- Neither touches land, a pin, badge, city label, leader line, the trail, the compass or the scroll
  at any of the six widths (test_maps_art_zoom), so both show on phones too.
- The art layer is aria-hidden.

**World map.**
- The same watercolor family: the ocean texture on the water and the land texture clipped to the
  outline.
- The same surf, paper rim, outline, paper grain and compass rose as California.
- Only two pieces, both in open ocean, never on land: the sailing ship (mid-Atlantic, 27°N 45°W) and
  the whale (South Pacific, 12°S 128°W). Each is clear of every marker and the compass at all six
  widths.
- The homepage preview uses the same art.

## Zoom

One component zooms both maps (`future-saints.js`, `initZoom`).
- **Limits:** 1–6× on the world map, 1–4× on California. Panning is clamped to the map.
- **Controls:** + / − / reset buttons (44 px, with aria-labels).
- **Pointer:** drag to pan; pinch on touch.
- **Wheel:** zooms only after the map has been clicked or focused, so page scrolling is never taken
  over.
- **Keyboard,** while the map has focus: + / − to zoom, the arrow keys to pan, 0 to reset.
- **Markers:** CSS counter-scales them, so they keep their screen size; their true spots never move.
- **Coastline strokes:** divided by the zoom, so they also keep their screen weight.
- **Overlap offsets:** the world map's desktop offsets and leader lines fade from 1× to 2×, by which
  zoom the pins separate.

**Region shortcuts** (world map). Each box is the projected bounds of a latitude/longitude box:

| Region | Latitude | Longitude |
|---|---|---|
| Europe | 35–59°N | 11°W–31°E |
| Holy Land | 30.5–33.6°N | 34.0–36.2°E |
| The Americas | 56°S–60°N | 168°W–34°W |

"Whole World" resets the map.

**Zooming to a story.** Choosing a story from the list, or arriving with `?story=` (or `?mission=`
on California), zooms and pans to it. With reduced motion it jumps instead of animating.

**Detail.** The first time the world map passes 2× (since the map was enlarged: the first time it is
drawn at more than 2.368 px per map unit, which is 2× on the 1440 map), it swaps to the Natural Earth **1:50m** outline
(`world-outline-50m.svg`: simplified at 0.12 units, 532 polygons, 233 KB, about 86 KB gzipped).
- It's built with `tools/build_world_outline.py --detail <ne_50m_land.geojson>`.
- Natural Earth is public domain.
- California's outline (simplified at about 220 m) stays sharp at 4×.

**Without JavaScript,** the static maps and lists still work, and the zoom controls and region
shortcuts stay hidden.

## Page weight

Measured on the first load at 1440 wide:

| Page | Total | New map art |
|---|---|---|
| World Discovery Map | 804 KB | 532 KB, plus 227 KB for the 1:50m outline, only after zooming past 2× |
| California Missions hub | 865 KB | 532 KB (the textures, ship and whale) |
| Future Saints homepage | 831 KB | 532 KB |

The CSS and JS grew by 2 KB and 10 KB.

---

# Country borders and names (World Discovery Map)

The world map is larger and shows country borders and English country names. Each story's card and
list entry also say which country it is in ("Country: Italy"). Everything stays behind
`SOG_FUTURE_SAINTS`. The homepage preview is unchanged.

## Source

- **Natural Earth, Admin 0 – Countries, point of view: United States (`ne_10m_admin_0_countries_usa`),
  version 5.1.2** (the latest release).
  https://www.naturalearthdata.com/downloads/10m-cultural-vectors/10m-admin-0-countries/
  The build used the GeoJSON copy at
  https://raw.githubusercontent.com/nvkelso/natural-earth-vector/v5.1.2/geojson/ne_10m_admin_0_countries_usa.geojson.
  That download isn't committed.
- Licence: public domain (Natural Earth terms of use).
- Natural Earth publishes the U.S. point of view only at 1:10m. The build simplifies it with the
  land outline's own Douglas-Peucker routine and tolerances, so no border is drawn or moved by hand.
- Built with `python tools/build_world_borders.py <ne_10m_admin_0_countries_usa.geojson>`. It uses
  only the standard library.

**Disputed areas, as this edition draws them** (decided before the build, 2026-11-20):

| Area | Drawn and named |
|---|---|
| Israel / West Bank and Gaza | Israel, and "Palestine" (one feature: the West Bank and Gaza). Jerusalem is in Israel. |
| Western Sahara | Its own shape, "Western Sahara". |
| Kosovo | Its own country, "Kosovo". |
| Taiwan | Its own shape, "Taiwan". |
| Crimea | Ukraine. |
| Kashmir | Split along the Line of Control; Aksai Chin in China. Every border is the same soft line (no dashed lines). |

**Folded pieces.** Every "Breakaway" and "Lease" feature is folded into its sovereign by Natural
Earth's `SOV_A3`, and the UK sovereign base areas into Cyprus (reviewed, `FOLD_INTO`). A folded piece gets no label, and no line is drawn
where both sides share a sovereign:
- Abkhazia and South Ossetia → Georgia (no line, no label).
- Guantánamo Bay → Cuba (`CU1`; no line, no label).
- Akrotiri and Dhekelia → Cyprus (no line, no label; reviewed 2026-11-20). By `SOV_A3` they would go
  to the United Kingdom (`GB1`) and keep a small line around each base, so they're mapped to `CYP`
  directly. This edition has one Cyprus feature (no separate north or buffer zone).

## Borders

- **One path of shared boundaries.** Every edge two different countries share, chained between
  junctions and drawn **once**. Coasts aren't borders: the coastline stays the land outline's.
- **Two levels**, each built with the land outline's tolerances. Junctions stay put, so the chains still
  meet. A segment that two chains simplify to the same line is dropped the second time; a test checks
  that no segment is drawn twice.

| File | Tolerance | Chains | Points | Size (gzipped) |
|---|---|---|---|---|
| `static/future_saints/svg/world-borders.svg` | 0.4 units | 360 | 2,942 | 42 KB (16.3 KB) |
| `static/future_saints/svg/world-borders-50m.svg` | 0.12 units | 370 | 7,514 | 106 KB (39.1 KB) |

- **Clipped** to the land outline (`#fs-world-land-clip`), so no border runs into the sea.
- **Detail swap:** the finer level loads with the 1:50m land outline (`data-fs-detail`). Both swap the
  first time the map is drawn at more than **2.368 px per map unit**, which is 2× on the 1440 map.
  It's a scale, not a zoom factor, so a phone that opens filling its height doesn't load the finer
  level before it needs it.
- **Style:** `#8a7550` (the coastline's warm brown) at 50% opacity, `0.8px × --lu`. `--lu` is map
  units per screen pixel, set by the zoom, so the line is about 0.8 px on screen at every zoom.
  Decorative: inside the aria-hidden art, under the markers, not clickable.

## Names

- **What gets a name:** 199 countries. That's each sovereign state's home part, plus Kosovo, Taiwan,
  Palestine, Western Sahara and Greenland. Dependencies, territories and the folded pieces get none,
  and nor do two Indeterminate reef and island features that aren't countries (Scarborough Shoal,
  and the Spratly Islands feature Natural Earth names "Wake Island").
- **Text:** Natural Earth's `NAME_EN`, with five reviewed plain names (`PLAIN_NAMES`):
  - United States of America → United States
  - People's Republic of China → China
  - The Gambia → Gambia
  - The Bahamas → Bahamas
  - Federated States of Micronesia → Micronesia

  Czech Republic, Ivory Coast, East Timor, Turkey, Cape Verde, Republic of the Congo and Palestine
  stay as Natural Earth has them.
- **Place:** SVG text at Natural Earth's `LABEL_X` / `LABEL_Y`, through `world_viewbox`.
  Written to `future_saints/data/world_labels.json`.
- **Style:** Future Saints Serif (Lora; it is both the heading and the body face), `#4f4537` with a
  parchment halo. 13 px for `LABELRANK` ≤ 2 (36 countries), 11 px for the rest, never smaller. The
  size is `px × --lu`, so it stays constant on screen while zooming. aria-hidden, not interactive.
- **When a name may show:** both of these, from Natural Earth's data.
  - **`rank_zoom`** — the map's zoom (1 = the whole world) at which the country's rank lets it show:
    its `MIN_LABEL`, one step earlier, with 1× taken as the 1440 map (about web zoom 2.2). So at 1×
    only large countries, and more as you zoom in, on every screen.
  - **`fit_scale`** — the scale (px per map unit, so the screen's size counts) at which the name fits
    across the country's main part and its height.

  A name that never fits by 6× on the 1440 map (Vatican City, San Marino, Monaco, Andorra,
  Liechtenstein, Malta and others) has no `fit_scale`. It may show only at the largest zoom. So may a
  name too long for a small screen even at its largest zoom.
- **Collisions:** names are placed greedily, largest countries first. A name is hidden at that zoom if
  it would touch:
  - a marker's 44 px button (pins always win);
  - the compass rose, the ship or the whale;
  - the zoom buttons or the full-screen "Close";
  - another name, or the map's edge.
- **With JavaScript,** `future-saints.js` does the placement at the real scale after every zoom,
  pan, resize, filter change and marker spread.
- **Without JavaScript,** the server runs the same placement for five width bands (`LABEL_BANDS`: 320,
  450, 700, 900 and 1100 px), each at zoom 1 (the static map is the whole world) and at its narrowest
  width. On desktop bands it also counts the
  markers' reviewed offset positions. CSS container queries on `.fs-wmap` then show each name in its
  bands and set `--lu` for that band.

## The country in text

`future_saints.countries` finds each pinned site's country by point in polygon against the same
U.S.-point-of-view countries (`future_saints/data/world_countries.json`, server-side only, about
0.8 MB gzipped). A pin gets a country only when the answer is clear:

- it's inside exactly one country's shape, **and**
- it's at least **1 km** from every other country's shape.

Otherwise it gets no country line, and staff see why on the map page ("outside every country's
shape", "inside two countries' shapes", "on the border of …"). Nothing is guessed.

**Lookup shapes.** Each ring is simplified in runs:
- land borders at 0.003° (about 330 m);
- coasts at 0.03° (about 3.3 km);
- island parts under 0.001 deg² (about 12 km²) are left out unless they're all a country has.

Against the 242 sacred sites in the local catalog, plus the ten control cities, this gives **the
same country as the unsimplified 1:10m shapes for every point**. One coastal site falls just outside
its coast and so gets a staff warning instead.

**Reviewed overrides** (`future_saints/data/pin_country_overrides.json`):
- Each entry names a site by **slug and title**, the country, the date it was reviewed and why.
- An entry is used only when both slug and title match. A slug whose title has changed is ignored,
  and staff see that.
- Overrides are for points the rule can't settle. Everything else follows point in polygon.

| Site (slug) | Country | Why |
|---|---|---|
| St. Peter's Basilica (`st-peters-basilica`) | Vatican City | Its coordinates fall 0.1 km from Natural Earth's simplified Vatican outline. |
| Tomb of St. John Paul II (St. Peter's Basilica) (`tomb-of-st-john-paul-ii`) | Vatican City | The same coordinates as the basilica. |
| St. Peter's Basilica (Tomb of St. Gregory the Great) (`st-peter-s-basilica`) | Vatican City | The same coordinates as the basilica. |
| Tomb of Lazarus (Bethany) (`tomb-of-lazarus`) | Palestine | Bethany (al-Eizariya) is in the West Bank; its coordinates are within 1 km of the line with Israel. |

- **Saints** use their `map_place` site (or single principal site), as for the pin. No place means
  no country line.
- **California missions** stay "California, United States" through the one callout, with no
  separate country line.
- **Marker labels** for screen readers end with the same country ("Church of the Holy Sepulchre,
  Holy Land, Israel").

| Control city | Country |
|---|---|
| Rome, Lanciano | Italy |
| Lourdes | France |
| Fátima | Portugal |
| Mexico City | Mexico |
| Jerusalem | Israel |
| Amsterdam | Netherlands |
| Kraków | Poland |
| Akita | Japan |
| Kibeho | Rwanda |

## Layout and zoom

- **Size.** The map has the full content width, and the story card always sits below it, never
  over it.
  - Desktop (≥ 1024): height `clamp(560px, 70vh, 820px)`.
  - Tablet and phone: height `max(360px, 60vh)`.
  - `.fs-wmap-frame` holds the height, so full screen never moves the page.
- **Fitting.** The box is taller than the world (1000 : 445). The stage keeps the viewBox's shape:
  - with JavaScript, it's fitted and centred in the box;
  - without JavaScript, CSS centres it.

  A sea margin (the ocean texture past the edges) fills the rest. Pins, region shortcuts and
  `?story=` use the same viewBox and Equal Earth projection, unchanged.
- **1×** is the whole world, fitted. "Whole World" returns to it.
- **Under 1024 px** the map opens filling the box's height, centred on 30°N 30°W (the Atlantic), so
  the Americas and Europe both partly show. The reset button and the 0 key return to this view.
- **Full screen.** A 44 px button ("Show the map full screen") sits next to the zoom buttons and
  uses the Fullscreen API. It's hidden where the API isn't available (for example iPhone Safari).
  "Close" and Esc leave, and focus returns to the button.

**Page weight** (the World Discovery Map, first load at 1440, nothing cached, uncompressed, measured
the same way on both builds): **950 KB before, 1,041 KB after** (+91 KB):
- borders: +42 KB (16 KB gzipped);
- the page HTML with the names: +31 KB;
- `future-saints.js`: +9 KB;
- `future-saints.css`: +4 KB.

Zooming past 2.368 px per map unit later loads the 1:50m borders (106 KB, 39 KB gzipped) with the
1:50m land outline. The pin-country shapes (2.4 MB, 0.8 MB gzipped) stay on the server.
