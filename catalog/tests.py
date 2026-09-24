from django.db import IntegrityError, transaction
from wagtail.models import Page, Site
from wagtail.test.utils import WagtailPageTestCase

from catalog.models import SacredSitePage, SaintPage, SiteTravelSection


class SacredSitePageTestCase(WagtailPageTestCase):
    """Shared helper for building a site page under the tree root."""

    def site_root(self):
        """Pages must hang off the default Site's root page, not the tree root,
        or they have no routable URL and every render assertion 404s."""
        return Site.objects.get(is_default_site=True).root_page

    def make_site(self, slug="test-site", **kwargs):
        root = self.site_root()
        page = SacredSitePage(
            title=kwargs.pop("title", "Test Site"),
            slug=slug,
            category="Marian Apparition",
            **kwargs,
        )
        root.add_child(instance=page)
        return SacredSitePage.objects.get(pk=page.pk)

    def add_travel(self, page, kind, body="<p>Body.</p>", teaser=""):
        return SiteTravelSection.objects.create(
            page=page, kind=kind, body=body, teaser=teaser
        )


class PlanClusterOrderTests(SacredSitePageTestCase):
    def test_canonical_order_regardless_of_creation_order(self):
        """Reading order comes from TRAVEL_CLUSTERS, not from creation order.

        Every site page must present the same twelve in the same shape, so a
        reader who learns the layout on one page finds it unchanged on the next.
        """
        page = self.make_site()
        for kind in ["what-to-bring", "best-time-to-visit", "where-to-stay"]:
            self.add_travel(page, kind)

        page = SacredSitePage.objects.get(pk=page.pk)
        self.assertEqual(
            [section.kind for section in page.plan_sections],
            ["best-time-to-visit", "where-to-stay", "what-to-bring"],
        )
        self.assertEqual(
            [label for label, _ in page.plan_clusters],
            ["Plan the trip", "On the ground", "Practical"],
        )

    def test_panels_numbered_across_the_whole_section(self):
        """A page with three of twelve reads 1-3, not 2, 5, 10."""
        page = self.make_site()
        for kind in ["best-time-to-visit", "where-to-stay", "what-to-bring"]:
            self.add_travel(page, kind)

        page = SacredSitePage.objects.get(pk=page.pk)
        self.assertEqual(
            [section.display_number for section in page.plan_sections], [1, 2, 3]
        )

    def test_empty_clusters_are_not_rendered(self):
        page = self.make_site()
        self.add_travel(page, "where-to-stay")

        page = SacredSitePage.objects.get(pk=page.pk)
        self.assertEqual([label for label, _ in page.plan_clusters], ["On the ground"])


class TravelSectionConstraintTests(SacredSitePageTestCase):
    def test_one_kind_per_page(self):
        """The unique constraint is what guarantees anchors cannot collide.

        Two "Where to Stay" panels would mean two #where-to-stay ids on one
        page, and a deep link to either would be undefined.
        """
        page = self.make_site()
        self.add_travel(page, "where-to-stay")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self.add_travel(page, "where-to-stay")

    def test_same_kind_on_different_pages_is_fine(self):
        first = self.make_site(slug="first")
        second = self.make_site(slug="second")
        self.add_travel(first, "where-to-stay")
        self.add_travel(second, "where-to-stay")
        self.assertEqual(SiteTravelSection.objects.count(), 2)


class SectionNavTests(SacredSitePageTestCase):
    def test_plan_entry_absent_without_travel_sections(self):
        page = self.make_site(the_story="<p>Story.</p>", go_deeper="<p>More.</p>")
        self.assertEqual(page.plan_clusters, [])
        self.assertNotIn("plan-your-visit", [item["id"] for item in page.section_nav])

    def test_plan_entry_carries_children_not_top_level_entries(self):
        """Children are a display level; they must not inflate the count that
        gates the rail and the two-column grid."""
        page = self.make_site(the_story="<p>Story.</p>")
        for kind in ["best-time-to-visit", "where-to-stay", "what-to-bring"]:
            self.add_travel(page, kind)

        page = SacredSitePage.objects.get(pk=page.pk)
        nav = page.section_nav
        self.assertEqual([item["id"] for item in nav], ["the-story", "plan-your-visit"])

        plan = nav[-1]
        self.assertEqual(
            [child["id"] for child in plan["children"]],
            ["best-time-to-visit", "where-to-stay", "what-to-bring"],
        )

    def test_plan_sits_between_teaching_and_go_deeper(self):
        page = self.make_site(
            catholic_teaching="<p>Teaching.</p>", go_deeper="<p>More.</p>"
        )
        self.add_travel(page, "where-to-stay")

        page = SacredSitePage.objects.get(pk=page.pk)
        self.assertEqual(
            [item["id"] for item in page.section_nav],
            ["catholic-teaching", "plan-your-visit", "go-deeper"],
        )

    def test_visiting_pilgrimage_no_longer_renders(self):
        """The legacy field is kept for one deploy, but must not double up with
        the panel its text was migrated into."""
        page = self.make_site(pilgrimage_info="<p>Old travel text.</p>")
        self.assertNotIn(
            "visiting-pilgrimage", [item["id"] for item in page.section_nav]
        )


class WithNavGateTests(SacredSitePageTestCase):
    """The 22cee897 regression, in its new disguise.

    A page whose only top-level entry is "Plan Your Visit" -- however many
    children it has -- must not become a two-column grid, or its content lands
    in the 210px nav column.
    """

    def test_single_top_level_entry_gets_no_grid(self):
        page = self.make_site(slug="lone-plan")
        for kind in ["best-time-to-visit", "where-to-stay"]:
            self.add_travel(page, kind)

        page = SacredSitePage.objects.get(pk=page.pk)
        self.assertEqual(len(page.section_nav), 1)

        html = self.client.get(page.url).content.decode()
        self.assertNotIn("section-layout--with-nav", html)

    def test_two_top_level_entries_get_the_grid(self):
        page = self.make_site(slug="two-entries", the_story="<p>Story.</p>")
        self.add_travel(page, "where-to-stay")

        html = self.client.get(page.url).content.decode()
        self.assertIn("section-layout--with-nav", html)
        self.assertIn("section-nav-sublist", html)

    def test_saint_page_still_has_no_rail(self):
        root = self.site_root()
        saint = SaintPage(title="Test Saint", slug="test-saint", body="<p>Life.</p>")
        root.add_child(instance=saint)

        response = self.client.get(SaintPage.objects.get(pk=saint.pk).url)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("section-layout--with-nav", response.content.decode())


class QuickCardTests(SacredSitePageTestCase):
    def test_hidden_with_one_cell(self):
        """One fact is worse than none -- a card with a single cell reads as
        broken rather than brief."""
        page = self.make_site(quick_ideal_stay="2-3 days")
        self.assertEqual(len(page.quick_card_cells), 1)
        self.assertFalse(page.show_quick_card)

    def test_shown_with_two_cells(self):
        page = self.make_site(quick_ideal_stay="2-3 days", feast_day="February 11")
        self.assertTrue(page.show_quick_card)
        self.assertEqual(
            [label for label, _, _ in page.quick_card_cells],
            ["Ideal stay", "Feast day"],
        )

    def test_rendered_in_the_page(self):
        page = self.make_site(
            slug="quick-card",
            the_story="<p>Story.</p>",
            quick_ideal_stay="2-3 days",
            quick_ideal_stay_note="1 day if passing through",
            feast_day="February 11",
        )
        self.add_travel(page, "where-to-stay")

        html = self.client.get(page.url).content.decode()
        self.assertIn("2-3 days", html)
        self.assertIn("1 day if passing through", html)


class PanelRenderingTests(SacredSitePageTestCase):
    def test_panels_are_closed_and_their_text_is_in_the_dom(self):
        """Collapsed, but crawlable and findable with Ctrl-F -- which is the
        whole reason these are <details> and not a JS accordion."""
        page = self.make_site(slug="panels", the_story="<p>Story.</p>")
        self.add_travel(
            page,
            "where-to-stay",
            body="<p>Stay inside the ten-minute ring.</p>",
            teaser="Inside the ten-minute ring",
        )

        html = self.client.get(page.url).content.decode()
        self.assertIn('id="where-to-stay"', html)
        self.assertIn("Stay inside the ten-minute ring.", html)
        self.assertIn("Inside the ten-minute ring", html)
        self.assertNotIn("<details class=\"plan-panel\" open", html)


class NearbySitesTests(SacredSitePageTestCase):
    """"In the Area" — the 40-mile band at the foot of a sacred site page."""

    def test_only_sites_inside_the_radius_appear_and_nearest_comes_first(self):
        # Lourdes, with two real neighbours and one site a country away.
        lourdes = self.make_site(
            slug="lourdes", title="Lourdes", latitude="43.096800", longitude="-0.048900"
        )
        betharram = self.make_site(
            slug="betharram", title="Betharram", latitude="43.124700", longitude="-0.223100"
        )  # ~9 mi
        garaison = self.make_site(
            slug="garaison", title="Garaison", latitude="43.161000", longitude="0.383000"
        )  # ~22 mi
        self.make_site(
            slug="fatima", title="Fatima", latitude="39.631700", longitude="-8.672200"
        )  # ~450 mi — must not appear

        nearby = SacredSitePage.objects.get(pk=lourdes.pk).nearby_sites
        self.assertEqual(
            [entry["page"].pk for entry in nearby], [betharram.pk, garaison.pk]
        )
        self.assertNotIn(lourdes.pk, [entry["page"].pk for entry in nearby])
        self.assertEqual(nearby[0]["miles_display"], "9")

    def test_a_site_without_coordinates_has_no_band(self):
        self.make_site(
            slug="neighbour", title="Neighbour", latitude="43.124700", longitude="-0.223100"
        )
        page = self.make_site(slug="no-coords", title="No Coords")
        self.assertEqual(SacredSitePage.objects.get(pk=page.pk).nearby_sites, [])

    def test_draft_neighbours_are_excluded(self):
        lourdes = self.make_site(
            slug="lourdes-2", title="Lourdes", latitude="43.096800", longitude="-0.048900"
        )
        draft = self.make_site(
            slug="draft-neighbour", title="Draft", latitude="43.124700", longitude="-0.223100"
        )
        draft.live = False
        draft.save()

        self.assertEqual(SacredSitePage.objects.get(pk=lourdes.pk).nearby_sites, [])

    def test_band_renders_the_chips_on_the_page(self):
        lourdes = self.make_site(
            slug="lourdes-3", title="Lourdes", latitude="43.096800", longitude="-0.048900",
            the_story="<p>Story.</p>",
        )
        self.make_site(
            slug="betharram-3", title="Betharram", latitude="43.124700", longitude="-0.223100"
        )

        html = self.client.get(lourdes.url).content.decode()
        self.assertIn("In the Area", html)
        self.assertIn("nearby-chip", html)
        self.assertIn("Betharram", html)
