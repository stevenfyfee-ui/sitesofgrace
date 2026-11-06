"""The one place that decides whether Future Saints (the children's section) renders.

settings.SOG_FUTURE_SAINTS (env var SOG_FUTURE_SAINTS):
    "off"   -- default; every /future-saints/ URL is a 404 and the rest of
               the site renders exactly as before
    "staff" -- only signed-in staff (request.user.is_staff) see it
    "on"    -- everyone sees it
Any other value is treated as "off", the same typo-means-off rule as
core.v2, whose helpers this reuses so the three modes behave identically.

Templates use the matching tag:
{% load future_saints_tags %}{% future_saints_enabled as fs %}.
"""
from core.v2 import _enabled, _mode


def future_saints_mode():
    return _mode("SOG_FUTURE_SAINTS")


def future_saints_enabled(request):
    return _enabled(future_saints_mode(), request)


def future_saints_public():
    """True only when the switch is "on": the section may be indexed, listed
    in the sitemap and found by search. Deliberately request-independent --
    crawlers are never staff."""
    return future_saints_mode() == "on"
