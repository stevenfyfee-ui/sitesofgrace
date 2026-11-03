"""Link the sites approved in a propose_destination_sites CSV.

    python manage.py apply_destination_sites docs/v2/reports/destination_sites.csv --dry-run
    python manage.py apply_destination_sites docs/v2/reports/destination_sites.csv

Only rows with approve=yes are used; every other row is ignored. Rows match
on site_id; the row's site_slug must still be that page's slug, and the page
must be live. Links are only ever added, never removed. Every approved row is
checked before anything is written; one bad row stops the whole run.
"""
import csv
import glob

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from catalog.models import SacredSitePage
from planner.models import DestinationCost

REQUIRED = {"destination_slug", "site_id", "site_slug", "approve"}


class Command(BaseCommand):
    help = "Add the approve=yes rows of a reviewed CSV to destinations' associated sites."

    def add_arguments(self, parser):
        parser.add_argument("path", help="The reviewed CSV (glob allowed; must match exactly one file).")
        parser.add_argument("--dry-run", action="store_true", help="Check and report; write nothing.")

    def handle(self, *args, **options):
        matches = sorted(glob.glob(options["path"]))
        if len(matches) != 1:
            raise CommandError(f"{options['path']!r} must match exactly one file; it matched {len(matches)}.")
        with open(matches[0], newline="", encoding="utf-8-sig") as fh:
            reader = csv.DictReader(fh)
            missing = REQUIRED - set(reader.fieldnames or [])
            if missing:
                raise CommandError(f"Missing column(s): {', '.join(sorted(missing))}")
            rows = list(reader)

        approved = [(n, r) for n, r in enumerate(rows, start=2) if (r.get("approve") or "").strip().lower() == "yes"]
        dests = {d.slug: d for d in DestinationCost.objects.all()}
        errors, todo = [], []
        for line, row in approved:
            dest = dests.get((row["destination_slug"] or "").strip())
            site_id = (row["site_id"] or "").strip()
            site = SacredSitePage.objects.filter(pk=int(site_id)).first() if site_id.isdigit() else None
            if dest is None:
                errors.append(f"line {line}: unknown destination {row['destination_slug']!r}")
            elif site is None:
                errors.append(f"line {line}: no site with id {site_id!r}")
            elif site.slug != (row["site_slug"] or "").strip():
                errors.append(f"line {line}: site {site.pk} is now {site.slug!r}, not {row['site_slug']!r}")
            elif not site.live:
                errors.append(f"line {line}: site {site.pk} ({site.slug}) isn't live")
            else:
                todo.append((dest, site))
        if errors:
            raise CommandError("Nothing was linked. Fix these rows first:\n  " + "\n  ".join(errors))

        added = already = 0
        with transaction.atomic():
            for dest, site in todo:
                if dest.associated_sites.filter(pk=site.pk).exists():
                    already += 1
                    continue
                added += 1
                self.stdout.write(f"{'[dry run] would link' if options['dry_run'] else 'Linked'} "
                                  f"{site.slug} -> {dest.slug}")
                if not options["dry_run"]:
                    dest.associated_sites.add(site)

        self.stdout.write(
            f"\nApproved rows: {len(approved)}   {'Would link' if options['dry_run'] else 'Linked'}: {added}   "
            f"Already linked: {already}   Ignored (not approved): {len(rows) - len(approved)}"
        )
