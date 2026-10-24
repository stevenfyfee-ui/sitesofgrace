"""Local-only sample content for previewing the v2 pages.

    python manage.py v2_dev_sample

Refuses to run unless settings.DEBUG is True AND the database is a local
one (host db / localhost / 127.0.0.1, and not the production settings
module). Standing Rule 5: invented values live only here, and every row
this command creates has "(sample)" in its name.

Phase 1: fills the mockup's values into the local "Our Lady of Lourdes"
page -- only fields that are still blank (Rule 4) -- and creates, if
missing, a sample St. Bernadette saint (linked from Lourdes and the Nevers
convent where their principal saint is blank), two sample shrines within
40 miles for the Nearby cards, and three sample Plan Your Visit panels.
Safe to run repeatedly: a second run changes nothing.

Phase 2: a sample operator with the mockup's "Lourdes & Fátima" tour (stops:
Lourdes, Fátima, and Lisbon as a place name; one past departure that must
not render, one upcoming) and a "Paris & Lisieux" tour that does not include
Lourdes -- so a French site with no tours (e.g. La Salette) shows the "None"
state with "Guided pilgrimages elsewhere in France". Booking links point at
example.com, a domain reserved for documentation.

Phase 4: runs create_destination_hubs (four unpublished drafts), then fills
the Assisi & Umbria draft with the mockup's hub text, retitles it "Assisi &
Umbria (sample)", and publishes it and the Destinations index -- locally only.

Phase 3: the mockup's Lourdes map points (two entrances, sacred places,
transit) and its five places to stay, all "(sample)"; three have walking
routes, two don't, so both info-bar states can be seen.

If Lourdes has an unpublished draft (real editorial work), the draft is left
exactly as it is: the blank sample fields are written to the page row only
-- what the public page renders -- and no revision is created or published.
"""
from datetime import date, timedelta
from decimal import Decimal

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from wagtail.models import Page

from catalog.models import SacredSitePage, SaintPage, SiteTravelSection

LOCAL_DB_HOSTS = {"db", "localhost", "127.0.0.1", ""}

LOURDES_SLUG = "lourdes"
NEVERS_SLUG = "nevers"

LOURDES_FIELDS = {
    "address": "1 avenue Mgr Théas, 65100 Lourdes",
    "time_needed": "1 day minimum · 2–3 days ideal",
    "visit_length": "weekend",
    "admission": "Free",
    "reservation_required": "no",
    "accessibility_summary": "Step-free domain; free wheelchairs and helpers",
    "accessibility_level": "step-free",
    "worship_status": "active",
    "worship_note": "Daily Mass and Confession, several languages",
    "worship_schedule_url": "https://www.lourdes-france.com/",
    "recognition_year": 1862,
    "guide_level": "full",
    "account_tradition": "<p>Bernadette's own testimony, given repeatedly to clergy and civil officials "
                         "in 1858, and the accounts of witnesses present at the grotto.</p>",
    "account_church_judgment": "<p>Declared worthy of belief by the local bishop in 1862. The feast was "
                               "extended to the whole Church in 1907.</p>",
    "account_findings": "<p>Claimed cures are examined by the Lourdes Medical Bureau, founded in 1883, and "
                        "then by the bishop of the healed person. Around seventy have been declared "
                        "miraculous.</p>",
    "account_teaching": "<p>Approved private revelations are not required belief. They can help the "
                        "faithful live the Gospel; they add nothing to it.</p>",
    "prep_prayer": "<p>Our Lady of Lourdes, pray for us.<br>Saint Bernadette, pray for us.</p>",
    "prep_readings": "<ul><li>Luke 1:46–55, the Magnificat</li><li>John 5:2–9, the healing at the pool"
                     "</li><li>A short life of St. Bernadette</li><li>Bring an intention, and plan to "
                     "go to Confession</li></ul>",
    "primary_references": '<p><a href="https://www.lourdes-france.com/">Sanctuary of Our Lady of '
                          'Lourdes</a> · Diocese of Tarbes and Lourdes · <i>Norms for Proceeding in the '
                          'Discernment of Alleged Supernatural Phenomena</i> (DDF, 2024)</p>',
}

SAINT = {"slug": "st-bernadette-soubirous-sample", "title": "St. Bernadette Soubirous (sample)",
         "feast_day": "April 16"}

NEARBY = [
    {"slug": "betharram-sample", "title": "Sanctuary of Bétharram (sample)",
     "latitude": Decimal("43.095800"), "longitude": Decimal("-0.210700"),
     "summary_short": "A Marian sanctuary on the Gave de Pau, a pilgrim stop since the Middle Ages (sample)."},
    {"slug": "garaison-sample", "title": "Notre-Dame de Garaison (sample)",
     "latitude": Decimal("43.235300"), "longitude": Decimal("0.500900"),
     "summary_short": "A sixteenth-century apparition shrine in the Gascony hills (sample)."},
]
NEARBY_PARENT_SLUG = "shrines-and-basilicas"

# Phase 4: the mockup's Assisi & Umbria hub. Only blank fields are filled;
# the local copy publishes it (and the index) so it can be previewed.
HUB_SLUG = "assisi-umbria"
HUB_TITLE = "Assisi & Umbria (sample)"
HUB_FIELDS = {
    "intro": "The hill town of St. Francis and St. Clare, the tomb of St. Carlo Acutis, and Eucharistic "
             "and saints' shrines within an easy day's drive.",
    "tile_caption": "Francis, Clare, Carlo Acutis",
    "country_codes": ["IT"],
    "localities": "Assisi\nCascia\nOrvieto\nNorcia",
    "include_auto": True,
    "getting_around": "<ul><li>Assisi's train station is in Santa Maria degli Angeli, below the old town. "
                      "A local bus climbs to the gates.</li><li>The old town is steep and partly cobbled. "
                      "Allow extra time with anyone who walks slowly.</li><li>Perugia airport (PEG) is about "
                      "20 minutes away; most U.S. travelers arrive via Rome.</li><li>A car makes Cascia and "
                      "Norcia practical; Orvieto is also reachable by train.</li></ul>",
    "travel_advisory_url": "https://travel.state.gov/content/travel/en/international-travel/"
                           "International-Travel-Country-Information-Pages/Italy.html",
}
HUB_SITE_SLUGS = ["basilica-of-st-francis-of-assisi", "tomb-of-st-clare-assisi", "carlo-acutis-assisi",
                  "porziuncola"]
HUB_STAYS = [
    ("1 day", "The Basilica of St. Francis, Santa Chiara, and the Sanctuary of the Renunciation. "
              "Possible from Rome, but rushed."),
    ("2–3 days", "Adds San Damiano, the Carceri hermitage and the Portiuncula, with time for Mass and quiet."),
    ("5 days", "Adds day trips to Orvieto, Cascia and Norcia. Pairs naturally with Rome."),
]
HUB_TRIPS = [
    ("eucharistic-miracle-of-bolsena-orvieto", "Orvieto", "Corporal of the Eucharistic Miracle of Bolsena",
     "1 h 30", "drive"),
    ("tomb-of-st-rita-cascia", "Cascia", "Basilica and tomb of St. Rita", "1 h 30", "drive"),
    (None, "Norcia", "Birthplace of St. Benedict and St. Scholastica", "1 h 40", "drive"),
    (None, "Rome", "The four papal basilicas and the tombs of Peter and Paul", "2 h", "train"),
]

# Phase 3: the mockup's Lourdes map (entrances, sacred places, transit) and
# its five places to stay. (lat, lng); routes are [lat, lng] lists here and
# stored as GeoJSON LineStrings ([lng, lat]).
MAP_POINTS = [
    ("main-entrance", "Saint-Michel Gate (sample)", "43.095700", "-0.053100", "Main entrance (sample)"),
    ("accessible-entrance", "Saint-Joseph Gate (sample)", "43.094600", "-0.054900", "Step-free entrance (sample)"),
    ("sacred-place", "Basilica of the Immaculate Conception (sample)", "43.097800", "-0.057000", ""),
    ("sacred-place", "The Cachot (sample)", "43.096100", "-0.047600", "Where the Soubirous family lived (sample)"),
    ("sacred-place", "Boly Mill, Bernadette's birthplace (sample)", "43.095400", "-0.046700", ""),
    ("prayer-location", "Parish church, baptismal font (sample)", "43.095000", "-0.045000", ""),
    ("train-station", "Lourdes train station (sample)", "43.100300", "-0.041600", ""),
    ("bus-stop", "Airport shuttle stop (sample)", "43.094200", "-0.046000", ""),
    ("parking", "Parking (sample)", "43.093500", "-0.054500", ""),
]
LODGINGS = [
    {"name": "Hotel by the Saint-Michel Gate (sample)", "kind": "hotel", "ll": ("43.096200", "-0.051200"),
     "to": "Saint-Michel Gate (sample)", "walk_minutes": 4, "walk_miles": "0.2", "slope": "level", "step_free": "yes",
     "note": "Lift to all floors. The easiest choice for wheelchair users.",
     "booking_url": "https://example.com/sample-hotel-1", "is_affiliate_link": True,
     "route": [[43.0962, -0.0512], [43.0959, -0.0522], [43.0957, -0.0531]]},
    {"name": "Pilgrim guesthouse with chapel (sample)", "kind": "religious-house", "ll": ("43.093800", "-0.052600"),
     "to": "Saint-Joseph Gate (sample)", "walk_minutes": 8, "walk_miles": "0.4", "slope": "level", "step_free": "yes",
     "note": "Level, along the river. Daily Mass in the house. Simple rooms, early curfew.",
     "website": "https://example.com/sample-guesthouse",
     "route": [[43.0938, -0.0526], [43.0942, -0.0537], [43.0946, -0.0549]]},
    {"name": "Hotel on Rue de la Grotte (sample)", "kind": "hotel", "ll": ("43.096800", "-0.048800"),
     "to": "Saint-Michel Gate (sample)", "walk_minutes": 7, "walk_miles": "0.3", "slope": "steep", "step_free": "no",
     "note": "Steep: downhill there, uphill back. The return climb is hard for older pilgrims.",
     "booking_url": "https://example.com/sample-hotel-3"},
    {"name": "Hotel near the train station (sample)", "kind": "hotel", "ll": ("43.099500", "-0.043000"),
     "to": "Saint-Michel Gate (sample)", "walk_minutes": 22, "walk_miles": "1.1", "slope": "gentle", "step_free": "yes",
     "note": "Busy crossings. Good for an early train out; too far for repeated visits in one day.",
     "booking_url": "https://example.com/sample-hotel-4"},
    {"name": "Accueil Notre-Dame (sample)", "kind": "pilgrim", "ll": ("43.095800", "-0.058500"),
     "to": "Saint-Joseph Gate (sample)", "walk_minutes": 6, "walk_miles": "0.3", "slope": "level", "step_free": "yes",
     "note": "For sick pilgrims, inside the Sanctuary. Booked through a diocesan pilgrimage or the Sanctuary, not online.",
     "route": [[43.0958, -0.0585], [43.0966, -0.0588], [43.0974, -0.0582]]},
]

TOURS = [
    {
        "title": "Lourdes & Fátima Pilgrimage (sample)",
        "stops": [("lourdes", "Lourdes"), ("fatima", "Fátima"), (None, "Lisbon")],
        "fields": {
            "travel_style": "pilgrimage", "duration_days": 10, "departure_city": "New York (JFK)",
            "departure_months": [5, 9], "price_note": "See operator", "priest_or_director": "priest",
            "mass": "daily", "confession_offered": "yes", "hotels_meals": "4-star, breakfast and dinner",
            "activity_level": "moderate", "group_size_max": 40,
            "cancellation_summary": "Set by the operator (sample).",
            "booking_url": "https://example.com/sample-tour-a", "is_affiliate_link": True, "is_live": True,
        },
        # One departure already past (must never render) and one upcoming.
        "departures": [(-60, {"status": "open"}), (200, {"status": "open", "airfare_included": True})],
    },
    {
        "title": "Paris & Lisieux Pilgrimage (sample)",
        "stops": [("rue-du-bac", "Rue du Bac"), ("sacre-coeur", "Sacré-Cœur"), ("lisieux", "Lisieux")],
        "fields": {
            "travel_style": "pilgrimage-sightseeing", "duration_days": 8, "departure_city": "Boston (BOS)",
            "departure_months": [6, 10], "price_note": "See operator", "priest_or_director": "director",
            "mass": "most-days", "confession_offered": "not-stated", "activity_level": "easy",
            "booking_url": "https://example.com/sample-tour-b", "is_affiliate_link": False, "is_live": True,
        },
        "departures": [],
    },
    {
        "title": "Rome, Assisi & Orvieto Pilgrimage (sample)",
        "stops": [(None, "Rome"), ("basilica-of-st-francis-of-assisi", "Assisi"),
                  ("eucharistic-miracle-of-bolsena-orvieto", "Orvieto")],
        "fields": {
            "travel_style": "pilgrimage", "duration_days": 9, "departure_city": "Chicago (ORD)",
            "departure_months": [4, 10], "price_note": "See operator", "priest_or_director": "priest",
            "mass": "daily", "confession_offered": "yes", "activity_level": "moderate", "group_size_max": 30,
            "booking_url": "https://example.com/sample-tour-c", "is_affiliate_link": False, "is_live": True,
        },
        "departures": [(150, {"status": "open"})],
    },
]

TRAVEL = [
    ("how-long-should-i-stay", "Two nights is the honest minimum (sample)",
     "<p>Sample text: one day covers the grotto and the basilicas; two nights add the torchlight "
     "procession and the baths.</p>", False),
    ("getting-there", "Paris or Toulouse, then rail (sample)",
     "<p>Sample text: fly to Paris or Toulouse, then take the train to Lourdes.</p>", False),
    ("accessibility", "Built for pilgrims who are ill (sample)",
     "<p>Sample text: the domain is step-free, with wheelchairs and volunteer helpers.</p>", True),
]


def refuse_unless_local():
    if not settings.DEBUG:
        raise CommandError("v2_dev_sample only runs with DEBUG = True.")
    module = getattr(settings, "SETTINGS_MODULE", "") or ""
    host = connection.settings_dict.get("HOST") or ""
    if module.endswith("production") or host not in LOCAL_DB_HOSTS:
        raise CommandError(f"v2_dev_sample refuses to run against this database (host {host!r}).")


def publish(page):
    page.save_revision(log_action=True).publish()


class Command(BaseCommand):
    help = "Local-only v2 sample content (DEBUG and a local database required)."

    def handle(self, *args, **options):
        refuse_unless_local()
        lourdes = SacredSitePage.objects.filter(slug=LOURDES_SLUG).first()
        if lourdes is None:
            raise CommandError("No local SacredSitePage with slug 'lourdes'.")
        with transaction.atomic():
            saint = self._saint()
            filled = self._fill_lourdes(lourdes, saint)
            linked = self._link_nevers(saint)
            created_sites = self._nearby()
            created_tours = self._tours()
            stay_rows = self._stay_map(SacredSitePage.objects.get(pk=lourdes.pk))
            hub_filled = self._hub()
        self.stdout.write(
            f"v2_dev_sample: Lourdes fields filled: {filled or 'none'}; "
            f"Nevers linked: {linked}; sample sites created: {created_sites or 'none'}; "
            f"sample tours created: {created_tours or 'none'}; map & lodging rows created: {stay_rows}; "
            f"Assisi & Umbria hub: {hub_filled}"
        )

    def _saint(self):
        saint = SaintPage.objects.filter(slug=SAINT["slug"]).first()
        if saint:
            return saint
        index = Page.objects.get(slug="saints")
        saint = SaintPage(title=SAINT["title"], slug=SAINT["slug"], feast_day=SAINT["feast_day"])
        index.add_child(instance=saint)
        publish(saint)
        return SaintPage.objects.get(pk=saint.pk)

    def _fill_lourdes(self, lourdes, saint):
        filled = [name for name, value in LOURDES_FIELDS.items() if not getattr(lourdes, name)]
        for name in filled:
            setattr(lourdes, name, LOURDES_FIELDS[name])
        if not lourdes.associated_saint_id:
            lourdes.associated_saint = saint
            filled.append("associated_saint")

        existing = {s.kind for s in lourdes.travel_sections.all()}
        sections = list(lourdes.travel_sections.all())
        for kind, teaser, body, confirm in TRAVEL:
            if kind not in existing:
                sections.append(SiteTravelSection(kind=kind, teaser=teaser, body=body, needs_confirmation=confirm))
                filled.append(f"travel:{kind}")
        if len(sections) != len(existing):
            lourdes.travel_sections = sections

        if not filled:
            return filled
        if lourdes.has_unpublished_changes:
            # Never publish over (or discard) someone's draft: write the row only.
            row_fields = [name for name in filled if not name.startswith("travel:")]
            lourdes.save(update_fields=row_fields)
            for section in sections:
                if section.pk is None:
                    section.page = lourdes
                    section.save()
            self.stdout.write("Lourdes has an unpublished draft: sample values written to the page row only; "
                              "the draft is untouched.")
        else:
            publish(lourdes)
        return filled

    def _link_nevers(self, saint):
        nevers = SacredSitePage.objects.filter(slug=NEVERS_SLUG).first()
        if nevers is None or nevers.associated_saint_id or nevers.has_unpublished_changes:
            return False
        nevers.associated_saint = saint
        publish(nevers)
        return True

    def _nearby(self):
        parent = Page.objects.get(slug=NEARBY_PARENT_SLUG)
        created = []
        for spec in NEARBY:
            if SacredSitePage.objects.filter(slug=spec["slug"]).exists():
                continue
            site = SacredSitePage(category="Shrine & Basilica", country="France", **spec)
            parent.add_child(instance=site)
            publish(site)
            created.append(spec["title"])
        return created

    def _tours(self):
        from tours.models import GuidedPilgrimage, TourDeparture, TourOperator, TourStop

        operator, _ = TourOperator.objects.get_or_create(
            name="Sample Catholic tour operator A (sample)",
            defaults={"website": "https://example.com/", "catholic_focused": True, "is_active": True},
        )
        created = []
        for spec in TOURS:
            if GuidedPilgrimage.objects.filter(title=spec["title"]).exists():
                continue
            tour = GuidedPilgrimage(operator=operator, **spec["fields"], title=spec["title"])
            stops = []
            for slug, place in spec["stops"]:
                site = SacredSitePage.objects.filter(slug=slug).first() if slug else None
                stops.append(TourStop(site=site, place_name=None if site else place))
            tour.stops = stops
            tour.departures = [
                TourDeparture(depart_date=date.today() + timedelta(days=offset), **extra)
                for offset, extra in spec["departures"]
            ]
            tour.save()
            created.append(spec["title"])
        return created

    def _stay_map(self, lourdes):
        """Rows are written directly (the local Lourdes has a draft we never
        publish over); matched by name, so a rerun adds nothing."""
        import json as _json

        from catalog.models import SiteLodging, SiteMapPoint

        created = 0
        points = {p.name: p for p in lourdes.map_points.all()}
        for order, (kind, name, lat, lng, note) in enumerate(MAP_POINTS):
            if name in points:
                continue
            points[name] = SiteMapPoint.objects.create(
                page=lourdes, sort_order=order, kind=kind, name=name, latitude=Decimal(lat),
                longitude=Decimal(lng), note=note or None, verified=False,
            )
            created += 1
        existing = set(lourdes.lodgings.values_list("name", flat=True))
        for order, spec in enumerate(LODGINGS):
            if spec["name"] in existing:
                continue
            route = spec.get("route")
            SiteLodging.objects.create(
                page=lourdes, sort_order=order, name=spec["name"], kind=spec["kind"],
                latitude=Decimal(spec["ll"][0]), longitude=Decimal(spec["ll"][1]),
                website=spec.get("website"), booking_url=spec.get("booking_url"),
                is_affiliate_link=spec.get("is_affiliate_link", False), nearest_point=points[spec["to"]],
                walk_minutes=spec["walk_minutes"], walk_miles=Decimal(spec["walk_miles"]),
                slope=spec["slope"], step_free=spec["step_free"], note=spec["note"],
                route_geojson=_json.dumps({"type": "LineString", "coordinates": [[lng, lat] for lat, lng in route]})
                if route else None,
            )
            created += 1
        return created

    def _hub(self):
        """Fill the Assisi & Umbria draft with the mockup's text (blank fields
        only), mark it "(sample)" and publish it and the index locally."""
        from django.core.management import call_command

        from destinations.models import CombineWith, DestinationHubPage, DestinationIndexPage, HubSite, StayOption

        call_command("create_destination_hubs", stdout=self.stdout)
        hub = DestinationHubPage.objects.filter(slug=HUB_SLUG).first()
        if hub is None:
            return "no assisi-umbria hub"
        hub = hub.get_latest_revision_as_object() if not hub.live else hub
        filled = [name for name, value in HUB_FIELDS.items() if not getattr(hub, name)]
        for name in filled:
            setattr(hub, name, HUB_FIELDS[name])
        if "(sample)" not in hub.title:
            hub.title = HUB_TITLE
            filled.append("title")
        if not hub.hub_sites.all():
            sites = [SacredSitePage.objects.filter(slug=s).first() for s in HUB_SITE_SLUGS]
            hub.hub_sites = [HubSite(site=s, sort_order=i) for i, s in enumerate(x for x in sites if x)]
            filled.append("hub_sites")
        if not hub.stay_options.all():
            hub.stay_options = [StayOption(label=a, text=b, sort_order=i) for i, (a, b) in enumerate(HUB_STAYS)]
            filled.append("stay_options")
        if not hub.combine_with.all():
            rows = []
            for i, (slug, name, reason, time, mode) in enumerate(HUB_TRIPS):
                site = SacredSitePage.objects.filter(slug=slug).first() if slug else None
                rows.append(CombineWith(site=site, name=name, reason=reason, travel_time=time, mode=mode,
                                        sort_order=i))
            hub.combine_with = rows
            filled.append("combine_with")
        if filled or not hub.live:
            hub.save_revision(log_action=True).publish()
        index = DestinationIndexPage.objects.first()
        if index and not index.live:
            index.save_revision(log_action=True).publish()
        return filled or "none"
