"""create_future_saints_tree (drafts, idempotent, review workflow) and the
local-only future_saints_dev_sample guard."""
from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.test import TestCase, override_settings
from wagtail.models import Page, Revision, Site, WorkflowPage

from catalog.models import SaintPage
from future_saints.models import FutureSaintsHomePage, FutureSaintsIndexPage, WorldMapPage


class CleanSiteCacheTestCase(TestCase):
    def setUp(self):
        # Wagtail caches site root paths process-wide; publishing fills it.
        # Clear it before and after so no other app's tests see stale roots.
        Site.clear_site_root_paths_cache()
        self.addCleanup(Site.clear_site_root_paths_cache)


class TreeCommandTests(CleanSiteCacheTestCase):

    def test_creates_six_unpublished_drafts_linked_by_object(self):
        out = StringIO()
        call_command("create_future_saints_tree", stdout=out)
        home = FutureSaintsHomePage.objects.get()
        self.assertFalse(home.live)
        self.assertFalse(home.show_in_menus)
        self.assertEqual(home.slug, "future-saints")
        self.assertEqual(home.get_parent().specific_class.__name__, "HomePage")
        indexes = {p.content_kind: p for p in FutureSaintsIndexPage.objects.child_of(home)}
        self.assertEqual(
            {k: p.slug for k, p in indexes.items()},
            {"saint": "saints", "marian_apparition": "marian-apparitions",
             "eucharistic_miracle": "eucharistic-miracles", "holy_land": "holy-land",
             "california_mission": "california-missions"},
        )
        self.assertFalse(any(p.live or p.show_in_menus for p in indexes.values()))
        self.assertEqual(home.card_1_page, indexes["saint"])
        self.assertEqual(home.card_2_page, indexes["marian_apparition"])
        self.assertEqual(home.card_3_page, indexes["eucharistic_miracle"])
        self.assertEqual(home.card_4_page, indexes["california_mission"])
        self.assertEqual(home.holy_land_page, indexes["holy_land"])
        self.assertEqual(home.headline, "Explore the Wonders of Our Faith!")
        self.assertEqual(WorkflowPage.objects.get(page=home).workflow.name, "Future Saints editorial review")
        self.assertIn("Nothing was published", out.getvalue())

    def test_dry_run_lists_every_page_and_writes_nothing(self):
        from django.contrib.auth.models import Group
        from wagtail.models import GroupPagePermission, Page, Revision, Workflow

        def counts():
            return (Page.objects.count(), Revision.objects.count(), Group.objects.count(),
                    GroupPagePermission.objects.count(), Workflow.objects.count(), WorkflowPage.objects.count())

        before = counts()
        out = StringIO()
        call_command("create_future_saints_tree", "--dry-run", stdout=out)
        self.assertEqual(counts(), before, "a dry run writes nothing")
        text = out.getvalue()
        self.assertIn("Dry run: nothing will be written.", text)
        lines = [line for line in text.splitlines() if line.startswith("Would create (draft):")]
        self.assertEqual(len(lines), 8, "home, five indexes, the World Discovery Map, A Note for Grown-Ups")
        self.assertIn("FutureSaintsHomePage", lines[0])
        self.assertIn("WorldMapPage  title 'World Discovery Map'  slug 'map'  path /home/future-saints/map/", lines[-2])
        self.assertIn("GrownUpsNotePage  title 'A Note for Grown-Ups'  slug 'for-grown-ups'  "
                      "path /home/future-saints/for-grown-ups/", lines[-1])
        self.assertIn("slug 'future-saints'", lines[0])
        for slug in ("saints", "marian-apparitions", "eucharistic-miracles", "california-missions", "holy-land"):
            self.assertTrue(any(f"slug '{slug}'" in line and "parent /home/future-saints/" in line for line in lines[1:]), slug)
        self.assertIn("Would set up review", text)

        # Once the tree exists, a dry run says so and still writes nothing.
        call_command("create_future_saints_tree", stdout=StringIO())
        after_real_run = counts()
        out = StringIO()
        call_command("create_future_saints_tree", "--dry-run", stdout=out)
        self.assertIn("Nothing to create", out.getvalue())
        self.assertEqual(counts(), after_real_run)

    def test_an_existing_tree_gets_only_the_missing_map_page(self):
        """Production today: the home page and five indexes exist (and are live); only the map is new."""
        call_command("create_future_saints_tree", stdout=StringIO())
        WorldMapPage.objects.get().delete()
        home = FutureSaintsHomePage.objects.get()
        home.save_revision().publish()
        pages, revisions = Page.objects.count(), Revision.objects.count()
        out = StringIO()
        call_command("create_future_saints_tree", "--dry-run", stdout=out)
        lines = [line for line in out.getvalue().splitlines() if line.startswith("Would create (draft):")]
        self.assertEqual(lines, ["Would create (draft): WorldMapPage  title 'World Discovery Map'  slug 'map'  "
                                 "path /home/future-saints/map/  parent /home/future-saints/"])
        self.assertNotIn("Would set up review", out.getvalue())
        self.assertEqual((Page.objects.count(), Revision.objects.count()), (pages, revisions))
        out = StringIO()
        call_command("create_future_saints_tree", stdout=out)
        world = WorldMapPage.objects.get()
        self.assertFalse(world.live, "a draft; an editor publishes it")
        self.assertEqual(world.get_parent().pk, home.pk)
        self.assertEqual(Page.objects.count(), pages + 1)
        home.refresh_from_db()
        self.assertTrue(home.live)
        self.assertFalse(home.has_unpublished_changes, "the existing home page isn't touched")

    def test_second_run_changes_nothing(self):
        call_command("create_future_saints_tree", stdout=StringIO())
        out = StringIO()
        call_command("create_future_saints_tree", stdout=out)
        self.assertIn("Nothing to create", out.getvalue())
        self.assertEqual(FutureSaintsHomePage.objects.count(), 1)
        self.assertEqual(FutureSaintsIndexPage.objects.count(), 5)
        self.assertEqual(WorldMapPage.objects.count(), 1)

    def test_index_subject_must_be_unique_under_the_home(self):
        call_command("create_future_saints_tree", stdout=StringIO())
        holy_land = FutureSaintsIndexPage.objects.get(content_kind="holy_land")
        holy_land.content_kind = "saint"
        with self.assertRaises(Exception):
            holy_land.full_clean()


class DevSampleGuardTests(CleanSiteCacheTestCase):
    def test_refuses_without_debug(self):
        with override_settings(DEBUG=False), self.assertRaisesMessage(CommandError, "DEBUG"):
            call_command("future_saints_dev_sample", stdout=StringIO())
        self.assertFalse(FutureSaintsHomePage.objects.exists())

    def test_refuses_a_non_local_database(self):
        with override_settings(DEBUG=True), \
                mock.patch.dict(connection.settings_dict, {"HOST": "db.example.com"}), \
                self.assertRaisesMessage(CommandError, "refuses"):
            call_command("future_saints_dev_sample", stdout=StringIO())
        self.assertFalse(FutureSaintsHomePage.objects.exists())

    def test_sample_text_is_marked_and_canonical_pages_untouched(self):
        root = Site.objects.get(is_default_site=True).root_page
        saint = SaintPage(title="St. Francis of Assisi", slug="st-francis-of-assisi", body="<p>Adult text.</p>")
        root.add_child(instance=saint)
        before = SaintPage.objects.filter(pk=saint.pk).values().get()
        with override_settings(DEBUG=True), mock.patch.dict(connection.settings_dict, {"HOST": "127.0.0.1"}):
            call_command("future_saints_dev_sample", stdout=StringIO())
        home = FutureSaintsHomePage.objects.get()
        self.assertTrue(home.live)
        self.assertEqual(home.saint_of_week_id, saint.pk)
        for field in ("card_1_line", "card_2_line", "card_3_line", "card_4_line", "holy_land_line", "saint_of_week_line"):
            self.assertIn("(sample)", getattr(home, field))
        for index in FutureSaintsIndexPage.objects.all():
            self.assertTrue(index.live)
            self.assertIn("(sample)", index.intro)
        self.assertEqual(SaintPage.objects.filter(pk=saint.pk).values().get(), before)
