from django import template

from future_saints.switch import future_saints_enabled as _future_saints_enabled

register = template.Library()


@register.simple_tag(takes_context=True)
def future_saints_enabled(context):
    """{% future_saints_enabled as fs %} -- future_saints.switch.future_saints_enabled(request)."""
    return _future_saints_enabled(context.get("request"))


@register.simple_tag(takes_context=True)
def future_saints_menu_url(context):
    """The main-site menu's "Future Saints" link, or "".

    "" unless the switch allows this request AND the Future Saints home page
    is live. With the switch off it returns before touching the database, so
    the adult header renders exactly as before. Not a wagtailmenus item on
    purpose: a menu item would show whenever the page is live, ignoring the
    switch.
    """
    request = context.get("request")
    if not _future_saints_enabled(request):
        return ""
    from future_saints.models import FutureSaintsHomePage

    page = FutureSaintsHomePage.objects.live().first()
    return page.get_url(request) if page else ""
