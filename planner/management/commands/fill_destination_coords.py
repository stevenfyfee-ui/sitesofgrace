"""Fill a planner destination's latitude/longitude from its linked sites.

    python manage.py fill_destination_coords --dry-run
    python manage.py fill_destination_coords
    python manage.py fill_destination_coords --set dublin=53.3498,-6.2603 --dry-run
    python manage.py fill_destination_coords --set dublin=53.3498,-6.2603

For each destination with no coordinates, averages the coordinates of its
live associated_sites that have them. --set gives the coordinates by hand
for a destination that has no linked site to average (repeatable); it is
applied first, and an unknown slug or an out-of-range value stops the run
before anything is written. A destination that already has coordinates is
never changed, by either route (Standing Rule 4). Destinations it can't fill
are listed at the end.
"""
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from planner.geo import has_coords
from planner.models import DestinationCost

SIX_PLACES = Decimal("0.000001")


def parse_set(value):
    """"dublin=53.3498,-6.2603" -> ("dublin", Decimal lat, Decimal lng)."""
    slug, sep, coords = value.partition("=")
    parts = coords.split(",")
    if not sep or not slug.strip() or len(parts) != 2:
        raise CommandError(f"--set {value!r}: use slug=latitude,longitude")
    try:
        lat, lng = (Decimal(p.strip()).quantize(SIX_PLACES, ROUND_HALF_UP) for p in parts)
    except InvalidOperation:
        raise CommandError(f"--set {value!r}: latitude and longitude must be numbers")
    if not (-90 <= lat <= 90 and -180 <= lng <= 180):
        raise CommandError(f"--set {value!r}: out of range")
    return slug.strip(), lat, lng


class Command(BaseCommand):
    help = "Fill blank destination coordinates by averaging their linked sites, or by hand with --set."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Report what would change; write nothing.")
        parser.add_argument("--set", action="append", default=[], metavar="SLUG=LAT,LNG",
                            help="Coordinates for a destination with no linked sites to average.")

    def handle(self, *args, **options):
        dry = options["dry_run"]
        manual = {}
        for value in options["set"]:
            slug, lat, lng = parse_set(value)
            manual[slug] = (lat, lng)
        dests = {d.slug: d for d in DestinationCost.objects.prefetch_related("associated_sites")}
        unknown = sorted(set(manual) - set(dests))
        if unknown:
            raise CommandError(f"--set: no destination with slug {', '.join(unknown)}. Nothing was written.")

        filled, set_by_hand, kept, already, cannot = [], [], [], 0, []
        with transaction.atomic():
            for slug, dest in sorted(dests.items(), key=lambda kv: kv[1].city):
                if has_coords(dest):
                    if slug in manual:
                        kept.append(dest)
                    already += 1
                    continue
                if slug in manual:
                    lat, lng = manual[slug]
                    set_by_hand.append((dest, lat, lng))
                else:
                    points = [s for s in dest.associated_sites.all() if s.live and has_coords(s)]
                    if not points:
                        cannot.append(dest)
                        continue
                    lat = (sum(Decimal(s.latitude) for s in points) / len(points)).quantize(SIX_PLACES, ROUND_HALF_UP)
                    lng = (sum(Decimal(s.longitude) for s in points) / len(points)).quantize(SIX_PLACES, ROUND_HALF_UP)
                    filled.append((dest, lat, lng, len(points)))
                if not dry:
                    dest.latitude, dest.longitude = lat, lng
                    dest.save(update_fields=["latitude", "longitude"])

        prefix = "[dry run] would fill" if dry else "Filled"
        for dest, lat, lng in set_by_hand:
            self.stdout.write(f"{prefix} {dest.slug}: {lat}, {lng} (set by hand)")
        for dest, lat, lng, n in filled:
            self.stdout.write(f"{prefix} {dest.slug}: {lat}, {lng} (average of {n} site{'s' if n != 1 else ''})")
        for dest in kept:
            self.stdout.write(f"Not changed {dest.slug}: already has {dest.latitude}, {dest.longitude} "
                              f"(--set ignored; edit it in the admin)")
        self.stdout.write(
            f"\n{'Would fill' if dry else 'Filled'}: {len(filled) + len(set_by_hand)} "
            f"({len(set_by_hand)} by hand)   Already had coordinates: {already}   Can't fill: {len(cannot)}"
        )
        if cannot:
            self.stdout.write("Can't fill (no linked live site with coordinates; use --set slug=lat,lng):")
            for dest in cannot:
                self.stdout.write(f"  - {dest.slug} ({dest.city})")
