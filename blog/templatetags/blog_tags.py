"""
{% blog_url as url %} -- the header, mobile nav, and footer link to the blog
the same way they link to "Our Story" (see home/templatetags/about_tags.py):
looked up live at render time, never pointing at a draft.
"""
from django import template

from blog.models import BlogIndexPage

register = template.Library()


@register.simple_tag
def blog_url():
    """The live, public BlogIndexPage's URL, or "" if it hasn't been published.

    max_count = 1 on BlogIndexPage means there is at most one to find.
    """
    page = BlogIndexPage.objects.live().public().first()
    return page.url if page else ""


@register.simple_tag(takes_context=True)
def absolute_url(context, url):
    """`url` made absolute against the current request, for og:image and
    JSON-LD. A URL that's already absolute (images on Spaces) passes through."""
    request = context.get("request")
    return request.build_absolute_uri(url) if request else url


@register.filter
def startswith(value, prefix):
    """{% if request.path|startswith:blog_link %} -- "Blog" stays current on
    the index, every category page, the feed, and every post under it."""
    return bool(prefix) and str(value).startswith(str(prefix))
