"""The planner's URL state:

    /plan/?t=rome-vatican-city.4,assisi.3&d=2027-05-10&p=2&l=mid&pace=3

t     stops as <destination slug>.<nights>, in order
d     start date, YYYY-MM-DD (optional)
p     travelers, 1-12
l     lodging tier: budget / mid / comfort
pace  sites a day for suggested days: 2 / 3 / 4

Parsing never fails: anything invalid is dropped (an unknown slug, a
repeated stop, nights out of range, a bad date) and the rest is kept. Stops
past max_stops are trimmed.
"""
import re
from dataclasses import dataclass, field
from datetime import date

from planner.itinerary import PACES, TIERS
from planner.models import NIGHTS_MAX, NIGHTS_MIN, PARTY_MAX, PARTY_MIN

SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
DEFAULT_PARTY, DEFAULT_TIER, DEFAULT_PACE = 2, "mid", 3


@dataclass
class PlanState:
    stops: list = field(default_factory=list)  # [(slug, nights)]
    start_date: date | None = None
    party: int = DEFAULT_PARTY
    tier: str = DEFAULT_TIER
    pace: int = DEFAULT_PACE

    def query(self):
        """The canonical query string for this state (no leading "?")."""
        parts = []
        if self.stops:
            parts.append("t=" + ",".join(f"{slug}.{n}" for slug, n in self.stops))
        if self.start_date:
            parts.append(f"d={self.start_date.isoformat()}")
        parts += [f"p={self.party}", f"l={self.tier}", f"pace={self.pace}"]
        return "&".join(parts)


def _int(value, lo, hi):
    try:
        n = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    return n if lo <= n <= hi else None


def parse_stops(raw, known_slugs, max_stops):
    stops, seen = [], set()
    for chunk in (raw or "").split(","):
        slug, _, nights = chunk.strip().rpartition(".")
        slug = slug.strip().lower()
        n = _int(nights, NIGHTS_MIN, NIGHTS_MAX)
        if not slug or n is None or not SLUG_RE.match(slug) or slug not in known_slugs or slug in seen:
            continue
        seen.add(slug)
        stops.append((slug, n))
    return stops[:max_stops]


def parse_date(raw):
    try:
        return date.fromisoformat((raw or "").strip()) if raw else None
    except ValueError:
        return None


def parse_state(params, known_slugs, max_stops, default_party=DEFAULT_PARTY):
    """params: a QueryDict or dict. known_slugs: the destination slugs that exist."""
    party = _int(params.get("p"), PARTY_MIN, PARTY_MAX)
    if party is None:
        party = default_party if PARTY_MIN <= default_party <= PARTY_MAX else DEFAULT_PARTY
    tier = (params.get("l") or "").strip().lower()
    pace = _int(params.get("pace"), min(PACES), max(PACES))
    return PlanState(
        stops=parse_stops(params.get("t"), known_slugs, max_stops),
        start_date=parse_date(params.get("d")),
        party=party,
        tier=tier if tier in TIERS else DEFAULT_TIER,
        pace=pace if pace in PACES else DEFAULT_PACE,
    )
