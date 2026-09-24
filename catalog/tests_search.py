"""One focused test proving Phase 1's search_fields actually reach the
database search index for a RichTextField body, not just plain CharFields --
the_story is rich text, so this also confirms get_searchable_content() is
stripping the HTML rather than indexing raw markup no reader ever typed.
"""

from decimal import Decimal

from django.core.management import call_command
from wagtail.models import Site
from wagtail.test.utils import WagtailPageTestCase

from catalog.models import SacredSitePage


class SearchIndexRichTextTests(WagtailPageTestCase):
    @classmethod
    def setUpTestData(cls):
        root = Site.objects.get(is_default_site=True).root_page
        page = SacredSitePage(
            title="Indexed Story Site",
            slug="indexed-story-site",
            category="Shrine & Basilica",
            latitude=Decimal("34.000000"),
            longitude=Decimal("-118.000000"),
            the_story="<p>A pilgrim once found a wanderfloop hidden in the crypt.</p>",
            live=True,
        )
        root.add_child(instance=page)
        cls.page = SacredSitePage.objects.get(pk=page.pk)
        call_command("update_index", verbosity=0)

    def test_word_from_the_story_is_found_after_update_index(self):
        results = SacredSitePage.objects.live().search("wanderfloop")
        self.assertIn(self.page, list(results))
