"""Phase 4: saved trips, My Trips, sharing and the shared view."""
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, override_settings

from planner import trips as trips_module
from planner.models import Trip, TripStop

from .base import PlannerTestCase

ON = override_settings(SOG_PLANNER_V2="on")
PLAN_Q = "t=rome-vatican-city.4,assisi.3&d=2027-05-10&p=2&l=mid&pace=3"
JSON = {"HTTP_X_REQUESTED_WITH": "fetch", "HTTP_ACCEPT": "application/json"}


class TripTestCase(PlannerTestCase):
    def setUp(self):
        super().setUp()
        cache.clear()
        self.addCleanup(cache.clear)
        self.seed_costs()
        self.rome = self.make_destination("rome-vatican-city")
        self.assisi = self.make_destination("assisi")
        self.make_plan_page()
        User = get_user_model()
        self.owner = User.objects.create_user("johndoe", "john.doe@example.com", "pw", first_name="John")
        self.other = User.objects.create_user("janedoe", "jane@example.com", "pw")
        self.staff = User.objects.create_user("staffer", "staff@example.com", "pw", is_staff=True, is_superuser=True)

    def save(self, q=PLAN_Q, trip=None, **extra):
        data = {"q": q}
        if trip:
            data["trip"] = trip
        return self.client.post("/plan/trips/save/", data, **extra)

    def make_trip(self, owner=None, shared=False):
        trip = Trip.objects.create(owner=owner or self.owner, title="Rome & Assisi", start_date=date(2027, 5, 10),
                                   party=2, tier="mid", pace=3, share_token="tok-" + "x" * 18 if shared else None)
        TripStop.objects.create(trip=trip, destination=self.rome, nights=4, sort_order=0)
        TripStop.objects.create(trip=trip, destination=self.assisi, nights=3, sort_order=1)
        return trip


@ON
class SaveTests(TripTestCase):
    def test_save_creates_a_private_trip(self):
        self.client.force_login(self.owner)
        data = self.save(**JSON).json()
        self.assertTrue(data["success"])
        trip = Trip.objects.get(pk=data["trip"])
        self.assertEqual((trip.owner, trip.title, trip.party, trip.tier, trip.pace, trip.start_date, trip.share_token),
                         (self.owner, "Rome & Assisi", 2, "mid", 3, date(2027, 5, 10), None))
        self.assertEqual([(s.destination.slug, s.nights) for s in trip.stops.all()],
                         [("rome-vatican-city", 4), ("assisi", 3)])

    def test_save_without_javascript_redirects_back_to_the_plan(self):
        self.client.force_login(self.owner)
        response = self.save()
        trip = Trip.objects.get()
        self.assertRedirects(response, f"/plan/?{PLAN_Q}&trip={trip.pk}&saved=1", fetch_redirect_response=False)
        page = self.client.get(response["Location"]).content.decode()
        self.assertIn("Saved to My Pilgrimage › <a", page)
        self.assertIn(f'name="trip" value="{trip.pk}"', page)
        self.assertIn("Save changes to My Pilgrimage", page)

    def test_save_with_trip_updates_it(self):
        trip = self.make_trip()
        self.client.force_login(self.owner)
        self.save(q="t=assisi.2&p=4&l=comfort&pace=2", trip=trip.pk, **JSON)
        trip.refresh_from_db()
        self.assertEqual(Trip.objects.count(), 1)
        self.assertEqual([(s.destination.slug, s.nights) for s in trip.stops.all()], [("assisi", 2)])
        self.assertEqual((trip.party, trip.tier, trip.pace, trip.start_date), (4, "comfort", 2, None))

    def test_cannot_save_into_someone_elses_trip(self):
        trip = self.make_trip()
        for user in (self.other, self.staff):
            self.client.force_login(user)
            self.assertEqual(self.save(q="t=assisi.1", trip=trip.pk, **JSON).status_code, 404)
        trip.refresh_from_db()
        self.assertEqual(trip.stops.count(), 2)

    def test_empty_plan_is_not_saved(self):
        self.client.force_login(self.owner)
        data = self.save(q="t=atlantis.3", **JSON).json()
        self.assertEqual((data["success"], data["error"]), (False, "invalid"))
        self.assertFalse(Trip.objects.exists())

    def test_signed_out_and_get_are_refused(self):
        self.assertEqual(self.save(**JSON).status_code, 404)
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get("/plan/trips/save/").status_code, 404)
        self.assertFalse(Trip.objects.exists())

    def test_csrf_is_enforced(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.owner)
        self.assertEqual(client.post("/plan/trips/save/", {"q": PLAN_Q}).status_code, 403)
        self.assertFalse(Trip.objects.exists())

    def test_rate_limited(self):
        old = trips_module.TRIP_WRITES_PER_HOUR
        trips_module.TRIP_WRITES_PER_HOUR = 2
        self.addCleanup(setattr, trips_module, "TRIP_WRITES_PER_HOUR", old)
        self.client.force_login(self.owner)
        results = [self.save(**JSON).json() for _ in range(3)]
        self.assertEqual([r["success"] for r in results], [True, True, False])
        self.assertEqual(results[2]["error"], "rate_limited")
        self.assertEqual(Trip.objects.count(), 2)

    def test_opening_someone_elses_trip_id_is_ignored(self):
        trip = self.make_trip()
        self.client.force_login(self.other)
        page = self.client.get(f"/plan/?{PLAN_Q}&trip={trip.pk}").content.decode()
        self.assertNotIn(f'name="trip" value="{trip.pk}"', page)
        self.assertNotIn("Rome &amp; Assisi", page)


@ON
class MyTripsTests(TripTestCase):
    def test_lists_only_my_trips_with_recalculated_totals(self):
        mine = self.make_trip()
        theirs = self.make_trip(owner=self.other)
        theirs.title = "Not mine"
        theirs.save()
        self.client.force_login(self.owner)
        html = self.client.get("/plan/trips/").content.decode()
        self.assertIn("Rome &amp; Assisi", html)
        self.assertNotIn("Not mine", html)
        self.assertIn("May 10–17, 2027 · 2 travelers", html)
        self.assertIn("Rome / Vatican City (4 nights) → Assisi (3 nights) · Estimated $4,265", html)
        self.assertIn(f'href="/plan/?{PLAN_Q.replace("&", "&amp;")}&amp;trip={mine.pk}"', html)
        self.assertIn('<meta name="robots" content="noindex">', html)

        # Prices are never stored: change a cost and the total follows.
        self.rome.hotel_night_usd = Decimal("230")
        self.rome.save()
        self.assertIn("Estimated $4,713", self.client.get("/plan/trips/").content.decode())

    def test_signed_out_goes_to_login(self):
        response = self.client.get("/plan/trips/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/?next=/plan/trips/", response["Location"])

    def test_rename_and_delete_are_owner_only(self):
        trip = self.make_trip()
        for user in (self.other, self.staff):
            self.client.force_login(user)
            self.assertEqual(self.client.post(f"/plan/trips/{trip.pk}/rename/", {"title": "Mine now"}).status_code, 404)
            self.assertEqual(self.client.post(f"/plan/trips/{trip.pk}/delete/").status_code, 404)
        trip.refresh_from_db()
        self.assertEqual(trip.title, "Rome & Assisi")
        self.client.force_login(self.owner)
        self.assertRedirects(self.client.post(f"/plan/trips/{trip.pk}/rename/", {"title": "  Spring   pilgrimage "}),
                             "/plan/trips/?done=renamed", fetch_redirect_response=False)
        trip.refresh_from_db()
        self.assertEqual(trip.title, "Spring pilgrimage")
        self.client.post(f"/plan/trips/{trip.pk}/delete/")
        self.assertFalse(Trip.objects.exists())

    def test_empty_state(self):
        self.client.force_login(self.owner)
        self.assertIn("You haven&rsquo;t saved a trip yet.", self.client.get("/plan/trips/").content.decode())

    def test_my_trips_in_account_menu_and_passport(self):
        from pilgrims.models import PilgrimProfile

        self.client.force_login(self.owner)
        html = self.client.get("/plan/").content.decode()
        self.assertEqual(html.count('href="/plan/trips/"'), 2)  # desktop panel + mobile menu
        pilgrim = PilgrimProfile.objects.get(user=self.owner)
        profile = self.client.get(f"/pilgrims/u/{pilgrim.handle}/")
        self.assertEqual(profile.status_code, 200)
        self.assertIn('<a class="btn btn-secondary" href="/plan/trips/">My Trips</a>', profile.content.decode())


@ON
class ShareTests(TripTestCase):
    def test_share_on_off_on_gives_a_new_token(self):
        trip = self.make_trip()
        self.client.force_login(self.owner)
        first = self.client.post(f"/plan/trips/{trip.pk}/share/", {"on": "1"}, **JSON).json()["share_url"]
        trip.refresh_from_db()
        token1 = trip.share_token
        self.assertEqual(len(token1), 22)
        self.assertTrue(first.endswith(f"/plan/t/{token1}/"))

        self.client.logout()
        self.assertEqual(self.client.get(f"/plan/t/{token1}/").status_code, 200)

        self.client.force_login(self.owner)
        self.client.post(f"/plan/trips/{trip.pk}/share/", {"on": "0"})
        trip.refresh_from_db()
        self.assertIsNone(trip.share_token)
        self.client.logout()
        self.assertEqual(self.client.get(f"/plan/t/{token1}/").status_code, 404)

        self.client.force_login(self.owner)
        self.client.post(f"/plan/trips/{trip.pk}/share/", {"on": "1"})
        trip.refresh_from_db()
        self.assertNotEqual(trip.share_token, token1)
        self.assertEqual(self.client.get(f"/plan/t/{token1}/").status_code, 404)

    def test_only_the_owner_can_share(self):
        trip = self.make_trip()
        for user in (self.other, self.staff):
            self.client.force_login(user)
            self.assertEqual(self.client.post(f"/plan/trips/{trip.pk}/share/", {"on": "1"}).status_code, 404)
        trip.refresh_from_db()
        self.assertIsNone(trip.share_token)

    def test_shared_view_is_read_only_noindex_and_anonymous(self):
        trip = self.make_trip(shared=True)
        response = self.client.get(f"/plan/t/{trip.share_token}/")
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn('<meta name="robots" content="noindex, nofollow">', html)
        self.assertEqual(response["X-Robots-Tag"], "noindex, nofollow")
        self.assertEqual(response["Referrer-Policy"], "same-origin")
        self.assertIn("Rome &amp; Assisi", html)
        self.assertIn("$4,265", html)
        self.assertIn("Arrive and settle in", html)
        for private in ("johndoe", "john.doe@example.com", "John"):
            self.assertNotIn(private, html)
        self.assertNotIn("trips/save/", html)
        self.assertNotIn('data-action="', html)
        self.assertIn(f'href="/plan/?{PLAN_Q.replace("&", "&amp;")}"', html)

    def test_staff_get_no_bypass(self):
        trip = self.make_trip()
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get("/plan/t/anything/").status_code, 404)
        self.assertEqual(self.client.get(f"/plan/t/{trip.pk}/").status_code, 404)

    def test_unknown_token(self):
        self.assertEqual(self.client.get("/plan/t/not-a-real-token/").status_code, 404)


class SwitchTests(TripTestCase):
    @override_settings(SOG_PLANNER_V2="off")
    def test_all_trip_routes_404_when_off(self):
        trip = self.make_trip(shared=True)
        self.client.force_login(self.owner)
        for method, path in (("get", "/plan/trips/"), ("post", "/plan/trips/save/"),
                             ("post", f"/plan/trips/{trip.pk}/rename/"), ("post", f"/plan/trips/{trip.pk}/delete/"),
                             ("post", f"/plan/trips/{trip.pk}/share/"), ("get", f"/plan/t/{trip.share_token}/")):
            self.assertEqual(getattr(self.client, method)(path).status_code, 404, path)
        self.assertNotIn("My Trips", self.client.get("/plan/").content.decode())
        self.assertTrue(Trip.objects.filter(pk=trip.pk).exists())

    def test_account_deletion_removes_trips(self):
        self.make_trip(shared=True)
        self.owner.delete()
        self.assertFalse(Trip.objects.exists())
        self.assertFalse(TripStop.objects.exists())


@ON
class ReviewFixTests(TripTestCase):
    """Fixes from the Phase 4 review."""

    def test_shared_view_hides_cut_rows_and_says_this_pilgrimage(self):
        for n in range(1, 6):
            self.add_day(self.assisi, n, f"Assisi day {n}")
        trip = self.make_trip(shared=True)
        html = self.client.get(f"/plan/t/{trip.share_token}/").content.decode()
        self.assertIn("Assisi day 3", html)
        self.assertNotIn("Assisi day 4", html)
        self.assertNotIn("add a night", html)
        self.assertNotIn("more days of sacred places", html)
        self.assertIn('<p class="pv2-eyebrow">This pilgrimage</p>', html)
        self.assertNotIn("Your pilgrimage", html)
        # The planner itself still shows them.
        self.assertIn("add a night", self.client.get(f"/plan/?{PLAN_Q.replace('assisi.3', 'assisi.1')}").content.decode())

    def test_share_link_note_in_my_trips(self):
        self.make_trip(shared=True)
        self.client.force_login(self.owner)
        self.assertIn("Anyone with this link can see this trip&rsquo;s name and plan.",
                      self.client.get("/plan/trips/").content.decode())


@ON
@override_settings(SECURE_PROXY_SSL_HEADER=("HTTP_X_FORWARDED_PROTO", "https"),
                   ALLOWED_HOSTS=["sitesofgrace.com", "sitesofgrace-abc12.ondigitalocean.app", "testserver"])
class ProductionShareUrlTests(TripTestCase):
    """Behind App Platform's proxy (production.py: SECURE_PROXY_SSL_HEADER),
    share URLs come from the Wagtail Site (https://sitesofgrace.com), never
    from the request's Host header."""

    PROXY = {"HTTP_HOST": "sitesofgrace-abc12.ondigitalocean.app", "HTTP_X_FORWARDED_PROTO": "https"}

    def setUp(self):
        super().setUp()
        from wagtail.models import Site

        Site.objects.filter(is_default_site=True).update(hostname="sitesofgrace.com", port=443)
        Site.clear_site_root_paths_cache()

    def test_share_response_and_my_trips(self):
        trip = self.make_trip()
        self.client.force_login(self.owner)
        url = self.client.post(f"/plan/trips/{trip.pk}/share/", {"on": "1"}, **JSON, **self.PROXY).json()["share_url"]
        trip.refresh_from_db()
        self.assertEqual(url, f"https://sitesofgrace.com/plan/t/{trip.share_token}/")
        html = self.client.get("/plan/trips/", **self.PROXY).content.decode()
        self.assertIn(f'value="https://sitesofgrace.com/plan/t/{trip.share_token}/"', html)
        self.assertNotIn("ondigitalocean.app", html)

    def test_planner_share_link_and_print_footer(self):
        html = self.client.get(f"/plan/?{PLAN_Q}", **self.PROXY).content.decode()
        self.assertIn('data-share-base="https://sitesofgrace.com/plan/"', html)
        self.assertIn("<span data-share-url>https://sitesofgrace.com/plan/?t=rome-vatican-city.4,assisi.3", html)
        self.assertNotIn("ondigitalocean.app", html)

    def test_scheme_comes_from_the_proxy_header(self):
        request_is_secure = self.client.get(f"/plan/?{PLAN_Q}", HTTP_HOST="sitesofgrace.com",
                                            HTTP_X_FORWARDED_PROTO="https").wsgi_request.is_secure()
        self.assertTrue(request_is_secure)
