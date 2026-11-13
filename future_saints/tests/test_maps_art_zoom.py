"""Maps PR: Steven's map art, the watercolor world map, and zoom on both maps.

Placement and accuracy are tested here in map units and CSS pixels; the zoom behaviour itself
(limits, pan clamp, marker size, keyboard, no page-scroll hijack, the 1:50m swap) runs in the
browser QA (tools/future_saints_maps_screens.py)."""
from pathlib import Path

from django.conf import settings

from future_saints.geo import point_in_polygon, to_viewbox, world_viewbox
from future_saints.missions import (
    BADGE_OFFSETS,
    CITY_LABEL_MIN_MAP_PX,
    MAP_WIDTHS_PX,
    badge_box,
    california_art,
    california_outline,
    city_labels,
)
from future_saints.worldmap import CALIFORNIA, REGIONS, WORLD_ZOOM_MAX, on_land, region_box, world_art

from .test_missions import MISSIONS, MissionsTestCase
from .test_world_map import WorldTestCase

STATIC = Path(settings.BASE_DIR) / "sitesofgrace" / "static" / "future_saints"
ART = ["land-texture.jpg", "ocean-texture.jpg", "mountain-range.png", "tall-mountain.png", "oak-tree.png", "redwoods.png",
       "palm-tree.png", "poppies.png", "sailing-ship.png", "whale-waves.png"]
TRAIL = [1, 18, 7, 4, 17, 9, 10, 19, 11, 5, 16, 3, 13, 2, 15, 12, 8, 14, 6, 20, 21]      # production stop order, south to north
DECOR = [(58, 930, 162, 1042), (52, 773, 308, 847)]                                        # compass, scroll


def hit(a, b, gap=0):
    return not (a[2] + gap <= b[0] or b[2] + gap <= a[0] or a[3] + gap <= b[1] or b[3] + gap <= a[1])


def segment_hits(p, q, box, pad=3):
    x1, y1, x2, y2 = box[0] - pad, box[1] - pad, box[2] + pad, box[3] + pad
    return any(x1 <= p[0] + (q[0] - p[0]) * t / 40 <= x2 and y1 <= p[1] + (q[1] - p[1]) * t / 40 <= y2 for t in range(41))


class ArtFileTests(MissionsTestCase):
    def test_the_ten_pieces_are_web_sized(self):
        for name in ART:
            path = STATIC / "map-art" / name
            self.assertTrue(path.exists(), name)
            self.assertLess(path.stat().st_size, 230 * 1024, f"{name}: web-optimized")
        detail = (STATIC / "svg" / "world-outline-50m.svg").read_text(encoding="utf-8")
        self.assertIn('id="fs-world-land"', detail)
        self.assertIn("ne_50m_land", detail)


class CaliforniaArtTests(MissionsTestCase):
    def test_each_piece_sits_where_it_belongs_and_clear_of_everything(self):
        outline = california_outline()
        pins = {n: to_viewbox(lat, lng) for n, (_, lat, lng, _) in MISSIONS.items()}
        labels = city_labels()
        label_boxes = [(c["x"], c["y"], c["x"] + c["w"], c["y"] + c["h"]) for c in labels]
        leaders = [((c["end_x"], c["end_y"]), (c["dot_x"], c["dot_y"])) for c in labels]
        trail = [(pins[a], pins[b]) for a, b in zip(TRAIL, TRAIL[1:])]
        wants = {"sailing-ship.png": "ocean", "whale-waves.png": "ocean", "poppies.png": "neighbour"}
        pieces = california_art()
        self.assertEqual(len(pieces), 9)
        for a in pieces:
            box = (a["x"], a["y"], a["x"] + a["w"], a["y"] + a["h"])
            kinds = set()
            for x in range(int(box[0]), int(box[2]) + 1, 4):
                for y in range(int(box[1]), int(box[3]) + 1, 4):
                    kinds.add("land" if any(point_in_polygon(x, y, r) for r in outline["rings"])
                              else "ocean" if point_in_polygon(x, y, outline["ocean"]) else "neighbour")
            self.assertEqual(kinds, {wants.get(a["file"], "land")}, a["file"])
            self.assertFalse(any(hit(box, d, 4) for d in DECOR), f"{a['file']}: compass/scroll")
            self.assertFalse(any(hit(box, lb, 4) for lb in label_boxes), f"{a['file']}: a city label")
            self.assertFalse(any(segment_hits(p, q, box) for p, q in leaders), f"{a['file']}: a leader line")
            self.assertFalse(any(segment_hits(p, q, box) for p, q in trail), f"{a['file']}: the trail")
            for other in pieces:
                if other is not a:
                    self.assertFalse(hit(box, (other["x"], other["y"], other["x"] + other["w"], other["y"] + other["h"]), 2),
                                     f"{a['file']} / {other['file']}")
            for width, map_px in MAP_WIDTHS_PX.items():
                if map_px < CITY_LABEL_MIN_MAP_PX and not a["phones"]:
                    continue                                   # hidden on a small map
                s = map_px / 1000
                px = tuple(v * s for v in box)
                for n, (x, y) in pins.items():
                    self.assertFalse(hit(px, (x * s - 16, y * s - 16, x * s + 16, y * s + 16), 2), f"{a['file']}: pin #{n} at {width}")
                    self.assertFalse(hit(px, badge_box(x, y, n, BADGE_OFFSETS.get(n, (0, 0)), s), 2), f"{a['file']}: badge #{n} at {width}")

    def test_the_hub_draws_the_art_textures_and_zoom(self):
        self.seed_and_publish()
        html = self.hub_html()
        self.assertEqual(html.count("<image class=\"fs-map-piece"), 9)
        self.assertEqual(html.count('class="fs-map-piece fs-map-piece--wide"'), 3, "these hide on a small map")
        self.assertIn('fill="url(#fs-ca-land-tex)"', html)
        self.assertIn('fill="url(#fs-ca-ocean-tex)"', html)
        self.assertIn('data-fs-zoom data-fs-zoom-max="4"', html)
        self.assertIn("hidden data-fs-zoom-controls", html, "no zoom controls without JavaScript")
        self.assertIn('aria-label="Zoom in"', html)
        art = html.split('<svg class="fs-map-art"')[1].split(">")[0]
        self.assertIn('aria-hidden="true"', art, "the art layer, pieces included, is hidden from assistive tech")
        # The pins are unchanged: still at their true projected spots.
        x, y = to_viewbox(*MISSIONS[1][1:3])
        self.assertIn(f"--x: {100 * x / 1000:.3f}%; --y: {100 * y / 1100:.3f}%", html)


class WorldArtAndZoomTests(WorldTestCase):
    def test_region_boxes_contain_their_cities(self):
        boxes = {key: region_box(sn, we) for key, _, sn, we in REGIONS}
        cities = {"europe": {"Rome": (41.9028, 12.4964), "Lourdes": (43.0967, -0.0558), "Fátima": (39.6317, -8.6724),
                             "Lanciano": (42.2306, 14.3903)},
                  "holy-land": {"Jerusalem": (31.7784, 35.2296)},
                  "americas": {"Mexico City": (19.4326, -99.1332), "the California callout": CALIFORNIA}}
        for key, places in cities.items():
            x1, y1, x2, y2 = boxes[key]
            for name, (lat, lng) in places.items():
                x, y = world_viewbox(lat, lng)
                self.assertTrue(x1 <= x <= x2 and y1 <= y <= y2, f"{name} in {key}")

    def test_world_art_only_in_open_ocean_clear_of_markers_and_compass(self):
        markers = [(i["x"], i["y"]) for i in self.items() if i["pinned"]]
        compass = (26, 318, 114, 414)
        for a in world_art():
            box = (a["x"], a["y"], a["x"] + a["w"], a["y"] + a["h"])
            for x in range(int(box[0]) - 4, int(box[2]) + 5, 3):
                for y in range(int(box[1]) - 4, int(box[3]) + 5, 3):
                    self.assertFalse(on_land(x, y), f"{a['file']} near land at ({x}, {y})")
            self.assertFalse(hit(box, compass), a["file"])
            for map_px in MAP_WIDTHS_PX.values():
                s = map_px / 1000
                for mx, my in markers:
                    self.assertFalse(hit(tuple(v * s for v in box), (mx * s - 22, my * s - 22, mx * s + 22, my * s + 22), 2),
                                     f"{a['file']} near a marker at {map_px}px")

    def test_the_map_page_draws_textures_ocean_art_and_zoom(self):
        html = self.map_html()
        self.assertIn('fill="url(#fs-world-ocean-tex)"', html)
        self.assertIn('fill="url(#fs-world-land-tex)"', html)
        self.assertEqual(html.count('class="fs-map-piece"'), 2, "ship and whale, in open ocean only")
        self.assertIn(f'data-fs-zoom data-fs-zoom-max="{WORLD_ZOOM_MAX}"', html)
        self.assertEqual(WORLD_ZOOM_MAX, 6)
        self.assertIn("world-outline-50m.svg#fs-world-land", html, "the 1:50m detail is named, loaded only past 2x")
        self.assertEqual(html.count('data-fs-detail="'), 4)
        self.assertIn("hidden data-fs-regions", html)
        for label in ("Europe", "Holy Land", "The Americas", "Whole World"):
            self.assertIn(f">{label}</button>", html)
        self.assertIn("hidden data-fs-zoom-controls", html)
        # Markers carry their true map units for zooming to them.
        lourdes = [i for i in self.items() if i["key"] == "our-lady-of-lourdes"][0]
        self.assertIn(f'value="our-lady-of-lourdes" class="fs-wm-pin" data-fs-world-pin data-x="{lourdes["x"]:.2f}" data-y="{lourdes["y"]:.2f}"', html)

    def test_the_homepage_preview_has_the_same_look(self):
        from .base import FS_ON

        with FS_ON:
            html = self.html("/future-saints/")
        preview = html.split("data-fs-world-preview>")[1].split("</a>")[0]
        self.assertIn('fill="url(#fs-world-land-tex)"', preview)
        self.assertIn("sailing-ship.png", preview)
        self.assertIn('class="fs-map-compass"', preview)
        self.assertNotIn("data-fs-zoom", preview, "the preview doesn't zoom")
