"""Run the whole content-sync sequence in one paste, instead of six.

Composes import_catalog, apply_enrichment, merge_saints and stub_saints
inside a single transaction and enforces the stop conditions in code
instead of asking a human to read six command outputs and decide whether
the numbers look right. A failed check raises CommandError, which rolls
back the entire transaction -- nothing partial is ever left in the
database -- and exits non-zero.

    python manage.py sync_catalog --dry-run
    python manage.py sync_catalog

--dry-run does NOT mean read-only for the whole pipeline -- only
apply_enrichment's own --dry-run pass is (see its docstring: no writes at
all, not even inside a transaction). import_catalog, merge_saints and
stub_saints still do their real writes here; --dry-run's only effect on
them is that sync_catalog's outer transaction gets rolled back at the
very end instead of committed. That's why a --dry-run's own output shows
pages actually being published and data_status actually being cleared --
it happened, inside the transaction, and then got undone. Don't reason
about cost or side effects from "--dry-run doesn't write"; it's "--dry-run
writes then throws it away," except for step 2, which never writes at
all.

Stop conditions (abort, roll back everything, exit non-zero):
  - import_catalog would create a saint page. Production is expected to
    already have every saint in the workbook; a create means the workbook
    and the database have drifted apart. Pass --allow-new-saints if a
    future workbook is genuinely adding new saints on purpose.
  - apply_enrichment would touch fewer than --min-enriched rows (default
    358 -- roughly 90% of the ~398 rows the September 2026 harvest is
    expected to touch on a first run). Checked with an internal dry run
    BEFORE the real apply, so a bad CSV or an unexpected DB state never
    writes anything.
  - stub_saints --publish --ready would publish a count other than
    --expect-published (default 8). Enrichment never writes significance,
    so this number should not move just because more fields got filled in.

Idempotent: run it twice back-to-back and the second run reports zero
everywhere except total-live (import_catalog only counts a save when a
field actually changed; apply_enrichment only fills blanks; merge_saints
and stub_saints are no-ops once their target state is reached). See
catalog/tests_sync_catalog.py.
"""
import os
import time

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from catalog.management.commands.apply_enrichment import Command as ApplyEnrichmentCommand
from catalog.management.commands.import_catalog import Command as ImportCatalogCommand
from catalog.management.commands.merge_saints import Command as MergeSaintsCommand
from catalog.management.commands.stub_saints import Command as StubSaintsCommand
from catalog.models import SaintPage

DEFAULT_WORKBOOK = os.path.join(
    settings.BASE_DIR, "tools", "SitesOfGrace_Saints_EXPANSION_2026-09.xlsx"
)
DEFAULT_ENRICHMENT_CSV = os.path.join(
    settings.BASE_DIR, "tools", "saints_data", "enrichment.csv"
)


class Command(BaseCommand):
    help = "Import, enrich, merge and publish the saints catalog as one guarded step."

    def add_arguments(self, parser):
        parser.add_argument("--workbook", default=DEFAULT_WORKBOOK,
                             help="Path to the catalog workbook (default: "
                                  "tools/SitesOfGrace_Saints_EXPANSION_2026-09.xlsx).")
        parser.add_argument("--enrichment-csv", default=DEFAULT_ENRICHMENT_CSV,
                             help="Path to the enrichment CSV (default: "
                                  "tools/saints_data/enrichment.csv).")
        parser.add_argument("--dry-run", action="store_true",
                             help="Run every step, print the summary, then roll back.")
        parser.add_argument("--allow-new-saints", action="store_true",
                             help="Allow import_catalog to create pages "
                                  "(default: abort if it would create any).")
        parser.add_argument("--min-enriched", type=int, default=358,
                             help="Abort if apply_enrichment would touch fewer rows than this.")
        parser.add_argument("--expect-published", type=int, default=8,
                             help="Abort unless stub_saints --publish --ready "
                                  "publishes exactly this many pages.")

    def phase(self, label):
        elapsed = time.monotonic() - self.start
        self.stdout.write(self.style.SUCCESS(f"== [{elapsed:6.1f}s] {label} =="))
        self.stdout.flush()

    def diagnose_publish_gap(self, publish_candidates, published_titles):
        """Called with the transaction still open (nothing rolled back yet),
        so this sees exactly the state the run produced. Names the specific
        pages, not just a count, so a future mismatch is diagnosable from
        the error message alone instead of sending someone to go hunting."""
        published_this_run = set(published_titles)
        already_live, not_live = [], []
        for candidate in publish_candidates:
            if candidate["title"] in published_this_run:
                continue
            saint = SaintPage.objects.filter(slug=candidate["slug"]).first()
            if saint is None:
                not_live.append(f"  {candidate['title']} ({candidate['slug']}) -- NOT FOUND in the database")
            elif saint.live:
                already_live.append(
                    f"  {saint.title} ({saint.slug}) -- live=True, data_status={saint.data_status!r} -- "
                    "already live BEFORE this run; import_catalog updated its content but stub_saints "
                    "only publishes pages that are currently hidden (live=False), so it was never counted"
                )
            else:
                not_live.append(
                    f"  {saint.title} ({saint.slug}) -- live=False, data_status={saint.data_status!r}, "
                    f"significance {'present' if saint.significance else 'BLANK'} "
                    f"({len(saint.significance)} chars)"
                )
        lines = [
            f"{len(publish_candidates)} workbook row(s) are stub-tagged with real significance "
            "(the publish candidates):",
            f"  published this run: {', '.join(published_titles) if published_titles else '(none)'}",
        ]
        if already_live:
            lines.append("  already live before this run (not counted as a publish):")
            lines.extend(already_live)
        if not_live:
            lines.append("  NOT live -- unexplained gap:")
            lines.extend(not_live)
        return "\n".join(lines)

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        self.start = time.monotonic()

        with transaction.atomic():
            saints_before = SaintPage.objects.count()

            self.phase("1/5 import_catalog")
            import_cmd = ImportCatalogCommand()
            import_cmd.stdout = self.stdout
            call_command(import_cmd, options["workbook"], only="saints")
            created = import_cmd.stats["saints"]["created"]
            updated = import_cmd.stats["saints"]["updated"]
            if created and not options["allow_new_saints"]:
                raise CommandError(
                    f"ABORTED, nothing saved: import_catalog would create {created} saint "
                    "page(s). Production should already have every saint in this workbook -- "
                    "pass --allow-new-saints if that's actually intended this time."
                )

            self.phase("2/5 apply_enrichment -- dry-run check")
            enrich_check = ApplyEnrichmentCommand()
            enrich_check.stdout = self.stdout
            call_command(enrich_check, options["enrichment_csv"], dry_run=True)
            projected = enrich_check.result["applied"]
            if projected < options["min_enriched"]:
                raise CommandError(
                    f"ABORTED, nothing saved: apply_enrichment would only touch {projected} "
                    f"row(s), expected at least {options['min_enriched']}. The CSV or the "
                    "database is not in the state this run expected."
                )

            self.phase("3/5 apply_enrichment -- writing")
            enrich_cmd = ApplyEnrichmentCommand()
            enrich_cmd.stdout = self.stdout
            call_command(enrich_cmd, options["enrichment_csv"])
            enriched = enrich_cmd.result["applied"]
            skipped_ambiguous = enrich_cmd.result["skipped_ambiguous"]

            self.phase("4/5 merge_saints")
            merge_cmd = MergeSaintsCommand()
            merge_cmd.stdout = self.stdout
            call_command(merge_cmd)
            merged = merge_cmd.result["newly_merged_count"]

            self.phase("5/5 stub_saints --publish --ready")
            publish_cmd = StubSaintsCommand()
            publish_cmd.stdout = self.stdout
            call_command(publish_cmd, publish=True, ready=True)
            published = publish_cmd.result["published"]
            if published != options["expect_published"]:
                diagnosis = self.diagnose_publish_gap(
                    import_cmd.publish_candidates, publish_cmd.result["published_titles"]
                )
                raise CommandError(
                    f"ABORTED, nothing saved: stub_saints --publish --ready published "
                    f"{published} page(s), expected exactly {options['expect_published']}. "
                    "Enrichment never writes significance, so this count should not move on "
                    f"its own -- something wrote a summary nobody reviewed.\n{diagnosis}"
                )

            saints_after = SaintPage.objects.count()
            total_live = SaintPage.objects.filter(live=True).count()

            if dry_run:
                transaction.set_rollback(True)

        self.phase("done")
        label = "DRY RUN (rolled back)" if dry_run else "APPLIED"
        summary = (
            f"sync_catalog: {label} | created={created} updated={updated} "
            f"enriched={enriched} skipped-ambiguous={skipped_ambiguous} merged={merged} "
            f"published={published} total-live={total_live} "
            f"(saints {saints_before} -> {saints_after})"
        )
        self.stdout.write(self.style.SUCCESS(summary))
