"""Phase 2 of Pilgrimage Platform v2: guided pilgrimages on site pages.

Protects: one tour record appearing on every site it stops at; the "None"
state (no bar item, single overview card, compact card, the elsewhere list
labeled as not including this site); interest create / idempotent /
sign-in redirect / deletion cascade; the click redirect counting without
storing anything about the visitor; past departures never rendering; the
rel attributes; and the switch hiding all of it.
"""
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import override_settings

from catalog.models import SacredSitePage
from catalog.tests_v2_site import V2SiteTestCase
from tours.models import (
    PENDING_INTEREST_KEY, PENDING_INTEREST_SECONDS, GuidedPilgrimage, TourClickDaily, TourDeparture,
    TourInterest, TourOperator, TourStop,
)

V2_ON = override_settings(SOG_V2_ENABLED="on")


class ToursTestCase(V2SiteTestCase):
    def setUp(self):
        self.operator = TourOperator.objects.create(name="Operator A (sample)")

    def make_tour(self, title, sites, place_names=(), departures=(), **fields):
        fields.setdefault("is_live", True)
        fields.setdefault("booking_url", "https://example.com/tour")
        tour = GuidedPilgrimage(title=title, operator=self.operator, **fields)
        tour.stops = [TourStop(site=s) for s in sites] + [TourStop(place_name=p) for p in place_names]
        tour.departures = [TourDeparture(**d) for d in departures]
        tour.save()
        return tour

    def section(self, html):
        return html.split('id="guided-pilgrimages"')[1].split("</section>")[0]


@V2_ON
class TourCardTests(ToursTestCase):
    def test_one_tour_shows_on_every_linked_site(self):
        lourdes = self.make_site(slug="t-lourdes", title="Lourdes Test", country="France")
        fatima = self.make_site(slug="t-fatima", title="Fatima Test", country="Portugal")
        self.make_tour("Lourdes & Fatima (sample)", [lourdes, fatima], place_names=["Lisbon"],
                       duration_days=10, mass="daily", confession_offered="yes")
        for site in (lourdes, fatima):
            html = self.html(site)
            section = self.section(html)
            self.assertIn(f"Guided pilgrimages that include {site.title}", section)
            self.assertIn("Lourdes &amp; Fatima (sample)", section)
            self.assertIn("Lisbon", section)
            self.assertIn("Daily Mass; Confession offered", section)
            self.assertIn("Cancellation terms set by the operator", section)
            self.assertIn('data-section-link="guided-pilgrimages"', html)
            self.assertIn("Join a guided pilgrimage", html)
        self.assertIn(f'<a href="{SacredSitePage.objects.get(pk=fatima.pk).url}">Fatima Test</a>',
                      self.section(self.html(lourdes)))

    def test_soonest_departure_first_max_three_and_draft_tours_hidden(self):
        site = self.make_site(slug="t-many")
        today = date.today()
        for i, offset in enumerate([300, 30, 120, 60]):
            self.make_tour(f"Tour {i}", [site], departures=[{"depart_date": today + timedelta(days=offset)}])
        self.make_tour("Hidden draft", [site], is_live=False)
        titles = [t.title for t in SacredSitePage.objects.get(pk=site.pk).guided_pilgrimages]
        self.assertEqual(titles, ["Tour 1", "Tour 3", "Tour 2"])

    def test_past_departures_never_render(self):
        site = self.make_site(slug="t-past")
        past = date.today() - timedelta(days=10)
        future = date.today() + timedelta(days=40)
        self.make_tour("Dated", [site], departures=[
            {"depart_date": past, "price": Decimal("999")},
            {"depart_date": future, "price": Decimal("2500"), "currency": "USD", "airfare_included": True},
        ])
        section = self.section(self.html(site))
        self.assertNotIn(f"{past:%b} {past.day}, {past.year}", section)
        self.assertNotIn("999", section)
        self.assertIn(f"Next {future:%b} {future.day}, {future.year}", section)
        self.assertIn("From $2,500 · Airfare included", section)

    def test_rel_attributes(self):
        site = self.make_site(slug="t-rel")
        affiliate = self.make_tour("Affiliate tour", [site], is_affiliate_link=True)
        plain = self.make_tour("Plain tour", [site], is_affiliate_link=False)
        section = self.section(self.html(site))
        self.assertIn(f'/go/tour/{affiliate.pk}/?from={site.pk}" target="_blank" rel="sponsored nofollow noopener"',
                      section)
        self.assertIn(f'/go/tour/{plain.pk}/?from={site.pk}" target="_blank" rel="nofollow noopener"', section)
        # The "tour_links" legal notice; its Affiliate Disclosure link waits for that page to be live.
        self.assertIn("<strong>Affiliate disclosure:</strong> Some pilgrimage-tour links on this page", section)
        self.assertNotIn('href="/affiliate-disclosure/"', section)

    def test_blank_tour_notice_falls_back_to_the_earlier_sentence(self):
        from home.models import LegalNotices

        site = self.make_site(slug="t-notice-blank")
        self.make_tour("Notice tour", [site])
        notices = LegalNotices.load()
        notices.tour_links = ""
        notices.save()
        section = self.section(self.html(site))
        self.assertIn("handled by the tour operator, not by Sites of Grace. Some links may earn us a commission.",
                      section)


@V2_ON
class NoneStateTests(ToursTestCase):
    def test_none_state(self):
        here = self.make_site(slug="t-salette", title="La Salette Test", country="France")
        elsewhere = self.make_site(slug="t-lisieux", title="Lisieux Test", country="France")
        other_country = self.make_site(slug="t-rome", title="Rome Test", country="Italy")
        self.make_tour("Paris & Lisieux (sample)", [elsewhere], duration_days=8)
        self.make_tour("Rome only", [other_country])
        html = self.html(here)
        self.assertNotIn('data-section-link="guided-pilgrimages"', html)
        self.assertNotIn("Join a guided pilgrimage", html)
        self.assertIn("v2-choice--wide", html)
        section = self.section(html)
        self.assertIn("Prefer to travel with a group?", section)
        self.assertIn("No guided pilgrimages that include La Salette Test are listed yet.", section)
        self.assertIn("Guided pilgrimages elsewhere in France", section)
        self.assertIn("These trips don&rsquo;t include La Salette Test.", section)
        self.assertIn("Paris &amp; Lisieux (sample) · 8 days", section)
        self.assertNotIn("Rome only", section)
        self.assertIn("We use this to ask Catholic tour operators to add trips.", section)

    def test_country_qualifiers_still_match(self):
        here = self.make_site(slug="t-q-here", country="Italy")
        tomb = self.make_site(slug="t-q-tomb", country="Italy (tomb)")
        self.make_tour("Italy tour", [tomb])
        self.assertIn("Guided pilgrimages elsewhere in Italy", self.section(self.html(here)))


@V2_ON
class InterestTests(ToursTestCase):
    def test_create_is_idempotent_and_shows_done(self):
        site = self.make_site(slug="t-int")
        user = get_user_model().objects.create_user("pilgrim", "p@example.com", "pw")
        self.client.force_login(user)
        self.assertIn("I&rsquo;m interested in a group pilgrimage here", self.html(site))
        for _ in range(2):
            response = self.client.post("/tours/interest/", {"site": site.pk})
            self.assertEqual(response.status_code, 302)
            self.assertTrue(response["Location"].endswith("#guided-pilgrimages"))
        self.assertEqual(TourInterest.objects.filter(user=user, site=site).count(), 1)
        self.assertIn("You&rsquo;ve told us you&rsquo;re interested", self.html(site))

    def sign_in(self, email="anon@example.com"):
        """Through allauth's real form, so the session (and the pending
        interest in it) is the one the visitor already had."""
        from allauth.account.models import EmailAddress

        user = get_user_model().objects.create_user(email.split("@")[0], email, "a-long-password-1")
        EmailAddress.objects.create(user=user, email=email, verified=True, primary=True)
        response = self.client.post("/accounts/login/", {"login": email, "password": "a-long-password-1"})
        self.assertEqual(response.status_code, 302, "sign-in should succeed")
        return user

    def test_signed_out_click_registers_interest_on_sign_in(self):
        site = self.make_site(slug="t-int-anon")
        page_url = SacredSitePage.objects.get(pk=site.pk).url
        html = self.html(site)
        self.assertIn('action="/tours/interest/"', self.section(html))
        response = self.client.post("/tours/interest/", {"site": site.pk})
        self.assertEqual(response.status_code, 302)
        self.assertIn(f"/accounts/login/?next={page_url}%23guided-pilgrimages",
                      response["Location"])
        self.assertEqual(TourInterest.objects.count(), 0)
        user = self.sign_in()
        self.assertEqual(TourInterest.objects.filter(user=user, site=site).count(), 1)
        self.assertNotIn(PENDING_INTEREST_KEY, self.client.session)
        self.assertIn("You&rsquo;ve told us you&rsquo;re interested", self.html(site))

    def test_pending_interest_is_dropped_if_they_do_not_sign_in_soon(self):
        site = self.make_site(slug="t-int-stale")
        self.client.post("/tours/interest/", {"site": site.pk})
        session = self.client.session
        session[PENDING_INTEREST_KEY]["at"] -= PENDING_INTEREST_SECONDS + 1
        session.save()
        self.sign_in("late@example.com")
        self.assertEqual(TourInterest.objects.count(), 0)
        self.assertNotIn(PENDING_INTEREST_KEY, self.client.session)

    def test_a_plain_link_never_creates_interest(self):
        site = self.make_site(slug="t-int-get")
        self.assertEqual(self.client.get(f"/tours/interest/?site={site.pk}").status_code, 405)
        self.sign_in("get@example.com")
        self.assertEqual(self.client.get(f"/tours/interest/?site={site.pk}").status_code, 405)
        self.assertEqual(TourInterest.objects.count(), 0)

    def test_deleting_the_account_removes_interest(self):
        site = self.make_site(slug="t-int-del")
        user = get_user_model().objects.create_user("gone", "g@example.com", "pw")
        TourInterest.objects.create(user=user, site=site)
        user.delete()
        self.assertEqual(TourInterest.objects.count(), 0)

    def test_bad_site_id_is_404(self):
        user = get_user_model().objects.create_user("p2", "p2@example.com", "pw")
        self.client.force_login(user)
        self.assertEqual(self.client.post("/tours/interest/", {"site": "abc"}).status_code, 404)


@V2_ON
class ClickRedirectTests(ToursTestCase):
    def test_redirect_counts_per_day_and_stores_nothing_about_the_visitor(self):
        site = self.make_site(slug="t-go")
        tour = self.make_tour("Go tour", [site], booking_url="https://example.com/book")
        for _ in range(3):
            response = self.client.get(f"/go/tour/{tour.pk}/?from={site.pk}", REMOTE_ADDR="203.0.113.9")
            self.assertEqual(response.status_code, 302)
            self.assertEqual(response["Location"], "https://example.com/book")
            self.assertFalse(response.cookies, "the redirect must not set any cookie")
        row = TourClickDaily.objects.get()
        self.assertEqual((row.pilgrimage_id, row.page_id, row.date, row.count), (tour.pk, site.pk, date.today(), 3))
        stored = {f.name for f in TourClickDaily._meta.get_fields()}
        self.assertEqual(stored, {"id", "pilgrimage", "page", "date", "count"})

    def test_unknown_or_draft_tour_is_404(self):
        site = self.make_site(slug="t-go-404")
        draft = self.make_tour("Draft", [site], is_live=False)
        self.assertEqual(self.client.get(f"/go/tour/{draft.pk}/").status_code, 404)
        self.assertEqual(self.client.get("/go/tour/999999/").status_code, 404)
        self.assertEqual(TourClickDaily.objects.count(), 0)

    def test_bad_from_value_still_redirects_without_a_page(self):
        site = self.make_site(slug="t-go-from")
        tour = self.make_tour("From tour", [site])
        self.assertEqual(self.client.get(f"/go/tour/{tour.pk}/?from=javascript:1").status_code, 302)
        self.assertIsNone(TourClickDaily.objects.get().page_id)


class SwitchOffTests(ToursTestCase):
    @override_settings(SOG_V2_ENABLED="off")
    def test_switch_off_hides_everything(self):
        site = self.make_site(slug="t-off")
        tour = self.make_tour("Off tour", [site])
        html = self.html(site)
        self.assertNotIn("Off tour", html)
        self.assertNotIn("guided-pilgrimages", html)
        self.assertEqual(self.client.get(f"/go/tour/{tour.pk}/").status_code, 404)
        user = get_user_model().objects.create_user("p3", "p3@example.com", "pw")
        self.client.force_login(user)
        self.assertEqual(self.client.post("/tours/interest/", {"site": site.pk}).status_code, 404)
        self.assertEqual(TourClickDaily.objects.count() + TourInterest.objects.count(), 0)


class AdminReportTests(ToursTestCase):
    def test_reports_are_staff_only_and_count(self):
        site = self.make_site(slug="t-report", title="Report Site")
        tour = self.make_tour("Report tour", [site])
        TourClickDaily.objects.create(pilgrimage=tour, page=site, date=date.today(), count=4)
        TourInterest.objects.create(user=get_user_model().objects.create_user("u", "u@example.com", "pw"), site=site)
        admin = get_user_model().objects.create_superuser("admin", "a@example.com", "pw")
        self.client.force_login(admin)
        interest = self.client.get("/admin/reports/tour-interest/").content.decode()
        self.assertIn("Report Site", interest)
        from catalog.models import LodgingClickDaily, SiteLodging

        lodging = SiteLodging.objects.create(page=site, name="Report hotel", kind="hotel",
                                             latitude=Decimal("1"), longitude=Decimal("1"))
        LodgingClickDaily.objects.create(lodging=lodging, page=site, date=date.today(), count=6)
        LodgingClickDaily.objects.create(lodging=lodging, page=site, date=date.today() - timedelta(days=60), count=50)
        clicks = self.client.get("/admin/reports/outbound-clicks/?days=90").content.decode()
        self.assertIn("Outbound clicks", clicks)
        self.assertIn("<h2>Tours</h2>", clicks)
        self.assertIn("<h2>Lodging</h2>", clicks)
        self.assertIn("Report tour", clicks)
        self.assertIn("Report hotel", clicks)
        self.assertIn("<td>4</td>", clicks)
        self.assertIn("<td>56</td>", clicks)
        last_30 = self.client.get("/admin/reports/outbound-clicks/").content.decode()
        self.assertIn("<td>6</td>", last_30)
        self.assertNotIn("<td>56</td>", last_30)
        self.assertNotIn("u@example.com", interest)

    def test_snippet_admin_lists_and_forms_render(self):
        site = self.make_site(slug="t-admin")
        tour = self.make_tour("Admin tour", [site], departure_months=[5, 9])
        admin = get_user_model().objects.create_superuser("admin2", "a2@example.com", "pw")
        self.client.force_login(admin)
        listing = self.client.get("/admin/snippets/tours/guidedpilgrimage/?is_live=true&q=Admin")
        self.assertEqual(listing.status_code, 200)
        self.assertIn("Admin tour", listing.content.decode())
        self.assertIn("Last verified on", listing.content.decode())
        edit = self.client.get(f"/admin/snippets/tours/guidedpilgrimage/edit/{tour.pk}/").content.decode()
        self.assertIn('type="checkbox" name="departure_months" value="5"', edit)
        self.assertEqual(self.client.get("/admin/snippets/tours/touroperator/").status_code, 200)
