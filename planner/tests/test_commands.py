"""Phase 1: the slug backfill and the four planner data commands."""
import csv
import importlib
import json
import os
import shutil
import tempfile
from decimal import Decimal
from io import StringIO

from django.apps import apps
from django.core.management import call_command
from django.core.management.base import CommandError

from planner.models import DestinationCost, DestinationPlanDay

from .base import PlannerTestCase

backfill = importlib.import_module("planner.migrations.0005_backfill_destination_slugs")


class TempDirMixin:
    def setUp(self):
        super().setUp()
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)

    def path(self, name):
        return os.path.join(self.tmp, name)

    def call(self, *args):
        out = StringIO()
        call_command(*args, stdout=out, stderr=out)
        return out.getvalue()


class SlugBackfillTests(PlannerTestCase):
    def test_backfill_fills_blank_slugs_only(self):
        DestinationCost.objects.create(city="Rome / Vatican City", region="Southern Europe")
        DestinationCost.objects.create(city="Mexico City (Guadalupe)", region="Latin America")
        DestinationCost.objects.create(city="Lourdes", slug="kept", region="Western Europe")
        DestinationCost.objects.update(slug=None)
        DestinationCost.objects.filter(city="Lourdes").update(slug="kept")
        backfill.backfill_slugs(apps, None)
        self.assertEqual(
            dict(DestinationCost.objects.values_list("city", "slug")),
            {"Rome / Vatican City": "rome-vatican-city", "Mexico City (Guadalupe)": "mexico-city",
             "Lourdes": "kept"},
        )


class FillCoordsTests(TempDirMixin, PlannerTestCase):
    def test_averages_linked_live_sites_and_reports_the_rest(self):
        dest = self.make_destination("assisi", latitude=None, longitude=None)
        empty = self.make_destination("lourdes", latitude=None, longitude=None)
        a = self.make_site("basilica-a", latitude=Decimal("43.0"), longitude=Decimal("12.0"))
        b = self.make_site("basilica-b", latitude=Decimal("43.2"), longitude=Decimal("12.4"))
        dark = self.make_site("not-live", latitude=Decimal("50"), longitude=Decimal("50"))
        dark.unpublish()
        dest.associated_sites.add(a, b, dark)

        out = self.call("fill_destination_coords", "--dry-run")
        dest.refresh_from_db()
        self.assertIsNone(dest.latitude)
        self.assertIn("lourdes", out)

        self.call("fill_destination_coords")
        dest.refresh_from_db()
        self.assertEqual((dest.latitude, dest.longitude), (Decimal("43.100000"), Decimal("12.200000")))
        empty.refresh_from_db()
        self.assertIsNone(empty.latitude)

    def test_never_overwrites(self):
        dest = self.make_destination("assisi")
        dest.associated_sites.add(self.make_site("far", latitude=Decimal("1"), longitude=Decimal("1")))
        self.call("fill_destination_coords")
        dest.refresh_from_db()
        self.assertEqual(dest.latitude, Decimal("43.070300"))


class ProposeApplyTests(TempDirMixin, PlannerTestCase):
    def setUp(self):
        super().setUp()
        self.dest = self.make_destination("assisi")
        self.near = self.make_site("san-damiano", locality="Santa Maria", latitude=Decimal("43.06"),
                                   longitude=Decimal("12.62"))
        self.by_name = self.make_site("named", locality="Assisi")
        self.far = self.make_site("far-away", locality="Elsewhere", latitude=Decimal("45"), longitude=Decimal("9"))
        self.linked = self.make_site("already", locality="Assisi")
        self.dest.associated_sites.add(self.linked)

    def proposals(self):
        out = self.path("p.csv")
        self.call("propose_destination_sites", "--out", out)
        with open(out, newline="", encoding="utf-8") as fh:
            return list(csv.DictReader(fh))

    def test_propose_is_read_only_and_finds_near_and_named(self):
        rows = self.proposals()
        slugs = {r["site_slug"] for r in rows if r["destination_slug"] == "assisi"}
        self.assertEqual(slugs, {"san-damiano", "named"})
        self.assertEqual(list(self.dest.associated_sites.all()), [self.linked])

    def test_dry_run_writes_no_file(self):
        out = self.call("propose_destination_sites", "--dry-run")
        self.assertIn("san-damiano", out)
        self.assertEqual(os.listdir(self.tmp), [])

    def test_apply_links_only_approved_rows(self):
        rows = self.proposals()
        for r in rows:
            r["approve"] = "yes" if r["site_slug"] == "san-damiano" else ""
        path = self.path("reviewed.csv")
        with open(path, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=rows[0].keys())
            w.writeheader()
            w.writerows(rows)

        self.call("apply_destination_sites", path, "--dry-run")
        self.assertFalse(self.dest.associated_sites.filter(pk=self.near.pk).exists())

        self.call("apply_destination_sites", path)
        self.assertEqual(set(self.dest.associated_sites.values_list("slug", flat=True)), {"already", "san-damiano"})
        out = self.call("apply_destination_sites", path)
        self.assertIn("Already linked: 1", out)

    def test_apply_stops_on_a_bad_row(self):
        path = self.path("bad.csv")
        with open(path, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["destination_slug", "site_id", "site_slug", "approve"])
            w.writerow(["assisi", self.near.pk, "san-damiano", "yes"])
            w.writerow(["assisi", self.far.pk, "wrong-slug", "yes"])
        with self.assertRaises(CommandError):
            self.call("apply_destination_sites", path)
        self.assertFalse(self.dest.associated_sites.filter(pk=self.near.pk).exists())


class ImportPlanDaysTests(TempDirMixin, PlannerTestCase):
    """The format in Claude outputs/claude-code-prompt-trip-planner.md: day
    order is a day's position in the list."""

    def setUp(self):
        super().setUp()
        self.dest = self.make_destination("assisi", gateway_airport_iata=None, gateway_airport_name=None)
        self.a = self.make_site("basilica-of-st-francis")
        self.b = self.make_site("san-damiano")
        self.c = self.make_site("santa-chiara")

    def write(self, days, slug="assisi", **extra):
        path = self.path("days.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"destinations": [{"slug": slug, **extra, "days": days}]}, fh)
        return path

    DAYS = [
        {"title": "Francis and Clare", "sites": ["basilica-of-st-francis", "santa-chiara"]},
        {"title": "San Damiano", "sites": ["san-damiano"], "extra_places": "Rocca Maggiore; Eremo delle Carceri"},
    ]

    def stored(self):
        through = DestinationPlanDay.sites.through
        return [
            (d.sort_order, d.title, d.extra_places,
             list(through.objects.filter(destinationplanday=d).order_by("id")
                  .values_list("sacredsitepage__slug", flat=True)))
            for d in self.dest.plan_days.order_by("sort_order")
        ]

    def test_dry_run_then_import_then_idempotent(self):
        path = self.write(self.DAYS, gateway_airport_iata="fco")
        self.call("import_plan_days", path, "--dry-run")
        self.assertEqual(self.stored(), [])
        self.call("import_plan_days", path)
        self.assertEqual(self.stored(), [
            (0, "Francis and Clare", None, ["basilica-of-st-francis", "santa-chiara"]),
            (1, "San Damiano", "Rocca Maggiore; Eremo delle Carceri", ["san-damiano"]),
        ])
        self.dest.refresh_from_db()
        self.assertEqual(self.dest.gateway_airport_iata, "FCO")
        out = self.call("import_plan_days", path)
        self.assertIn("Changed: 0", out)
        self.assertIn("Unchanged: 1", out)
        self.call("import_plan_days", path, "--verify")

    def test_adding_a_day_later_keeps_the_first_ones(self):
        self.call("import_plan_days", self.write(self.DAYS[:1]))
        self.call("import_plan_days", self.write(self.DAYS))
        self.assertEqual([d[1] for d in self.stored()], ["Francis and Clare", "San Damiano"])

    def test_unknown_site_slugs_are_listed_and_nothing_written(self):
        days = [{"title": "x", "sites": ["san-damiano", "nope", "also-nope"]}]
        out = self.call("import_plan_days", self.write(days))
        self.assertIn("nope, also-nope", out)
        self.assertEqual(self.stored(), [])

    def test_non_live_site_is_rejected(self):
        self.c.unpublish()
        out = self.call("import_plan_days", self.write(self.DAYS))
        self.assertIn("santa-chiara", out)
        self.assertEqual(self.stored(), [])

    def test_conflicting_day_skips_destination(self):
        self.add_day(self.dest, 1, "Something else", [self.a])
        out = self.call("import_plan_days", self.write(self.DAYS))
        self.assertIn("Conflicts: 1", out)
        self.assertEqual(len(self.stored()), 1)

    def test_filled_gateway_is_never_overwritten(self):
        DestinationCost.objects.filter(pk=self.dest.pk).update(gateway_airport_iata="PEG")
        out = self.call("import_plan_days", self.write(self.DAYS, gateway_airport_iata="FCO"))
        self.assertIn("Conflicts: 1", out)
        self.assertEqual(self.stored(), [])

    def test_status_and_unknown_destination(self):
        out = self.call("import_plan_days", self.write(self.DAYS, status="Draft"))
        self.assertIn("Not ready: 1", out)
        out = self.call("import_plan_days", self.write(self.DAYS, slug="atlantis"))
        self.assertIn("no destination with this slug", out)
        self.assertEqual(self.stored(), [])

    def test_verify_fails_when_missing(self):
        with self.assertRaises(CommandError):
            self.call("import_plan_days", self.write(self.DAYS), "--verify")

    def test_day_with_no_sites_and_only_extra_places(self):
        """Some destinations (Dublin, for one) have days with no site pages."""
        days = [
            {"title": "Around the city", "sites": [], "extra_places": "Whitefriar Street Church; St. Mary's Pro-Cathedral"},
            {"title": "San Damiano", "sites": ["san-damiano"]},
        ]
        path = self.write(days)
        self.call("import_plan_days", path)
        self.assertEqual(self.stored(), [
            (0, "Around the city", "Whitefriar Street Church; St. Mary's Pro-Cathedral", []),
            (1, "San Damiano", None, ["san-damiano"]),
        ])
        self.assertIn("Unchanged: 1", self.call("import_plan_days", path))
        self.call("import_plan_days", path, "--verify")
