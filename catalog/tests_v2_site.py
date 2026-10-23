"""Phase 1 of Pilgrimage Platform v2: the sacred site page.

What these protect: the switch (off renders the old page exactly, staff
and on render v2), the ALWAYS-ON "Not Applicable" suppression, the v2
page's hide-when-empty rules, Pilgrim Photos staying last, no review dates
in public HTML, the two read-only report commands, and the importer's
dry-run / idempotency / draft-skip / conflict rules.
"""
import csv
import json
import os
import shutil
import tempfile
from datetime import date
from decimal import Decimal
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings

from catalog.models import CATEGORY_STYLES, SacredSitePage, SaintPage, SiteTravelSection
from catalog.tests import SacredSitePageTestCase
from core.v2 import v2_enabled

V2_ON = override_settings(SOG_V2_ENABLED="on")


class V2SiteTestCase(SacredSitePageTestCase):
    def make_site(self, slug="test-site", **kwargs):
        """Like the shared helper, but the category can be chosen."""
        page = SacredSitePage(
            title=kwargs.pop("title", "Test Site"),
            slug=slug,
            category=kwargs.pop("category", "Marian Apparition"),
            **kwargs,
        )
        self.site_root().add_child(instance=page)
        return SacredSitePage.objects.get(pk=page.pk)

    def html(self, page):
        return self.client.get(SacredSitePage.objects.get(pk=page.pk).url).content.decode()


class SwitchTests(V2SiteTestCase):
    def test_v2_enabled_modes(self):
        class Req:
            def __init__(self, user):
                self.user = user

        staff = get_user_model().objects.create_user("staff", "s@example.com", "x", is_staff=True)
        pilgrim = get_user_model().objects.create_user("pilgrim", "p@example.com", "x")
        with override_settings(SOG_V2_ENABLED="off"):
            self.assertFalse(v2_enabled(Req(staff)))
        with override_settings(SOG_V2_ENABLED="staff"):
            self.assertTrue(v2_enabled(Req(staff)))
            self.assertFalse(v2_enabled(Req(pilgrim)))
        with override_settings(SOG_V2_ENABLED="on"):
            self.assertTrue(v2_enabled(Req(pilgrim)))
        with override_settings(SOG_V2_ENABLED="yes please"):
            self.assertFalse(v2_enabled(Req(staff)), "an unknown value must read as off")

    def test_off_renders_the_original_page(self):
        page = self.make_site(slug="switch-off", the_story="<p>Story.</p>")
        with override_settings(SOG_V2_ENABLED="off"):
            html = self.html(page)
        self.assertIn('class="catalog-hero"', html)
        self.assertNotIn("v2-site", html)
        self.assertNotIn("site-v2.css", html)

    def test_staff_mode_shows_v2_to_staff_only(self):
        page = self.make_site(slug="switch-staff", the_story="<p>Story.</p>")
        with override_settings(SOG_V2_ENABLED="staff"):
            self.assertNotIn("v2-site", self.html(page))
            staff = get_user_model().objects.create_user("st", "st@example.com", "pw", is_staff=True)
            self.client.force_login(staff)
            self.assertIn("v2-site", self.html(page))

    @V2_ON
    def test_on_renders_v2(self):
        page = self.make_site(slug="switch-on", the_story="<p>Story.</p>")
        html = self.html(page)
        self.assertIn("v2-site", html)
        self.assertNotIn('class="catalog-hero"', html)


class NotApplicableTests(V2SiteTestCase):
    """ALWAYS ON: no badge, chip or row for blank or "Not Applicable"."""

    def test_not_applicable_never_renders_in_either_version(self):
        page = self.make_site(slug="holy-sepulchre-test", category="Holy Land",
                              canonical_status="Not Applicable", feast_day="Easter")
        for mode in ("off", "on"):
            with override_settings(SOG_V2_ENABLED=mode):
                html = self.html(page)
            self.assertNotIn("Not Applicable", html, mode)
            self.assertNotIn("badge-status", html, mode)
            self.assertNotIn("v2-pill--status", html, mode)
            self.assertNotIn("Church recognition</dt>", html, mode)

    def test_blank_status_renders_nothing(self):
        page = self.make_site(slug="st-francis-test", category="Saints & Tombs", canonical_status="")
        with V2_ON:
            html = self.html(page)
        self.assertNotIn("v2-pill--status", html)
        self.assertFalse(SacredSitePage.objects.get(pk=page.pk).status_applies)

    def test_off_still_shows_a_real_status_as_stored(self):
        page = self.make_site(slug="real-status-off", canonical_status="Recognized Devotion")
        with override_settings(SOG_V2_ENABLED="off"):
            self.assertIn('<span class="badge badge-status">Recognized Devotion</span>', self.html(page))

    @V2_ON
    def test_v2_shows_plain_label_with_term_in_tooltip(self):
        page = self.make_site(slug="chapel-test", category="Saints & Tombs",
                              canonical_status="Constat de supernaturalitate (legacy)", recognition_year=1873)
        html = self.html(page)
        self.assertIn('title="Constat de supernaturalitate (legacy)">Church approved · 1873</span>', html)
        devotion = self.make_site(slug="devotion-test", canonical_status="Recognized Devotion")
        self.assertIn(">Church-recognized devotion</span>", self.html(devotion))

    def test_approved_without_year_has_no_year(self):
        page = self.make_site(slug="no-year", canonical_status="Constat de supernaturalitate (legacy)")
        self.assertEqual(SacredSitePage.objects.get(pk=page.pk).status_label, "Church approved")


@V2_ON
class SectionBarTests(V2SiteTestCase):
    def bar_ids(self, page):
        return [item["id"] for item in SacredSitePage.objects.get(pk=page.pk).v2_section_bar]

    def test_bar_lists_only_filled_sections(self):
        page = self.make_site(slug="bar-min")
        self.assertEqual(self.bar_ids(page), ["overview", "pilgrim-photos"])

        page = self.make_site(slug="bar-full", the_story="<p>S.</p>", church_recognition="<p>R.</p>",
                              prep_prayer="<p>Pray.</p>")
        self.add_travel(page, "getting-there")
        self.assertEqual(
            self.bar_ids(page),
            ["overview", "the-story", "church-recognition", "plan-your-visit", "prepare", "pilgrim-photos"],
        )
        html = self.html(page)
        self.assertIn('data-section-link="prepare"', html)
        self.assertNotIn('data-section-link="nearby"', html)

    def test_other_narrative_sections_keep_their_content(self):
        page = self.make_site(slug="bar-other", catholic_teaching="<p>Teaching text.</p>",
                              go_deeper="<p>Deeper text.</p>")
        html = self.html(page)
        self.assertIn("Teaching text.", html)
        self.assertIn("Deeper text.", html)

    def test_read_more_markup_is_hidden_until_js_measures(self):
        page = self.make_site(slug="bar-clamp", the_story="<p>Story.</p>")
        html = self.html(page)
        self.assertIn('data-clamp-toggle aria-expanded="false" aria-controls="the-story-body" hidden', html)
        self.assertNotIn("is-clamped", html)


@V2_ON
class AtAGlanceTests(V2SiteTestCase):
    def test_panel_hides_below_two_rows(self):
        page = self.make_site(slug="glance-one", feast_day="May 13")
        self.assertNotIn("At a Glance", self.html(page))

    def test_rows_hide_when_empty_and_render_when_filled(self):
        page = self.make_site(
            slug="glance-full", address="1 Main St (sample)", latitude=Decimal("43.1"),
            longitude=Decimal("-0.05"), admission="Free", reservation_required="some",
            worship_status="active", feast_day="February 11",
        )
        html = self.html(page)
        self.assertIn("At a Glance", html)
        self.assertIn("1 Main St (sample)", html)
        self.assertIn("https://www.google.com/maps/dir/?api=1&amp;destination=43.100000,-0.050000", html)
        self.assertIn("Free · Reservations for some activities", html)
        self.assertIn("Active church with regular Mass", html)
        self.assertNotIn("Time needed", html)
        self.assertNotIn("Official website", html)
        self.assertIn(f"/plan/?site={page.slug}", html)

    def test_renders_without_travel_sections(self):
        page = self.make_site(slug="glance-no-plan", admission="Free", feast_day="May 13")
        self.assertFalse(SacredSitePage.objects.get(pk=page.pk).has_plan_section)
        self.assertIn("At a Glance", self.html(page))

    def test_time_needed_falls_back_to_the_quick_card(self):
        page = self.make_site(slug="glance-fallback", quick_ideal_stay="2 days")
        rows = SacredSitePage.objects.get(pk=page.pk).at_a_glance_rows
        self.assertEqual([(r["label"], r["text"]) for r in rows], [("Time needed", "2 days")])


@V2_ON
class AccountBoxTests(V2SiteTestCase):
    def test_needs_two_cells(self):
        page = self.make_site(slug="acct-one", church_recognition="<p>R.</p>", account_tradition="<p>T.</p>")
        self.assertNotIn("v2-readbox", self.html(page))

    def test_labels_and_marian_findings_label(self):
        page = self.make_site(slug="acct-marian", category="Marian Apparition",
                              account_tradition="<p>T.</p>", account_findings="<p>F.</p>")
        html = self.html(page)
        self.assertIn("v2-readbox", html)
        self.assertIn(">The tradition<", html)
        self.assertIn(">Reported healings<", html)
        other = self.make_site(slug="acct-euch", category="Eucharistic Miracle",
                               account_church_judgment="<p>J.</p>", account_findings="<p>F.</p>",
                               eucharistic_kind="miracle")
        html = self.html(other)
        self.assertIn(">Reported findings<", html)
        self.assertIn(">Church judgment<", html)
        self.assertIn(">Eucharistic miracle</span>", html)

    def test_box_alone_still_renders_church_recognition(self):
        page = self.make_site(slug="acct-only", account_tradition="<p>T.</p>", account_teaching="<p>C.</p>")
        self.assertIn('id="church-recognition"', self.html(page))


@V2_ON
class NearbyTests(V2SiteTestCase):
    def test_cards_show_miles_only_and_saint_connection(self):
        saint = SaintPage(title="St. Test", slug="st-test")
        self.site_root().add_child(instance=saint)
        here = self.make_site(slug="near-here", latitude=Decimal("43.0967"), longitude=Decimal("-0.0558"),
                              associated_saint=saint)
        self.make_site(slug="near-one", title="Betharram Test", latitude=Decimal("43.0958"),
                       longitude=Decimal("-0.2107"), summary_short="A sanctuary on the river.")
        self.make_site(slug="far-saint", title="Nevers Test", latitude=Decimal("46.9884"),
                       longitude=Decimal("3.1560"), associated_saint=saint)
        html = self.html(here)
        self.assertIn("Betharram Test", html)
        self.assertIn("A sanctuary on the river.", html)
        self.assertIn("8 mi", html)
        self.assertIn("Connected by St. Test", html)
        self.assertIn("Nevers Test", html)
        self.assertIn("mi</span>", html)
        self.assertNotIn("drive", html.split('id="nearby"')[1].split("</section>")[0])
        self.assertIn('data-section-link="nearby"', html)

    def test_saint_connection_skips_sites_already_listed(self):
        saint = SaintPage(title="St. Near", slug="st-near")
        self.site_root().add_child(instance=saint)
        here = self.make_site(slug="conn-here", latitude=Decimal("43.0967"), longitude=Decimal("-0.0558"),
                              associated_saint=saint)
        self.make_site(slug="conn-near", latitude=Decimal("43.0958"), longitude=Decimal("-0.2107"),
                       associated_saint=saint)
        self.assertEqual(SacredSitePage.objects.get(pk=here.pk).connected_sites, [])


@V2_ON
class PhotosAndPrivacyTests(V2SiteTestCase):
    def test_pilgrim_photos_is_last_and_keeps_its_empty_state(self):
        page = self.make_site(slug="photos-last", the_story="<p>S.</p>", prep_readings="<ul><li>R</li></ul>",
                              latitude=Decimal("43.0967"), longitude=Decimal("-0.0558"))
        self.add_travel(page, "getting-there")
        html = self.html(page)
        main = html.split('class="v2-main"')[1]
        last_section = main.split('<section class="v2-block')[-1]
        self.assertIn('id="pilgrim-photos"', last_section)
        self.assertIn("No pilgrim photos yet", last_section)
        self.assertIn("Sign in to add your photos", last_section)

    def test_no_review_dates_in_public_html(self):
        page = self.make_site(slug="no-dates", reviewed_history_on=date(2026, 3, 14),
                              reviewed_status_on=date(2026, 3, 15), reviewed_travel_on=date(2026, 3, 16),
                              reviewed_contacts_on=date(2026, 3, 17))
        html = self.html(page)
        for needle in ("2026-03-1", "March 14", "March 15", "March 16", "March 17", "reviewed", "Reviewed"):
            self.assertNotIn(needle, html)

    def test_learn_link_follows_the_category(self):
        from learning.models import LearnPage

        root = self.site_root()
        root.add_child(instance=LearnPage(title="Mary", slug="learn-mary-apparitions", lede="L"))
        root.add_child(instance=LearnPage(title="Eucharist", slug="the-eucharist-and-eucharistic-miracles", lede="L"))
        marian = self.make_site(slug="learn-marian", canonical_status="Nihil obstat")
        euch = self.make_site(slug="learn-euch", category="Eucharistic Miracle", canonical_status="Recognized Devotion")
        shrine = self.make_site(slug="learn-shrine", category="Shrine & Basilica", canonical_status="Recognized Devotion")
        self.assertIn('/learn-mary-apparitions/">How the Church judges apparitions</a>', self.html(marian))
        self.assertIn('/the-eucharist-and-eucharistic-miracles/">How the Church judges Eucharistic miracles</a>',
                      self.html(euch))
        self.assertNotIn("How the Church judges", self.html(shrine))

    def test_report_button_waits_for_a_live_contact_form(self):
        # A plain page at /contact/ is not the form: no button, no link.
        from wagtail.models import Page

        self.site_root().add_child(instance=Page(title="Contact", slug="contact-plain"))
        page = self.make_site(slug="report-hidden")
        html = self.html(page)
        self.assertNotIn("Report something", html)
        self.assertNotIn("topic=correction", html)

    def test_report_button_replaces_the_spot_an_error_link(self):
        from home.models import ContactPage

        self.site_root().add_child(instance=ContactPage(title="Contact", slug="contact"))
        page = self.make_site(slug="report-live")
        html = self.html(page)
        self.assertIn(f'href="/contact/?topic=correction&amp;page={page.pk}">Report something that&rsquo;s wrong</a>',
                      html)
        self.assertNotIn("Spot an error?", html, "v2 shows the button instead of the link, not both")
        with override_settings(SOG_V2_ENABLED="off"):
            off = self.html(page)
        self.assertIn("Spot an error?", off)
        self.assertNotIn("Report something", off)

    def test_travel_notice_renders_with_v2_on_and_off(self):
        page = self.make_site(slug="travel-notice")
        self.add_travel(page, "getting-there")
        for mode in ("on", "off"):
            with override_settings(SOG_V2_ENABLED=mode):
                html = self.html(page)
            self.assertIn('<p class="plan-travel-note"><strong>Pilgrim travel note:</strong>', html, mode)

    def test_plan_pills_render_only_in_v2(self):
        page = self.make_site(slug="pills", guide_level="full")
        SiteTravelSection.objects.create(page=page, kind="accessibility", body="<p>B.</p>", needs_confirmation=True)
        self.assertIn("Fully researched guide", self.html(page))
        self.assertIn("Needs confirmation", self.html(page))
        with override_settings(SOG_V2_ENABLED="off"):
            html = self.html(page)
        self.assertNotIn("Needs confirmation", html)
        self.assertNotIn("Fully researched guide", html)


class CategoryStylesTests(V2SiteTestCase):
    def test_map_reads_styles_from_python(self):
        from home.models import MapPage

        self.site_root().add_child(instance=MapPage(title="Map", slug="interactive-map"))
        html = self.client.get("/interactive-map/").content.decode()
        self.assertEqual(html.count('id="category-styles"'), 1)
        self.assertIn(CATEGORY_STYLES["Eucharistic Miracle"]["stroke"], html)
        self.assertNotIn("'Marian Apparition':", html, "no hard-coded JS copy")


class ReportCommandTests(V2SiteTestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def snapshot(self):
        return (
            list(SacredSitePage.objects.order_by("pk").values_list("pk", "eucharistic_kind", "the_story")),
            list(SiteTravelSection.objects.order_by("pk").values_list("pk", "body")),
            sum(p.revisions.count() for p in SacredSitePage.objects.all()),
        )

    def test_eucharistic_worksheet_writes_csv_and_changes_nothing(self):
        self.make_site(slug="lanciano-test", title="Lanciano Test", category="Eucharistic Miracle",
                       the_story="<p>" + "Word " * 80 + "</p>")
        self.make_site(slug="not-euch", category="Marian Apparition")
        before = self.snapshot()
        out = os.path.join(self.tmpdir, "euch.csv")
        call_command("eucharistic_kind_worksheet", "--out", out, stdout=StringIO())
        rows = list(csv.reader(open(out, encoding="utf-8")))
        self.assertEqual(rows[0][:3], ["id", "title", "url"])
        self.assertEqual([r[1] for r in rows[1:]], ["Lanciano Test"])
        self.assertEqual(len(rows[1][-1]), 200)
        self.assertEqual(self.snapshot(), before)

    def test_travel_report_flags_templated_text_and_changes_nothing(self):
        body = "<p>Most pilgrims to {name} stay two nights. The town of {name} has 12 hotels near the shrine.</p>"
        a = self.make_site(slug="tpl-a", title="Alpha Shrine", locality="Alphaville")
        b = self.make_site(slug="tpl-b", title="Beta Shrine", locality="Betatown")
        c = self.make_site(slug="tpl-c", title="Gamma Shrine")
        self.add_travel(a, "where-to-stay", body=body.format(name="Alphaville").replace("12", "9"))
        self.add_travel(b, "where-to-stay", body=body.format(name="Betatown"))
        self.add_travel(c, "where-to-stay", body="<p>Completely different words about lodging options here.</p>")
        before = self.snapshot()
        out = os.path.join(self.tmpdir, "travel.csv")
        call_command("travel_content_report", "--out", out, stdout=StringIO())
        rows = list(csv.DictReader(open(out, encoding="utf-8")))
        self.assertEqual(sorted(r["title"] for r in rows), ["Alpha Shrine", "Beta Shrine"])
        self.assertEqual(rows[0]["similarity"], "1.000")
        self.assertEqual(self.snapshot(), before)


class ImportSiteDetailsTests(V2SiteTestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def write_file(self, pages):
        path = os.path.join(self.tmpdir, "site_details_test.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"pages": pages}, fh)
        return path

    def run_import(self, path, *flags):
        out = StringIO()
        call_command("import_site_details", path, *flags, stdout=out)
        return out.getvalue()

    def entry(self, page, **fields):
        return {"id": page.pk, "title": page.title, "status": "Ready to import",
                "fields": fields or {"admission": "Free", "visit_length": "One day", "recognition_year": "1862"}}

    def test_dry_run_writes_nothing(self):
        page = self.make_site(slug="imp-dry")
        out = self.run_import(self.write_file([self.entry(page)]), "--dry-run")
        self.assertIn("Would change:  1", out)
        page = SacredSitePage.objects.get(pk=page.pk)
        self.assertIsNone(page.admission)
        self.assertEqual(page.revisions.count(), 0)

    def test_applies_then_second_run_reports_zero_changed(self):
        page = self.make_site(slug="imp-twice")
        path = self.write_file([self.entry(page)])
        out = self.run_import(path)
        self.assertIn("Pages changed:  1", out)
        page = SacredSitePage.objects.get(pk=page.pk)
        self.assertEqual((page.admission, page.visit_length, page.recognition_year), ("Free", "one-day", 1862))
        self.assertEqual(page.live_revision_id, page.latest_revision_id)
        revisions = page.revisions.count()
        out = self.run_import(path)
        self.assertIn("Pages changed:  0", out)
        self.assertIn("Already correct:      3", out)
        self.assertEqual(page.revisions.count(), revisions)
        self.assertIn("Pages matching the file:       1", self.run_import(path, "--verify"))

    def test_page_with_a_draft_is_skipped(self):
        page = self.make_site(slug="imp-draft")
        page.save_revision()
        out = self.run_import(self.write_file([self.entry(page)]))
        self.assertIn("unpublished changes", out)
        self.assertIsNone(SacredSitePage.objects.get(pk=page.pk).admission)

    def test_filled_field_is_a_conflict_not_an_overwrite(self):
        page = self.make_site(slug="imp-conflict", admission="Donation welcome")
        out = self.run_import(self.write_file([self.entry(page, admission="Free", address="1 Main St")]))
        self.assertIn("Conflicts:            1", out)
        page = SacredSitePage.objects.get(pk=page.pk)
        self.assertEqual((page.admission, page.address), ("Donation welcome", None))

    def test_too_long_value_is_rejected_not_truncated(self):
        page = self.make_site(slug="imp-long")
        out = self.run_import(self.write_file([self.entry(page, admission="x" * 121)]))
        self.assertIn("admission is 121 chars (max 120)", out)
        self.assertIsNone(SacredSitePage.objects.get(pk=page.pk).admission)

    def test_blank_and_not_ready_rows_change_nothing(self):
        page = self.make_site(slug="imp-blank", admission="Kept")
        not_ready = dict(self.entry(page, address="Somewhere"), status="Draft")
        out = self.run_import(self.write_file([self.entry(page, admission="", address=None), not_ready]))
        self.assertIn("Not ready (skipped):  1", out)
        self.assertIn("Pages unchanged:      1", out)
        page = SacredSitePage.objects.get(pk=page.pk)
        self.assertEqual((page.admission, page.address), ("Kept", None))

    def test_verify_reports_a_mismatch(self):
        page = self.make_site(slug="imp-verify")
        path = self.write_file([self.entry(page)])
        self.run_import(path)
        SacredSitePage.objects.filter(pk=page.pk).update(admission="Changed")
        with self.assertRaises(CommandError):
            call_command("import_site_details", path, "--verify", stdout=StringIO())


class DevSampleTests(V2SiteTestCase):
    @override_settings(DEBUG=False)
    def test_refuses_without_debug(self):
        with self.assertRaises(CommandError):
            call_command("v2_dev_sample", stdout=StringIO())
