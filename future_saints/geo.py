"""California Albers (EPSG:3310) in plain Python, and the missions map's viewBox.

One function, to_viewbox(lat, lng), places everything on the California map:
tools/build_california_outline.py uses it once to draw the state outline, and
the missions hub uses it on every request for the pins, from each canonical
page's latitude/longitude. Nothing is hard-coded per mission.

EPSG:3310 "NAD83 / California Albers": Albers equal-area conic on the GRS80
ellipsoid, standard parallels 34°N and 40.5°N, latitude of origin 0°, central
meridian 120°W, false easting 0, false northing -4,000,000 m (Snyder,
"Map Projections: A Working Manual", USGS PP 1395, eqs. 14-1 to 14-19, 3-12).
Calibration: docs/future-saints/map-calibration.md.
"""
from math import asin, cos, log, radians, sin, sqrt

# GRS80
A = 6378137.0
E2 = 0.0066943800229
E = sqrt(E2)

LAT_1, LAT_2, LAT_0, LON_0 = 34.0, 40.5, 0.0, -120.0
FALSE_EASTING, FALSE_NORTHING = 0.0, -4000000.0

# The map's SVG viewBox and the metres -> viewBox units mapping. Fixed once
# (see map-calibration.md); the outline and the pins both go through it.
VIEWBOX_WIDTH = 1000
VIEWBOX_HEIGHT = 1100
VIEWBOX = f"0 0 {VIEWBOX_WIDTH} {VIEWBOX_HEIGHT}"
METRES_PER_UNIT = 1100.0          # 1 viewBox unit = 1.1 km
ORIGIN_X = -440000.0              # EPSG:3310 metres at viewBox x = 0
ORIGIN_Y = 480000.0               # EPSG:3310 metres at viewBox y = 0 (y grows downward)


def _q(phi):
    s = sin(phi)
    return (1 - E2) * (s / (1 - E2 * s * s) - (1 / (2 * E)) * log((1 - E * s) / (1 + E * s)))


def _m(phi):
    s = sin(phi)
    return cos(phi) / sqrt(1 - E2 * s * s)


_P1, _P2, _P0 = radians(LAT_1), radians(LAT_2), radians(LAT_0)
_M1, _M2 = _m(_P1), _m(_P2)
_Q1, _Q2, _Q0 = _q(_P1), _q(_P2), _q(_P0)
_N = (_M1 ** 2 - _M2 ** 2) / (_Q2 - _Q1)
_C = _M1 ** 2 + _N * _Q1
_RHO0 = A * sqrt(_C - _N * _Q0) / _N


def albers(lat, lng):
    """(x, y) in EPSG:3310 metres for a latitude/longitude in degrees."""
    rho = A * sqrt(_C - _N * _q(radians(float(lat)))) / _N
    theta = _N * radians(float(lng) - LON_0)
    return FALSE_EASTING + rho * sin(theta), FALSE_NORTHING + _RHO0 - rho * cos(theta)


def to_viewbox(lat, lng):
    """(x, y) in the map's viewBox units; y grows downward, as in SVG."""
    x, y = albers(lat, lng)
    return (x - ORIGIN_X) / METRES_PER_UNIT, (ORIGIN_Y - y) / METRES_PER_UNIT


def point_in_polygon(x, y, ring):
    """Even-odd test: is (x, y) inside the closed ring [(x, y), ...]?"""
    inside = False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i]
        xj, yj = ring[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


# --- The World Discovery Map: Equal Earth --------------------------------------------
# Equal Earth (Šavrič, Patterson & Jenny, 2018, "The Equal Earth map projection", IJGIS
# 33(3)), on a sphere, central meridian 0°. world_viewbox(lat, lng) places the Natural Earth
# land outline (tools/build_world_outline.py, once) and every pin (each request) in one
# fixed viewBox. Antarctica is trimmed: the viewBox stops just below 60°S.
EE_A1, EE_A2, EE_A3, EE_A4 = 1.340264, -0.081106, 0.000893, 0.003796
EE_M = sqrt(3) / 2


def equal_earth(lat, lng):
    """(x, y) in Equal Earth's own units (sphere of radius 1), y north-up."""
    theta = asin(EE_M * sin(radians(float(lat))))
    t2 = theta * theta
    t6 = t2 * t2 * t2
    x = radians(float(lng)) * cos(theta) / (EE_M * (EE_A1 + 3 * EE_A2 * t2 + t6 * (7 * EE_A3 + 9 * EE_A4 * t2)))
    y = theta * (EE_A1 + EE_A2 * t2 + t6 * (EE_A3 + EE_A4 * t2))
    return x, y


WORLD_VIEWBOX_WIDTH = 1000
WORLD_VIEWBOX_HEIGHT = 445
WORLD_VIEWBOX = f"0 0 {WORLD_VIEWBOX_WIDTH} {WORLD_VIEWBOX_HEIGHT}"
_EE_XMAX = equal_earth(0, 180)[0]
_EE_YMAX = equal_earth(90, 0)[1]
WORLD_SCALE = (WORLD_VIEWBOX_WIDTH / 2) / _EE_XMAX       # viewBox units per Equal Earth unit
WORLD_TRIM_LAT = -60.0                                   # land wholly south of this is left out


def world_viewbox(lat, lng):
    """(x, y) in the world map's viewBox units; y grows downward, as in SVG."""
    x, y = equal_earth(lat, lng)
    return WORLD_VIEWBOX_WIDTH / 2 + x * WORLD_SCALE, (_EE_YMAX - y) * WORLD_SCALE
