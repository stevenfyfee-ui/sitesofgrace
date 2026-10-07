"""
A small fixed-window rate limiter on Django's cache, shared by any view that
needs one (the Support page now; the Contact page later).

Callers pass an ip_hash (pilgrims.views._ip_hash), never a raw IP, so no
address is ever written to the cache.

With the default LocMemCache (production sets no CACHES), counts are per
process, so the limit is soft: N gunicorn workers allow up to N x limit.
That's acceptable where a downstream service is the real guard (Stripe
Radar, for checkout).
"""
from django.core.cache import cache


def hit(key_prefix, ip_hash, limit, window_seconds):
    """Record one hit; return True if this hit is OVER the limit.

    cache.add only succeeds for the first hit in a window (it never
    overwrites), and cache.incr is atomic, so two requests arriving at once
    can't both read the same count. The window starts at the first hit and
    is not extended by later ones.
    """
    key = f"ratelimit:{key_prefix}:{ip_hash}"
    if cache.add(key, 1, timeout=window_seconds):
        return 1 > limit
    try:
        count = cache.incr(key)
    except ValueError:
        # The key expired between add() and incr(): this hit opens a new window.
        cache.add(key, 1, timeout=window_seconds)
        count = 1
    return count > limit
