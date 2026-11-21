"""Which country a World Discovery Map pin is in, for the story card and the list ("Country: Italy").

The shapes are Natural Earth's U.S.-point-of-view countries (future_saints/data/world_countries.json,
built by tools/build_world_borders.py from the same source as the map's borders and names), searched
on the server only. A pin gets a country only when the answer is clear:

- inside exactly one country's shape, and
- at least BORDER_KM from every other country's shape.

Otherwise it gets no country and a staff warning: outside every country (in the sea at this
simplification, or a gap), inside two shapes, or on a border. Nothing is ever guessed.

The one exception is a reviewed override (future_saints/data/pin_country_overrides.json): a site,
matched by slug AND title, whose country a person has checked. It is used only on an exact match;
a slug whose title no longer matches is ignored and reported to staff.
See docs/future-saints/map-calibration.md ("Country borders and names").
"""
import json
import math
from functools import lru_cache
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent / "data"
COUNTRIES_FILE = DATA_DIR / "world_countries.json"
OVERRIDES_FILE = DATA_DIR / "pin_country_overrides.json"
BORDER_KM = 1.0
_KM_PER_DEG_LAT = 110.57


@lru_cache(maxsize=1)
def _countries():
    data = json.loads(COUNTRIES_FILE.read_text(encoding="utf-8"))
    out = []
    for c in data["countries"]:
        polys = []
        for poly in c["polygons"]:
            rings = [tuple((p[0], p[1]) for p in ring) for ring in poly]
            xs, ys = [p[0] for p in rings[0]], [p[1] for p in rings[0]]
            polys.append((rings, (min(xs), min(ys), max(xs), max(ys))))
        out.append((c["name"], polys, tuple(c["bbox"])))
    return out


@lru_cache(maxsize=1)
def overrides():
    """{slug: {"site_title", "country", ...}} from the reviewed override file."""
    data = json.loads(OVERRIDES_FILE.read_text(encoding="utf-8"))
    return {o["site_slug"]: o for o in data["overrides"]}


def country_names():
    return {name for name, _, _ in _countries()}


def _inside(x, y, ring):
    c = False
    for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]):
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            c = not c
    return c


def _in_box(x, y, box, margin=0.0):
    return box[0] - margin <= x <= box[2] + margin and box[1] - margin <= y <= box[3] + margin


def _km_to_rings(lat, lng, rings):
    kx = _KM_PER_DEG_LAT * math.cos(math.radians(lat)) * (111.32 / _KM_PER_DEG_LAT)
    best = math.inf
    for ring in rings:
        for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]):
            ax, ay = (x1 - lng) * kx, (y1 - lat) * _KM_PER_DEG_LAT
            bx, by = (x2 - lng) * kx, (y2 - lat) * _KM_PER_DEG_LAT
            dx, dy = bx - ax, by - ay
            t = max(0.0, min(1.0, -(ax * dx + ay * dy) / (dx * dx + dy * dy))) if (dx or dy) else 0.0
            best = min(best, math.hypot(ax + t * dx, ay + t * dy))
    return best


def country_at(lat, lng):
    """(country name, "") or ("", why there is no country)."""
    lat, lng = float(lat), float(lng)
    hits = []
    for name, polys, box in _countries():
        if not _in_box(lng, lat, box):
            continue
        for rings, pbox in polys:
            if _in_box(lng, lat, pbox) and _inside(lng, lat, rings[0]) and not any(_inside(lng, lat, h) for h in rings[1:]):
                hits.append(name)
                break
    if not hits:
        return "", "outside every country's shape"
    if len(hits) > 1:
        return "", f"inside two countries' shapes ({' / '.join(sorted(hits))})"
    found = hits[0]
    margin = BORDER_KM / 50.0        # degrees: generous, only to skip far-away shapes
    for name, polys, box in _countries():
        if name == found or not _in_box(lng, lat, box, margin):
            continue
        for rings, pbox in polys:
            if _in_box(lng, lat, pbox, margin) and _km_to_rings(lat, lng, rings) < BORDER_KM:
                return "", f"on the border of {found} and {name} (within {BORDER_KM:g} km)"
    return found, ""


def site_country(site):
    """(country, warning) for a pinned site: a reviewed override, else country_at. warning is "" when fine."""
    o = overrides().get(site.slug)
    if o is not None:
        if o["site_title"] == site.title:
            return o["country"], ""
        override_note = f"the country override for slug {site.slug!r} names {o['site_title']!r}, not {site.title!r}, so it is ignored; "
    else:
        override_note = ""
    country, why = country_at(site.latitude, site.longitude)
    if country:
        return country, override_note.rstrip("; ") if override_note else ""
    return "", f"{override_note}no country shown: {why}"
