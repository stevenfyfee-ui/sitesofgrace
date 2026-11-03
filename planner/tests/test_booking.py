"""Phase 5: booking links, built and switched off.

The booking card and /go/planner/<id>/ need BOTH Settings > Trip planner >
show_booking_links AND a live Affiliate Disclosure page, checked every time
(not only when the setting is saved), plus SOG_PLANNER_V2 for the request.
"""
from urllib.parse import parse_qs, urlparse

from django.core.cache import cache
from django.test import override_settings

from planner.models import PlannerBookingClickDaily, PlannerBookingLink, PlannerSettings

from .base import PlannerTestCase

PLAN = "/plan/?t=assisi.3,rome-vatican-city.2&d=2027-05-10&p=2&l=mid&pace=3"
DISCLOSURE_LINE = ("Some links may earn Sites of Grace a commission at no extra cost to you. "
                   '<a href="{url}">Affiliate Disclosure</a>')


@override_settings(SOG_PLANNER_V2="on")
class BookingTestCase(PlannerTestCase):
    def setUp(self):
        super().setUp()
        cache.clear()
        self.addCleanup(cache.clear)
        self.seed_costs()
        self.assisi = self.make_destination("assisi")
        self.make_destination("rome-vatican-city")
        self.make_plan_page()
        self.flights = PlannerBookingLink.objects.create(
            label="Flights to {iata}", provider="Aviasales", sort_order=1,
            url_template="https://www.aviasales.com/search?destination={iata}&marker=123&sub_id={sub_id}&d={dest_slug}",
        )
        self.esim = PlannerBookingLink.objects.create(
            label="eSIM for your phone", provider="Airalo", sort_order=2, url_template="https://example.com/esim?s={sub_id}",
        )

    def set_show(self, on):
        # Saved straight to the table, as if it had been switched on while the
        # disclosure was live; clean() is tested in test_models.BookingGateTests.
        PlannerSettings.objects.update_or_create(pk=PlannerSettings.load().pk, defaults={"show_booking_links": on})

    def go(self, link=None, dest="assisi"):
        return self.client.get(f"/go/planner/{(link or self.flights).pk}/?dest={dest}")

    def assert_off(self):
        html = self.client.get(PLAN).content.decode()
        self.assertNotIn("Book the pieces", html)
        self.assertNotIn("/go/planner/", html)
        self.assertNotIn("commission", html)
        self.assertEqual(self.go().status_code, 404)
        self.assertEqual(self.go(self.esim).status_code, 404)
        self.assertFalse(PlannerBookingClickDaily.objects.exists())


class OffTests(BookingTestCase):
    def test_off_when_show_booking_links_is_false_even_with_live_disclosure(self):
        self.publish_disclosure()
        self.set_show(False)
        self.assert_off()

    def test_off_when_true_but_disclosure_not_published(self):
        self.set_show(True)
        self.assert_off()

    def test_off_when_true_but_disclosure_is_a_draft(self):
        self.publish_disclosure(live=False)
        self.set_show(True)
        self.assert_off()

    def test_off_again_when_disclosure_is_unpublished_later(self):
        page = self.publish_disclosure()
        self.set_show(True)
        self.assertEqual(self.go().status_code, 302)
        page.unpublish()
        PlannerBookingClickDaily.objects.all().delete()
        self.assert_off()

    def test_off_when_the_planner_switch_is_off(self):
        self.publish_disclosure()
        self.set_show(True)
        with override_settings(SOG_PLANNER_V2="off"):
            self.assertEqual(self.go().status_code, 404)
        with override_settings(SOG_PLANNER_V2="staff"):
            self.assertEqual(self.go().status_code, 404)
        self.assertFalse(PlannerBookingClickDaily.objects.exists())

    def test_default_install_is_off(self):
        self.assertFalse(PlannerSettings.load().show_booking_links)
        self.assert_off()


class OnTests(BookingTestCase):
    def setUp(self):
        super().setUp()
        self.disclosure = self.publish_disclosure()
        self.set_show(True)

    def test_card_with_disclosure_exactly_as_in_the_mockup(self):
        html = self.client.get(PLAN).content.decode()
        self.assertIn('<p class="pv2-eyebrow">Book the pieces</p>', html)
        self.assertIn(f'href="/go/planner/{self.flights.pk}/?dest=assisi" target="_blank" '
                      f'rel="sponsored nofollow noopener"><span>Flights to FCO</span><small>Aviasales</small></a>', html)
        self.assertIn(DISCLOSURE_LINE.format(url=self.disclosure.url), html)

    def test_redirect_fills_the_template_from_the_first_stop(self):
        response = self.go()
        self.assertEqual(response.status_code, 302)
        target = urlparse(response["Location"])
        self.assertEqual((target.scheme, target.netloc, target.path), ("https", "www.aviasales.com", "/search"))
        self.assertEqual(parse_qs(target.query), {"destination": ["FCO"], "marker": ["123"], "sub_id": ["assisi"],
                                                  "d": ["assisi"]})
        self.assertEqual(response["Cache-Control"], "no-store")

    def test_click_is_counted_without_anything_about_the_visitor(self):
        for _ in range(3):
            self.go()
        self.go(self.esim)
        rows = list(PlannerBookingClickDaily.objects.values_list("link__provider", "destination__slug", "count"))
        self.assertEqual(sorted(rows), [("Airalo", "assisi", 1), ("Aviasales", "assisi", 3)])
        fields = {f.name for f in PlannerBookingClickDaily._meta.get_fields()}
        self.assertEqual(fields, {"id", "link", "destination", "date", "count"})

    def test_redirect_sets_no_cookie(self):
        response = self.go()
        self.assertEqual(response.cookies, {})
        self.assertNotIn("Set-Cookie", response)

    def test_inactive_link_unknown_destination_and_post_are_refused(self):
        self.esim.active = False
        self.esim.save()
        self.assertEqual(self.go(self.esim).status_code, 404)
        self.assertEqual(self.go(dest="atlantis").status_code, 404)
        self.assertEqual(self.client.get(f"/go/planner/{self.flights.pk}/").status_code, 404)
        self.assertEqual(self.client.post(f"/go/planner/{self.flights.pk}/?dest=assisi").status_code, 405)
        self.assertNotIn("eSIM for your phone", self.client.get(PLAN).content.decode())

    def test_placeholder_values_are_url_encoded(self):
        link = PlannerBookingLink(label="x", provider="x", url_template="https://example.com/?s={sub_id}&i={iata}")
        self.assertEqual(link.fill("a b&c", "F/O"), "https://example.com/?s=a%20b%26c&i=F%2FO")

    def test_no_card_for_an_empty_plan(self):
        self.assertNotIn("Book the pieces", self.client.get("/plan/").content.decode())


class AdminSettingTests(BookingTestCase):
    """Through the real Wagtail settings form, not just clean()."""

    def setUp(self):
        super().setUp()
        from django.contrib.auth import get_user_model

        self.client.force_login(get_user_model().objects.create_superuser("admin", "admin@example.com", "pw"))
        response = self.client.get("/admin/settings/planner/plannersettings/")
        self.url = response.url if response.status_code == 302 else "/admin/settings/planner/plannersettings/"

    def post(self, show):
        data = {"max_stops": "6"}
        if show:
            data["show_booking_links"] = "on"
        return self.client.post(self.url, data)

    def test_admin_refuses_without_live_disclosure(self):
        response = self.post(True)
        self.assertEqual(response.status_code, 200)
        self.assertIn("Publish the Affiliate Disclosure page before turning on booking links.", response.content.decode())
        self.assertFalse(PlannerSettings.load().show_booking_links)

    def test_admin_allows_with_live_disclosure(self):
        self.publish_disclosure()
        self.assertEqual(self.post(True).status_code, 302)
        self.assertTrue(PlannerSettings.load().show_booking_links)
