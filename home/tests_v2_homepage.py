"""Phase 5 of Pilgrimage Platform v2: the homepage.

Protects: the band order with v2 on; the three-column band (with Today in
the Church) and News absent with v2 on and present with it off; hub tiles
only for live hubs, in the chosen order else by title; upcoming feasts that
only link live pages, keep to the 60-day window and the cap of 4, and hide
when nothing matches; and ?_date= honored only in DEBUG.
"""
from datetime import date, datetime

from django.core.cache import cache
from django.test import RequestFactory, override_settings
from django.utils import timezone
from wagtail.models import Page, Site
from wagtail.test.utils import WagtailPageTestCase

from catalog.models import SacredSitePage, SaintPage
from destinations.models import DestinationHubPage, DestinationIndexPage
from home.models import FeatureCard, HomeDestinationTile, HomePage, Partner
from liturgy import calendar as litcal
from liturgy.today import upcoming_feasts
from news.models import NewsItem, NewsSource

V2_ON = override_settings(SOG_V2_ENABLED="on")
OCT_21 = timezone.make_aware(datetime(2026, 10, 21, 12, 0))


class V2HomeTestCase(WagtailPageTestCase):
    def setUp(self):
        Site.clear_site_root_paths_cache()
        cache.clear()
        litcal._events_by_date.cache_clear()
        root = Page.get_first_root_node()
        self.home = HomePage(title="Home", slug="v2-home")
        root.add_child(instance=self.home)
        Site.objects.filter(is_default_site=True).update(root_page=self.home)
        # .update() skips the signal that clears Wagtail's cached site root
        # paths, so clear it now and again afterwards -- otherwise the next
        # app's tests see this test's (rolled-back) home page.
        Site.clear_site_root_paths_cache()
        self.addCleanup(Site.clear_site_root_paths_cache)
        FeatureCard.objects.create(page=self.home, title="Mary, Our Mother", blurb="Apparitions", link_url="/explore/")
        Partner.objects.create(page=self.home, name="Partner Parish (sample)")
        self.home = HomePage.objects.get(pk=self.home.pk)

    def html(self, query=""):
        return self.client.get("/" + query).content.decode()

    def saint(self, title, feast_day, live=True):
        saint = SaintPage(title=title, slug=title.lower().replace(" ", "-").replace(".", ""), feast_day=feast_day)
        self.home.add_child(instance=saint)
        if not live:
            saint.unpublish()
        return saint

    def hub(self, title, live=True, index=None):
        if index is None:
            index = DestinationIndexPage.objects.first()
            if index is None:
                index = DestinationIndexPage(title="Destinations", slug="destinations")
                self.home.add_child(instance=index)
        hub = DestinationHubPage(title=title, slug=title.lower().replace(" ", "-").replace("&", "and"),
                                 tile_caption=f"{title} caption")
        index.add_child(instance=hub)
        if not live:
            hub.unpublish()
        return hub


@V2_ON
class BandOrderTests(V2HomeTestCase):
    def test_order_with_v2_on(self):
        self.hub("Rome & Vatican City")
        self.saint("St. John Paul II", "October 22")
        html = self.html("?_date=2026-10-21")
        positions = [html.index(marker) for marker in (
            'class="hero', 'class="feature-cards"', "v2-home-destinations", "v2-home-feasts", "partners-band",
        )]
        self.assertEqual(positions, sorted(positions))
        self.assertIn("site-footer", html)

    def test_removed_bands_are_gone_with_v2_on(self):
        source = NewsSource.objects.create(name="Source (sample)", feed_url="https://example.com/feed")
        NewsItem.objects.create(source=source, title="News (sample)", guid="g1", link="https://example.com/n",
                                published_at=timezone.now())
        html = self.html()
        for marker in ("pilgrim-band", "news-feed", "News (sample)", "today-in-church", "Featured Sites and Saints"):
            self.assertNotIn(marker, html)
        self.assertIn("Mary, Our Mother", html, "the four image cards stay")


class SwitchOffTests(V2HomeTestCase):
    @override_settings(SOG_V2_ENABLED="off")
    def test_removed_bands_present_and_new_bands_absent_with_v2_off(self):
        source = NewsSource.objects.create(name="Source (sample)", feed_url="https://example.com/feed")
        NewsItem.objects.create(source=source, title="News (sample)", guid="g2", link="https://example.com/n",
                                published_at=timezone.now())
        self.hub("Rome & Vatican City")
        html = self.html()
        self.assertIn("pilgrim-band", html)
        self.assertIn("News (sample)", html)
        self.assertNotIn("v2-home-", html)


@V2_ON
class DestinationTileTests(V2HomeTestCase):
    def test_only_live_hubs_by_title_then_chosen_order(self):
        self.hub("Portugal")
        assisi = self.hub("Assisi & Umbria")
        self.hub("Draft Hub", live=False)
        html = self.html()
        band = html.split("v2-home-destinations")[1].split("</section>")[0]
        self.assertLess(band.index("Assisi &amp; Umbria"), band.index("Portugal"))
        self.assertNotIn("Draft Hub", band)
        self.assertIn("Assisi &amp; Umbria caption", band)
        self.assertIn("All destinations", band)
        portugal = DestinationHubPage.objects.get(title="Portugal")
        HomeDestinationTile.objects.create(page=self.home, hub=portugal, sort_order=0)
        HomeDestinationTile.objects.create(page=self.home, hub=assisi, sort_order=1)
        band = self.html().split("v2-home-destinations")[1].split("</section>")[0]
        self.assertLess(band.index("Portugal"), band.index("Assisi &amp; Umbria"))

    def test_band_hides_with_no_live_hub(self):
        self.hub("Draft Hub", live=False)
        self.assertNotIn("v2-home-destinations", self.html())


class UpcomingFeastTests(V2HomeTestCase):
    def test_window_cap_live_pages_and_today_tomorrow(self):
        self.saint("St. John Paul II", "October 22")            # tomorrow
        self.saint("St. John of Capestrano", "October 23")
        self.saint("St. Anthony Mary Claret", "October 24")
        self.saint("Sts. Simon and Jude", "October 28")
        self.saint("St. Martin of Tours", "November 11")        # 5th: over the cap
        self.saint("St. Agnes", "January 21")                    # outside 60 days
        feasts = upcoming_feasts(now=OCT_21)
        self.assertEqual(len(feasts), 4)
        self.assertEqual([f["place"]["title"] for f in feasts],
                         ["St. John Paul II", "St. John of Capestrano", "St. Anthony Mary Claret", "Sts. Simon and Jude"])
        self.assertEqual(feasts[0]["when"], "Tomorrow")
        self.assertEqual(feasts[0]["rank_label"], "Optional Memorial")
        self.assertEqual((feasts[0]["month"], feasts[0]["day_number"]), ("OCT", 22))
        self.assertFalse(any(f["place"]["title"] == "St. Agnes" for f in upcoming_feasts(now=OCT_21, limit=10)))

    def test_only_live_pages(self):
        self.saint("St. John Paul II", "October 22", live=False)
        self.assertEqual(upcoming_feasts(now=OCT_21), [])

    def test_a_site_is_preferred_over_the_saint_page(self):
        saint = self.saint("St. John Paul II", "October 22")
        site = SacredSitePage(title="Tomb of St. John Paul II (sample)", slug="jp2-tomb", category="Saints & Tombs",
                              associated_saint=saint)
        self.home.add_child(instance=site)
        cache.clear()
        feasts = upcoming_feasts(now=OCT_21, limit=1)
        self.assertEqual(feasts[0]["place"]["title"], "Tomb of St. John Paul II (sample)")
        self.assertEqual(feasts[0]["place"]["url"], SacredSitePage.objects.get(pk=site.pk).url)

    @V2_ON
    @override_settings(DEBUG=True)
    def test_band_renders_and_hides_when_empty(self):
        self.assertNotIn("v2-home-feasts", self.html("?_date=2026-10-21"))
        self.saint("St. John Paul II", "October 22")
        cache.clear()
        html = self.html("?_date=2026-10-21")
        band = html.split("v2-home-feasts")[1].split("</section>")[0]
        self.assertIn("Saint John Paul II, Pope", band)
        self.assertIn("<strong>Tomorrow</strong>", band)
        self.assertIn('href="/st-john-paul-ii/"', band)

    @V2_ON
    def test_band_respects_upcoming_enabled(self):
        self.saint("St. John Paul II", "October 22")
        HomePage.objects.filter(pk=self.home.pk).update(upcoming_enabled=False)
        with override_settings(DEBUG=True):
            self.assertNotIn("v2-home-feasts", self.html("?_date=2026-10-21"))


class DateOverrideTests(V2HomeTestCase):
    def test_date_override_only_in_debug(self):
        request = RequestFactory().get("/?_date=2026-12-07")
        with override_settings(DEBUG=False):
            self.assertIsNone(HomePage._calendar_now(request))
        with override_settings(DEBUG=True):
            self.assertEqual(timezone.localtime(HomePage._calendar_now(request)).date(), date(2026, 12, 7))
