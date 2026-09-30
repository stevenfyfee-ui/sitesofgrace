"""
One small tag so the header, mobile nav, and footer can link to the "Our
Story" page without a hardcoded URL -- and without ever pointing at a draft.

AboutPage is created later by an editor (see home.models.AboutPage), not by
a migration, so nothing in the page tree can be wired to it ahead of time
the way a wagtailmenus MenuItem normally would be. This tag looks the live
page up at render time instead.
"""
from django import template

from home.models import AboutPage

register = template.Library()


@register.simple_tag
def our_story_url():
    """The live, public AboutPage's URL, or "" if it hasn't been published.

    max_count = 1 on AboutPage means there is at most one to find.
    """
    page = AboutPage.objects.live().public().first()
    return page.url if page else ""
