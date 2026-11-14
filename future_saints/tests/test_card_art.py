"""Selection-card pictures: the World Discovery Map story card and the California Missions hub
panel show the selected story's picture (index thumbnail, else hero illustration, else the
placeholder frame), server-rendered for ?story= / ?mission= and in the data the browser swaps
from. The browser side (every way of selecting) runs in tools/future_saints_card_screens.py."""
import json
import re

from wagtail.images import get_image_model
from wagtail.images.tests.utils import get_test_image_file

from future_saints.learning import art_json
from future_saints.missions import PANEL_ART_SPEC
from future_saints.worldmap import CARD_ART_SPEC

from .test_missions import MissionsTestCase
from .test_world_map import WorldTestCase


def image(title):
    return get_image_model().objects.create(title=title, file=get_test_image_file())


def card_picture(html, marker):
    """(src, alt) of the picture in the card opened by `marker`, or "placeholder"."""
    card = html.split(marker, 1)[1].split("</aside>", 1)[0]
    found = re.search(r'<figure class="fs-art[^"]*">\s*<img src="([^"]+)"[^>]*alt="([^"]*)"', card)
    if found:
        return found.groups()
    return "placeholder" if "fs-art--placeholder" in card else None


class WorldCardArtTests(WorldTestCase):
    def setUp(self):
        super().setUp()
        self.thumb, self.hero = image("Thumb (sample)"), image("Hero (sample)")
        lourdes = self.pages["lourdes"]
        lourdes.index_thumbnail, lourdes.index_thumbnail_alt = self.thumb, "The grotto (sample)"
        lourdes.hero_illustration, lourdes.hero_illustration_alt = self.hero, "Not this one (sample)"
        lourdes.save_revision().publish()
        lanciano = self.pages["lanciano"]
        lanciano.hero_illustration, lanciano.hero_illustration_alt = self.hero, "The church (sample)"
        lanciano.save_revision().publish()

    def test_card_art_is_thumbnail_else_hero_else_none(self):
        self.pages["lourdes"].refresh_from_db()
        self.assertEqual(self.pages["lourdes"].specific.card_art()["image"], self.thumb)
        self.assertEqual(self.pages["lanciano"].specific.card_art()["image"], self.hero)
        self.assertIsNone(self.pages["sepulchre"].specific.card_art())

    def test_server_rendered_card_for_each_story(self):
        lourdes = art_json({"image": self.thumb, "alt": "The grotto (sample)"}, CARD_ART_SPEC)
        lanciano = art_json({"image": self.hero, "alt": "The church (sample)"}, CARD_ART_SPEC)
        cases = {"our-lady-of-lourdes": (lourdes["src"], "The grotto (sample)"),
                 "eucharistic-miracle-of-lanciano": (lanciano["src"], "The church (sample)"),
                 "church-of-the-holy-sepulchre": "placeholder"}
        for key, want in cases.items():
            html = self.map_html(story=key)
            self.assertEqual(card_picture(html, "data-fs-world-card>"), want, key)

    def test_the_data_the_browser_swaps_from(self):
        html = self.map_html()
        data = {s["key"]: s for s in json.loads(html.split('id="fs-world-data" type="application/json">')[1].split("</script>")[0])}
        self.assertEqual(data["our-lady-of-lourdes"]["art"]["alt"], "The grotto (sample)")
        self.assertTrue(data["our-lady-of-lourdes"]["art"]["src"].endswith(".png"))
        self.assertEqual(data["eucharistic-miracle-of-lanciano"]["art"]["alt"], "The church (sample)")
        self.assertIsNone(data["church-of-the-holy-sepulchre"]["art"], "none: the placeholder frame")
        self.assertIsNone(data["carlo-acutis"]["art"])
        for s in data.values():
            self.assertNotIn("credit", json.dumps(s).lower(), "credits are never rendered")


class HubPanelArtTests(MissionsTestCase):
    def test_panel_shows_the_missions_story_picture(self):
        self.seed_and_publish()
        story = self.story(1)
        hero = image("Hero (sample)")
        story.hero_illustration, story.hero_illustration_alt = hero, "Mission church (sample)"
        story.save_revision().publish()
        html = self.hub_html(mission=self.sites[1].slug)
        want = art_json({"image": hero, "alt": "Mission church (sample)"}, PANEL_ART_SPEC)
        self.assertEqual(card_picture(html, "data-fs-panel>"), (want["src"], "Mission church (sample)"))
        data = {m["slug"]: m for m in json.loads(html.split('id="fs-mission-data" type="application/json">')[1].split("</script>")[0])}
        self.assertEqual(data[self.sites[1].slug]["art"]["alt"], "Mission church (sample)")
        self.assertIsNone(data[self.sites[2].slug]["art"], "a mission with no story: the placeholder")
        self.assertEqual(card_picture(self.hub_html(mission=self.sites[2].slug), "data-fs-panel>"), "placeholder")
