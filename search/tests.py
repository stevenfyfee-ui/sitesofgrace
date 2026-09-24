"""Tests for site-wide search.

Two things matter most here: that Phase 1's search_fields actually widened
what's searchable (a hit on body text, not just the title -- see
SuggestSummaryShortRegressionTests), and that .public() is never dropped from
the suggest query, since that's the only thing standing between this endpoint
and leaking a restricted page's title once the site goes behind page privacy.
"""

import json
from decimal import Decimal

from django.core.management import call_command
from django.test import Client, TestCase
from django.test.utils import CaptureQueriesContext
from django.db import connection
from django.urls import reverse
from wagtail.models import PageViewRestriction, Site

from catalog.models import CATEGORY_CHOICES, PilgrimageTrailPage, SacredSitePage, SaintPage


class SearchTestCase(TestCase):
    @classmethod
    def site_root(cls):
        return Site.objects.get(is_default_site=True).root_page

    @classmethod
    def make_site(cls, slug, title="A Site", category="Shrine & Basilica", **kwargs):
        page = SacredSitePage(
            title=title,
            slug=slug,
            category=category,
            latitude=Decimal(kwargs.pop("latitude", "34.000000")),
            longitude=Decimal(kwargs.pop("longitude", "-118.000000")),
            live=True,
            **kwargs,
        )
        cls.site_root().add_child(instance=page)
        return SacredSitePage.objects.get(pk=page.pk)

    @classmethod
    def make_saint(cls, slug, title="A Saint", **kwargs):
        page = SaintPage(title=title, slug=slug, live=True, **kwargs)
        cls.site_root().add_child(instance=page)
        return SaintPage.objects.get(pk=page.pk)

    @classmethod
    def make_trail(cls, slug="a-trail", title="A Trail", **kwargs):
        page = PilgrimageTrailPage(title=title, slug=slug, live=True, **kwargs)
        cls.site_root().add_child(instance=page)
        return PilgrimageTrailPage.objects.get(pk=page.pk)

    @classmethod
    def reindex(cls):
        call_command("update_index", verbosity=0)


class SuggestShortQueryTests(SearchTestCase):
    def test_query_under_two_chars_returns_empty_groups_not_an_error(self):
        client = Client()
        response = client.get(reverse("search_suggest"), {"q": "a"})
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data["query"], "a")
        self.assertEqual(data["groups"], [])


class SuggestSummaryShortRegressionTests(SearchTestCase):
    """The single most important assertion in this file: Phase 1 added
    search_fields for summary_short, so a word that never appears in the
    title must still surface a site here. Before Phase 1, only the title
    was indexed and this would have returned nothing."""

    @classmethod
    def setUpTestData(cls):
        cls.site = cls.make_site(
            "quiet-chapel",
            title="Quiet Chapel",
            summary_short="Locals still speak of the florbleglorp apparition here.",
        )
        cls.reindex()

    def test_word_only_in_summary_short_finds_the_page(self):
        client = Client()
        response = client.get(reverse("search_suggest"), {"q": "florbleglorp"})
        data = json.loads(response.content)
        sites_group = next((g for g in data["groups"] if g["key"] == "sites"), None)
        self.assertIsNotNone(sites_group, "expected a 'sites' group in the response")
        titles = [r["title"] for r in sites_group["results"]]
        self.assertIn("Quiet Chapel", titles)


class SuggestTypesFilterTests(SearchTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.site = cls.make_site("pilgrimtestword-shrine", title="Pilgrimtestword Shrine")
        cls.saint = cls.make_saint("pilgrimtestword-saint", title="Pilgrimtestword Saint")
        cls.reindex()

    def test_no_types_param_returns_both_groups(self):
        client = Client()
        response = client.get(reverse("search_suggest"), {"q": "pilgrimtestword"})
        data = json.loads(response.content)
        keys = {g["key"] for g in data["groups"]}
        self.assertIn("sites", keys)
        self.assertIn("saints", keys)

    def test_types_sites_excludes_saints(self):
        client = Client()
        response = client.get(reverse("search_suggest"), {"q": "pilgrimtestword", "types": "sites"})
        data = json.loads(response.content)
        keys = {g["key"] for g in data["groups"]}
        self.assertIn("sites", keys)
        self.assertNotIn("saints", keys)


class SuggestPrivacyTests(SearchTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.restricted = cls.make_site("secretville", title="Secretville Shrine of Confidentialtestia")
        PageViewRestriction.objects.create(
            page=cls.restricted, restriction_type=PageViewRestriction.PASSWORD, password="hunter2"
        )
        cls.reindex()

    def test_restricted_page_does_not_appear_in_suggest(self):
        client = Client()
        response = client.get(reverse("search_suggest"), {"q": "confidentialtestia"})
        data = json.loads(response.content)
        self.assertEqual(data["groups"], [], "a restricted page's title leaked through suggest()")


class SuggestSerializationTests(SearchTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.site = cls.make_site(
            "lighthouse-shrine", title="Lighthouse Shrine", category="Marian Apparition"
        )
        cls.saint = cls.make_saint("lighthouse-saint", title="Lighthouse Saint")
        cls.reindex()

    def test_results_carry_url_and_site_results_carry_chip_fill(self):
        client = Client()
        response = client.get(reverse("search_suggest"), {"q": "lighthouse"})
        data = json.loads(response.content)

        for group in data["groups"]:
            for result in group["results"]:
                self.assertTrue(result["url"], "result missing a url")
                if group["key"] == "sites":
                    self.assertIsNotNone(result["chip_fill"])
                else:
                    self.assertIsNone(result["chip_fill"])


class ResultsPageGroupingTests(SearchTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.marian = cls.make_site(
            "groupword-marian", title="Groupword Marian Site", category="Marian Apparition"
        )
        cls.shrine = cls.make_site(
            "groupword-shrine", title="Groupword Shrine Site", category="Shrine & Basilica"
        )
        cls.saint = cls.make_saint("groupword-saint", title="Groupword Saint")
        cls.reindex()

    def test_overview_group_counts_match_rendered_rows(self):
        client = Client()
        response = client.get(reverse("search"), {"query": "groupword"})
        self.assertEqual(response.status_code, 200)

        groups_preview = response.context["groups_preview"]
        self.assertIsNotNone(groups_preview)
        for group in groups_preview:
            # Preview is capped at 10 -- with this small a fixture the total
            # should equal what's rendered, so this also proves total isn't
            # silently under/over-counting.
            self.assertEqual(group["total"], len(group["results"]))

        total_count = response.context["total_count"]
        rendered = sum(len(g["results"]) for g in groups_preview)
        self.assertEqual(total_count, rendered)

    def test_category_param_narrows_to_that_category_only(self):
        client = Client()
        category = dict(CATEGORY_CHOICES)["Marian Apparition"]
        response = client.get(reverse("search"), {"query": "groupword", "category": category})
        self.assertEqual(response.status_code, 200)

        self.assertEqual(response.context["active_group_key"], "sites")
        self.assertEqual(response.context["active_site_category"], "Marian Apparition")

        titles = [r.title for r in response.context["active_results"]]
        self.assertIn("Groupword Marian Site", titles)
        self.assertNotIn("Groupword Shrine Site", titles)
        self.assertNotIn("Groupword Saint", titles)


class SuggestQueryCostTests(SearchTestCase):
    """Pins the worst case per keystroke: a query that matches nothing runs
    all three resolution tiers (autocomplete, search, icontains) against all
    three groups, since none of them short-circuits early. If this number
    ever creeps up, something added an extra query per group per tier --
    exactly the cost that matters most, since it's paid on every keystroke
    a visitor types with no hits yet (the common case while typing)."""

    @classmethod
    def setUpTestData(cls):
        # Real fixtures, not an empty table -- the fallback chain still has
        # to run all three tiers per group even when data exists, it's just
        # that none of it matches this particular query.
        cls.site = cls.make_site("querycost-site", title="Querycost Site")
        cls.saint = cls.make_saint("querycost-saint", title="Querycost Saint")
        cls.trail = cls.make_trail("querycost-trail", title="Querycost Trail")
        cls.reindex()

    def test_no_match_in_any_group_worst_case_query_count(self):
        client = Client()
        with CaptureQueriesContext(connection) as ctx:
            response = client.get(reverse("search_suggest"), {"q": "nomatchanywherexyz"})
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data["groups"], [])
        # 3 groups x (1 PageViewRestriction + 3 fallback tiers) = 12.
        # ContentType lookups don't add a query here because setUpTestData's
        # own page creation already warmed Django's process-wide ContentType
        # cache -- which is also the realistic steady state: a live worker
        # process serves this endpoint many times, so the *first* request
        # after startup pays one extra query per group for that cache (15
        # total, measured against a cold process), but every keystroke after
        # that -- the actual "per keystroke" cost -- pays this number.
        self.assertEqual(
            len(ctx.captured_queries), 12,
            "suggest query count changed - see the comment above before adjusting",
        )
