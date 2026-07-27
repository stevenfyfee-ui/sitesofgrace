from decimal import Decimal, InvalidOperation

import openpyxl
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from planner.models import (
    CalculatorDefaults,
    DestinationCost,
    RegionFlightAssumption,
)


def s(value):
    return "" if value is None else str(value).strip()


def dec(value):
    text = s(value)
    if not text:
        return Decimal("0")
    try:
        return Decimal(text)
    except InvalidOperation:
        return Decimal("0")


def read_sheet(ws, key_token):
    """Find the header row (the row whose cells include key_token) and return
    the data rows below it as dicts."""
    rows = list(ws.iter_rows(values_only=True))
    header = None
    start = 0
    for i, row in enumerate(rows):
        cells = [s(c).lower() for c in row]
        if key_token.lower() in cells:
            header = [s(c) for c in row]
            start = i + 1
            break
    if header is None:
        return []
    result = []
    for row in rows[start:]:
        if all(c is None for c in row):
            continue
        result.append(dict(zip(header, row)))
    return result


class Command(BaseCommand):
    help = "Import Plan-page cost seed data from the XLSX workbook."

    def add_arguments(self, parser):
        parser.add_argument("workbook", help="Path to SitesOfGrace_PlanCosts_Seed.xlsx")
        parser.add_argument("--dry-run", action="store_true",
                            help="Run inside a transaction and roll back; save nothing.")

    def handle(self, *args, **options):
        try:
            wb = openpyxl.load_workbook(options["workbook"], data_only=True)
        except FileNotFoundError:
            raise CommandError(f"Workbook not found: {options['workbook']}")

        stats = {"destinations": [0, 0], "regions": [0, 0], "defaults": 0}

        with transaction.atomic():
            # Destinations
            for row in read_sheet(wb["Destinations"], "city"):
                city = s(row.get("city"))
                if not city:
                    continue
                _, created = DestinationCost.objects.update_or_create(
                    city=city,
                    defaults={
                        "country": s(row.get("country")),
                        "region": s(row.get("region")),
                        "nearest_airport_iata": s(row.get("nearest_airport_iata")),
                        "nearest_airport_name": s(row.get("nearest_airport_name")),
                        "hotel_night_usd": dec(row.get("hotel_night_usd")),
                        "meal_usd": dec(row.get("meal_usd")),
                        "local_transport_day_usd": dec(row.get("local_transport_day_usd")),
                        "taxi_typical_usd": dec(row.get("taxi_typical_usd")),
                        "notes": s(row.get("notes")),
                    },
                )
                stats["destinations"][0 if created else 1] += 1

            # Region flight assumptions
            for row in read_sheet(wb["RegionFlights"], "region"):
                region = s(row.get("region"))
                if not region:
                    continue
                _, created = RegionFlightAssumption.objects.update_or_create(
                    region=region,
                    defaults={
                        "avg_roundtrip_usd_from_us": dec(row.get("avg_roundtrip_usd_from_us")),
                        "notes": s(row.get("notes")),
                    },
                )
                stats["regions"][0 if created else 1] += 1

            # Calculator defaults (singleton settings row)
            defaults = {s(r.get("key")): r.get("value")
                        for r in read_sheet(wb["CalculatorDefaults"], "key")}
            obj = CalculatorDefaults.objects.first() or CalculatorDefaults()
            int_fields = ["default_party_size", "default_nights", "meals_per_day",
                          "people_per_room", "misc_buffer_percent"]
            dec_fields = ["hotel_tier_budget_multiplier", "hotel_tier_midrange_multiplier",
                          "hotel_tier_comfort_multiplier"]
            for k, v in defaults.items():
                if k in int_fields and v is not None:
                    setattr(obj, k, int(v))
                elif k in dec_fields and v is not None:
                    setattr(obj, k, dec(v))
                elif k == "currency" and s(v):
                    obj.currency = s(v)
            obj.save()
            stats["defaults"] = 1

            if options["dry_run"]:
                transaction.set_rollback(True)

        if options["dry_run"]:
            self.stdout.write(self.style.WARNING("Dry run — rolled back, nothing saved."))
        d = stats["destinations"]; r = stats["regions"]
        self.stdout.write(f"destinations: {d[0]} created, {d[1]} updated")
        self.stdout.write(f"regions: {r[0]} created, {r[1]} updated")
        self.stdout.write(f"calculator defaults: {'saved' if stats['defaults'] else 'skipped'}")
