"""
Kept as `community_tags` (library name + tag name + include-template path)
on purpose: catalog/templates/catalog/sacred_site_page.html loads this
library and calls {% journey_buttons page %} without knowing or caring that
the former `community` app was absorbed into `pilgrims`. Renaming this
library would mean touching a catalog template outside this phase's scope
for no functional gain.
"""
from django import template

from pilgrims.models import SiteVisit

register = template.Library()


@register.inclusion_tag("community/_journey_buttons.html", takes_context=True)
def journey_buttons(context, site):
    request = context["request"]
    current_status = None
    if request.user.is_authenticated:
        visit = SiteVisit.objects.filter(owner=request.user, site=site).first()
        current_status = visit.status if visit else None
    return {
        "site": site,
        "current_status": current_status,
        "is_authenticated": request.user.is_authenticated,
        "request": request,
    }
