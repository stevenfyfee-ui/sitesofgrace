"""Phase 2: the itinerary engine (pure Python, no database).

Budget expectations were computed by hand from today's plan.js formula and
the seed values in planner/tests/base.py, not from the engine.
"""
from datetime import date
from decimal import Decimal
from unittest import TestCase

from planner.itinerary import (
    DestinationData, PlanDayRef, Pricing, SiteRef, build_itinerary, default_nights, money,
    nearest_neighbor, round_half_up,
)

PRICING = Pricing(
    meals_per_day=3, people_per_room=2,
    multipliers={"budget": Decimal("0.70"), "mid": Decimal("1.00"), "comfort": Decimal("1.60")},
    misc_pct=12, hop=Decimal("150"),
    region_flights={"Southern Europe": Decimal("850"), "Western Europe": Decimal("800")},
)


def site(slug, lat=None, lng=None, pk=0):
    return SiteRef(slug=slug, title=slug.replace("-", " ").title(), url=f"/{slug}/", latitude=lat, longitude=lng,
                   pk=pk)


def rome(**kw):
    return DestinationData(**{**dict(
        slug="rome-vatican-city", city="Rome / Vatican City", region="Southern Europe",
        latitude=41.9022, longitude=12.4539, airport_iata="FCO",
        hotel=Decimal("130"), meal=Decimal("22"), transport=Decimal("8")), **kw})


def assisi(**kw):
    return DestinationData(**{**dict(
        slug="assisi", city="Assisi", region="Southern Europe", latitude=43.0703, longitude=12.6196,
        airport_iata="PEG", gateway_iata="FCO",
        hotel=Decimal("100"), meal=Decimal("20"), transport=Decimal("6")), **kw})


def lourdes(**kw):
    return DestinationData(**{**dict(
        slug="lourdes", city="Lourdes", region="Western Europe", latitude=43.0949, longitude=-0.0460,
        airport_iata="LDE", hotel=Decimal("110"), meal=Decimal("20"), transport=Decimal("5")), **kw})


def curated(*titles):
    return [PlanDayRef(title=t, sites=[site(t.lower().replace(" ", "-"))]) for t in titles]


class BudgetTests(TestCase):
    def budget(self, stops, party=2, tier="mid"):
        return build_itinerary(stops, None, party, tier, 3, pricing=PRICING).budget

    def test_golden_rome_assisi_mid(self):
        b = self.budget([(rome(), 4), (assisi(), 3)])
        self.assertEqual(b.total, Decimal("4264.96"))
        self.assertEqual(money(b.total), "$4,265")
        self.assertEqual(money(b.per_person), "$2,132")
        self.assertEqual((b.flights, b.lodging, b.meals, b.transport), (Decimal(2000), Decimal(820), Decimal(888),
                                                                         Decimal(100)))
        self.assertEqual(b.basis, "1 room, 7 nights, mid-range lodging, 1 round trip from the U.S. "
                                  "+ 1 hop between stops.")

    def test_budget_tier(self):
        b = self.budget([(rome(), 4), (assisi(), 3)], tier="budget")
        self.assertEqual(b.total, Decimal("3989.44"))
        self.assertEqual((money(b.total), money(b.per_person)), ("$3,989", "$1,995"))

    def test_comfort_tier(self):
        b = self.budget([(rome(), 4), (assisi(), 3)], tier="comfort")
        self.assertEqual(b.total, Decimal("4816.00"))
        self.assertEqual((money(b.total), money(b.per_person)), ("$4,816", "$2,408"))

    def test_three_stops_takes_largest_round_trip_plus_hops(self):
        b = self.budget([(rome(), 4), (assisi(), 3), (lourdes(), 2)])
        # flights 850*2 + 150*2*2; lodging 520+300+220; meals 528+360+240; transport 64+36+20
        self.assertEqual(b.flights, Decimal("2300"))
        self.assertEqual(b.total, Decimal("5138.56"))
        self.assertEqual((money(b.total), money(b.per_person)), ("$5,139", "$2,569"))
        self.assertIn("+ 2 hops between stops", b.basis)

    def test_odd_party_rounds_rooms_up(self):
        b = self.budget([(rome(), 4)], party=3)
        self.assertEqual(b.rooms, 2)
        self.assertEqual(b.total, Decimal("5015.36"))
        self.assertEqual(money(b.per_person), "$1,672")

    def test_round_half_up_like_math_round(self):
        self.assertEqual([round_half_up(Decimal(x)) for x in ("0.5", "1.5", "2.5", "2.49")], [1, 2, 3, 2])


class ItineraryTests(TestCase):
    def build(self, stops, start=None, pace=3):
        return build_itinerary(stops, start, 2, "mid", pace, pricing=PRICING)

    def test_first_day_is_arrival_and_curated_starts_day_2(self):
        it = self.build([(rome(curated=curated("Vatican", "Basilicas", "Catacombs")), 4)], date(2027, 5, 10))
        first, second = it.days[0], it.days[1]
        self.assertEqual((first.number, first.kind, first.title), (1, "arrival", "Arrive and settle in"))
        self.assertEqual(first.tag, "Arrive · fly into FCO")
        self.assertEqual((second.number, second.title, second.date), (2, "Vatican", date(2027, 5, 11)))
        self.assertEqual(it.days[-1].kind, "departure")
        self.assertEqual((it.day_count, it.nights, it.end_date), (5, 4, date(2027, 5, 14)))

    def test_extra_nights_become_free_days(self):
        it = self.build([(rome(curated=curated("Vatican")), 4)])
        self.assertEqual([d.kind for d in it.days], ["arrival", "curated", "free", "free", "departure"])
        self.assertEqual(it.days[2].title, "Free day")

    def test_rows_that_dont_fit_are_cut(self):
        it = self.build([(rome(curated=curated("Vatican", "Basilicas", "Catacombs")), 2)])
        self.assertEqual([(d.title, d.number, d.cut) for d in it.days], [
            ("Arrive and settle in", 1, False), ("Vatican", 2, False),
            ("Basilicas", None, True), ("Catacombs", None, True), ("Departure", 3, False),
        ])

    def test_later_stop_travel_label_whole_miles_and_gateway_departure(self):
        it = self.build([(rome(curated=curated("Vatican")), 2), (assisi(curated=curated("Francis", "Clare")), 2)])
        travel = [d for d in it.days if d.stop_slug == "assisi"][0]
        self.assertEqual(travel.tag, "Travel from Rome · about 81 mi")
        self.assertEqual(travel.number, 3)
        self.assertEqual(it.days[-1].tag, "Fly home from FCO")
        self.assertFalse(any("hour" in d.tag or " h " in d.tag or "min" in d.tag for d in it.days))

    def test_no_coordinates_drops_the_distance_only(self):
        it = self.build([(rome(), 1), (assisi(latitude=None, longitude=None), 1)])
        self.assertEqual(it.days[1].tag, "Travel from Rome")

    def test_suggested_order_split_by_pace(self):
        sites = [site(f"s{i}", 41.9 + i / 100, 12.45, pk=i) for i in range(5)]
        it = self.build([(rome(sites=sites), 3)], pace=2)
        rows = [d for d in it.days if d.kind == "suggested"]
        self.assertEqual([([s.slug for s in d.sites], d.cut) for d in rows],
                         [(["s0", "s1"], False), (["s2", "s3"], False), (["s4"], True)])
        self.assertEqual({d.title for d in rows}, {"Sacred places"})

    def test_nearest_neighbor_is_stable(self):
        a, b, c = site("a", 0.0, 0.0, 1), site("b", 0.0, 1.0, 2), site("c", 0.0, 0.5, 3)
        tie1, tie2 = site("tie-x", 0.0, 2.0, 5), site("tie-y", 0.0, 2.0, 4)
        nowhere = site("nowhere")
        for order in ([a, b, c, tie1, tie2, nowhere], [nowhere, tie2, c, tie1, b, a]):
            self.assertEqual([s.slug for s in nearest_neighbor(order, (0.0, -0.1))],
                             ["a", "c", "b", "tie-x", "tie-y", "nowhere"])

    def test_no_sites_and_no_curated_rows_means_free_days_only(self):
        it = self.build([(rome(), 3)])
        self.assertEqual([d.kind for d in it.days], ["arrival", "free", "free", "departure"])
        self.assertEqual(rome().plan_kind, "none")
        self.assertFalse(any(d.kind == "suggested" for d in it.days))

    def test_default_nights(self):
        self.assertEqual(default_nights(rome(curated=curated("A", "B", "C")), first=True), 4)
        self.assertEqual(default_nights(assisi(curated=curated("A", "B")), first=False), 2)
        self.assertEqual(default_nights(assisi(), first=False), 1)
        self.assertEqual(default_nights(rome(), first=True), 1)

    def test_default_nights_caps_curated_days_at_three(self):
        """Rome's 5 curated days: 4 nights first (3 + arrival), the rest "add a night"."""
        five = curated("Vatican", "Basilicas", "Catacombs", "Centro", "Trastevere")
        self.assertEqual(default_nights(rome(curated=five), first=True), 4)
        self.assertEqual(default_nights(rome(curated=five), first=False), 3)
        self.assertEqual(default_nights(assisi(curated=curated("A", "B", "C")), first=False), 3)
        it = build_itinerary([(rome(curated=five), 4)], None, 2, "mid", 3, pricing=PRICING)
        self.assertEqual([d.title for d in it.days if d.cut], ["Centro", "Trastevere"])

    def test_default_nights_suggested_rows_are_not_capped(self):
        sites = [site(f"s{i}", 41.9 + i / 100, 12.45, pk=i) for i in range(12)]
        self.assertEqual(default_nights(rome(sites=sites), first=False, pace=3), 4)

    def test_empty_plan(self):
        it = self.build([])
        self.assertEqual((it.days, it.budget, it.day_count), ([], None, 0))


class AirportTests(TestCase):
    def build(self, stops):
        return build_itinerary(stops, None, 2, "mid", 3, pricing=PRICING)

    def test_gateway_with_nearest_airport_shown_when_different(self):
        it = self.build([(assisi(), 2)])
        arrival, departure = it.days[0], it.days[-1]
        self.assertEqual(arrival.tag, "Arrive · fly into FCO · nearest airport PEG")
        self.assertEqual((arrival.airport, arrival.nearest_airport), ("FCO", "PEG"))
        self.assertEqual((departure.tag, departure.airport, departure.nearest_airport),
                         ("Fly home from FCO", "FCO", "PEG"))

    def test_no_gateway_or_same_airport_shows_one(self):
        for dest in (rome(), rome(gateway_iata="FCO")):
            it = self.build([(dest, 2)])
            self.assertEqual(it.days[0].tag, "Arrive · fly into FCO")
            self.assertEqual((it.days[0].nearest_airport, it.days[-1].nearest_airport), ("", ""))
