"""PR B: Future Saints search (kids-safe).

Scope (published Future Saints pages only), matching (accents, case, word starts, one letter
off on 5+ letters), the cached index and its invalidation, the results page and empty state,
the three placements, the switch, banned words and privacy (nothing written, nothing stored).
The type-ahead itself runs in the browser QA (tools/future_saints_search_screens.py).
"""
import json
from pathlib import Path

from django.conf import settings
from django.core.cache import cache
from django.db import connection
from django.test.utils import CaptureQueriesContext
from wagtail.contrib.search_promotions.models import Query

from catalog.models import SaintPage
from future_saints.models import MissionProjectsGuidePage, MissionSchoolProject, SaintLearningPage, WordToKnow
from future_saints.search import INDEX_CACHE_KEY, build_index, first_sentence, fold, search, search_index
from future_saints.worldmap import CALLOUT_KEY

from .base import FS_OFF, FS_ON, FS_STAFF
from .test_privacy import BANNED as BOUNDARY_BANNED
from .test_world_map import BANNED as WORLD_BANNED, WorldTestCase

JS = Path(settings.BASE_DIR) / "sitesofgrace" / "static" / "js" / "future-saints.js"
SEARCH = "/future-saints/search/"
INDEX = "/future-saints/search/index/"


class SearchTestCase(WorldTestCase):
    def setUp(self):
        super().setUp()
        cache.delete(INDEX_CACHE_KEY)
        self.addCleanup(cache.delete, INDEX_CACHE_KEY)

    def index(self):
        return build_index(self.home)

    def titles(self, query):
        return [e["t"] for e in search(self.index(), query)]


class ScopeTests(SearchTestCase):
    def test_only_published_future_saints_pages(self):
        draft = self.story(SaintLearningPage, "saint", "draft-saint", "Saint Draftina", None, publish=False)
        titles = [e["t"] for e in self.index()]
        for t in ("Our Lady of Lourdes", "Eucharistic Miracle of Lanciano", "Church of the Holy Sepulchre",
                  "Saint Carlo Acutis", "Mission San Diego de Alcalá"):
            self.assertIn(t, titles)
        self.assertNotIn(draft.title, titles, "never drafts")
        self.assertNotIn("St. Carlo Acutis", titles, "never the adult saint page")
        self.assertNotIn("Shrine of St. Carlo Acutis (Assisi)", titles, "never an adult site page")
        self.pages["lourdes"].unpublish()
        self.assertNotIn("Our Lady of Lourdes", [e["t"] for e in self.index()], "unpublished pages drop out")

    def test_hub_guide_and_only_published_projects(self):
        hub = self.pages["san_diego"].get_parent().specific
        guide = MissionProjectsGuidePage(title="How to Build a California Mission Model (sample)", slug="projects",
                                         intro="Plan it first. Then build it.")
        hub.add_child(instance=guide)
        guide.save_revision().publish()
        project = MissionSchoolProject.objects.create(page=self.pages["san_diego"], project_title="Build San Diego (sample)",
                                                      status="in_review", project_intro="Start here. Then glue.")
        kinds = {e["t"]: e["k"] for e in self.index()}
        self.assertEqual(kinds[hub.title], "california_mission")
        self.assertEqual(kinds[guide.title], "california_mission")
        self.assertNotIn(project.project_title, kinds, "a project shows only once Published")
        project.status = "published"
        project.save()
        entry = next(e for e in self.index() if e["t"] == project.project_title)
        self.assertEqual(entry["k"], "project")
        self.assertTrue(entry["u"].endswith("/mission-san-diego-de-alcala/#build"))
        self.assertEqual(entry["i"], "Start here.")

    def test_entry_fields(self):
        page = self.pages["lourdes"]
        page.intro = "<p>Mary appeared to <b>Bernadette</b>. She was fourteen.</p>"
        page.words = [WordToKnow(word="grotto", definition="A small cave (sample).")]
        page.save_revision().publish()
        entry = next(e for e in self.index() if e["t"] == "Our Lady of Lourdes")
        self.assertEqual(entry["k"], "marian_apparition")
        self.assertEqual(entry["s"], "Our Lady of Lourdes subtitle (sample)")
        self.assertEqual(entry["p"], "Lourdes, France")
        self.assertEqual(entry["w"], ["grotto"])
        self.assertEqual(entry["i"], "Mary appeared to Bernadette.")
        self.assertEqual(entry["m"], "our-lady-of-lourdes", "pinned: selects its own marker")
        self.assertEqual(first_sentence("<p>No full stop</p>"), "No full stop")

    def test_map_keys(self):
        no_place = SaintPage(title="St. Nowhere", slug="st-nowhere")
        self.root.add_child(instance=no_place)
        self.story(SaintLearningPage, "saint", "saint-nowhere", "Saint Nowhere", no_place)
        keys = {e["t"]: e["m"] for e in self.index()}
        self.assertEqual(keys["Saint Nowhere"], "saint-nowhere", "no pin: its card shows, with the not-on-the-map note")
        self.assertEqual(keys["Mission San Diego de Alcalá"], "mission-san-diego-de-alcala", "a mission: in the callout")
        self.assertEqual(keys[self.pages["san_diego"].get_parent().title], CALLOUT_KEY)


class MatchingTests(SearchTestCase):
    def test_accents_case_and_word_starts(self):
        self.assertEqual(fold("Fátima ÁLCALÁ"), "fatima alcala")
        self.assertIn("Mission San Diego de Alcalá", self.titles("ALCALA"))
        self.assertIn("Mission San Diego de Alcalá", self.titles("san die"))
        self.assertIn("Our Lady of Lourdes", self.titles("lour"))
        self.assertEqual(self.titles("rdes"), [], "only the start of a word matches")
        self.assertEqual(self.titles("lourdes zebra"), [], "every word must match")

    def test_one_letter_off_only_on_five_letters_or_more(self):
        self.assertIn("Our Lady of Lourdes", self.titles("lurdes"), "one letter missing")
        self.assertIn("Our Lady of Lourdes", self.titles("loordes"), "one letter changed")
        self.assertIn("Eucharistic Miracle of Lanciano", self.titles("lanciiano"), "one letter added")
        self.assertEqual(self.titles("lurdez"), [], "two letters off")
        self.assertEqual(self.titles("crlo"), [], "four letters: no tolerance")

    def test_place_and_words_to_know_are_searched_title_ranks_first(self):
        self.assertEqual(self.titles("france"), ["Our Lady of Lourdes"])
        page = self.pages["carlo"]
        page.words = [WordToKnow(word="Lourdes", definition="(sample)")]
        page.save_revision().publish()
        self.assertEqual(self.titles("lourdes"), ["Our Lady of Lourdes", "Saint Carlo Acutis"])


class CacheTests(SearchTestCase):
    def test_cached_and_dropped_on_publish_and_unpublish(self):
        first = search_index(self.home)
        self.assertEqual(cache.get(INDEX_CACHE_KEY), first)
        self.story(SaintLearningPage, "saint", "saint-new", "Saint Newly", None)
        self.assertIsNone(cache.get(INDEX_CACHE_KEY), "publishing drops the index")
        self.assertIn("Saint Newly", [e["t"] for e in search_index(self.home)])
        self.pages["lourdes"].unpublish()
        self.assertIsNone(cache.get(INDEX_CACHE_KEY), "unpublishing drops the index")
        self.assertNotIn("Our Lady of Lourdes", [e["t"] for e in search_index(self.home)])


class PageTests(SearchTestCase):
    def test_results_grouped_by_type(self):
        with FS_ON:
            html = self.html(SEARCH, q="saint")
        self.assertIn("1 story found", html)
        self.assertIn('id="fs-sg-saint"', html)
        self.assertIn(f'href="{self.pages["carlo"].url}"', html)
        with FS_ON:
            html = self.html(SEARCH, q="of")
        order = [html.index(f'id="fs-sg-{k}"') for k in ("marian_apparition", "eucharistic_miracle")]
        self.assertEqual(order, sorted(order), "groups in the header nav's order")

    def test_empty_state_with_three_suggestion_links(self):
        with FS_ON:
            html = self.html(SEARCH, q="zzqx")
        self.assertIn("No stories found. Try another word!", html)
        links = html.split('class="fs-search-suggest"')[1].split("</ul>")[0]
        self.assertEqual(links.count("<a href=\"?q="), 3)
        self.assertIn('href="?q=Carlo"', links, "the placeholder's words, when each finds something")
        self.assertIn('href="?q=San%20Diego"', links)
        self.assertNotIn("tima", links, "no Fátima story here, so it isn't suggested")
        self.assertIn('href="?q=Lourdes"', links, "then a published story's name not already covered")

    def test_noindex_switch_and_index_json(self):
        with FS_ON:
            response = self.get(SEARCH, q="lourdes")
            data = json.loads(self.get(INDEX).content)
        self.assertEqual(response["X-Robots-Tag"], "noindex, nofollow", "noindex even when the section is public")
        self.assertIn('<meta name="robots" content="noindex,nofollow">', response.content.decode())
        self.assertEqual([g[0] for g in data["groups"]][-1], "project")
        self.assertIn("Our Lady of Lourdes", [e["t"] for e in data["entries"]])
        for url in (SEARCH, INDEX):
            with FS_OFF:
                for user in (None, self.staff):
                    self.assertEqual(self.get(url, user).status_code, 404, url)
            with FS_STAFF:
                self.assertEqual(self.get(url).status_code, 404, url)
                self.assertEqual(self.get(url, self.staff).status_code, 200, url)

    def test_placements(self):
        map_html = self.map_html()
        with FS_ON:
            home = self.html("/future-saints/")
            saint = self.html(self.pages["carlo"].url)
        box = home.split('class="fs-wrap fs-home-search"')[1].split("</form>")[0]
        self.assertIn(">Search for a saint, a miracle, or a place</label>", box)
        self.assertIn('placeholder="Try Carlo, Fátima, or San Diego"', box)
        self.assertLess(home.index("fs-hero"), home.index("fs-home-search"), "under the hero")
        self.assertLess(map_html.index('data-fs-search="map"'), map_html.index("data-fs-world-filters"), "above the filters")
        self.assertIn("This story isn't on the map yet.", map_html)
        for html in (home, map_html, saint):
            self.assertIn(f'class="fs-search-link" href="{SEARCH}" aria-label="Search"', html)
        self.assertNotIn('role="combobox"', box, "a plain field until JavaScript makes it a combobox")
        self.assertIn('aria-live="polite"', box)

    def test_no_banned_words(self):
        with FS_ON:
            pages = [self.html(SEARCH), self.html(SEARCH, q="lourdes"), self.html(SEARCH, q="zzqx"),
                     self.get(INDEX).content.decode()]
        for html in pages:
            lower = html.lower()
            for word in set(BOUNDARY_BANNED) | set(WORLD_BANNED):
                self.assertNotIn(word, lower)


class PrivacyTests(SearchTestCase):
    def test_a_search_writes_nothing_and_sets_no_cookie(self):
        self.client.logout()
        with FS_ON:
            self.client.get(SEARCH, {"q": "lourdes"})       # warm the index cache (cache, not the database)
            with CaptureQueriesContext(connection) as queries:
                for params in ({"q": "lourdes"}, {"q": "zzqx"}, {}):
                    response = self.client.get(SEARCH, params)
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(dict(response.cookies), {})
                    self.assertFalse(response.has_header("Set-Cookie"))
                response = self.client.get(INDEX)
                self.assertFalse(response.has_header("Set-Cookie"))
        writes = [q["sql"] for q in queries if q["sql"].lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE"))]
        self.assertEqual(writes, [], "no query logging, no hit counts")
        self.assertFalse(Query.objects.exists(), "no Wagtail search promotions queries")

    def test_the_type_ahead_stores_and_sends_nothing(self):
        js = JS.read_text(encoding="utf-8")
        block = js.split("// ---- Search (kids-safe)")[1]
        block = "\n".join(line for line in block.splitlines() if not line.strip().startswith("//"))   # code only
        for banned in ("localStorage", "sessionStorage", "document.cookie", "sendBeacon", "gtag", "analytics", "XMLHttpRequest"):
            self.assertNotIn(banned, block)
        self.assertEqual(block.count("fetch("), 1, "one fetch: the index, never the query")
        self.assertIn('setAttribute("role", "combobox")', block)
