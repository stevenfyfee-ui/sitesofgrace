"""Distances for the planner. Straight-line (great-circle) miles only: the
planner never shows drive or train times."""
from math import asin, cos, radians, sin, sqrt

EARTH_RADIUS_MI = 3958.8


def haversine_miles(lat1, lng1, lat2, lng2):
    lat1, lng1, lat2, lng2 = (radians(float(v)) for v in (lat1, lng1, lat2, lng2))
    a = sin((lat2 - lat1) / 2) ** 2 + cos(lat1) * cos(lat2) * sin((lng2 - lng1) / 2) ** 2
    return 2 * EARTH_RADIUS_MI * asin(sqrt(a))


def has_coords(obj):
    return obj.latitude is not None and obj.longitude is not None


def locality_matches(locality, city):
    """The same loose match the planner has always used for ?site=: equal,
    or one contains the other, ignoring case."""
    low, cl = (locality or "").strip().lower(), (city or "").strip().lower()
    if not low or not cl:
        return False
    return low == cl or cl in low or low in cl
