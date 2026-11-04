"""Phase 2: the PlanPage routes. One test per route, so losing
RoutablePageMixin in a merge (as the photo gallery once did) fails here."""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import override_settings

from planner import api
from planner.models import PlanPage

from .base import PlannerTestCase

ON = override_settings(SOG_PLANNER_V2="on")
STAFF = override_settings(SOG_PLANNER_V2="staff")
OFF = override_settings(SOG_PLANNER_V2="off")
GOLDEN_T = "/plan/build/?t=rome-vatican-city.4,assisi.3&p=2&l=mid&pace=3"


class RouteTestCase(PlannerTestCase):
    def setUp(self):
        super().setUp()
        cache.clear()
        self.addCleanup(cache.clear)
        self.seed_costs()
        self.rome = self.make_destination("rome-vatican-city")
        self.assisi = self.make_destination("assisi")
        self.lourdes = self.make_destination("lourdes")
        self.make_plan_page()


class RoutesExistTests(RouteTestCase):
    def test_plan_page_is_routable(self):
        self.assertTrue(hasattr(PlanPage, "reverse_subpage"))
        page = PlanPage.objects.get()
        self.assertEqual(page.reverse_subpage("build_json"), "build/")
        self.assertEqual(page.reverse_subpage("search_json"), "search/")

    @ON
    def test_index_route_still_renders_the_page(self):
        self.assertEqual(self.client.get("/plan/").status_code, 200)

    @ON
    def test_build_route(self):
        self.assertEqual(self.client.get(GOLDEN_T).status_code, 200)

    @ON
    def test_search_route(self):
        self.assertEqual(self.client.get("/plan/search/?q=assisi").status_code, 200)

    @ON
    def test_routes_exist_only_under_the_plan_page(self):
        self.make_site("some-shrine")
        self.assertEqual(self.client.get("/some-shrine/build/").status_code, 404)
        self.assertEqual(self.client.get("/no-such-page/search/?q=rome").status_code, 404)
        self.assertEqual(self.client.get("/plan/other/").status_code, 404)
        self.assertEqual(self.client.get("/plan/build.json").status_code, 404)


class SwitchTests(RouteTestCase):
    @OFF
    def test_off_404s(self):
        self.assertEqual(self.client.get(GOLDEN_T).status_code, 404)
        self.assertEqual(self.client.get("/plan/search/?q=rome").status_code, 404)

    @STAFF
    def test_staff_mode(self):
        self.assertEqual(self.client.get(GOLDEN_T).status_code, 404)
        self.client.force_login(get_user_model().objects.create_user("staff", "s@example.com", "pw", is_staff=True))
        response = self.client.get(GOLDEN_T)
        self.assertEqual(response.status_code, 200)
        self.assertIn("private", response["Cache-Control"])

    @ON
    def test_on_is_publicly_cacheable(self):
        response = self.client.get(GOLDEN_T)
        self.assertIn("public", response["Cache-Control"])
        self.assertIn("max-age=300", response["Cache-Control"])


@ON
class BuildJsonTests(RouteTestCase):
    def test_golden_budget_through_the_route(self):
        data = self.client.get(GOLDEN_T).json()
        budget = data["itinerary"]["budget"]
        self.assertEqual((budget["total"], budget["per_person"], budget["total_exact"]),
                         ("$4,265", "$2,132", "4264.96"))
        self.assertEqual(data["query"], "t=rome-vatican-city.4,assisi.3&p=2&l=mid&pace=3")
        self.assertEqual(data["itinerary"]["day_count"], 8)
        self.assertEqual(data["itinerary"]["days"][-1]["tag"], "Fly home from FCO")
        self.assertEqual([(s["fly_iata"], s["nearest_iata"]) for s in data["stops"]], [("FCO", ""), ("FCO", "PEG")])
        self.assertEqual(data["itinerary"]["days"][0]["tag"], "Arrive · fly into FCO")

    def test_garbage_never_500s(self):
        response = self.client.get("/plan/build/?t=%00,..,assisi.999,rome-vatican-city.2&d=nope&p=-1&l=x&pace=")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["state"]["stops"], [{"slug": "rome-vatican-city", "nights": 2}])

    def test_near_your_route(self):
        data = self.client.get("/plan/build/?t=rome-vatican-city.3").json()
        self.assertEqual(data["near"], {"slug": "assisi", "city": "Assisi", "short": "Assisi", "miles": 81,
                                        "from": "Rome"})

    def test_near_your_route_hidden_without_coordinates(self):
        from planner.models import DestinationCost

        DestinationCost.objects.update(latitude=None, longitude=None)
        data = self.client.get("/plan/build/?t=rome-vatican-city.3").json()
        self.assertIsNone(data["near"])

    def test_stop_without_sites_degrades_to_free_days(self):
        """Before destinations have links or coordinates: no suggested order,
        free days only, and no near-route suggestion."""
        from planner.models import DestinationCost

        DestinationCost.objects.update(latitude=None, longitude=None)
        data = self.client.get("/plan/build/?t=lourdes.3").json()
        self.assertEqual([d["kind"] for d in data["itinerary"]["days"]], ["arrival", "free", "free", "departure"])
        self.assertEqual(data["stops"][0]["plan_kind"], "none")
        self.assertIsNone(data["near"])

    def test_curated_rows_and_live_sites_only(self):
        live = self.make_site("basilica-of-st-francis", title="Basilica of St. Francis")
        gone = self.make_site("unpublished-site")
        gone.unpublish()
        self.add_day(self.assisi, 1, "Francis and Clare", [live, gone])
        data = self.client.get("/plan/build/?t=assisi.2").json()
        day2 = data["itinerary"]["days"][1]
        self.assertEqual((day2["kind"], day2["title"]), ("curated", "Francis and Clare"))
        self.assertEqual([s["slug"] for s in day2["sites"]], ["basilica-of-st-francis"])
        self.assertEqual(day2["sites"][0]["url"], live.url)
        self.assertEqual(data["stops"][0]["default_nights"], 2)

    def test_rate_limited(self):
        old = api.BUILD_LIMIT
        api.BUILD_LIMIT = 2
        self.addCleanup(setattr, api, "BUILD_LIMIT", old)
        codes = [self.client.get(GOLDEN_T).status_code for _ in range(3)]
        self.assertEqual(codes, [200, 200, 429])
        self.assertEqual(self.client.get(GOLDEN_T).json()["error"], "rate_limited")


@ON
class SearchJsonTests(RouteTestCase):
    def test_destinations_and_sites_with_their_destination(self):
        linked = self.make_site("san-damiano", title="San Damiano Assisi Shrine", locality="Elsewhere")
        self.assisi.associated_sites.add(linked)
        self.make_site("assisi-by-locality", title="Hermitage", locality="Assisi")
        self.make_site("lanciano", title="Eucharistic Miracle of Lanciano", locality="Lanciano")
        results = self.client.get("/plan/search/?q=assisi").json()["results"]
        self.assertEqual(results[0], {"kind": "destination", "label": "Assisi", "sub": "Italy", "dest": "assisi",
                                      "dest_city": "Assisi"})
        by_slug = {r.get("slug"): r for r in results if r["kind"] == "site"}
        self.assertEqual(by_slug["san-damiano"]["dest"], "assisi")
        self.assertEqual(by_slug["assisi-by-locality"]["dest"], "assisi")

        unplannable = self.client.get("/plan/search/?q=lanciano").json()["results"]
        self.assertEqual([(r["slug"], r["dest"]) for r in unplannable], [("lanciano", None)])

    def test_non_live_sites_are_not_found(self):
        self.make_site("hidden-shrine", title="Hidden Shrine").unpublish()
        self.assertEqual(self.client.get("/plan/search/?q=hidden").json()["results"], [])

    def test_short_query(self):
        self.assertEqual(self.client.get("/plan/search/?q=a").json()["results"], [])

    def test_rate_limited(self):
        old = api.SEARCH_LIMIT
        api.SEARCH_LIMIT = 1
        self.addCleanup(setattr, api, "SEARCH_LIMIT", old)
        self.assertEqual([self.client.get("/plan/search/?q=rome").status_code for _ in range(2)], [200, 429])


class EngineAgreesWithModelsTests(RouteTestCase):
    def test_default_party_comes_from_settings(self):
        from planner.models import CalculatorDefaults

        d = CalculatorDefaults.load()
        d.default_party_size = 4
        d.save()
        from django.http import QueryDict

        plan = api.build_plan(None, QueryDict("t=assisi.2"))
        self.assertEqual(plan["state"].party, 4)
        self.assertEqual(plan["itinerary"].budget.rooms, 2)
        self.assertEqual(plan["itinerary"].budget.flights, Decimal("3400"))
