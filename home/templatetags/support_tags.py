"""
{% support_page as support %} -- the footer's "Support" link and the home
page's support band look the live page up at render time, the same way
"Our Story" does (home/templatetags/about_tags.py), so neither ever points
at a draft. Neither depends on settings.SUPPORT_ENABLED: once the page is
live they show, and the page itself handles its "opens soon" state.
"""
from django import template

from home.models import SupportPage

register = template.Library()


@register.simple_tag
def support_page():
    """The live, public SupportPage, or None if it hasn't been published.

    max_count = 1 on SupportPage means there is at most one to find.
    """
    return SupportPage.objects.live().public().first()
