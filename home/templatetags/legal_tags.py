"""
Links to the legal pages, and the short legal notices, for any template.

{% legal_url "privacy-policy" %} is the live page's URL or "" -- the same
idea as our_story_url (about_tags.py): legal pages start life as drafts, so
nothing links to one until it's published.

{% notice "signup" %} renders that field of the "Legal notices" setting
through home/legal.py: render_notice. A link to a legal page inside a notice
shows only once that page is live; until then its words show as plain text.

One query per request finds every live legal page, however many links and
notices a page renders.
"""
import re

from django import template
from django.utils.html import escape
from django.utils.safestring import mark_safe

from home import legal
from home.models import LegalDetails, LegalNotices

register = template.Library()

# Footer "Legal & Policies" column, in order.
FOOTER_LEGAL_LINKS = [
    ("Privacy Policy", "privacy-policy"),
    ("Terms of Use", "terms-of-use"),
    ("Affiliate Disclosure", "affiliate-disclosure"),
    ("Travel Disclaimer", "travel-disclaimer"),
    ("Copyright & Content Policy", "copyright-policy"),
    ("Cookie Notice", "cookie-notice"),
]


def _legal_urls(context):
    request = context.get("request")
    if request is None:
        return legal.live_legal_urls()
    if not hasattr(request, "_legal_urls"):
        request._legal_urls = legal.live_legal_urls(request)
    return request._legal_urls


@register.simple_tag(takes_context=True)
def legal_url(context, slug):
    """The live, public legal page's URL, or "" if it isn't published."""
    return _legal_urls(context).get(slug, "")


@register.simple_tag(takes_context=True)
def footer_legal_links(context):
    """[(label, url), ...] for the footer's live legal pages, in order."""
    urls = _legal_urls(context)
    return [(label, urls[slug]) for label, slug in FOOTER_LEGAL_LINKS if urls.get(slug)]


@register.simple_tag(takes_context=True)
def notice(context, key, amount=None, link_text="", link_url=""):
    """A "Legal notices" field as safe HTML.

    amount fills {amount} (wrapped in a span support.js can update);
    link_text/link_url turn the first occurrence of link_text into a link
    when link_url is set ("Manage monthly support").
    """
    request = context.get("request")
    notices = LegalNotices.load(request_or_site=request)
    details = LegalDetails.load(request_or_site=request)
    html = legal.render_notice(getattr(notices, key), details, _legal_urls(context), amount=amount)
    if link_text and link_url:
        html = html.replace(
            escape(link_text), f'<a href="{escape(link_url)}" rel="noopener">{escape(link_text)}</a>', 1
        )
    return mark_safe(html)


_HOW_IT_WORKS_RE = re.compile(r'<a linktype="page" id="\d+">How this works</a>')


@register.simple_tag(takes_context=True)
def how_it_works_source(context, source):
    """A Support page "way" text with its "How this works" link pointed at
    the live Affiliate Disclosure page (the Store page until then)."""
    from home.models import _live_page_at

    target = _live_page_at("/affiliate-disclosure/") or _live_page_at("/store/")
    if target is None:
        return _HOW_IT_WORKS_RE.sub("How this works", source)
    return _HOW_IT_WORKS_RE.sub(f'<a linktype="page" id="{target.pk}">How this works</a>', source)
