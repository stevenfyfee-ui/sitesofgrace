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
"""
import json
from functools import lru_cache
from pathlib import Path

from django.db import models
from wagtail.admin.panels import FieldPanel
from wagtail.models import Page

from .geo import WORLD_VIEWBOX, WORLD_VIEWBOX_HEIGHT, WORLD_VIEWBOX_WIDTH, point_in_polygon, world_viewbox
from .models import FutureSaintsGateMixin

OUTLINE_FILE = Path(__file__).resolve().parent / "data" / "world_outline.json"

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
DESKTOP_MAP_PX = 691.2                    # the map's width at 1440 (panel beside it), as on the missions hub
# Reviewed offsets (CSS px, desktop >= 1024 only) for markers that would overlap at 1440.
# Keyed by the place a marker sits on (the sacred site's exact title, or the callout's key),
# so an offset stays with its spot whatever page links there. A thin line and a dot anchor
# each moved marker to its true spot. The smallest offsets that clear every marker.
WORLD_MARKER_OFFSETS = {
    "Our Lady of Lourdes": (-16, 0),
    "Shrine of St. Carlo Acutis (Assisi)": (0, -8),
    "Eucharistic Miracle of Lanciano": (0, 28),
}


@lru_cache(maxsize=1)
def world_outline():
    return json.loads(OUTLINE_FILE.read_text(encoding="utf-8"))


def on_land(x, y):
    return any(point_in_polygon(x, y, p["outer"]) and not any(point_in_polygon(x, y, h) for h in p["holes"])
               for p in world_outline()["polygons"])


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
                place_line, country = _site_place(site), (site.country or "").strip()
        else:
            site, reason = saint_place(page)
            if site is None:
                warnings.append(f"{title}: {reason}")
            elif site.latitude is None or site.longitude is None:
                warnings.append(f"{title}: #{site.pk} {site.title!r} has no latitude/longitude, so no pin")
                site = None
            if site is not None:
                place_line, country = f"A place connected to {title}: {site.title}", (site.country or "").strip()
        if site is not None:
            x, y = world_viewbox(site.latitude, site.longitude)
        items.append(_item(kind, page.slug, title, page.subtitle, page.get_url(request), page.art()["thumbnail"],
                           place_line, country, x, y, "Read the Story", place=site.title if site else ""))
    for page in missions:
        items.append(_item("california_mission", page.slug, page.student_title or page.title, page.subtitle,
                           page.get_url(request), page.art()["thumbnail"], "California, United States",
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
        "fs_world_card_data": [
            {"key": i["key"], "kind": i["kind"], "type_label": i["type_label"], "title": i["title"],
             "subtitle": i["subtitle"], "place_line": i["place_line"], "url": i["url"], "link_label": i["link_label"],
             "icon": i["icon"]} for i in items],
    }


def world_preview(home, request):
    """The homepage preview: the live map page and its pinned markers (static, not interactive)."""
    page = WorldMapPage.objects.child_of(home).live().public().first() if home else None
    if page is None:
        return None
    items, _ = world_items(home, request)
    return {"url": page.get_url(request), "title": page.title, "viewbox": WORLD_VIEWBOX,
            "items": [i for i in items if i["pinned"]]}
