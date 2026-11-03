"""Link the sites approved in a reviewed destination/site CSV.

    python manage.py apply_destination_sites docs/v2/reports/destination_sites.csv --dry-run
    python manage.py apply_destination_sites docs/v2/reports/destination_sites.csv

Columns: destination_slug, site_slug, approve, and optionally site_id (as
propose_destination_sites writes it). Only rows with approve=yes are used;
every other row is ignored.

A row with a site_id matches on it, and its site_slug must still be that
page's slug. A row without one matches its site_slug against live pages,
which must find exactly one. The page must be live. Links are only ever
added, never removed. Every approved row is checked before anything is
written, and one bad row stops the whole run.

--skip-missing lists approved rows whose site slug doesn't exist here and
skips them instead of stopping (for a local database older than production).
Every other problem still stops the run.
"""
import csv
import glob

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from catalog.models import SacredSitePage
from planner.models import DestinationCost

REQUIRED = {"destination_slug", "site_slug", "approve"}


class Command(BaseCommand):
    help = "Add the approve=yes rows of a reviewed CSV to destinations' associated sites."

    def add_arguments(self, parser):
        parser.add_argument("path", help="The reviewed CSV (glob allowed; must match exactly one file).")
        parser.add_argument("--dry-run", action="store_true", help="Check and report; write nothing.")
        parser.add_argument("--skip-missing", action="store_true",
                            help="Skip (and list) site slugs that don't exist in this database.")

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
        errors, not_here, todo = [], [], []
        for line, row in approved:
            dest = dests.get((row["destination_slug"] or "").strip())
            slug = (row["site_slug"] or "").strip()
            site_id = (row.get("site_id") or "").strip()
            if dest is None:
                errors.append(f"line {line}: unknown destination {row['destination_slug']!r}")
                continue
            if site_id:
                site = SacredSitePage.objects.filter(pk=int(site_id)).first() if site_id.isdigit() else None
                if site is None:
                    errors.append(f"line {line}: no site with id {site_id!r}")
                elif site.slug != slug:
                    errors.append(f"line {line}: site {site.pk} is now {site.slug!r}, not {slug!r}")
                elif not site.live:
                    errors.append(f"line {line}: site {site.pk} ({site.slug}) isn't live")
                else:
                    todo.append((dest, site))
                continue
            found = list(SacredSitePage.objects.filter(slug=slug))
            live = [s for s in found if s.live]
            if not found:
                (not_here if options["skip_missing"] else errors).append(f"line {line}: no site with slug {slug!r}")
            elif not live:
                errors.append(f"line {line}: site {slug!r} isn't live")
            elif len(live) > 1:
                errors.append(f"line {line}: {len(live)} live sites have the slug {slug!r}; add a site_id column")
            else:
                todo.append((dest, live[0]))
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
            f"Already linked: {already}   Skipped (not in this database): {len(not_here)}   "
            f"Ignored (not approved): {len(rows) - len(approved)}"
        )
        for line in not_here:
            self.stdout.write(f"  - {line}")
