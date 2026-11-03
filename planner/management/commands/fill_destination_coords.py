"""Fill a planner destination's latitude/longitude from its linked sites.

    python manage.py fill_destination_coords --dry-run
    python manage.py fill_destination_coords

For each destination with no coordinates, averages the coordinates of its
live associated_sites that have them. A destination that already has
coordinates is never changed (Standing Rule 4). Destinations it can't fill
(no linked live sites with coordinates) are listed at the end.
"""
from decimal import ROUND_HALF_UP, Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from planner.geo import has_coords
from planner.models import DestinationCost

SIX_PLACES = Decimal("0.000001")


class Command(BaseCommand):
    help = "Fill blank destination coordinates by averaging their linked sites."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Report what would change; write nothing.")

    def handle(self, *args, **options):
        dry = options["dry_run"]
        filled, already, cannot = [], 0, []
        with transaction.atomic():
            for dest in DestinationCost.objects.prefetch_related("associated_sites"):
                if has_coords(dest):
                    already += 1
                    continue
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
        for dest, lat, lng, n in filled:
            self.stdout.write(f"{prefix} {dest.slug}: {lat}, {lng} (average of {n} site{'s' if n != 1 else ''})")
        self.stdout.write(
            f"\n{'Would fill' if dry else 'Filled'}: {len(filled)}   Already had coordinates: {already}   "
            f"Can't fill: {len(cannot)}"
        )
        if cannot:
            self.stdout.write("Can't fill (no linked live site with coordinates):")
            for dest in cannot:
                self.stdout.write(f"  - {dest.slug} ({dest.city})")
