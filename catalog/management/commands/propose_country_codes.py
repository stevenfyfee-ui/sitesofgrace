"""Map the free-text `country` strings on SacredSitePages to ISO codes.

    python manage.py propose_country_codes --out country_codes.csv
    python manage.py propose_country_codes --apply country_codes.csv --dry-run
    python manage.py propose_country_codes --apply country_codes.csv

--out writes one row per distinct country string: how many sites use it,
the proposed ISO 3166-1 alpha-2 code, its name, a confidence ("high",
"medium", or blank where unsure), a note, and an empty "approved" column.
Nothing is written to the database.

--apply reads that CSV back and applies only rows whose "approved" column
says yes (yes / y / true / 1 / approved) and whose code is a real ISO code
-- edit the code first if the proposal was wrong. Following
docs/v2/IMPORT-RULES.md: each changed page gets a new published revision;
pages with drafts, and pages that aren't live, are skipped; a page whose
country_code is already set to something else is a conflict, never
overwritten. The `country` text itself is never changed.
"""
import csv
from collections import Counter

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from catalog.countries import COUNTRY_NAMES, country_name, propose
from catalog.models import SacredSitePage

APPROVED = {"yes", "y", "true", "1", "approved"}
COLUMNS = ["country", "sites", "proposed_code", "country_name", "confidence", "note", "approved"]


class Command(BaseCommand):
    help = "Propose ISO country codes for SacredSitePage.country (CSV), or apply approved rows."

    def add_arguments(self, parser):
        mode = parser.add_mutually_exclusive_group(required=True)
        mode.add_argument("--out", help="Write the proposal CSV here (read-only).")
        mode.add_argument("--apply", help="Apply the approved rows of this CSV.")
        parser.add_argument("--dry-run", action="store_true", help="With --apply: report only.")

    def handle(self, *args, **options):
        if options["out"]:
            return self._propose(options["out"])
        return self._apply(options["apply"], options["dry_run"])

    def _propose(self, out):
        counts = Counter(SacredSitePage.objects.values_list("country", flat=True))
        rows, unsure = [], 0
        for country, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0] or "")):
            code, confidence, note = propose(country)
            unsure += not code
            rows.append([country or "", n, code, country_name(code), confidence, note, ""])
        with open(out, "w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(COLUMNS)
            writer.writerows(rows)
        self.stdout.write(f"wrote {len(rows)} distinct country strings to {out}; {unsure} left blank (unsure)")

    def _apply(self, path, dry_run):
        try:
            with open(path, newline="", encoding="utf-8") as fh:
                rows = list(csv.DictReader(fh))
        except FileNotFoundError:
            raise CommandError(f"{path} not found")
        if rows and not {"country", "proposed_code", "approved"} <= set(rows[0]):
            raise CommandError(f"{path}: expected the columns {', '.join(COLUMNS)}")

        totals, problems = Counter(), []
        w = self.stdout.write
        w(("DRY RUN -- nothing will be written. " if dry_run else "") + f"Applying {path}")
        for row in rows:
            if (row.get("approved") or "").strip().lower() not in APPROVED:
                totals["rows_not_approved"] += 1
                continue
            code = (row.get("proposed_code") or "").strip().upper()
            if code not in COUNTRY_NAMES:
                problems.append(f"{row['country']!r}: {code!r} is not an ISO 3166-1 code; row skipped")
                continue
            totals["rows_approved"] += 1
            for page in SacredSitePage.objects.filter(country=row["country"]):
                if page.country_code == code:
                    totals["already_correct"] += 1
                elif page.country_code:
                    totals["conflicts"] += 1
                    problems.append(f"{page.pk} {page.title}: has {page.country_code}, file says {code} (conflict)")
                elif page.has_unpublished_changes:
                    totals["skipped"] += 1
                    problems.append(f"{page.pk} {page.title}: unpublished changes (draft) -- skipped")
                elif not page.live:
                    totals["skipped"] += 1
                    problems.append(f"{page.pk} {page.title}: not live -- skipped")
                else:
                    totals["changed"] += 1
                    if not dry_run:
                        with transaction.atomic():
                            page.country_code = code
                            page.save_revision(log_action=True).publish()
        w(f"{'Would change' if dry_run else 'Pages changed'}:  {totals['changed']}")
        w(f"Already correct:      {totals['already_correct']}")
        w(f"Approved rows:        {totals['rows_approved']}")
        w(f"Rows not approved:    {totals['rows_not_approved']}")
        w(f"Conflicts:            {totals['conflicts']}")
        w(f"Skipped:              {totals['skipped']}")
        for line in problems:
            w(f"  - {line}")
