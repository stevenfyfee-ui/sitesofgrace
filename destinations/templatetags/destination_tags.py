"""Links into destination hubs from existing pages. Every caller wraps these
in {% v2_enabled %}, so with v2 off nothing here is even evaluated."""
from django import template

from destinations.models import (
    MENU_HUBS_MAX, DestinationIndexPage, live_hubs, live_hubs_for_saint, live_hubs_for_site,
)

register = template.Library()


@register.simple_tag(takes_context=True)
def destination_menu(context):
    """{"hubs": up to four live hubs, "index_url": the live index or ""},
    looked up once per request."""
    request = context.get("request")
    if request is not None and hasattr(request, "_destination_menu"):
        return request._destination_menu
    index = DestinationIndexPage.objects.live().public().first()
    menu = {
        "hubs": live_hubs()[:MENU_HUBS_MAX],
        "index_url": index.get_url(request) if index else "",
    }
    if request is not None:
        request._destination_menu = menu
    return menu


@register.simple_tag
def hubs_for_site(site):
    return live_hubs_for_site(site)


@register.simple_tag
def hubs_for_saint(saint):
    return live_hubs_for_saint(saint)
