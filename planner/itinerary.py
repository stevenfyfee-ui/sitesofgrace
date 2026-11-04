"""The one itinerary engine. Pure Python: no database, no request.

build_itinerary() turns stops (DestinationData, nights) plus the trip
settings into days and a budget. The planner page, /plan/build/ and the
shared-trip view all call it; planner/plan_data.py loads the inputs.

Rules (docs/planner/trip-planner-mockup.html review notes):
- Day 1 is always a light arrival day. The first stop's rows start on day 2.
- Each stop uses its curated rows in order. Extra nights become free days;
  rows that don't fit come back cut=True ("add a night").
- No curated rows: the stop's live sites in nearest-neighbor order from the
  destination's coordinates, split by pace, labelled "Suggested order".
  No sites either: free days only, with no "Suggested order".
- A later stop's first day says "Travel from <previous> · about N mi"
  (straight-line, whole miles). Never drive or train times.
- The last day is Departure, from the last stop's gateway or nearest airport.
- Budget: today's plan.js formula, exactly. Prices are never stored.
"""
from dataclasses import asdict, dataclass, field
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal
from math import ceil

from planner.geo import haversine_miles

ARRIVAL_TITLE = "Arrive and settle in"
ARRIVAL_NOTE = "Rest after the flight. Find an evening Mass near where you're staying."
FREE_TITLE = "Free day"
FREE_NOTE = "Rest, go back to a favorite place, or take a day trip."
SUGGESTED_TITLE = "Sacred places"
DEPARTURE_TITLE = "Departure"

TIERS = ("budget", "mid", "comfort")
TIER_LABELS = {"budget": "Budget", "mid": "Mid-range", "comfort": "Comfort"}
PACES = (2, 3, 4)


@dataclass
class SiteRef:
    slug: str
    title: str
    url: str = ""
    latitude: float | None = None
    longitude: float | None = None
    pk: int = 0


@dataclass
class PlanDayRef:
    title: str
    sites: list = field(default_factory=list)
    extra_places: str = ""


@dataclass
class DestinationData:
    slug: str
    city: str
    region: str
    country: str = ""
    latitude: float | None = None
    longitude: float | None = None
    airport_iata: str = ""
    airport_name: str = ""
    gateway_iata: str = ""
    gateway_name: str = ""
    hotel: Decimal = Decimal("0")
    meal: Decimal = Decimal("0")
    transport: Decimal = Decimal("0")
    curated: list = field(default_factory=list)
    sites: list = field(default_factory=list)

    @property
    def short_name(self):
        """"Rome / Vatican City" -> "Rome", as the mockup's route strip shows it."""
        return self.city.split(" / ")[0].strip()

    @property
    def has_coords(self):
        return self.latitude is not None and self.longitude is not None

    @property
    def fly_iata(self):
        """The international airport: the gateway when set, else the nearest."""
        return self.gateway_iata or self.airport_iata

    @property
    def nearest_iata_if_different(self):
        """The nearest airport, only when it isn't the one we fly into
        ("Fly into FCO · nearest airport PEG")."""
        if self.gateway_iata and self.airport_iata and self.airport_iata != self.gateway_iata:
            return self.airport_iata
        return ""

    @property
    def plan_kind(self):
        if self.curated:
            return "curated"
        return "suggested" if self.sites else "none"


@dataclass
class Pricing:
    meals_per_day: int
    people_per_room: int
    multipliers: dict
    misc_pct: int
    hop: Decimal
    region_flights: dict
    currency: str = "USD"


@dataclass
class Day:
    number: int | None
    date: object
    stop_slug: str
    kind: str
    title: str
    sites: list = field(default_factory=list)
    extra_places: str = ""
    note: str = ""
    tag: str = ""
    cut: bool = False
    airport: str = ""
    nearest_airport: str = ""


@dataclass
class Budget:
    flights: Decimal
    lodging: Decimal
    meals: Decimal
    transport: Decimal
    extras: Decimal
    total: Decimal
    per_person: Decimal
    rooms: int
    nights: int
    misc_pct: int
    basis: str


@dataclass
class Itinerary:
    days: list
    budget: Budget | None
    nights: int
    day_count: int
    start_date: object = None
    end_date: object = None


def round_half_up(value):
    """JavaScript's Math.round for positive amounts: halves go up."""
    return int(Decimal(value).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def whole_miles(a, b):
    if not (a.has_coords and b.has_coords):
        return None
    return round_half_up(Decimal(str(haversine_miles(a.latitude, a.longitude, b.latitude, b.longitude))))


def nearest_neighbor(sites, start=None):
    """Sites in nearest-neighbor order, starting with the one nearest
    `start` (lat, lng). Ties break on title then pk so the order is stable.
    Sites without coordinates follow, by title."""
    placed = [s for s in sites if s.latitude is not None and s.longitude is not None]
    rest = sorted((s for s in sites if s.latitude is None or s.longitude is None), key=lambda s: (s.title, s.pk))
    if not placed:
        return rest
    remaining = sorted(placed, key=lambda s: (s.title, s.pk))
    if start is None:
        current = remaining.pop(0)
    else:
        current = min(remaining, key=lambda s: (haversine_miles(start[0], start[1], s.latitude, s.longitude),
                                                s.title, s.pk))
        remaining.remove(current)
    ordered = [current]
    while remaining:
        current = min(remaining, key=lambda s: (haversine_miles(current.latitude, current.longitude,
                                                                s.latitude, s.longitude), s.title, s.pk))
        remaining.remove(current)
        ordered.append(current)
    return ordered + rest


def stop_rows(dest, pace):
    """The rows a stop wants, before fitting them to its nights:
    [(kind, title, sites, extra_places)]."""
    if dest.curated:
        return [("curated", d.title, list(d.sites), d.extra_places or "") for d in dest.curated]
    start = (dest.latitude, dest.longitude) if dest.has_coords else None
    ordered = nearest_neighbor(dest.sites, start)
    return [("suggested", SUGGESTED_TITLE, ordered[i:i + pace], "") for i in range(0, len(ordered), pace)]


DEFAULT_CURATED_DAYS_CAP = 3


def default_nights(dest, first, pace=3):
    """Step 1's default: one night per curated day (at most 3; the rest show
    as "add a night"), or per suggested row, plus the arrival night for the
    first stop. At least 1."""
    if dest.curated:
        rows = min(len(dest.curated), DEFAULT_CURATED_DAYS_CAP)
    else:
        rows = len(stop_rows(dest, pace))
    return max(1, rows + (1 if first else 0))


def build_itinerary(stops, start_date, party, tier, pace, *, pricing=None):
    """stops: [(DestinationData, nights)] in trip order. start_date may be None."""
    days, number = [], 0

    def date_for(n):
        return start_date + timedelta(days=n - 1) if start_date and n else None

    for i, (dest, nights) in enumerate(stops):
        rows = stop_rows(dest, pace)
        if i == 0:
            rows = [("arrival", ARRIVAL_TITLE, [], "")] + rows
        for k in range(max(nights, len(rows))):
            fits = k < nights
            if fits:
                number += 1
            if k < len(rows):
                kind, title, sites, extra = rows[k]
            elif fits:
                kind, title, sites, extra = "free", FREE_TITLE, [], ""
            else:
                continue
            tag, airport, nearest = "", "", ""
            if fits and k == 0 and i == 0:
                airport, nearest = dest.fly_iata, dest.nearest_iata_if_different
                tag = (f"Arrive · fly into {airport}" if airport else "Arrive") + (
                    f" · nearest airport {nearest}" if nearest else "")
            elif fits and k == 0:
                prev = stops[i - 1][0]
                miles = whole_miles(prev, dest)
                tag = f"Travel from {prev.short_name}" + (f" · about {miles:,} mi" if miles is not None else "")
            note = ARRIVAL_NOTE if kind == "arrival" else FREE_NOTE if kind == "free" else ""
            days.append(Day(
                number=number if fits else None, date=date_for(number) if fits else None,
                stop_slug=dest.slug, kind=kind, title=title, sites=sites, extra_places=extra,
                note=note, tag=tag, cut=not fits, airport=airport, nearest_airport=nearest,
            ))

    nights_total = sum(n for _, n in stops)
    if stops:
        last = stops[-1][0]
        number += 1
        days.append(Day(
            number=number, date=date_for(number), stop_slug=last.slug, kind="departure",
            title=DEPARTURE_TITLE, tag=f"Fly home from {last.fly_iata}" if last.fly_iata else "Fly home",
            airport=last.fly_iata, nearest_airport=last.nearest_iata_if_different,
        ))

    return Itinerary(
        days=days,
        budget=build_budget(stops, party, tier, pricing) if (stops and pricing) else None,
        nights=nights_total,
        day_count=nights_total + 1 if stops else 0,
        start_date=start_date if stops else None,
        end_date=(start_date + timedelta(days=nights_total)) if (start_date and stops) else None,
    )


def build_budget(stops, party, tier, pricing):
    """Today's plan.js formula, in Decimal. Round only for display."""
    p = pricing
    rooms = ceil(party / p.people_per_room)
    mult = Decimal(str(p.multipliers.get(tier, p.multipliers["mid"])))
    lodging = meals = transport = Decimal("0")
    max_rt = Decimal("0")
    nights_total = 0
    for dest, nights in stops:
        lodging += Decimal(dest.hotel) * mult * rooms * nights
        meals += Decimal(dest.meal) * p.meals_per_day * party * nights
        transport += Decimal(dest.transport) * party * nights
        nights_total += nights
        max_rt = max(max_rt, Decimal(str(p.region_flights.get(dest.region, 0))))
    flights = max_rt * party + Decimal(p.hop) * party * max(0, len(stops) - 1)
    subtotal = flights + lodging + meals + transport
    extras = subtotal * p.misc_pct / 100
    total = subtotal + extras

    hops = len(stops) - 1
    basis = (f"{rooms} room{'s' if rooms > 1 else ''}, {nights_total} nights, "
             f"{TIER_LABELS.get(tier, 'Mid-range').lower()} lodging, 1 round trip from the U.S."
             + (f" + {hops} hop{'s' if hops > 1 else ''} between stops" if hops > 0 else "") + ".")
    return Budget(flights=flights, lodging=lodging, meals=meals, transport=transport, extras=extras,
                  total=total, per_person=total / party, rooms=rooms, nights=nights_total,
                  misc_pct=p.misc_pct, basis=basis)


def money(amount, currency="USD"):
    """Display rounding, the way the old estimator showed it."""
    n = round_half_up(amount)
    return f"${n:,}" if currency == "USD" else f"{n:,} {currency}"


def itinerary_json(it, currency="USD"):
    """The /plan/build/ payload: plain types only."""
    def day(d):
        out = asdict(d)
        out["date"] = d.date.isoformat() if d.date else None
        out["sites"] = [{"slug": s.slug, "title": s.title, "url": s.url} for s in d.sites]
        return out

    b = it.budget
    budget = None
    if b:
        budget = {
            "flights": money(b.flights, currency), "lodging": money(b.lodging, currency),
            "meals": money(b.meals, currency), "transport": money(b.transport, currency),
            "extras": money(b.extras, currency), "total": money(b.total, currency),
            "per_person": money(b.per_person, currency), "total_exact": str(b.total.quantize(Decimal("0.01"))),
            "misc_pct": b.misc_pct, "rooms": b.rooms, "nights": b.nights, "basis": b.basis,
        }
    return {
        "days": [day(d) for d in it.days],
        "budget": budget,
        "nights": it.nights,
        "day_count": it.day_count,
        "start_date": it.start_date.isoformat() if it.start_date else None,
        "end_date": it.end_date.isoformat() if it.end_date else None,
    }
