"""Build the world land outline for the Future Saints World Discovery Map (run once, by hand).

    python tools/build_world_outline.py path/to/ne_110m_land.geojson

Source (public domain): Natural Earth, 1:110m Physical Vectors, Land, version 5.1.2
https://www.naturalearthdata.com/downloads/110m-physical-vectors/110m-land/
(GeoJSON copy: https://raw.githubusercontent.com/nvkelso/natural-earth-vector/v5.1.2/geojson/ne_110m_land.geojson).
"All versions of Natural Earth raster + vector map data found on this website are in the
public domain." https://www.naturalearthdata.com/about/terms-of-use/

Projects every vertex with future_saints.geo.world_viewbox (Equal Earth) -- the same function
the map uses for its pins -- leaves out land wholly south of 60°S (Antarctica), simplifies each
ring with Douglas-Peucker at TOLERANCE viewBox units, drops islands smaller than MIN_AREA, and
writes:

- future_saints/data/world_outline.json             (rings + holes, for the tests and staff checks)
- sitesofgrace/static/future_saints/svg/world-outline.svg   (one <path id="fs-world-land">; both the
  World Discovery Map and the homepage preview <use> it, so browsers cache it once)

Standard library only. Calibration notes: docs/future-saints/map-calibration.md (world section).
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from future_saints.geo import WORLD_TRIM_LAT, WORLD_VIEWBOX, world_viewbox  # noqa: E402

SOURCE = {
    "publisher": "Natural Earth",
    "title": "1:110m Physical Vectors, Land (ne_110m_land), version 5.1.2",
    "url": "https://www.naturalearthdata.com/downloads/110m-physical-vectors/110m-land/",
    "licence": "Public domain (Natural Earth terms of use)",
}
TOLERANCE = 0.4          # viewBox units (1 unit is about 40 km at the equator)
MIN_AREA = 2.0           # square viewBox units


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


def project(ring):
    return [(round(x, 2), round(y, 2)) for x, y in simplify([world_viewbox(lat, lng) for lng, lat in ring], TOLERANCE)]


def main(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    polygons, trimmed = [], 0
    for feature in data["features"]:
        geometry = feature["geometry"]
        parts = geometry["coordinates"] if geometry["type"] == "MultiPolygon" else [geometry["coordinates"]]
        for part in parts:
            outer = part[0]
            if max(lat for _, lat in outer) < WORLD_TRIM_LAT:
                trimmed += 1
                continue
            ring = project(outer)
            if area(ring) < MIN_AREA:
                continue
            holes = [h for h in (project(r) for r in part[1:]) if area(h) >= MIN_AREA]
            polygons.append({"outer": ring, "holes": holes})
    polygons.sort(key=lambda p: area(p["outer"]), reverse=True)
    path_d = " ".join("M" + " L".join(f"{x:g},{y:g}" for x, y in r[:-1]) + " Z"
                      for p in polygons for r in [p["outer"], *p["holes"]])
    out = {"source": SOURCE, "projection": "Equal Earth via future_saints.geo.world_viewbox", "viewBox": WORLD_VIEWBOX,
           "trimmed_south_of": WORLD_TRIM_LAT, "tolerance_units": TOLERANCE, "min_area_units": MIN_AREA, "polygons": polygons}
    data_file = ROOT / "future_saints" / "data" / "world_outline.json"
    data_file.write_text(json.dumps(out, separators=(",", ":")) + "\n", encoding="utf-8", newline="\n")
    svg = ROOT / "sitesofgrace" / "static" / "future_saints" / "svg" / "world-outline.svg"
    svg.write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{WORLD_VIEWBOX}">\n'
        f"<!-- Future Saints World Discovery Map land outline. {SOURCE['title']}; {SOURCE['licence']}. "
        f"Equal Earth; land wholly south of {WORLD_TRIM_LAT:g}° (Antarctica) left out. Built by tools/build_world_outline.py. -->\n"
        f'<defs><path id="fs-world-land" fill-rule="evenodd" d="{path_d}"/></defs>\n</svg>\n',
        encoding="utf-8", newline="\n",
    )
    points = sum(len(p["outer"]) + sum(len(h) for h in p["holes"]) for p in polygons)
    print(f"{len(polygons)} polygon(s), {sum(len(p['holes']) for p in polygons)} hole(s), {points} points; "
          f"{trimmed} trimmed south of {WORLD_TRIM_LAT:g}°; wrote {data_file.relative_to(ROOT)} and "
          f"{svg.relative_to(ROOT)} ({svg.stat().st_size} bytes)")


if __name__ == "__main__":
    main(sys.argv[1])
