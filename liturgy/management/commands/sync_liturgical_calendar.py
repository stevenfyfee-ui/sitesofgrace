"""Refresh the committed liturgical calendar files from the Liturgical Calendar API.

    python manage.py sync_liturgical_calendar --years 2026-2030
    python manage.py sync_liturgical_calendar --years 2031

Writes liturgy/data/litcal-US-<year>.json, one file per civil year. The site
reads only those files at runtime and never calls the API itself, so this is
run by hand (and committed) whenever the data needs to reach further out --
liturgy.tests fails once next year's file is missing.

year_type=CIVIL matters: the API's default is the LITURGICAL year, which
starts at Advent of the previous year.
"""
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from liturgy.calendar import DATA_DIR, data_path

API_URL = "https://litcal.johnromanodorazio.com/api/v5/calendar/nation/US/{year}?year_type=CIVIL"
USER_AGENT = "SitesOfGrace/1.0 (+https://sitesofgrace.com)"
TIMEOUT = 20
KEEP = (
    "date", "event_key", "name", "grade", "grade_lcl", "color",
    "liturgical_season", "liturgical_season_lcl", "type",
)
# Checked against github.com/Liturgical-Calendar/LiturgicalCalendarAPI: its
# LICENSE file is the Apache License 2.0, with no NOTICE file.
LICENSE = {
    "name": "Liturgical Calendar API",
    "project": "https://github.com/Liturgical-Calendar/LiturgicalCalendarAPI",
    "license": "Apache-2.0",
    "license_url": "https://www.apache.org/licenses/LICENSE-2.0",
    "attribution": "Liturgical calendar: Liturgical Calendar API (US), "
                   "https://litcal.johnromanodorazio.com, Apache License 2.0",
}


def parse_years(value):
    try:
        if "-" in value:
            first, last = (int(part) for part in value.split("-", 1))
        else:
            first = last = int(value)
    except ValueError:
        raise CommandError(f"--years must look like 2026 or 2026-2030, not {value!r}")
    if not 1970 <= first <= last <= 9999:
        raise CommandError(f"--years range {value!r} is out of order or out of range")
    return list(range(first, last + 1))


def fetch(url):
    try:
        import requests
    except ImportError:
        requests = None
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    if requests is not None:
        response = requests.get(url, headers=headers, timeout=TIMEOUT)
        response.raise_for_status()
        return response.json()
    from urllib.request import Request, urlopen

    with urlopen(Request(url, headers=headers), timeout=TIMEOUT) as response:
        return json.loads(response.read().decode("utf-8"))


def slim(events, year):
    """Keep one civil year's real celebrations, trimmed to the fields we read."""
    kept = []
    for event in events:
        if event.get("is_vigil_mass"):
            continue
        day = str(event.get("date", ""))[:10]
        if not day.startswith(f"{year}-"):
            continue
        row = {key: event.get(key) for key in KEEP}
        row["date"] = day
        kept.append(row)
    kept.sort(key=lambda row: row["date"])
    return kept


class Command(BaseCommand):
    help = "Download the US liturgical calendar for one or more civil years into liturgy/data/."

    def add_arguments(self, parser):
        parser.add_argument("--years", required=True, help="A year (2031) or an inclusive range (2026-2030).")

    def handle(self, *args, **options):
        years = parse_years(options["years"])
        Path(DATA_DIR).mkdir(parents=True, exist_ok=True)
        for i, year in enumerate(years):
            if i:
                time.sleep(1)
            url = API_URL.format(year=year)
            try:
                payload = fetch(url)
            except Exception as exc:
                raise CommandError(f"{year}: fetch failed: {exc}")
            events = payload.get("litcal")
            if not isinstance(events, list) or not events:
                raise CommandError(f"{year}: response has no 'litcal' list")
            rows = slim(events, year)
            days = {row["date"] for row in rows}
            document = {
                "source": {
                    "url": url,
                    "fetched_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
                    **LICENSE,
                },
                "events": rows,
            }
            path = data_path(year)
            with open(path, "w", encoding="utf-8", newline="\n") as fh:
                json.dump(document, fh, sort_keys=True, indent=1, ensure_ascii=False)
                fh.write("\n")
            self.stdout.write(
                f"{year}: {len(rows)} events over {len(days)} days "
                f"(dropped {len(events) - len(rows)} vigil / out-of-year) -> {path}"
            )
        self.stdout.write(self.style.SUCCESS(f"synced {len(years)} year(s)"))
