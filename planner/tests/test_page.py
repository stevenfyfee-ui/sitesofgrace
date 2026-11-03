"""Phase 3: the Trip Planner v2 page (/plan/ with SOG_PLANNER_V2 on)."""
from decimal import Decimal
from urllib.parse import quote

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import override_settings

from pilgrims.models import SiteVisit
from planner.models import PlannerBookingLink, PlannerSettings

from .base import PlannerTestCase

ON = override_settings(SOG_PLANNER_V2="on")
GOLDEN = "/plan/?t=rome-vatican-city.4,assisi.3&d=2027-05-10&p=2&l=mid&pace=3"


class PageTestCase(PlannerTestCase):
    def setUp(self):
        super().setUp()
        cache.clear()
        self.addCleanup(cache.clear)
        self.seed_costs()
        self.rome = self.make_destination("rome-vatican-city")
        self.assisi = self.make_destination("assisi")
        self.lourdes = self.make_destination("lourdes")
        self.make_plan_page()

    def html(self, path):
        response = self.client.get(path)
        self.assertEqual(response.status_code, 200, path)
        return response.content.decode()


class SwitchTests(PageTestCase):
    @override_settings(SOG_PLANNER_V2="off")
    def test_off_renders_the_old_estimator(self):
        response = self.client.get(GOLDEN)
        self.assertTemplateUsed(response, "planner/plan_page.html")
        self.assertNotIn("Build your pilgrimage", response.content.decode())

    @override_settings(SOG_PLANNER_V2="staff")
    def test_staff_only(self):
        self.assertTemplateUsed(self.client.get(GOLDEN), "planner/plan_page.html")
        self.client.force_login(get_user_model().objects.create_user("staff", "s@example.com", "pw", is_staff=True))
        self.assertTemplateUsed(self.client.get(GOLDEN), "planner/v2/page.html")


@ON
class RenderTests(PageTestCase):
    def test_server_renders_the_plan_from_the_query_string(self):
        html = self.html(GOLDEN)
        for text in ("Build your pilgrimage", "Rome / Vatican City", "Assisi", "Arrive and settle in",
                     "Travel from Rome · about 81 mi", "Fly home from FCO", "$4,265", "$2,132",
                     "8 days, 7 nights · May 10 – May 17, 2027", "Estimated budget · 2 travelers"):
            self.assertIn(text, html)

    def test_canonical_is_the_bare_page(self):
        html = self.html(GOLDEN)
        self.assertIn('<link rel="canonical" href="http://localhost/plan/">', html)

    def test_garbage_is_dropped_never_500(self):
        html = self.html("/plan/?t=%3Cscript%3E.2,assisi.99,rome-vatican-city.2&d=2027-13-40&p=abc&l=x&pace=9")
        self.assertIn("Rome / Vatican City", html)
        self.assertNotIn("<script>.2", html)
        self.assertIn("Estimated budget · 2 travelers", html)

    def test_more_than_max_stops_is_trimmed(self):
        settings = PlannerSettings.load()
        settings.max_stops = 2
        settings.save()
        html = self.html("/plan/?t=rome-vatican-city.2,assisi.2,lourdes.2")
        self.assertNotIn("Lourdes</div>", html)
        self.assertIn("Add up to two stops", html)

    def test_controls_are_real_links_that_carry_the_plan(self):
        html = self.html(GOLDEN)
        self.assertIn('href="?t=rome-vatican-city.5,assisi.3&amp;d=2027-05-10&amp;p=2&amp;l=mid&amp;pace=3"', html)
        self.assertIn('href="?t=assisi.3,rome-vatican-city.4&amp;d=2027-05-10&amp;p=2&amp;l=mid&amp;pace=3"', html)
        self.assertIn('href="?t=rome-vatican-city.4&amp;d=2027-05-10&amp;p=2&amp;l=mid&amp;pace=3"', html)
        self.assertIn('rel="nofollow"', html)

    def test_add_uses_default_nights(self):
        self.add_day(self.lourdes, 1, "The Grotto")
        self.add_day(self.lourdes, 2, "Bernadette")
        html = self.html("/plan/?t=rome-vatican-city.4&add=lourdes")
        self.assertIn("Lourdes", html)
        self.assertIn('?t=rome-vatican-city.4,lourdes.2&amp;', html)

    def test_add_duplicate_says_so(self):
        self.assertIn("Assisi is already in your plan.", self.html("/plan/?t=assisi.2&add=assisi"))

    def test_add_past_max_stops_says_so(self):
        settings = PlannerSettings.load()
        settings.max_stops = 1
        settings.save()
        self.assertIn("One stop is the most a plan can hold.", self.html("/plan/?t=assisi.2&add=lourdes"))

    def test_search_without_javascript(self):
        html = self.html("/plan/?t=assisi.2&q=lour")
        self.assertIn('href="?t=assisi.2&amp;p=2&amp;l=mid&amp;pace=3&amp;add=lourdes"', html)

    def test_empty_plan(self):
        html = self.html("/plan/")
        self.assertIn("Add a place to start your plan.", html)
        self.assertIn("Your plan appears here once you add a place.", html)
        self.assertIn("No stops yet", html)

    def test_pills_and_degraded_stop(self):
        self.add_day(self.assisi, 1, "Francis and Clare", [self.make_site("basilica-of-st-francis")])
        html = self.html("/plan/?t=assisi.2,lourdes.2")
        self.assertIn("✓ Curated plan · 1 day", html)
        lourdes_part = html.split('data-slug="lourdes"')[1].split("</li>")[0]
        self.assertNotIn("Suggested order", lourdes_part)

    def test_site_names_link_to_their_pages(self):
        site = self.make_site("basilica-of-st-francis", title="Basilica of St. Francis")
        self.add_day(self.assisi, 1, "Francis and Clare", [site], extra="San Damiano")
        html = self.html("/plan/?t=assisi.2")
        self.assertIn(f'<a href="{site.url}">Basilica of St. Francis</a>', html)
        self.assertIn("San Damiano", html)


@ON
class SiteParamTests(PageTestCase):
    def test_linked_site_becomes_first_stop_with_chip(self):
        site = self.make_site("our-lady-of-lourdes", title="Our Lady of Lourdes", locality="Somewhere")
        self.lourdes.associated_sites.add(site)
        self.add_day(self.lourdes, 1, "The Grotto")
        self.add_day(self.lourdes, 2, "Bernadette")
        html = self.html("/plan/?t=assisi.2&site=our-lady-of-lourdes")
        self.assertIn("✦ Added from <b>Our Lady of Lourdes</b>", html)
        self.assertIn('data-query="t=lourdes.3,assisi.2&amp;p=2&amp;l=mid&amp;pace=3"', html)

    def test_locality_match_counts_as_linked(self):
        self.make_site("hermitage", title="Hermitage", locality="Assisi")
        html = self.html("/plan/?site=hermitage")
        self.assertIn("Added from <b>Hermitage</b>", html)
        self.assertIn('data-query="t=assisi.1&amp;', html)

    def test_unlinked_site(self):
        site = self.make_site("lanciano", title="Eucharistic Miracle of Lanciano", locality="Lanciano")
        html = self.html("/plan/?site=lanciano")
        self.assertIn("We can&rsquo;t plan around <b>Eucharistic Miracle of Lanciano</b> yet.", html)
        self.assertIn(f'href="{site.url}"', html)
        self.assertIn("Add a place to start your plan.", html)

    def test_non_live_site_is_ignored(self):
        site = self.make_site("hidden", title="Hidden Shrine", locality="Assisi")
        site.unpublish()
        html = self.html("/plan/?site=hidden")
        self.assertNotIn("Hidden Shrine", html)
        self.assertNotIn("Added from", html)
        self.assertIn("Add a place to start your plan.", html)

    def test_journey_preselect_for_signed_in_pilgrims(self):
        user = get_user_model().objects.create_user("pilgrim", "p@example.com", "pw")
        site = self.make_site("tomb-of-st-francis", locality="Assisi")
        SiteVisit.objects.create(owner=user, site=site, status="want_to_go")
        self.client.force_login(user)
        html = self.html("/plan/")
        self.assertIn('data-query="t=assisi.1&amp;', html)
        self.assertNotIn("From your journey", html)  # already chosen, so no chip


@ON
class SidebarTests(PageTestCase):
    def test_signed_out_save_goes_to_login_with_the_plan(self):
        html = self.html(GOLDEN)
        self.assertIn("Sign in to save this trip", html)
        nxt = quote("/plan/?t=rome-vatican-city.4,assisi.3&d=2027-05-10&p=2&l=mid&pace=3", safe="")
        self.assertIn(f'/accounts/login/?next={nxt}"', html)

    def test_signed_in_save(self):
        self.client.force_login(get_user_model().objects.create_user("pilgrim", "p@example.com", "pw"))
        self.assertIn("Save to My Pilgrimage", self.html(GOLDEN))

    def test_booking_card_off_by_default(self):
        PlannerBookingLink.objects.create(label="Flights", provider="Aviasales", url_template="https://example.com/")
        self.publish_disclosure()
        self.assertNotIn("Book the pieces", self.html(GOLDEN))

    def test_booking_card_off_when_disclosure_not_live(self):
        PlannerBookingLink.objects.create(label="Flights", provider="Aviasales", url_template="https://example.com/")
        PlannerSettings.objects.update_or_create(pk=PlannerSettings.load().pk, defaults={"show_booking_links": True})
        self.assertNotIn("Book the pieces", self.html(GOLDEN))
        self.assertNotIn("/go/planner/", self.html(GOLDEN))

    def test_booking_card_on_with_setting_and_live_disclosure(self):
        link = PlannerBookingLink.objects.create(label="Flights", provider="Aviasales", url_template="https://example.com/")
        page = self.publish_disclosure()
        PlannerSettings.objects.update_or_create(pk=PlannerSettings.load().pk, defaults={"show_booking_links": True})
        html = self.html(GOLDEN)
        self.assertIn("Book the pieces", html)
        self.assertIn(f'href="/go/planner/{link.pk}/?dest=rome-vatican-city" target="_blank" rel="sponsored nofollow noopener"', html)
        self.assertIn(f'<a href="{page.url}">Affiliate Disclosure</a>', html)

    def test_group_card_none_state_never_samples(self):
        from tours.models import GuidedPilgrimage, TourOperator, TourStop

        site = self.make_site("basilica-of-st-francis")
        self.assisi.associated_sites.add(site)
        op = TourOperator.objects.create(name="Pilgrim Tours (sample)")
        tour = GuidedPilgrimage.objects.create(title="Assisi week (sample)", operator=op, is_live=True)
        TourStop.objects.create(pilgrimage=tour, site=site)
        with override_settings(SOG_V2_ENABLED="on"):
            html = self.html("/plan/?t=assisi.2")
        self.assertIn("Guided Catholic pilgrimages that visit these places will appear here.", html)
        self.assertNotIn("(sample)", html)

    def test_estimate_notice_is_shown(self):
        from home.models import LegalNotices

        notices = LegalNotices.load()
        notices.plan_estimate = "Planning estimate only."
        notices.save()
        self.assertIn("Planning estimate only.", self.html(GOLDEN))


@ON
class BuildFragmentTests(PageTestCase):
    def test_build_returns_the_page_fragments(self):
        data = self.client.get("/plan/build/?t=rome-vatican-city.4,assisi.3&p=2&l=mid&pace=3").json()
        self.assertEqual(set(data["html"]), {"stops", "days", "route", "budget", "mbar"})
        self.assertIn("$4,265", data["html"]["budget"])
        self.assertIn("Arrive and settle in", data["html"]["days"])
        self.assertIn("Rome", data["html"]["route"])

    def test_build_add(self):
        data = self.client.get("/plan/build/?t=rome-vatican-city.4&p=2&l=mid&pace=3&add=assisi").json()
        self.assertEqual(data["query"], "t=rome-vatican-city.4,assisi.1&p=2&l=mid&pace=3")


@ON
class ReviewFixTests(PageTestCase):
    """Fixes from the Phase 3 review."""

    def test_sacred_places_counts_distinct_sites(self):
        grotto = self.make_site("our-lady-of-lourdes", title="Our Lady of Lourdes")
        self.add_day(self.lourdes, 1, "The Grotto", [grotto])
        self.add_day(self.lourdes, 2, "Bernadette", [grotto])
        html = self.html("/plan/?t=lourdes.3")
        self.assertIn("1 sacred place · fly into LDE", html)
        self.assertNotIn("2 sacred places", html)

    def test_only_the_first_stop_flies_in(self):
        html = self.html(GOLDEN)
        rome = html.split('data-slug="rome-vatican-city"')[1].split("</li>")[0]
        assisi = html.split('data-slug="assisi"')[1].split("</li>")[0]
        self.assertIn("fly into FCO", rome)
        self.assertNotIn("fly into", assisi)
        self.assertIn("nearest airport PEG", assisi)
        first = self.html("/plan/?t=assisi.2,rome-vatican-city.2")
        self.assertIn("fly into FCO · nearest airport PEG", first.split('data-slug="assisi"')[1].split("</li>")[0])

    def test_at_most_two_cut_rows_then_a_summary_line(self):
        for n in range(1, 6):
            self.add_day(self.assisi, n, f"Assisi day {n}")
        html = self.html("/plan/?t=rome-vatican-city.1,assisi.1")
        self.assertIn("Assisi day 1", html)
        self.assertIn("Assisi day 2", html)
        self.assertIn("Assisi day 3", html)
        self.assertNotIn("Assisi day 4", html)
        self.assertNotIn("Assisi day 5", html)
        self.assertEqual(html.count("pv2-day-cut"), 2)
        self.assertIn('<p class="pv2-cut-more">+2 more days of sacred places · add nights to include them</p>', html)
        self.assertIn('pv2-print-only">+4 more days of sacred places · add nights to include them</p>', html)

    def test_journey_row_capped_and_popular_skips_it(self):
        user = get_user_model().objects.create_user("pilgrim", "p@example.com", "pw")
        for slug in ("fatima", "medjugorje", "jerusalem", "knock", "dublin"):
            dest = self.make_destination(slug)
            site = self.make_site(f"site-in-{slug}")
            dest.associated_sites.add(site)
            SiteVisit.objects.create(owner=user, site=site, status="want_to_go")
        self.client.force_login(user)
        html = self.html("/plan/?t=lourdes.2")
        journey = html.split("From your journey:")[1].split("</div>")[0]
        self.assertEqual(journey.count("data-add="), 4)
        popular = html.split("Popular:")[1].split("</div>")[0]
        for slug in ("fatima", "medjugorje", "jerusalem", "lourdes"):
            self.assertNotIn(f'data-add="{slug}"', popular)
        self.assertIn('data-add="rome-vatican-city"', popular)

    def test_print_footer_carries_the_share_url(self):
        html = self.html(GOLDEN)
        self.assertIn("Sites of Grace · sitesofgrace.com · Reopen this plan: <span data-share-url>"
                      "http://localhost/plan/?t=rome-vatican-city.4,assisi.3&amp;d=2027-05-10&amp;p=2&amp;l=mid&amp;pace=3"
                      "</span>", html)


@ON
class SearchRankingTests(PageTestCase):
    def test_destinations_then_plannable_sites_then_the_rest(self):
        self.make_site("aaa-shrine-of-lourdes-replica", title="Aaa Lourdes Replica", locality="Nowhere")
        linked = self.make_site("our-lady-of-lourdes", title="Our Lady of Lourdes", locality="Somewhere")
        self.lourdes.associated_sites.add(linked)
        results = self.client.get("/plan/search/?q=lourdes").json()["results"]
        self.assertEqual([(r["kind"], r.get("slug"), r["dest"]) for r in results], [
            ("destination", None, "lourdes"),
            ("site", "our-lady-of-lourdes", "lourdes"),
            ("site", "aaa-shrine-of-lourdes-replica", None),
        ])
