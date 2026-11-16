from django import template

from future_saints.switch import future_saints_enabled as _future_saints_enabled

register = template.Library()


@register.simple_tag(takes_context=True)
def future_saints_enabled(context):
    """{% future_saints_enabled as fs %} -- future_saints.switch.future_saints_enabled(request)."""
    return _future_saints_enabled(context.get("request"))


# The banner's four features: (text field, icon in home/includes/_fs_banner_icon.html, page path
# under the Future Saints home).
BANNER_FEATURES = (
    ("feature_1", "book", "saints/"),
    ("feature_2", "marker", "map/"),
    ("feature_3", "palette", "california-missions/projects/"),
    ("feature_4", "group", "for-grown-ups/"),
)


@register.simple_tag(takes_context=True)
def future_saints_banner(context, page):
    """The adult homepage's Future Saints banner (home/includes/_future_saints_banner.html), or None.

    None unless the switch allows this request AND the Future Saints home page is live. With the
    switch off it returns before touching the database, so the homepage renders exactly as before.
    Each feature links to its page only while that page is live; otherwise its label shows unlinked.
    """
    request = context.get("request")
    if not _future_saints_enabled(request):
        return None
    from wagtail.models import Page

    from future_saints.models import FutureSaintsHomePage

    home = FutureSaintsHomePage.objects.live().first()
    if home is None:
        return None
    live = {p.url_path: p for p in Page.objects.live().filter(
        url_path__in=[home.url_path + path for _, _, path in BANNER_FEATURES])}
    texts = page.fs_banner_texts()
    features = []
    for name, icon, path in BANNER_FEATURES:
        target = live.get(home.url_path + path)
        features.append({"label": texts[name], "icon": icon, "url": target.get_url(request) if target else ""})
    return {"url": home.get_url(request), "texts": texts, "features": features}
