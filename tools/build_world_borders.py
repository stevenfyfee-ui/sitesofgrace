"""Build the World Discovery Map's country borders, country labels and pin-country shapes (run once, by hand).

    python tools/build_world_borders.py path/to/ne_10m_admin_0_countries_usa.geojson

Source (public domain): Natural Earth, Admin 0 - Countries, point of view: United States
(ne_10m_admin_0_countries_usa), version 5.1.2. The U.S. edition exists only at 1:10m, so both border
levels are simplified here from 1:10m with the same Douglas-Peucker routine and tolerances as the land
outline (tools/build_world_outline.py): 0.4 viewBox units for the 1x level, 0.12 for the zoom level.
https://www.naturalearthdata.com/downloads/10m-cultural-vectors/10m-admin-0-countries/
(GeoJSON copy: https://raw.githubusercontent.com/nvkelso/natural-earth-vector/v5.1.2/geojson/ne_10m_admin_0_countries_usa.geojson).
"All versions of Natural Earth raster + vector map data found on this website are in the public domain."
https://www.naturalearthdata.com/about/terms-of-use/

What it does (no border is drawn or moved by hand):
- Folds every "Breakaway" and "Lease" feature into the feature of its sovereign (SOV_A3), and the UK
  sovereign base areas (Akrotiri, Dhekelia) into Cyprus (FOLD_INTO, reviewed): no line where both sides
  are folded together, and no label for the folded piece.
- Borders: every edge two different countries share, chained between junctions, each drawn ONCE
  (no doubled lines), projected with future_saints.geo.world_viewbox, simplified per chain (junctions
  stay put, so chains still meet), with any segment repeated after simplifying dropped.
  The map clips them to the land outline, so they never run into the sea.
- Labels: one per country (each sovereign state's home part, plus Kosovo, Taiwan, Palestine,
  Western Sahara and Greenland) at Natural Earth's LABEL_X/LABEL_Y, with the English name (NAME_EN,
  with the five reviewed plain names in PLAIN_NAMES), the font size (13 px for LABELRANK <= 2, else 11)
  and when it may show: rank_zoom (the zoom its rank allows) and fit_scale (the scale at which it
  fits; see label_thresholds).
- Pin countries: the same countries, lightly simplified in latitude/longitude (LOOKUP_TOLERANCE_DEG),
  for future_saints.countries (server-side only; never sent to the browser).

Writes:
- sitesofgrace/static/future_saints/svg/world-borders.svg       (<path id="fs-world-borders">, 1x)
- sitesofgrace/static/future_saints/svg/world-borders-50m.svg   (the same id, loaded past 2x)
- future_saints/data/world_labels.json
- future_saints/data/world_countries.json

Standard library only. Calibration notes: docs/future-saints/map-calibration.md ("Country borders and names").
"""
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from build_world_outline import simplify  # noqa: E402
from future_saints.geo import WORLD_TRIM_LAT, WORLD_VIEWBOX, world_viewbox  # noqa: E402

SOURCE = {
    "publisher": "Natural Earth",
    "title": "Admin 0 - Countries, point of view: United States (ne_10m_admin_0_countries_usa), version 5.1.2",
    "url": "https://www.naturalearthdata.com/downloads/10m-cultural-vectors/10m-admin-0-countries/",
    "licence": "Public domain (Natural Earth terms of use)",
}
TOLERANCE = 0.4            # the 1x borders, as the 1:110m land outline
DETAIL_TOLERANCE = 0.12    # the zoom borders, as the 1:50m land outline
LOOKUP_TOLERANCE_DEG = 0.003        # pin-country shapes, land borders: about 330 m at the equator
LOOKUP_COAST_TOLERANCE_DEG = 0.03   # pin-country shapes, coasts: about 3.3 km (a pin that falls outside is warned about)
LOOKUP_MIN_PART_DEG2 = 0.001        # pin-country shapes: island parts smaller than this (about 12 km²) are left out,
                                    # unless they are all the country has
FOLD_TYPES = {"Breakaway", "Lease"}
# Reviewed 2026-11-20: Akrotiri and Dhekelia (UK sovereign base areas) are folded into Cyprus, not by SOV_A3
# (which would give the United Kingdom and leave a small line around each base).
FOLD_INTO = {"WSB": "CYP", "ESB": "CYP"}
LABEL_TYPES = {"Sovereign country", "Sovereignty", "Country", "Disputed", "Indeterminate"}
LABEL_ALSO = {"KOS", "TWN", "PSX", "SAH", "GRL"}
# Indeterminate reef and island features that are not countries (no label, no pin country):
# Scarborough Shoal, and the Spratly Islands feature whose NAME_EN reads "Wake Island".
NOT_COUNTRIES = {"SCR", "PGA"}
PLAIN_NAMES = {   # reviewed 2026-11-20 (step 0d): Natural Earth NAME_EN -> the plain name shown
    "United States of America": "United States",
    "People's Republic of China": "China",
    "The Gambia": "Gambia",
    "The Bahamas": "Bahamas",
    "Federated States of Micronesia": "Micronesia",
}
DESKTOP_1X_SCALE = 1.184   # px per viewBox unit: the whole world on the 1440 map (1184 px wide)
CHAR_EM = 0.58             # Future Saints Serif (Lora): a generous average advance, for the fit test
FIT_SLACK = 1.15           # a label may run this much wider than its country's main part


def parts(feature):
    g = feature["geometry"]
    return g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]


def key(p):
    return (round(p[0], 7), round(p[1], 7))


def fold_map(features):
    """ADM0_A3 -> the code its shapes are drawn and looked up under."""
    by_sov = {}
    for f in features:
        p = f["properties"]
        if p["TYPE"] not in FOLD_TYPES and p["ADM0_A3"] not in FOLD_INTO and p["HOMEPART"] == 1:
            by_sov.setdefault(p["SOV_A3"], p["ADM0_A3"])
    out = {}
    for f in features:
        p = f["properties"]
        if p["ADM0_A3"] in FOLD_INTO:
            out[p["ADM0_A3"]] = FOLD_INTO[p["ADM0_A3"]]
        elif p["TYPE"] in FOLD_TYPES:
            out[p["ADM0_A3"]] = by_sov[p["SOV_A3"]]
        else:
            out[p["ADM0_A3"]] = p["ADM0_A3"]
    return out


def border_chains(features, code_of):
    edges = defaultdict(set)
    for f in features:
        code = code_of[f["properties"]["ADM0_A3"]]
        for part in parts(f):
            for ring in part:
                pts = [key(q) for q in ring]
                for a, b in zip(pts, pts[1:]):
                    if a != b:
                        edges[frozenset((a, b))].add(code)
    inner = [tuple(e) for e, codes in edges.items() if len(codes) >= 2]
    adj = defaultdict(list)
    for a, b in inner:
        adj[a].append(b)
        adj[b].append(a)
    used, chains = set(), []

    def walk(start, nxt):
        chain, prev, cur = [start, nxt], start, nxt
        used.add(frozenset((start, nxt)))
        while len(adj[cur]) == 2:
            n = adj[cur][0] if adj[cur][1] == prev else adj[cur][1]
            e = frozenset((cur, n))
            if e in used:
                break
            used.add(e)
            chain.append(n)
            prev, cur = cur, n
        return chain

    for starts_at_junction in (True, False):      # junction-to-junction first, then closed loops
        for node in list(adj):
            if starts_at_junction and len(adj[node]) == 2:
                continue
            for n in adj[node]:
                if frozenset((node, n)) not in used:
                    chains.append(walk(node, n))
    return chains


def project_chains(chains, tolerance):
    out, seen = [], set()
    for chain in chains:
        pts = [world_viewbox(lat, lng) for lng, lat in chain]
        pts = [(round(x, 2), round(y, 2)) for x, y in simplify(pts, tolerance)]
        # Drop a segment that another chain already drew (two short chains between the same
        # junctions can simplify to the same straight line); split the chain there.
        run = [pts[0]]
        for a, b in zip(pts, pts[1:]):
            seg = frozenset((a, b))
            if a == b or seg in seen:
                if len(run) >= 2:
                    out.append(run)
                run = [b]
                continue
            seen.add(seg)
            run.append(b)
        if len(run) >= 2:
            out.append(run)
    return out


def path_d(chains):
    return " ".join("M" + " L".join(f"{x:g},{y:g}" for x, y in c) for c in chains)


def write_svg(name, chains, tolerance):
    svg = ROOT / "sitesofgrace" / "static" / "future_saints" / "svg" / name
    svg.write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{WORLD_VIEWBOX}">\n'
        f"<!-- Future Saints World Discovery Map country borders (shared boundaries, each drawn once). "
        f"{SOURCE['title']}; {SOURCE['licence']}. Equal Earth; simplified at {tolerance:g} units. "
        f"Built by tools/build_world_borders.py. -->\n"
        f'<defs><path id="fs-world-borders" d="{path_d(chains)}"/></defs>\n</svg>\n',
        encoding="utf-8", newline="\n")
    print(f"wrote {svg.relative_to(ROOT)}: {len(chains)} chains, {sum(len(c) for c in chains)} points, "
          f"{svg.stat().st_size} bytes")


def ring_area(ring):
    return abs(sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]))) / 2


def inside(x, y, ring):
    c = False
    for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]):
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            c = not c
    return c


def label_thresholds(p, name, px, main_ring):
    """(rank_zoom, fit_scale): when this label may show. Both come from Natural Earth's data.

    - rank_zoom: the map's zoom (1 = the whole world) at which the country's rank lets it show: its
      MIN_LABEL (a web-map zoom), one step earlier than Natural Earth, with 1x taken as the 1440 map
      (about web zoom 2.2). So at 1x only large countries; more as you zoom in, on every screen.
    - fit_scale: the map scale (px per map unit, the screen's size included) at which the name fits
      across the country's main part and its height. None when it never fits by 6x on the 1440 map
      (Vatican City, Monaco, ...): such a name may show only at the largest zoom.
    The map's collision rules still apply on top.
    """
    rank_zoom = max(1.0, 256 * 2 ** (p["MIN_LABEL"] - 1) / 1000 / DESKTOP_1X_SCALE)
    xs, ys = [q[0] for q in main_ring], [q[1] for q in main_ring]
    w, h = max(xs) - min(xs), max(ys) - min(ys)
    fit = max(len(name) * CHAR_EM * px / (w * FIT_SLACK), px * 1.1 / (h * 1.4))
    return round(rank_zoom, 3), (round(fit, 3) if fit <= DESKTOP_1X_SCALE * 6 else None)


def main(path):
    features = json.loads(Path(path).read_text(encoding="utf-8"))["features"]
    code_of = fold_map(features)
    chains = border_chains(features, code_of)
    write_svg("world-borders.svg", project_chains(chains, TOLERANCE), TOLERANCE)
    write_svg("world-borders-50m.svg", project_chains(chains, DETAIL_TOLERANCE), DETAIL_TOLERANCE)

    # Labels.
    labels, left_out = [], []
    for f in features:
        p = f["properties"]
        a3 = p["ADM0_A3"]
        if a3 in NOT_COUNTRIES or code_of[a3] != a3 or not ((p["HOMEPART"] == 1 and p["TYPE"] in LABEL_TYPES) or a3 in LABEL_ALSO):
            left_out.append(p["NAME_EN"])
            continue
        if p["LABEL_Y"] < WORLD_TRIM_LAT:
            continue
        name = PLAIN_NAMES.get(p["NAME_EN"], p["NAME_EN"])
        px = 13 if p["LABELRANK"] <= 2 else 11
        main_ring = None
        for part in parts(f):
            if inside(p["LABEL_X"], p["LABEL_Y"], part[0]):
                main_ring = part[0]
                break
        if main_ring is None:
            main_ring = max((part[0] for part in parts(f)), key=ring_area)
        x, y = world_viewbox(p["LABEL_Y"], p["LABEL_X"])
        main_vb = [world_viewbox(lat, lng) for lng, lat in main_ring]
        iso = p["ISO_A2_EH"] if p["ISO_A2_EH"] not in ("-99", None) else a3
        rank_zoom, fit_scale = label_thresholds(p, name, px, main_vb)
        labels.append({"iso": iso, "a3": a3, "name": name, "ne_name": p["NAME_EN"], "x": round(x, 2), "y": round(y, 2),
                       "px": px, "rank_zoom": rank_zoom, "fit_scale": fit_scale, "labelrank": p["LABELRANK"],
                       "ne_min_label": p["MIN_LABEL"]})
    # The placement order (largest countries first): the earliest to show, then 13px before 11px.
    labels.sort(key=lambda r: (max(r["rank_zoom"] * DESKTOP_1X_SCALE, r["fit_scale"] if r["fit_scale"] is not None else 99),
                               -r["px"], r["name"]))
    out = {"source": SOURCE, "projection": "Equal Earth via future_saints.geo.world_viewbox", "viewBox": WORLD_VIEWBOX,
           "desktop_1x_scale": DESKTOP_1X_SCALE, "plain_names": PLAIN_NAMES, "labels": labels}
    target = ROOT / "future_saints" / "data" / "world_labels.json"
    target.write_text(json.dumps(out, ensure_ascii=False, indent=0) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {target.relative_to(ROOT)}: {len(labels)} labels; left out {len(left_out)}")

    # Pin-country shapes (latitude/longitude), grouped by the folded code. Each ring is simplified in
    # runs: land borders (edges another country shares) at LOOKUP_TOLERANCE_DEG, coasts at
    # LOOKUP_COAST_TOLERANCE_DEG; run ends stay put. A ring that would collapse keeps every point.
    shared = set()
    owners = defaultdict(set)
    for f in features:
        code = code_of[f["properties"]["ADM0_A3"]]
        for part in parts(f):
            for ring in part:
                pts = [key(q) for q in ring]
                for a, b in zip(pts, pts[1:]):
                    owners[frozenset((a, b))].add(code)
    shared = {e for e, codes in owners.items() if len(codes) >= 2}
    names = {lab["a3"]: lab["name"] for lab in labels}
    shapes = defaultdict(list)
    for f in features:
        p = f["properties"]
        code = code_of[p["ADM0_A3"]]
        if code not in names:
            continue
        for part in parts(f):
            rings = []
            for ring in part:
                pts = [key(q) for q in ring]
                runs, run, kind = [], [pts[0]], None
                for a, b in zip(pts, pts[1:]):
                    k = frozenset((a, b)) in shared
                    if kind is not None and k != kind:
                        runs.append((kind, run))
                        run = [a]
                    kind = k
                    run.append(b)
                runs.append((kind, run))
                out = []
                for k, r in runs:
                    s = simplify(r, LOOKUP_TOLERANCE_DEG if k else LOOKUP_COAST_TOLERANCE_DEG) if len(r) > 2 else r
                    out.extend(s if not out else s[1:])
                if len(out) < 4:
                    out = pts
                rings.append([[round(a, 3), round(b, 3)] for a, b in out])
            shapes[code].append(rings)
    shapes = {code: ([poly for poly in polys if ring_area(poly[0]) >= LOOKUP_MIN_PART_DEG2] or polys)
              for code, polys in shapes.items()}
    countries = []
    for code, polys in sorted(shapes.items()):
        allpts = [q for poly in polys for q in poly[0]]
        countries.append({"a3": code, "name": names[code], "polygons": polys,
                          "bbox": [min(q[0] for q in allpts), min(q[1] for q in allpts),
                                   max(q[0] for q in allpts), max(q[1] for q in allpts)]})
    out = {"source": SOURCE, "coordinates": "longitude, latitude (degrees)",
           "tolerance_degrees": {"land_borders": LOOKUP_TOLERANCE_DEG, "coasts": LOOKUP_COAST_TOLERANCE_DEG},
           "min_island_part_deg2": LOOKUP_MIN_PART_DEG2, "folded": sorted(k for k, v in code_of.items() if k != v),
           "countries": countries}
    target = ROOT / "future_saints" / "data" / "world_countries.json"
    target.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {target.relative_to(ROOT)}: {len(countries)} countries, {target.stat().st_size} bytes")


if __name__ == "__main__":
    main(sys.argv[1])
