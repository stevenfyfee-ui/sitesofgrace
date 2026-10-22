"""The one place that decides whether Pilgrimage Platform v2 UI renders.

settings.SOG_V2_ENABLED (env var SOG_V2_ENABLED):
    "off"   -- default; every page renders exactly as before v2
    "staff" -- only signed-in staff (request.user.is_staff) see v2
    "on"    -- everyone sees v2
Any other value is treated as "off", so a typo can never switch v2 on.

Templates use the matching tag: {% load v2_tags %}{% v2_enabled as v2 %}.
"""
from django.conf import settings

V2_MODES = ("off", "staff", "on")


def v2_mode():
    mode = str(getattr(settings, "SOG_V2_ENABLED", "off") or "off").strip().lower()
    return mode if mode in V2_MODES else "off"


def v2_enabled(request):
    mode = v2_mode()
    if mode == "on":
        return True
    if mode == "staff":
        user = getattr(request, "user", None)
        return bool(user is not None and user.is_authenticated and user.is_staff)
    return False
