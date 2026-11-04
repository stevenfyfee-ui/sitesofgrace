"""The one place that decides whether Pilgrimage Platform v2 UI renders.

settings.SOG_V2_ENABLED (env var SOG_V2_ENABLED):
    "off"   -- default; every page renders exactly as before v2
    "staff" -- only signed-in staff (request.user.is_staff) see v2
    "on"    -- everyone sees v2
Any other value is treated as "off", so a typo can never switch v2 on.

Templates use the matching tag: {% load v2_tags %}{% v2_enabled as v2 %}.

settings.SOG_PLANNER_V2 switches Trip Planner v2 the same way, on its own:
planner_v2_enabled(request) / {% planner_v2_enabled as planner_v2 %}.
"""
from django.conf import settings

V2_MODES = ("off", "staff", "on")


def _mode(setting_name):
    mode = str(getattr(settings, setting_name, "off") or "off").strip().lower()
    return mode if mode in V2_MODES else "off"


def _enabled(mode, request):
    if mode == "on":
        return True
    if mode == "staff":
        user = getattr(request, "user", None)
        return bool(user is not None and user.is_authenticated and user.is_staff)
    return False


def v2_mode():
    return _mode("SOG_V2_ENABLED")


def v2_enabled(request):
    return _enabled(v2_mode(), request)


def planner_v2_mode():
    """settings.SOG_PLANNER_V2: the Trip Planner v2 switch. Same three values
    and the same typo-means-off rule as SOG_V2_ENABLED, set independently."""
    return _mode("SOG_PLANNER_V2")


def planner_v2_enabled(request):
    return _enabled(planner_v2_mode(), request)
