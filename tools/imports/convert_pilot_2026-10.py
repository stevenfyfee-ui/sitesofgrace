"""Convert the October 2026 pilot content files to the importers' input format.

    python tools/imports/convert_pilot_2026-10.py

Reads, in tools/imports/:
    site_details_pilot_2026-10.json   -> site_details_pilot_2026-10_converted.json (import_site_details)
    site_map_pilot_2026-10.json       -> site_map_pilot_2026-10_converted.json     (import_site_map)
    hubs_2026-10.json                 -> hubs_2026-10_converted.json               (import_hubs)

The source files use flat field names and the human labels from the v2
brief; this writes the nested shape each importer reads, with stored choice
keys. It never touches the database, and the importers are unchanged.

- "_meta" and every key starting with "_" are dropped.
- Choice labels map to stored keys, read from the models' own choices;
  any label with no match stops the conversion.
- location_link is written only for the pages in LOCATION_LINK_BLANK (all
  ten already have one in production, so none is written; see the PR).
- guide_level "" and recognition_year null are left out (leave unset).
- Lodging slope "unknown" is left unset (UNSET_LABELS); reservation
  "some activities" maps to "some" (LABEL_ALIASES).
- Map points keep verified=false; a lodging's nearest_point stays the
  entrance's name (import_site_map resolves it after the points exist).
- route_geojson null = no route; walk_minutes null = distance only.
- Lodging marked _needs_coordinates gets the coordinates approved in
  APPROVED_COORDINATES, with walk_minutes / walk_miles computed like the
  rest (straight line x 1.3 at 4.5 km/h; distance only beyond 1.2 miles).
  Rows without approved coordinates are left out.
- Hubs are matched by title to the drafts in HUB_IDS (production ids).
"""
import json
import math
import os
import re
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "sitesofgrace.settings.dev")

import django  # noqa: E402

django.setup()

from catalog.models import (  # noqa: E402
    ENTRANCE_KINDS, SacredSitePage, SiteLodging, SiteMapPoint,
)

READY = "Ready to import"

# Pages whose location_link is blank in production (checked 2026-10-24: none).
LOCATION_LINK_BLANK = set()

# Production ids of the hub drafts made by create_destination_hubs.
HUB_IDS = {
    "Rome & Vatican City": 2515,
    "Assisi & Umbria": 2516,
    "Paris & Northern France": 2517,
    "Portugal": 2518,
}

# Labels in the source files that differ from the models' labels only in
# wording. Keyed by (model field, source label).
LABEL_ALIASES = {
    ("reservation_required", "some activities"): "some",  # "Reservations for some activities"
}

# Labels that mean "unknown" for a field with no unknown choice: left unset.
# (Lodging slope has only level / gentle / steep; unset is how it says unknown.)
UNSET_LABELS = {
    ("slope", "unknown"),
}

# Approved lookups for lodging that came without coordinates (OpenStreetMap,
# approved 2026-10-24): (page id, lodging name) -> (latitude, longitude).
# Retreat Village and Carramore House (Knock) and the Carmelite Teresian
# Sisters (Via Tasso, street-level only) were not approved and are left out.
APPROVED_COORDINATES = {
    (1092, "Holiday Inn Express Mexico Basilica"): (19.456146, -99.129131),  # OSM way 1427830387
    (1093, "Retreat House of Our Lady of Mount Carmel (Casa Carmo)"): (39.630535, -8.671992),  # way 159973438
    (1093, "Retreat House of Our Lady of Sorrows (Casa Dores)"): (39.632097, -8.674139),  # way 159973440
    (1093, "Paul VI Pastoral Centre"): (39.627915, -8.677810),  # relation 13757394
    (1139, "Abitart Hotel"): (41.871992, 12.480746),  # relation 13019848
}

WALK_FACTOR = 1.3
WALK_KMH = 4.5
DISTANCE_ONLY_MILES = 1.2
METERS_PER_MILE = 1609.344

SITE_DETAIL_FIELDS = [
    "address", "time_needed", "visit_length", "admission", "reservation_required",
    "accessibility_summary", "accessibility_level",
    "worship_status", "worship_note", "worship_schedule_url",
    "account_tradition", "account_church_judgment", "account_findings", "account_teaching",
    "guide_level", "prep_prayer", "prep_readings", "primary_references", "recognition_year",
]
POINT_KEYS = {"lat": "latitude", "lng": "longitude"}
LODGING_COPY = [
    "kind", "website", "booking_url", "is_affiliate_link", "nearest_point", "walk_minutes",
    "walk_miles", "slope", "step_free", "note", "route_geojson",
]


class Stop(Exception):
    pass


def normalize(text):
    text = str(text).lower().replace("–", "-").replace("—", "-")
    text = re.sub(r"[()]", " ", text)
    text = re.sub(r"\s*/\s*", " / ", text)
    return " ".join(text.split())


def choice_key(model, field_name, value, where):
    field = model._meta.get_field(field_name)
    keys = {key for key, _ in field.choices}
    if value in keys:
        return value
    alias = LABEL_ALIASES.get((field_name, value))
    if alias is not None:
        return alias
    by_label = {normalize(label): key for key, label in field.choices}
    by_key = {normalize(key.replace("-", " ")): key for key in keys}
    found = by_label.get(normalize(value)) or by_key.get(normalize(value))
    if found is None:
        raise Stop(f"{where}: {field_name} label {value!r} matches none of {sorted(keys)}")
    return found


def blank(value):
    return value is None or (isinstance(value, str) and value.strip() == "")


def public(row):
    return {k: v for k, v in row.items() if not k.startswith("_")}


def distance_m(lat1, lng1, lat2, lng2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lng2 - lng1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6371000 * math.asin(math.sqrt(h))


def walk(straight_m):
    """(walk_minutes or None, walk_miles) for a straight-line distance."""
    meters = straight_m * WALK_FACTOR
    miles = round(meters / METERS_PER_MILE, 1)
    if meters / METERS_PER_MILE > DISTANCE_ONLY_MILES:
        return None, miles
    return max(1, round(meters / (WALK_KMH * 1000) * 60)), miles


# ------------------------------------------------------------- site details

def convert_details(data, log):
    pages = []
    for row in data["pages"]:
        row = public(row)
        where = f"site details {row['id']}"
        fields = {}
        for name in SITE_DETAIL_FIELDS:
            value = row.get(name)
            if blank(value):
                if name in ("guide_level", "recognition_year"):
                    log["left unset"][name] += 1
                continue
            if SacredSitePage._meta.get_field(name).choices:
                key = choice_key(SacredSitePage, name, value, where)
                if key != value:
                    log["labels mapped"][f"{name}: {value} -> {key}"] += 1
                value = key
            fields[name] = value
        if not blank(row.get("location_link")):
            if row["id"] in LOCATION_LINK_BLANK:
                fields["location_link"] = row["location_link"]
            else:
                log["location_link left out"][row["id"]] += 1
        extra = sorted(set(row) - set(SITE_DETAIL_FIELDS) - {"id", "title", "status", "location_link"})
        if extra:
            raise Stop(f"{where}: unexpected field(s) {', '.join(extra)}")
        pages.append({"id": row["id"], "title": row["title"], "status": row.get("status", READY),
                      "fields": fields})
    return {"pages": pages}


# ----------------------------------------------------------------- site map

def convert_map(data, log):
    pages = []
    for page in data["pages"]:
        page = public(page)
        where = f"site map {page['id']}"
        points, entrances = [], {}
        for raw in page.get("map_points", []):
            point = public(raw)
            out = {"name": point["name"]}
            for key, value in point.items():
                if key == "name" or blank(value):
                    continue
                if key == "kind":
                    stored = choice_key(SiteMapPoint, "kind", value, f"{where} point {point['name']!r}")
                    if stored != value:
                        log["labels mapped"][f"point kind: {value} -> {stored}"] += 1
                    value = stored
                out[POINT_KEYS.get(key, key)] = value
            out["verified"] = False
            if out["kind"] in ENTRANCE_KINDS:
                entrances[out["name"]] = (out["latitude"], out["longitude"])
            points.append(out)

        lodgings = []
        for raw in page.get("lodging", []):
            lodging = public(raw)
            name = lodging["name"]
            lwhere = f"{where} lodging {name!r}"
            out = {"name": name}
            lat, lng = lodging.get("lat"), lodging.get("lng")
            if raw.get("_needs_coordinates"):
                approved = APPROVED_COORDINATES.get((page["id"], name))
                if approved is None:
                    log["lodging left out (no approved coordinates)"][f"{page['id']} {name}"] += 1
                    continue
                lat, lng = approved
                target = entrances.get(lodging.get("nearest_point"))
                if target is None:
                    raise Stop(f"{lwhere}: nearest_point {lodging.get('nearest_point')!r} is not an entrance on this page")
                lodging["walk_minutes"], lodging["walk_miles"] = walk(distance_m(lat, lng, *target))
                log["coordinates added"][f"{page['id']} {name}"] += 1
            if lat is None or lng is None:
                raise Stop(f"{lwhere}: no coordinates")
            out["latitude"], out["longitude"] = lat, lng
            for key in LODGING_COPY:
                value = lodging.get(key)
                if blank(value):
                    continue
                if (key, value) in UNSET_LABELS:
                    log["left unset"][f"lodging {key} {value!r}"] += 1
                    continue
                if key in ("kind", "slope", "step_free"):
                    stored = choice_key(SiteLodging, key, value, lwhere)
                    if stored != value:
                        log["labels mapped"][f"lodging {key}: {value} -> {stored}"] += 1
                    value = stored
                if key == "nearest_point" and value not in entrances:
                    raise Stop(f"{lwhere}: nearest_point {value!r} is not an entrance on this page")
                out[key] = value
            if out.get("walk_minutes") is None and out.get("walk_miles") is not None:
                log["distance only"][f"{page['id']} {name}"] += 1
            extra = sorted(set(lodging) - set(LODGING_COPY) - {"name", "lat", "lng"})
            if extra:
                raise Stop(f"{lwhere}: unexpected field(s) {', '.join(extra)}")
            lodgings.append(out)

        pages.append({"id": page["id"], "title": page["title"], "status": page.get("status", READY),
                      "map_points": points, "lodging": lodgings})
    return {"pages": pages}


# --------------------------------------------------------------------- hubs

def convert_hubs(data, log):
    pages = []
    for hub in data["hubs"]:
        hub = public(hub)
        title = hub["title"]
        if title not in HUB_IDS:
            raise Stop(f"hub {title!r} matches none of {sorted(HUB_IDS)}")
        fields = {name: hub[name] for name in
                  ("intro", "tile_caption", "country_codes", "localities", "include_auto",
                   "getting_around", "travel_advisory_url", "plan_link_url")
                  if name in hub and not blank(hub[name]) and hub[name] != []}
        combine = []
        for trip in hub.get("combine_with", []):
            trip = public(trip)
            row = {"site": trip.get("site_id"), "name": trip.get("name"), "reason": trip.get("reason"),
                   "travel_time": trip.get("travel_time"), "mode": trip.get("mode")}
            if row["site"] is None:
                log["combine_with name-only"][f"{title}: {trip.get('name')}"] += 1
            combine.append(row)
        extra = sorted(set(hub) - set(fields) - {"title", "status", "hub_sites", "stay_options",
                                                  "combine_with", "related_trails", "localities"})
        if extra:
            raise Stop(f"hub {title!r}: unexpected field(s) {', '.join(extra)}")
        entry = {"id": HUB_IDS[title], "title": title, "status": hub.get("status", READY),
                 "fields": fields, "hub_sites": hub.get("hub_sites", []),
                 "stay_options": [public(o) for o in hub.get("stay_options", [])],
                 "combine_with": combine}
        if hub.get("related_trails"):
            entry["related_trails"] = hub["related_trails"]
        pages.append(entry)
    return {"pages": pages}


JOBS = [
    ("site_details_pilot_2026-10.json", "site_details_pilot_2026-10_converted.json", convert_details),
    ("site_map_pilot_2026-10.json", "site_map_pilot_2026-10_converted.json", convert_map),
    ("hubs_2026-10.json", "hubs_2026-10_converted.json", convert_hubs),
]


def main():
    logs = {}
    try:
        results = []
        for source, target, convert in JOBS:
            with open(HERE / source, encoding="utf-8") as fh:
                data = json.load(fh)
            log = {k: Counter() for k in (
                "labels mapped", "left unset", "location_link left out", "coordinates added",
                "lodging left out (no approved coordinates)", "distance only", "combine_with name-only")}
            results.append((target, convert(data, log)))
            logs[source] = log
    except Stop as stop:
        sys.exit(f"STOPPED: {stop}")
    for target, converted in results:
        with open(HERE / target, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(converted, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        print(f"wrote tools/imports/{target}: {len(converted['pages'])} pages")
    for source, log in logs.items():
        print(f"\n{source}")
        for heading, counts in log.items():
            if counts:
                print(f"  {heading}:")
                for item, n in sorted(counts.items(), key=str):
                    print(f"    {item}" + (f"  (x{n})" if n > 1 else ""))


if __name__ == "__main__":
    main()
