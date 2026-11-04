"""Whether the planner may show affiliate booking links.

One rule, checked both when Settings > Trip planner is saved (PlannerSettings.clean)
and every time a page or /go/planner/ link renders: booking links need
show_booking_links on AND a live Affiliate Disclosure page (Standing Rule 9).
If the disclosure page is unpublished later, the links disappear with it.
"""
from home.legal import live_legal_urls

DISCLOSURE_SLUG = "affiliate-disclosure"


def affiliate_disclosure_url(request=None):
    """The live Affiliate Disclosure page's URL, or "" if it isn't published."""
    return live_legal_urls(request).get(DISCLOSURE_SLUG) or ""


def affiliate_disclosure_live(request=None):
    return bool(affiliate_disclosure_url(request))


def booking_links_allowed(request=None):
    from planner.models import PlannerSettings

    if not PlannerSettings.load(request_or_site=request).show_booking_links:
        return False
    return affiliate_disclosure_live(request)
