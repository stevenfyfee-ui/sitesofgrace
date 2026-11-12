"""Build the California outline for the Future Saints missions map (run once, by hand).

    python tools/build_california_outline.py path/to/cb_2023_us_state_500k.zip

Source (public domain, US government work): US Census Bureau, 2023 Cartographic
Boundary File, States, 1:500,000, KML:
https://www2.census.gov/geo/tiger/GENZ2023/kml/cb_2023_us_state_500k.zip

Reads California's polygons (the mainland plus islands larger than MIN_AREA),
projects every vertex with future_saints.geo.to_viewbox -- the same function
the hub uses for the pins -- simplifies each ring with Douglas-Peucker at
TOLERANCE viewBox units, and writes:

- future_saints/data/california_outline.json  (rings + the SVG path, used by the hub and the tests)
- docs/future-saints/map-art-template.svg      (outline + viewBox only, for an illustrator)

Standard library only. Calibration notes: docs/future-saints/map-calibration.md.
"""
import json
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from future_saints.geo import VIEWBOX, to_viewbox  # noqa: E402

SOURCE = {
    "publisher": "US Census Bureau",
    "title": "2023 Cartographic Boundary File, States, 1:500,000 (cb_2023_us_state_500k, KML)",
    "url": "https://www2.census.gov/geo/tiger/GENZ2023/kml/cb_2023_us_state_500k.zip",
    "licence": "Public domain (US government work)",
}
TOLERANCE = 0.2          # viewBox units (1 unit = 1.1 km), so about 220 m
MIN_AREA = 4.0           # square viewBox units: keeps the Channel Islands, drops rocks
KML = "{http://www.opengis.net/kml/2.2}"
# The Pacific beyond California's own coast, only to close the ocean shape at the map's
# edges (decorative; never used for pins): approximate coast points north into Oregon and
# south into Baja California (lat, lng), named for the calibration notes.
OREGON_COAST = [("Brookings, OR", 42.05, -124.28), ("Cape Ferrelo, OR", 42.10, -124.35)]
BAJA_COAST = [("Rosarito, BC", 32.36, -117.06), ("Ensenada, BC", 31.86, -116.63), ("Punta Banda, BC", 31.75, -116.75)]


def california_rings(zip_path):
    with zipfile.ZipFile(zip_path) as zf:
        name = next(n for n in zf.namelist() if n.endswith(".kml"))
        root = ElementTree.fromstring(zf.read(name))
    for placemark in root.iter(f"{KML}Placemark"):
        fields = {d.get("name"): (d.text or "") for d in placemark.iter(f"{KML}SimpleData")}
        if fields.get("STATEFP") != "06":
            continue
        rings = []
        for outer in placemark.iter(f"{KML}outerBoundaryIs"):
            coords = outer.find(f".//{KML}coordinates").text.split()
            rings.append([tuple(float(v) for v in c.split(",")[:2]) for c in coords])  # (lng, lat)
        return rings
    raise SystemExit("California (STATEFP 06) not found in the file")


def area(ring):
    return abs(sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]))) / 2


def simplify(points, tolerance):
    """Douglas-Peucker, iterative."""
    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]
    while stack:
        first, last = stack.pop()
        (x1, y1), (x2, y2) = points[first], points[last]
        dx, dy = x2 - x1, y2 - y1
        length = (dx * dx + dy * dy) ** 0.5
        worst, index = 0.0, None
        for i in range(first + 1, last):
            px, py = points[i]
            d = abs(dy * px - dx * py + x2 * y1 - y2 * x1) / length if length else ((px - x1) ** 2 + (py - y1) ** 2) ** 0.5
            if d > worst:
                worst, index = d, i
        if index is not None and worst > tolerance:
            keep[index] = True
            stack += [(first, index), (index, last)]
    return [p for p, k in zip(points, keep) if k]


def ocean_ring(mainland):
    """The Pacific as one ring: California's coast from the Oregon border (the mainland's
    northernmost vertex) south to the Mexico border at the sea (its southernmost vertex),
    then the neighbour coast points and the map's west and south edges. Everything else
    outside California is land (Oregon, Nevada, Arizona, Mexico) and is drawn as such."""
    from future_saints.geo import VIEWBOX_HEIGHT

    ring = mainland[:-1] if mainland[0] == mainland[-1] else mainland
    north = min(range(len(ring)), key=lambda i: ring[i][1])
    south = max(range(len(ring)), key=lambda i: ring[i][1])
    coast = (ring[north:] + ring[:south + 1]) if north > south else ring[north:south + 1]
    if sum(x for x, _ in coast) / len(coast) > sum(x for x, _ in ring) / len(ring):
        coast = (ring[south:] + ring[:north + 1])[::-1]          # took the inland side; flip
    oregon = [to_viewbox(lat, lng) for _, lat, lng in reversed(OREGON_COAST)]
    baja = [to_viewbox(lat, lng) for _, lat, lng in BAJA_COAST]
    top = (oregon[0][0] - oregon[0][1] * (oregon[1][0] - oregon[0][0]) / (oregon[1][1] - oregon[0][1]), 0)
    bottom = (baja[-1][0], VIEWBOX_HEIGHT)
    points = [(0, 0), top, *oregon, *coast, *baja, bottom, (0, VIEWBOX_HEIGHT)]
    return [(round(x, 2), round(y, 2)) for x, y in points]


def main(zip_path):
    rings = []
    for ring in california_rings(zip_path):
        projected = [to_viewbox(lat, lng) for lng, lat in ring]
        if area(projected) < MIN_AREA:
            continue
        simple = simplify(projected, TOLERANCE)
        rings.append([(round(x, 2), round(y, 2)) for x, y in simple])
    rings.sort(key=area, reverse=True)          # the mainland first
    path = " ".join("M" + " L".join(f"{x:g},{y:g}" for x, y in r[:-1]) + " Z" for r in rings)
    ocean = ocean_ring(rings[0])
    out = {
        "source": SOURCE,
        "projection": "EPSG:3310 California Albers via future_saints.geo.to_viewbox",
        "viewBox": VIEWBOX,
        "tolerance_units": TOLERANCE,
        "min_island_area_units": MIN_AREA,
        "rings": rings,
        "path": path,
        "ocean": ocean,
        "ocean_path": "M" + " L".join(f"{x:g},{y:g}" for x, y in ocean) + " Z",
        "neighbour_coast": [name for name, _, _ in OREGON_COAST + BAJA_COAST],
    }
    data = ROOT / "future_saints" / "data" / "california_outline.json"
    data.parent.mkdir(exist_ok=True)
    data.write_text(json.dumps(out, separators=(",", ":")) + "\n", encoding="utf-8", newline="\n")
    template = ROOT / "docs" / "future-saints" / "map-art-template.svg"
    template.write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{VIEWBOX}" width="1000" height="1100">\n'
        f"  <!-- California outline for the Future Saints missions map. {SOURCE['title']}; "
        f"{SOURCE['licence']}. Paint the basemap under this outline; keep the viewBox. -->\n"
        f'  <rect width="100%" height="100%" fill="#ffffff"/>\n'
        f'  <path d="{path}" fill="none" stroke="#000000" stroke-width="1"/>\n</svg>\n',
        encoding="utf-8", newline="\n",
    )
    points = sum(len(r) for r in rings)
    print(f"{len(rings)} ring(s), {points} points; mainland {len(rings[0])} points; "
          f"wrote {data.relative_to(ROOT)} ({data.stat().st_size} bytes) and {template.relative_to(ROOT)}")
    xs = [x for r in rings for x, _ in r]
    ys = [y for r in rings for _, y in r]
    print(f"bounds: x {min(xs):.1f}..{max(xs):.1f}, y {min(ys):.1f}..{max(ys):.1f} (viewBox {VIEWBOX})")


if __name__ == "__main__":
    main(sys.argv[1])
