"""Phase 2: the planner's URL state (?t=&d=&p=&l=&pace=)."""
from datetime import date
from unittest import TestCase

from django.http import QueryDict

from planner.urlstate import PlanState, parse_state

KNOWN = {"rome-vatican-city", "assisi", "lourdes", "fatima", "paris", "lisieux", "knock", "dublin"}


class UrlStateTests(TestCase):
    def parse(self, qs, max_stops=6):
        return parse_state(QueryDict(qs), KNOWN, max_stops)

    def test_round_trip(self):
        qs = "t=rome-vatican-city.4,assisi.3&d=2027-05-10&p=2&l=mid&pace=3"
        state = self.parse(qs)
        self.assertEqual(state, PlanState(stops=[("rome-vatican-city", 4), ("assisi", 3)],
                                          start_date=date(2027, 5, 10), party=2, tier="mid", pace=3))
        self.assertEqual(state.query(), qs)
        self.assertEqual(self.parse(state.query()), state)

    def test_garbage_is_dropped_not_fatal(self):
        state = self.parse(
            "t=rome-vatican-city.4,atlantis.3,assisi.0,lourdes.22,fatima.x,paris,.3,ROME-VATICAN-CITY.2,"
            "<script>.2,knock.2&d=2027-02-30&p=99&l=palace&pace=7"
        )
        self.assertEqual(state.stops, [("rome-vatican-city", 4), ("knock", 2)])
        self.assertEqual((state.start_date, state.party, state.tier, state.pace), (None, 2, "mid", 3))

    def test_empty(self):
        state = self.parse("")
        self.assertEqual(state, PlanState())
        self.assertEqual(state.query(), "p=2&l=mid&pace=3")

    def test_more_than_max_stops_is_trimmed(self):
        qs = "t=" + ",".join(f"{s}.1" for s in ["rome-vatican-city", "assisi", "lourdes", "fatima", "paris",
                                                  "lisieux", "knock", "dublin"])
        self.assertEqual(len(self.parse(qs).stops), 6)
        self.assertEqual([s for s, _ in self.parse(qs, max_stops=2).stops], ["rome-vatican-city", "assisi"])
