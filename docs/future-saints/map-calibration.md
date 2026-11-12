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
- `MissionHubEntry.map_offset_x/y` only nudge a pin's number label. They never move the pin.

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
- The compass rose and the scroll don't touch land.
- The border control points match the outline's extremes.
- The `albers()` reference values match PROJ.
