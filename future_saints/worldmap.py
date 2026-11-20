"""Future Saints Phase 4: the World Discovery Map (brief §8).

Only PUBLISHED learning pages appear, and only they link anywhere.

Where each story's pin goes (never guessed):
- Marian apparitions, Eucharistic miracles, Holy Land: the canonical SacredSitePage's
  latitude/longitude. Without coordinates there's no pin (list only; staff see a warning).
- Saints: SaintLearningPage.map_place if set (a live sacred site connected to the saint);
  otherwise the saint's single live principal site (SacredSitePage.associated_saint, i.e.
  SaintPage.sites). None, or two or more, means list only, and staff see the saint in the
  "needs a map place" list. The card says "A place connected to {saint}: {site}".
- California missions: ONE callout on California with the number of published mission
  pages; its card links to the missions hub. Never 21 dots.

Pins go through future_saints.geo.world_viewbox (Equal Earth), the same function that drew
the outline (sitesofgrace/static/future_saints/svg/world-outline.svg). Where markers would
overlap on the desktop map, a reviewed offset (WORLD_MARKER_OFFSETS) moves the marker and a
thin line anchors it to its true spot; staff see any remaining overlap.

Countries (future_saints.countries): each pinned site's country comes from Natural Earth's
U.S.-point-of-view shapes (point in polygon, never guessed; a reviewed override file for the
rare exception). It shows in the card and the list as "Country: Italy". Borders and English
country names are drawn on the map from the same source (tools/build_world_borders.py);
the names are decorative (aria-hidden), placed so they never cover a pin.
"""
import json
from functools import lru_cache
from pathlib import Path

from django.db import models
from wagtail.admin.panels import FieldPanel
from wagtail.models import Page

from .countries import site_country
from .geo import WORLD_VIEWBOX, WORLD_VIEWBOX_HEIGHT, WORLD_VIEWBOX_WIDTH, point_in_polygon, world_viewbox
from .models import FutureSaintsGateMixin

OUTLINE_FILE = Path(__file__).resolve().parent / "data" / "world_outline.json"
LABELS_FILE = Path(__file__).resolve().parent / "data" / "world_labels.json"

# (content_kind, filter label, type label on cards and markers, sprite icon), in nav order.
KINDS = [
    ("saint", "Saints", "Saint", "saint"),
    ("marian_apparition", "Marian Apparitions", "Marian apparition", "star"),
    ("eucharistic_miracle", "Eucharistic Miracles", "Eucharistic miracle", "chalice"),
    ("holy_land", "Holy Land", "Holy Land", "scroll"),
    ("california_mission", "California Missions", "California mission", "bell"),
]
KIND_LABELS = {k: label for k, _, label, _ in KINDS}
SITE_KINDS = {"marian_apparition", "eucharistic_miracle", "holy_land"}
CALLOUT_KEY = "california-missions"
CALIFORNIA = (37.2, -119.6)               # the callout's spot: central California
MARKER_PX = 34                            # the drawn marker disc (CSS .fs-wm-disc)
CARD_ART_SPEC = "fill-800x600"            # the story card's picture (_art_frame.html, variant "thumb")
DESKTOP_MAP_PX = 1184.0                   # the whole world's width on the 1440 map (full content width, card below)
DESKTOP_1X_SCALE = DESKTOP_MAP_PX / WORLD_VIEWBOX_WIDTH   # px per map unit there: the labels' and detail's reference
DETAIL_SCALE = 2 * DESKTOP_1X_SCALE      # past this scale both the land outline and the borders swap to the finer level
HOME_CENTER = (30.0, -30.0)              # phones and tablets open on the Atlantic, filling the map's height
# No-JavaScript country names: the map's width decides its scale, so each label carries the width
# bands it shows in (CSS container queries), placed at each band's narrowest width (the most crowded).
LABEL_BANDS = [("a", 320), ("b", 450), ("c", 700), ("d", 900), ("e", 1100)]
PIN_HIT_PX = 44                          # a marker's button (CSS .fs-wm-pin)
LABEL_CHAR_EM = 0.58                     # Future Saints Serif: a generous average advance (no-JS estimate only)
LABEL_PAD_PX = 2
COMPASS_BOX = (28.0, 304.0, 112.0, 412.0)   # the compass rose and its N, in map units (translate(70 370) scale(.8))
# Reviewed offsets (CSS px, desktop >= 1024 only) for markers that would overlap at 1440.
# Keyed by the place a marker sits on (the sacred site's exact title, or the callout's key),
# so an offset stays with its spot whatever page links there. A thin line and a dot anchor
# each moved marker to its true spot. The smallest offsets that clear every marker.
WORLD_MARKER_OFFSETS = {
    "Our Lady of Lourdes": (-16, 0),
    "Shrine of St. Carlo Acutis (Assisi)": (0, -8),
    "Eucharistic Miracle of Lanciano": (0, 28),
}


# Decorative pieces on the world map: ONLY in open ocean (never on land, so nothing can be read
# as a place), clear of every marker and the compass at all six widths (test_world_map).
# (file, lat, lng, width in map units, height/width)
WORLD_ART = [
    ("sailing-ship.png", 27.0, -45.0, 60, 1.0),     # the mid-Atlantic
    ("whale-waves.png", -12.0, -128.0, 64, 0.6),    # the South Pacific
]
WORLD_TEXTURE_TILE = 250          # map units per texture tile (1254 px), mirrored 2 x 2
WORLD_ZOOM_MAX = 6
# Zoom shortcuts: (key, label, (south, north), (west, east)); each box is its projected bounds.
REGIONS = [
    ("europe", "Europe", (35.0, 59.0), (-11.0, 31.0)),
    ("holy-land", "Holy Land", (30.5, 33.6), (34.0, 36.2)),
    ("americas", "The Americas", (-56.0, 60.0), (-168.0, -34.0)),
]


def region_box(south_north, west_east, steps=24):
    """(x1, y1, x2, y2) in viewBox units: the projected bounds of a latitude/longitude box."""
    (s, n), (w, e) = south_north, west_east
    pts = []
    for i in range(steps + 1):
        t = i / steps
        lat, lng = s + (n - s) * t, w + (e - w) * t
        pts += [world_viewbox(lat, w), world_viewbox(lat, e), world_viewbox(s, lng), world_viewbox(n, lng)]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


def world_regions():
    return [{"key": key, "label": label, "box": ",".join(f"{v:.1f}" for v in region_box(sn, we))}
            for key, label, sn, we in REGIONS]


def world_art():
    out = []
    for file, lat, lng, width, aspect in WORLD_ART:
        cx, cy = world_viewbox(lat, lng)
        out.append({"file": file, "x": round(cx - width / 2, 1), "y": round(cy - width * aspect / 2, 1),
                    "w": width, "h": round(width * aspect, 1)})
    return out


def art_context():
    """What _world_art.html needs (the map page and the homepage preview)."""
    return {"fs_world_art": world_art(), "fs_texture_tile": WORLD_TEXTURE_TILE, "fs_texture_tile2": WORLD_TEXTURE_TILE * 2}


@lru_cache(maxsize=1)
def world_outline():
    return json.loads(OUTLINE_FILE.read_text(encoding="utf-8"))


def on_land(x, y):
    return any(point_in_polygon(x, y, p["outer"]) and not any(point_in_polygon(x, y, h) for h in p["holes"])
               for p in world_outline()["polygons"])


@lru_cache(maxsize=1)
def label_data():
    """The country names (tools/build_world_borders.py), in placement order: largest countries first."""
    return json.loads(LABELS_FILE.read_text(encoding="utf-8"))["labels"]


def label_obstacles():
    """Boxes (map units) no country name may touch: the compass rose and the ocean art."""
    return [COMPASS_BOX] + [(a["x"], a["y"], a["x"] + a["w"], a["y"] + a["h"]) for a in world_art()]


def label_box(label, scale, pad_px=LABEL_PAD_PX):
    """A label's box in map units at `scale` px per unit (centred on its point; estimated width)."""
    w = (len(label["name"]) * LABEL_CHAR_EM * label["px"] + 2 * pad_px) / scale
    h = (label["px"] * 1.3 + 2 * pad_px) / scale
    return (label["x"] - w / 2, label["y"] - h / 2, label["x"] + w / 2, label["y"] + h / 2)


def _touch(a, b):
    return not (a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1])


def label_may_show(label, zoom, scale):
    """Its rank allows it at this zoom (1 = the whole world) and the name fits at this scale (px per unit)."""
    return label["fit_scale"] is not None and label["rank_zoom"] <= zoom + 1e-6 and label["fit_scale"] <= scale + 1e-6


def place_labels(labels, items, scale, offsets=False, zoom=1.0):
    """The labels that may show at `scale` and `zoom`, greedily in order: pins always win, then the
    art, then earlier labels. `offsets` adds each marker's reviewed desktop offset position as well."""
    half = PIN_HIT_PX / 2 / scale
    taken = list(label_obstacles())
    for i in items:
        if not i["pinned"]:
            continue
        spots = [(i["x"], i["y"])] + ([(i["x"] + i["dx"] / scale, i["y"] + i["dy"] / scale)] if offsets else [])
        taken += [(x - half, y - half, x + half, y + half) for x, y in spots]
    shown = []
    for lab in labels:
        if not label_may_show(lab, zoom, scale):
            continue
        box = label_box(lab, scale)
        if box[0] < 0 or box[1] < 0 or box[2] > WORLD_VIEWBOX_WIDTH or box[3] > WORLD_VIEWBOX_HEIGHT:
            continue
        if any(_touch(box, t) for t in taken):
            continue
        taken.append(box)
        shown.append(lab)
    return shown


def world_labels(items):
    """Every label for the template, each with the no-JavaScript width bands it shows in (the static
    map is the whole world, so zoom 1, at the band's narrowest width)."""
    labels = label_data()
    bands = {lab["iso"]: [] for lab in labels}
    for band, width in LABEL_BANDS:
        for lab in place_labels(labels, items, width / WORLD_VIEWBOX_WIDTH, offsets=width >= 900):
            bands[lab["iso"]].append(band)
    return [{**lab, "bands": " ".join(f"is-{b}" for b in bands[lab["iso"]])} for lab in labels]


class WorldMapPage(FutureSaintsGateMixin, Page):
    subtitle = models.CharField(max_length=200, blank=True, help_text="One line under the title.")
    intro = models.TextField(max_length=800, blank=True, help_text="A short introduction above the map.")

    parent_page_types = ["future_saints.FutureSaintsHomePage"]
    subpage_types = []
    max_count = 1

    content_panels = Page.content_panels + [FieldPanel("subtitle"), FieldPanel("intro")]

    class Meta:
        verbose_name = "Future Saints World Discovery Map"

    def get_template(self, request, *args, **kwargs):
        return "future_saints/world_map_page.html"

    def get_context(self, request, *args, **kwargs):
        context = super().get_context(request, *args, **kwargs)
        context.update(world_context(context["fs_home"], request))
        return context


def _site_place(site):
    return ", ".join(v for v in ((site.locality or "").strip(), (site.country or "").strip()) if v)


def saint_place(page):
    """(site, reason): the map place for a saint learning page, or (None, why not)."""
    place = page.map_place
    if place is not None and place.live:
        return place, ""
    canonical = page.canonical_page
    if canonical is None:
        return None, "no live canonical saint page"
    sites = list(canonical.sites.live().order_by("pk")[:2])
    if len(sites) == 1:
        return sites[0], ""
    return None, "needs a map place (no single principal site: choose one in map_place)" if sites else \
        "needs a map place (the saint has no principal site: choose one in map_place)"


def world_items(home, request):
    """The published stories, in list order (type in nav order, then A–Z), with their pins."""
    from .learning import LearningPage

    items, warnings, missions = [], [], []
    hub_url = ""
    for page in LearningPage.objects.descendant_of(home).live().public().specific():
        kind = page.content_kind
        if kind == "california_mission":
            missions.append(page)
            hub = page.get_parent()
            hub_url = hub_url or (hub.get_url(request) if hub.live else "")
            continue
        title = page.student_title or page.title
        x = y = None
        place_line, country, site = "", "", None
        if kind in SITE_KINDS:
            site = page.canonical_page
            if site is None:
                warnings.append(f"{title}: no live canonical page, so no pin")
            elif site.latitude is None or site.longitude is None:
                warnings.append(f"{title}: #{site.pk} {site.title!r} has no latitude/longitude, so no pin")
                site = None
            if site is not None:
                place_line = _site_place(site)
        else:
            site, reason = saint_place(page)
            if site is None:
                warnings.append(f"{title}: {reason}")
            elif site.latitude is None or site.longitude is None:
                warnings.append(f"{title}: #{site.pk} {site.title!r} has no latitude/longitude, so no pin")
                site = None
            if site is not None:
                place_line = f"A place connected to {title}: {site.title}"
        if site is not None:
            x, y = world_viewbox(site.latitude, site.longitude)
            country, why = site_country(site)
            if why:
                warnings.append(f"{title}: #{site.pk} {site.title!r}: {why}")
        items.append(_item(kind, page.slug, title, page.subtitle, page.get_url(request), page.card_art(),
                           place_line, country, x, y, "Read the Story", place=site.title if site else ""))
    for page in missions:
        items.append(_item("california_mission", page.slug, page.student_title or page.title, page.subtitle,
                           page.get_url(request), page.card_art(), "California, United States",
                           "United States", None, None, "Read the Story", in_callout=True))
    if missions and hub_url:
        n = len(missions)
        x, y = world_viewbox(*CALIFORNIA)
        items.append(_item("california_mission", CALLOUT_KEY, "California Missions",
                           f"{n} mission stor{'y' if n == 1 else 'ies'} to explore", hub_url, None,
                           "California, United States", "United States", x, y,
                           "Explore the California Missions", count=n, place=CALLOUT_KEY))
    order = {k: i for i, (k, *_) in enumerate(KINDS)}
    items.sort(key=lambda i: (order[i["kind"]], i["key"] != CALLOUT_KEY, i["title"].lower()))
    return items, warnings


def _item(kind, key, title, subtitle, url, art, place_line, country, x, y, link_label, in_callout=False, count=None,
          place=""):
    pinned = x is not None
    offset = WORLD_MARKER_OFFSETS.get(place, (0, 0)) if pinned else (0, 0)
    return {
        "kind": kind, "key": key, "title": title, "subtitle": subtitle, "url": url, "art": art,
        "type_label": KIND_LABELS[kind], "icon": dict((k, i) for k, _, _, i in KINDS)[kind],
        "place_line": place_line, "link_label": link_label, "count": count, "in_callout": in_callout,
        "country_line": f"Country: {country}" if country and kind != "california_mission" else "",
        "pinned": pinned, "x": x, "y": y,
        "left": f"{100 * x / WORLD_VIEWBOX_WIDTH:.3f}" if pinned else "",
        "top": f"{100 * y / WORLD_VIEWBOX_HEIGHT:.3f}" if pinned else "",
        "dx": offset[0], "dy": offset[1],
        "aria_label": ", ".join(v for v in (title, KIND_LABELS[kind] if count is None else
                                            f"{count} mission stor{'y' if count == 1 else 'ies'}", country) if v),
    }


def marker_box(item, map_px=DESKTOP_MAP_PX):
    """A marker's disc in CSS px on a map `map_px` wide (desktop offsets applied)."""
    s = map_px / WORLD_VIEWBOX_WIDTH
    cx, cy = item["x"] * s + item["dx"], item["y"] * s + item["dy"]
    half = MARKER_PX / 2
    return (cx - half, cy - half, cx + half, cy + half)


def overlapping(items, map_px=DESKTOP_MAP_PX):
    pinned = [i for i in items if i["pinned"]]
    boxes = [(i, marker_box(i, map_px)) for i in pinned]
    clashes = []
    for n, (a, A) in enumerate(boxes):
        for b, B in boxes[n + 1:]:
            if not (A[2] <= B[0] or B[2] <= A[0] or A[3] <= B[1] or B[3] <= A[1]):
                clashes.append((a["title"], b["title"]))
    return clashes


def world_context(home, request):
    from .learning import art_json

    items, warnings = world_items(home, request) if home else ([], [])
    wanted = request.GET.get("story", "")
    selected = next((i for i in items if i["key"] == wanted), None) or (items[0] if items else None)
    for i in items:
        i["selected"] = i is selected
    groups = [{"kind": k, "label": label, "items": [i for i in items if i["kind"] == k]} for k, label, _, _ in KINDS]
    clashes = overlapping(items)
    if clashes:
        warnings += [f"markers overlap at 1440: {a} / {b} (add a reviewed offset)" for a, b in clashes]
    return {
        "fs_world_items": items, "fs_world_selected": selected, "fs_world_groups": groups,
        "fs_world_kinds": KINDS, "fs_world_viewbox": WORLD_VIEWBOX, "fs_world_warnings": warnings,
        "fs_world_regions": world_regions(), "fs_world_zoom_max": WORLD_ZOOM_MAX,
        "fs_world_vb_w": WORLD_VIEWBOX_WIDTH, "fs_world_vb_h": WORLD_VIEWBOX_HEIGHT, **art_context(),
        "fs_world_labels": world_labels(items), "fs_world_detail_scale": f"{DETAIL_SCALE:.3f}",
        "fs_world_home_x": f"{world_viewbox(*HOME_CENTER)[0]:.1f}",
        "fs_world_obstacles": ";".join(",".join(f"{v:.1f}" for v in b) for b in label_obstacles()),
        "fs_world_card_data": [
            {"key": i["key"], "kind": i["kind"], "type_label": i["type_label"], "title": i["title"],
             "subtitle": i["subtitle"], "place_line": i["place_line"], "country_line": i["country_line"],
             "url": i["url"], "link_label": i["link_label"],
             "icon": i["icon"], "in_callout": i["in_callout"], "art": art_json(i["art"], CARD_ART_SPEC)}
            for i in items],
    }


def world_preview(home, request):
    """The homepage preview: the live map page and its pinned markers (static, not interactive)."""
    page = WorldMapPage.objects.child_of(home).live().public().first() if home else None
    if page is None:
        return None
    items, _ = world_items(home, request)
    return {"url": page.get_url(request), "title": page.title, "viewbox": WORLD_VIEWBOX,
            "items": [i for i in items if i["pinned"]], **art_context()}
