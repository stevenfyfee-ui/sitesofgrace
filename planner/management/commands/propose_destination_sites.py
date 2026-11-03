"""List live sacred sites that probably belong to a planner destination but
aren't linked to it yet. Read-only: the CSV is a review list.

    python manage.py propose_destination_sites --dry-run
    python manage.py propose_destination_sites --out docs/v2/reports/destination_sites.csv

A site is proposed for a destination when it is within 15 miles of the
destination's coordinates, or its locality matches the destination's city
(the same loose match ?site= uses). A destination with no coordinates yet
measures from the average of its locality-matched sites instead, and the
report says so. Mark the rows to link with approve=yes, then run
apply_destination_sites on the edited file.
"""
import csv

from django.core.management.base import BaseCommand, CommandError

from catalog.models import SacredSitePage
from planner.geo import has_coords, haversine_miles, locality_matches
from planner.models import DestinationCost

RADIUS_MI = 15
COLUMNS = [
    "destination_slug", "destination_city", "site_id", "site_slug", "site_title",
    "locality", "country", "miles", "match", "linked_elsewhere", "approve",
]


class Command(BaseCommand):
    help = "Write a CSV of live sites to review for linking to planner destinations. Changes nothing."

    def add_arguments(self, parser):
        parser.add_argument("--out", help="CSV file to write.")
        parser.add_argument("--dry-run", action="store_true", help="Print the CSV instead of writing a file.")

    def handle(self, *args, **options):
        if not options["dry_run"] and not options["out"]:
            raise CommandError("Give --out <csv>, or --dry-run to print the list.")

        sites = list(SacredSitePage.objects.live().only("id", "slug", "title", "locality", "country",
                                                         "latitude", "longitude"))
        links = {}
        for dest in DestinationCost.objects.prefetch_related("associated_sites"):
            for site in dest.associated_sites.all():
                links.setdefault(site.pk, set()).add(dest.slug)

        rows, notes = [], []
        for dest in DestinationCost.objects.all():
            linked = {s.pk for s in dest.associated_sites.all()}
            by_locality = [s for s in sites if locality_matches(s.locality, dest.city)]
            locality_ids = {s.pk for s in by_locality}
            centre = None
            if has_coords(dest):
                centre = (dest.latitude, dest.longitude)
            else:
                pts = [s for s in by_locality if has_coords(s)]
                if pts:
                    centre = (sum(float(s.latitude) for s in pts) / len(pts),
                              sum(float(s.longitude) for s in pts) / len(pts))
                    notes.append(f"{dest.slug}: no coordinates; measured from {len(pts)} locality-matched site(s)")
                else:
                    notes.append(f"{dest.slug}: no coordinates and no locality match; locality matching only")

            found = 0
            for site in sites:
                if site.pk in linked:
                    continue
                miles = None
                if centre and has_coords(site):
                    miles = haversine_miles(centre[0], centre[1], site.latitude, site.longitude)
                near = miles is not None and miles <= RADIUS_MI
                by_name = site.pk in locality_ids
                if not (near or by_name):
                    continue
                found += 1
                rows.append({
                    "destination_slug": dest.slug,
                    "destination_city": dest.city,
                    "site_id": site.pk,
                    "site_slug": site.slug,
                    "site_title": site.title,
                    "locality": site.locality,
                    "country": site.country,
                    "miles": "" if miles is None else f"{miles:.1f}",
                    "match": "both" if near and by_name else ("within 15 mi" if near else "locality"),
                    "linked_elsewhere": " ".join(sorted(links.get(site.pk, set()) - {dest.slug})),
                    "approve": "",
                })
            if not found:
                notes.append(f"{dest.slug}: nothing to propose")

        rows.sort(key=lambda r: (r["destination_slug"], r["miles"] == "", float(r["miles"] or 0), r["site_title"]))

        if options["dry_run"]:
            writer = csv.DictWriter(self.stdout, fieldnames=COLUMNS, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
        else:
            with open(options["out"], "w", newline="", encoding="utf-8") as fh:
                writer = csv.DictWriter(fh, fieldnames=COLUMNS, lineterminator="\n")
                writer.writeheader()
                writer.writerows(rows)

        self.stderr.write(
            f"\n{len(rows)} proposal(s) across {len({r['destination_slug'] for r in rows})} destination(s) "
            f"from {len(sites)} live sites."
            + ("" if options["dry_run"] else f" Wrote {options['out']}.")
        )
        for note in notes:
            self.stderr.write(f"  - {note}")
