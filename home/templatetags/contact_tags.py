"""
Links to the Contact page without a hardcoded URL -- and without ever
pointing at a draft. The same idea as our_story_url (about_tags.py).

{% correction_url page %} is the one helper every "report an error" link
uses: "<contact url>?topic=correction&page=<id>", or "" while no
ContactPage is live, so the link simply doesn't render.
"""
from django import template

from home.models import ContactPage

register = template.Library()


def _contact_page(context):
    """The live, public ContactPage (max_count = 1), looked up once per
    request."""
    request = context.get("request")
    if request is not None and hasattr(request, "_contact_page"):
        return request._contact_page
    page = ContactPage.objects.live().public().first()
    if request is not None:
        request._contact_page = page
    return page


@register.simple_tag(takes_context=True)
def contact_url(context):
    """The live, public ContactPage's URL, or ""."""
    page = _contact_page(context)
    return page.get_url(context.get("request")) if page else ""


@register.simple_tag(takes_context=True)
def correction_url(context, page):
    """The Contact form, preset to "Submit a correction" about `page`."""
    url = contact_url(context)
    if not url or not getattr(page, "pk", None):
        return ""
    return f"{url}?topic=correction&page={page.pk}"
