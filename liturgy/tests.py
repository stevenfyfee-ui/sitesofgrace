import tempfile
from datetime import date, datetime, timedelta, timezone as dt_timezone
from unittest import mock
from zoneinfo import ZoneInfo

from django.core.cache import cache
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from wagtail.models import PageViewRestriction, Site

from catalog.models import SacredSitePage, SaintPage
from home.models import HomePage
from liturgy import calendar as litcal
from liturgy.feasts import (
    INDEX_CACHE_KEY,
    MOVABLE_FEASTS,
    build_day_index,
    parse_anniversaries,
    parse_feast_text,
)
from liturgy.today import (
    date_at_noon,
    fold_celebration,
    liturgical_date,
    liturgical_today,
    rank_label,
)

LA = ZoneInfo("America/Los_Angeles")


def at_noon(iso):
    """Pin the clock to midday, Pacific, on the given date."""
    return date_at_noon(date.fromisoformat(iso))


def names(events):
    return [event["name"] for event in events]


def keys(events):
    return [event["event_key"] for event in events]


def reset_calendar_caches():
    litcal._events_by_date.cache_clear()
    litcal._warn_missing.cache_clear()


class CalendarDataTests(TestCase):
    def test_data_files_exist_for_this_year_and_next(self):
        # Deliberately not pinned: this is the test that fails in late 2029,
        # so someone runs `sync_liturgical_calendar --years 2031` (etc.)
        # before the card runs out of calendar.
        this_year = liturgical_date().year
        for year in (this_year, this_year + 1):
            self.assertTrue(
                litcal.data_path(year).exists(),
                f"liturgy/data/litcal-US-{year}.json is missing -- run "
                f"`manage.py sync_liturgical_calendar --years {year}-{year + 4}` and commit the files",
            )

    def test_rosary_2026_10_07_is_a_memorial(self):
        events = litcal.celebrations_on(date(2026, 10, 7))
        rosary = [e for e in events if e["event_key"] == "OurLadyOfTheRosary"]
        self.assertEqual(len(rosary), 1)
        self.assertEqual(rank_label(rosary[0]), "Memorial")

    def test_immaculate_conception_2026_is_a_solemnity_on_an_advent_tuesday(self):
        day = date(2026, 12, 8)
        self.assertEqual(day.strftime("%A"), "Tuesday")
        events = litcal.celebrations_on(day)
        self.assertEqual(keys(events)[0], "ImmaculateConception")
        self.assertEqual(rank_label(events[0]), "Solemnity")
        self.assertEqual(litcal.season_on(day), ("ADVENT", "Advent"))

    def test_corpus_christi_2026_is_kept_on_sunday_in_the_us(self):
        day = date(2026, 6, 7)
        self.assertEqual(day.strftime("%A"), "Sunday")
        self.assertIn("CorpusChristi", keys(litcal.celebrations_on(day)))

    def test_divine_mercy_sunday_2026(self):
        events = litcal.celebrations_on(date(2026, 4, 12))
        self.assertIn("Easter2", keys(events))
        self.assertIn("Divine Mercy", names(events)[0])

    def test_corpus_christi_and_sacred_heart_2027(self):
        self.assertIn("CorpusChristi", keys(litcal.celebrations_on(date(2027, 5, 30))))
        self.assertIn("SacredHeart", keys(litcal.celebrations_on(date(2027, 6, 4))))

    def test_highest_grade_first_and_no_vigils(self):
        events = litcal.celebrations_on(date(2026, 10, 6))
        grades = [e["grade"] for e in events]
        self.assertEqual(grades, sorted(grades, reverse=True))
        for year in range(2026, 2031):
            for event in litcal._events_by_date(year).get(f"{year}-12-31", []):
                self.assertNotIn("Vigil", event["name"])

    def test_every_movable_feast_key_exists_in_2026(self):
        all_keys = {e["event_key"] for day in litcal._events_by_date(2026).values() for e in day}
        self.assertEqual(set(MOVABLE_FEASTS.values()) - all_keys, set())


class MissingYearTests(TestCase):
    def setUp(self):
        reset_calendar_caches()
        self.addCleanup(reset_calendar_caches)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        patcher = mock.patch.object(litcal, "DATA_DIR", litcal.Path(self.tmp.name))
        patcher.start()
        self.addCleanup(patcher.stop)
        cache.clear()

    def test_missing_year_is_empty_and_warns_once(self):
        with self.assertLogs("liturgy.calendar", level="WARNING") as logs:
            self.assertEqual(litcal.celebrations_on(date(2026, 10, 7)), [])
            self.assertEqual(litcal.celebrations_on(date(2026, 10, 8)), [])
            self.assertEqual(litcal.season_on(date(2026, 10, 8)), ("", ""))
        self.assertEqual(len(logs.records), 1)

    def test_liturgical_today_does_not_raise(self):
        with self.assertLogs("liturgy.calendar", level="WARNING"):
            days = liturgical_today(at_noon("2026-10-07"))
        self.assertEqual(days["today"]["celebrations"], [])
        self.assertEqual(days["today"]["label"], "Wednesday, October 7")

    def test_home_page_still_renders(self):
        with self.assertLogs("liturgy.calendar", level="WARNING"):
            response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "data-today-card")


class TimeZoneTests(TestCase):
    def test_early_utc_morning_is_still_the_previous_day_in_los_angeles(self):
        now = datetime(2026, 10, 7, 6, 30, tzinfo=dt_timezone.utc)
        self.assertEqual(liturgical_date(now), date(2026, 10, 6))
        cache.clear()
        days = liturgical_today(now)
        self.assertEqual(days["today"]["date"], date(2026, 10, 6))
        self.assertEqual(days["yesterday"]["date"], date(2026, 10, 5))
        self.assertEqual(days["tomorrow"]["date"], date(2026, 10, 7))

    @override_settings(LITURGICAL_TIME_ZONE="Europe/Rome")
    def test_time_zone_setting_is_honoured(self):
        now = datetime(2026, 10, 7, 6, 30, tzinfo=dt_timezone.utc)
        self.assertEqual(liturgical_date(now), date(2026, 10, 7))

    def test_year_rollover_reads_next_years_file(self):
        cache.clear()
        days = liturgical_today(at_noon("2026-12-31"))
        self.assertEqual(days["tomorrow"]["date"], date(2027, 1, 1))
        self.assertEqual(days["tomorrow"]["celebrations"][0]["name"], "Mary, Mother of God")
        self.assertEqual(days["tomorrow"]["celebrations"][0]["rank_label"], "Solemnity")


class CelebrationListTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_weekday_row_hidden_under_a_memorial(self):
        # 2026-10-19: Brébeuf & Jogues (Memorial), Paul of the Cross (Optional
        # Memorial), Monday of the 29th Week (weekday).
        today = liturgical_today(at_noon("2026-10-19"))["today"]
        listed = [c["name"] for c in today["celebrations"]]
        self.assertFalse(any("Week of Ordinary Time" in name for name in listed), listed)
        self.assertEqual(len(listed), 2)
        self.assertEqual(today["color"], "red")

    def test_weekday_row_kept_with_only_optional_memorials(self):
        today = liturgical_today(at_noon("2026-10-06"))["today"]
        listed = [c["name"] for c in today["celebrations"]]
        self.assertIn("Tuesday of the 27th Week of Ordinary Time", listed)
        self.assertEqual(today["color"], "green")


class ParserTests(TestCase):
    def test_feast_text_table(self):
        table = [
            ("October 7", [("fixed", 10, 7)]),
            ("Oct 7", [("fixed", 10, 7)]),
            ("Oct. 7", [("fixed", 10, 7)]),
            ("7 October", [("fixed", 10, 7)]),
            ("October 7th", [("fixed", 10, 7)]),
            ("Sept. 3", [("fixed", 9, 3)]),
            ("february 29", [("fixed", 2, 29)]),
            ("October 7; December 8", [("fixed", 10, 7), ("fixed", 12, 8)]),
            ("October 7, December 8", [("fixed", 10, 7), ("fixed", 12, 8)]),
            ("October 7 / December 8", [("fixed", 10, 7), ("fixed", 12, 8)]),
            ("October 7 and December 8", [("fixed", 10, 7), ("fixed", 12, 8)]),
            ("Divine Mercy Sunday", [("movable", "Easter2")]),
            ("Second Sunday of Easter", [("movable", "Easter2")]),
            ("Pentecost", [("movable", "Pentecost")]),
            ("Trinity Sunday", [("movable", "Trinity")]),
            ("Corpus Christi", [("movable", "CorpusChristi")]),
            ("Most Holy Body and Blood of Christ", [("movable", "CorpusChristi")]),
            ("Feast of the Sacred Heart (movable)", [("movable", "SacredHeart")]),
            ("Immaculate Heart of Mary", [("movable", "ImmaculateHeart")]),
            ("Christ the King", [("movable", "ChristKing")]),
            ("Holy Family", [("movable", "HolyFamily")]),
            ("Baptism of the Lord", [("movable", "BaptismLord")]),
            ("Ascension", [("movable", "Ascension")]),
            ("EASTER", [("movable", "Easter")]),
            ("Ash Wednesday", [("movable", "AshWednesday")]),
            ("Palm Sunday", [("movable", "PalmSun")]),
            ("Good Friday", [("movable", "GoodFri")]),
            ("Mary, Mother of the Church", [("movable", "MaryMotherChurch")]),
            ("Holy Thursday and Pentecost", [("movable", "HolyThurs"), ("movable", "Pentecost")]),
            ("Pentecost; October 7", [("movable", "Pentecost"), ("fixed", 10, 7)]),
            # A feast used only as a reference point is some other day.
            ("Blutfreitag (Friday after Ascension)", []),
            ("Easter Monday", []),
            ("Third Sunday of Easter", []),
            # Never guess.
            ("Sveta Nedelja (early September)", []),
            ("October", []),
            ("1917", []),
            ("February 30", []),
            ("Varies", []),
            ("asdf qwerty 99", []),
            ("", []),
            (None, []),
        ]
        for text, expected in table:
            with self.subTest(text=text):
                self.assertEqual(parse_feast_text(text), expected)

    def test_anniversary_table(self):
        table = [
            ("October 13, 1917", [(10, 13, 1917)]),
            ("13 October 1917", [(10, 13, 1917)]),
            ("May 13 – October 13, 1917", [(5, 13, 1917), (10, 13, 1917)]),
            ("May 13 - October 13, 1917", [(5, 13, 1917), (10, 13, 1917)]),
            ("Dedicated Oct. 7, 1571", [(10, 7, 1571)]),
            ("1917", []),
            ("October 1917", []),
            ("Built 1937–1947", []),
            ("4th century origins", []),
            ("October 13", []),
            ("February 29, 1917", []),
            ("", []),
        ]
        for text, expected in table:
            with self.subTest(text=text):
                self.assertEqual(parse_anniversaries(text), expected)

    def test_rank_labels(self):
        cases = [
            ({"grade": 0, "event_key": "OrdWeekday27Tuesday"}, ""),
            ({"grade": 1, "event_key": "StPolycarp"}, "Commemoration"),
            ({"grade": 2, "event_key": "StBruno"}, "Optional Memorial"),
            ({"grade": 3, "event_key": "OurLadyOfTheRosary"}, "Memorial"),
            ({"grade": 4, "event_key": "StLuke"}, "Feast"),
            ({"grade": 5, "event_key": "BaptismLord"}, "Feast"),
            ({"grade": 5, "event_key": "OrdSunday28"}, ""),
            ({"grade": 6, "event_key": "Assumption"}, "Solemnity"),
            ({"grade": 6, "event_key": "AllSouls"}, ""),
            ({"grade": 7, "event_key": "Pentecost"}, "Solemnity"),
            ({"grade": 7, "event_key": "Lent2"}, ""),
            ({"grade": 7, "event_key": "AshWednesday"}, ""),
        ]
        for event, expected in cases:
            with self.subTest(event=event):
                self.assertEqual(rank_label(event), expected)

    def test_fold_celebration_matches_page_titles(self):
        from catalog.text import fold

        self.assertEqual(fold_celebration("Saint Bruno, Priest"), fold("St. Bruno"))
        self.assertEqual(
            fold_celebration("Saint Gregory the Great, Pope and Doctor of the Church"),
            fold("St. Gregory the Great"),
        )
        self.assertEqual(
            fold_celebration("[ US ] Blessed Marie Rose Durocher, Virgin"),
            fold("Bl. Marie Rose Durocher"),
        )
        # A comma clause that isn't a title is kept.
        self.assertEqual(fold_celebration("Mary, Mother of God"), "mary mother of god")


class PageMatchingTests(TestCase):
    """Real pages under the default site's home page, clock pinned throughout."""

    @classmethod
    def setUpTestData(cls):
        cls.home = HomePage.objects.get(pk=Site.objects.get(is_default_site=True).root_page_id)

        def saint(slug, title, feast, live=True, honorific=""):
            page = SaintPage(title=title, slug=slug, feast_day=feast, honorific_type=honorific, live=live)
            cls.home.add_child(instance=page)
            return page

        def site(slug, title, feast="", date_display="", live=True):
            page = SacredSitePage(
                title=title, slug=slug, category="Shrine & Basilica", feast_day=feast,
                date_display=date_display, locality="Fatima", country="Portugal", live=live,
            )
            cls.home.add_child(instance=page)
            return page

        cls.bruno = saint("st-bruno", "St. Bruno", "October 6", honorific="Founder of the Carthusians")
        cls.faustina = saint("st-faustina", "St. Faustina Kowalska", "October 5")
        cls.other_oct6 = saint("st-other", "St. Other Oct Six", "Oct. 6th")
        cls.stub = saint("st-stub", "St. Unpublished Stub", "October 6", live=False)
        cls.restricted = saint("st-restricted", "St. Behind A Password", "October 6")
        PageViewRestriction.objects.create(
            page=cls.restricted, restriction_type=PageViewRestriction.PASSWORD, password="secret",
        )
        cls.oct6_site = site("oct6-shrine", "Shrine of the Sixth", feast="October 6")
        cls.fatima = site("fatima", "Sanctuary of Fatima", date_display="May 13 – October 13, 1917")
        cls.corpus = site("corpus-site", "Corpus Christi Miracle", feast="Corpus Christi")
        cls.lonely = saint("st-lonely", "St. Lonely", "October 20")

    def setUp(self):
        cache.clear()

    def test_order_linked_then_saints_then_sites_then_anniversaries(self):
        today = liturgical_today(at_noon("2026-10-06"))["today"]
        bruno_cel = [c for c in today["celebrations"] if c["name"] == "Saint Bruno, Priest"][0]
        self.assertEqual(bruno_cel["page_url"], self.bruno.url)
        self.assertEqual(bruno_cel["rank_label"], "Optional Memorial")
        self.assertEqual(
            [item["title"] for item in today["items"]],
            ["St. Bruno", "St. Other Oct Six", "Shrine of the Sixth"],
        )
        self.assertEqual(today["items"][0]["meta"], "Founder of the Carthusians")
        self.assertEqual(today["items"][2]["meta"], "Fatima, Portugal")
        # Green Ordinary Time weekday, despite two (white) optional memorials.
        self.assertEqual(today["color"], "green")
        self.assertEqual(today["season"], "Ordinary Time")

    def test_unpublished_and_restricted_saints_never_appear(self):
        days = liturgical_today(at_noon("2026-10-06"))
        titles = [i["title"] for d in days.values() for i in d["items"]]
        self.assertNotIn("St. Unpublished Stub", titles)
        self.assertNotIn("St. Behind A Password", titles)
        index_titles = {e["page"]["title"] for entries in build_day_index().values() for e in entries}
        self.assertNotIn("St. Unpublished Stub", index_titles)
        self.assertNotIn("St. Behind A Password", index_titles)

    def test_anniversary_item(self):
        today = liturgical_today(at_noon("2026-05-13"))["today"]
        fatima = [i for i in today["items"] if i["title"] == "Sanctuary of Fatima"]
        self.assertEqual(len(fatima), 1)
        self.assertEqual(fatima[0]["meta"], "On this day in 1917")

    def test_movable_feast_follows_the_calendar(self):
        for iso in ("2026-06-07", "2027-05-30"):
            with self.subTest(iso=iso):
                titles = [i["title"] for i in liturgical_today(at_noon(iso))["today"]["items"]]
                self.assertIn("Corpus Christi Miracle", titles)
        titles = [i["title"] for i in liturgical_today(at_noon("2026-06-08"))["today"]["items"]]
        self.assertNotIn("Corpus Christi Miracle", titles)

    def test_upcoming_only_when_today_is_empty(self):
        days = liturgical_today(at_noon("2026-10-15"))
        self.assertEqual(days["today"]["items"], [])
        self.assertEqual(days["today"]["upcoming"]["date"], date(2026, 10, 20))
        self.assertEqual(days["today"]["upcoming"]["item"]["title"], "St. Lonely")
        self.assertIsNone(liturgical_today(at_noon("2026-10-06"))["today"]["upcoming"])

    def test_query_count_cold_and_warm_index(self):
        now = at_noon("2026-10-06")
        liturgical_today(now)  # warm Wagtail's own site-root-path cache
        cache.delete(INDEX_CACHE_KEY)
        # Cold: (PageViewRestriction + pages) for saints, then for sites.
        with self.assertNumQueries(4):
            liturgical_today(now)
        # Warm: the index comes from the cache and the calendar from disk.
        with self.assertNumQueries(0):
            liturgical_today(now)

    def test_publish_and_unpublish_clear_the_index(self):
        build_day_index()
        self.assertIsNotNone(cache.get(INDEX_CACHE_KEY))
        self.lonely.save_revision().publish()
        self.assertIsNone(cache.get(INDEX_CACHE_KEY))
        build_day_index()
        self.lonely.unpublish()
        self.assertIsNone(cache.get(INDEX_CACHE_KEY))
        titles = {e["page"]["title"] for entries in build_day_index().values() for e in entries}
        self.assertNotIn("St. Lonely", titles)


class HomePageCardTests(TestCase):
    def setUp(self):
        cache.clear()
        self.home = HomePage.objects.get(pk=Site.objects.get(is_default_site=True).root_page_id)

    def test_card_renders_when_enabled(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "data-today-card")
        self.assertContains(response, "Today in the Church")
        self.assertContains(response, 'role="tablist"')
        self.assertContains(response, "Liturgical Calendar API")
        self.assertContains(response, "js/today-in-church.js")
        self.assertNotContains(response, "waitlist")

    def test_card_absent_when_disabled(self):
        self.home.calendar_enabled = False
        self.home.save_revision().publish()
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "data-today-card")
        self.assertNotContains(response, "js/today-in-church.js")
        self.assertContains(response, "pilgrim-band-grid--two")

    def test_failure_falls_back_to_a_quiet_link(self):
        with mock.patch("home.models.liturgical_today", side_effect=RuntimeError("boom")):
            with self.assertLogs("home.models", level="ERROR"):
                response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Explore the saints")
        self.assertNotContains(response, 'role="tablist"')

    @override_settings(DEBUG=True)
    def test_debug_date_override(self):
        response = self.client.get("/", {"_date": "2026-12-08"})
        self.assertContains(response, "Tuesday, December 8")
        self.assertContains(response, "Solemnity")

    @override_settings(DEBUG=False)
    def test_date_override_ignored_without_debug(self):
        fixed = datetime(2026, 10, 7, 19, 0, tzinfo=dt_timezone.utc)
        with mock.patch("liturgy.today.timezone.now", return_value=fixed):
            response = self.client.get("/", {"_date": "2026-12-08"})
        self.assertContains(response, "Wednesday, October 7")
        self.assertNotContains(response, "Tuesday, December 8")

    def test_response_sets_no_cache_lifetime(self):
        # The card changes at midnight; nothing should let a cache hold the
        # home page HTML past that.
        response = self.client.get("/")
        self.assertFalse(response.has_header("Expires"))
        self.assertNotIn("max-age", response.get("Cache-Control", ""))
