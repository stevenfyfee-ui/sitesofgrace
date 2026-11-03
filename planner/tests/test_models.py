"""Phase 1: the planner data model."""
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db.models import ProtectedError

from planner.booking import booking_links_allowed
from planner.models import (
    DestinationCost, PlannerBookingLink, PlannerSettings, Trip, TripStop, destination_slug_for,
)

from .base import PlannerTestCase


class DestinationSlugTests(PlannerTestCase):
    def test_slug_filled_from_city_when_blank(self):
        dest = DestinationCost.objects.create(city="Rome / Vatican City", region="Southern Europe")
        self.assertEqual(dest.slug, "rome-vatican-city")

    def test_override(self):
        self.assertEqual(destination_slug_for("Mexico City (Guadalupe)"), "mexico-city")
        self.assertEqual(destination_slug_for("Santiago de Compostela"), "santiago-de-compostela")
        self.assertEqual(destination_slug_for("San Giovanni Rotondo"), "san-giovanni-rotondo")

    def test_editor_slug_is_kept(self):
        dest = DestinationCost.objects.create(city="Rome", slug="the-eternal-city", region="Southern Europe")
        dest.city = "Rome / Vatican City"
        dest.save()
        dest.refresh_from_db()
        self.assertEqual(dest.slug, "the-eternal-city")

    def test_departure_prefers_gateway(self):
        self.assertEqual(self.make_destination("assisi").departure_airport, ("FCO", "Rome Fiumicino"))
        self.assertEqual(self.make_destination("lourdes").departure_airport, ("LDE", "Tarbes-Lourdes"))


class TripModelTests(PlannerTestCase):
    def setUp(self):
        super().setUp()
        self.user = get_user_model().objects.create_user("pilgrim", "pilgrim@example.com", "pw")
        self.dest = self.make_destination("assisi")

    def test_account_deletion_removes_trips(self):
        trip = Trip.objects.create(owner=self.user, title="Umbria")
        TripStop.objects.create(trip=trip, destination=self.dest, nights=3)
        self.user.delete()
        self.assertFalse(Trip.objects.exists())
        self.assertFalse(TripStop.objects.exists())

    def test_destination_in_a_trip_is_protected(self):
        trip = Trip.objects.create(owner=self.user, title="Umbria")
        TripStop.objects.create(trip=trip, destination=self.dest, nights=3)
        with self.assertRaises(ProtectedError):
            self.dest.delete()

    def test_party_and_nights_ranges(self):
        trip = Trip(owner=self.user, title="Too many", party=13)
        with self.assertRaises(ValidationError):
            trip.full_clean()
        stop = TripStop(trip=Trip.objects.create(owner=self.user, title="x"), destination=self.dest, nights=22)
        with self.assertRaises(ValidationError):
            stop.full_clean()


class BookingGateTests(PlannerTestCase):
    def test_setting_refuses_without_live_disclosure(self):
        settings = PlannerSettings.load()
        settings.show_booking_links = True
        with self.assertRaises(ValidationError):
            settings.clean()

    def test_setting_refuses_with_draft_disclosure(self):
        self.publish_disclosure(live=False)
        settings = PlannerSettings.load()
        settings.show_booking_links = True
        with self.assertRaises(ValidationError):
            settings.clean()

    def test_setting_allowed_with_live_disclosure(self):
        self.publish_disclosure()
        settings = PlannerSettings.load()
        settings.show_booking_links = True
        settings.clean()

    def test_render_time_check_follows_the_disclosure(self):
        """Saved on while the page was live, then the page was unpublished:
        the links must go away without anyone touching the setting."""
        page = self.publish_disclosure()
        settings = PlannerSettings.load()
        settings.show_booking_links = True
        settings.save()
        self.assertTrue(booking_links_allowed())
        page.unpublish()
        self.assertFalse(booking_links_allowed())

    def test_off_by_default(self):
        self.publish_disclosure()
        self.assertFalse(PlannerSettings.load().show_booking_links)
        self.assertFalse(booking_links_allowed())
        self.assertEqual(PlannerSettings.load().max_stops, 6)


class BookingLinkTemplateTests(PlannerTestCase):
    def test_known_placeholders(self):
        PlannerBookingLink(label="Flights", provider="Aviasales",
                           url_template="https://example.com/?to={iata}&s={sub_id}&d={dest_slug}").clean()

    def test_unknown_placeholder_rejected(self):
        with self.assertRaises(ValidationError):
            PlannerBookingLink(label="Flights", provider="X", url_template="https://example.com/?x={city}").clean()

    def test_https_required(self):
        with self.assertRaises(ValidationError):
            PlannerBookingLink(label="Flights", provider="X", url_template="http://example.com/").clean()


class AdminTests(PlannerTestCase):
    def setUp(self):
        super().setUp()
        self.admin = get_user_model().objects.create_superuser("admin", "admin@example.com", "pw")
        self.client.force_login(self.admin)

    def test_destination_edit_form_has_curated_plan(self):
        dest = self.make_destination("assisi")
        self.add_day(dest, 1, "Francis and Clare", [self.make_site("basilica-of-st-francis")])
        response = self.client.get(f"/admin/snippets/planner/destinationcost/edit/{dest.pk}/")
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn("Curated plan", html)
        self.assertIn("Francis and Clare", html)
        self.assertIn("gateway_airport_iata", html)

    def test_settings_page_renders(self):
        response = self.client.get("/admin/settings/planner/plannersettings/")
        self.assertIn(response.status_code, (200, 302))
        if response.status_code == 302:
            self.assertEqual(self.client.get(response.url).status_code, 200)


class PlannerSwitchTests(PlannerTestCase):
    def test_modes(self):
        from types import SimpleNamespace

        from django.contrib.auth.models import AnonymousUser
        from django.test import override_settings

        from core.v2 import planner_v2_enabled

        staff = SimpleNamespace(user=get_user_model()(is_staff=True))
        pilgrim = SimpleNamespace(user=get_user_model()(is_staff=False))
        anon = SimpleNamespace(user=AnonymousUser())
        cases = {"off": (False, False, False), "staff": (True, False, False), "on": (True, True, True),
                 "yes please": (False, False, False)}
        for mode, expected in cases.items():
            with override_settings(SOG_PLANNER_V2=mode, SOG_V2_ENABLED="on"):
                self.assertEqual(tuple(planner_v2_enabled(r) for r in (staff, pilgrim, anon)), expected, mode)
