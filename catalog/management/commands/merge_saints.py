"""Merge known-duplicate SaintPages found during the Wikidata enrichment work.

Both pairs below are the same real person under two different catalog
titles (confirmed by matching Wikidata QID and near-identical body text):

  St. Birgitta - Bridget of Sweden  <-  St. Bridget of Sweden
  St. John Leonardi                 <-  St. Giovanni Leonardi

For each pair: any also_known_as value the loser has that the winner
lacks is copied across, the loser is unpublished (live=False -- never
deleted), and a permanent Redirect from the loser's old URL to the
winner is created or repointed. Idempotent: safe to run again on an
already-merged pair, or on an environment where the loser was already
unpublished.

    python manage.py merge_saints --dry-run
    python manage.py merge_saints
"""
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from catalog.models import SaintPage

PAIRS = [
    {"winner": "st-birgitta-bridget-of-sweden", "loser": "st-bridget-of-sweden",
     "transfer_aka": "Birgitta of Sweden"},
    {"winner": "st-john-leonardi", "loser": "st-giovanni-leonardi", "transfer_aka": None},
]


class Command(BaseCommand):
    help = "Merge known-duplicate saint pages: unpublish the loser, redirect to the winner."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true",
                            help="Report what would change and roll back.")

    def handle(self, *args, **options):
        from wagtail.contrib.redirects.models import Redirect
        from wagtail.models import Site

        try:
            site = Site.objects.get(is_default_site=True)
        except Site.DoesNotExist:
            raise CommandError("No default Site configured -- cannot create redirects.")

        report = []
        pair_results = []

        with transaction.atomic():
            for pair in PAIRS:
                try:
                    winner = SaintPage.objects.get(slug=pair["winner"])
                    loser = SaintPage.objects.get(slug=pair["loser"])
                except SaintPage.DoesNotExist as exc:
                    report.append(f"SKIPPED {pair['winner']} / {pair['loser']}: {exc}")
                    pair_results.append({
                        "winner": pair["winner"], "loser": pair["loser"],
                        "skipped": True, "newly_merged": False,
                    })
                    continue

                changed = []
                newly_merged = False
                old_path = loser.url

                aka = pair.get("transfer_aka")
                if aka:
                    current = [a.strip() for a in (winner.also_known_as or "").split(",") if a.strip()]
                    if aka not in current:
                        current.append(aka)
                        winner.also_known_as = ", ".join(current)
                        winner.save(update_fields=["also_known_as"])
                        changed.append(f"winner.also_known_as += {aka!r}")
                        newly_merged = True

                if loser.live:
                    loser.live = False
                    loser.save(update_fields=["live"])
                    changed.append("loser unpublished")
                    newly_merged = True
                else:
                    changed.append("loser already unpublished")

                if old_path:
                    normalised = Redirect.normalise_path(old_path, decode_unicode=False)
                    redirect, created = Redirect.objects.get_or_create(
                        old_path=normalised, site=site,
                        defaults={"redirect_page": winner, "is_permanent": True,
                                  "automatically_created": False},
                    )
                    if not created and redirect.redirect_page_id != winner.pk:
                        redirect.redirect_page = winner
                        redirect.is_permanent = True
                        redirect.save(update_fields=["redirect_page", "is_permanent"])
                        changed.append(f"redirect repointed: {normalised} -> {winner.title}")
                        newly_merged = True
                    elif created:
                        changed.append(f"redirect created: {normalised} -> {winner.title}")
                        newly_merged = True
                    else:
                        changed.append(f"redirect already correct: {normalised} -> {winner.title}")
                else:
                    changed.append("loser has no URL (not routable) -- no redirect created")

                report.append(f"{loser.title!r} ({pair['loser']}) -> {winner.title!r} ({pair['winner']})")
                for c in changed:
                    report.append("  " + c)
                pair_results.append({
                    "winner": pair["winner"], "loser": pair["loser"],
                    "skipped": False, "newly_merged": newly_merged,
                })

            if options["dry_run"]:
                transaction.set_rollback(True)

        for line in report:
            self.stdout.write(line)
        verb = "would process" if options["dry_run"] else "processed"
        self.stdout.write(self.style.SUCCESS(f"{verb} {len(PAIRS)} pair(s)"))
        if options["dry_run"]:
            self.stdout.write(self.style.WARNING("dry run -- rolled back, nothing saved"))

        # Structured result for callers that compose this command (e.g.
        # sync_catalog) -- see the note in apply_enrichment.py about why
        # this isn't a return value.
        self.result = {
            "pairs": pair_results,
            "newly_merged_count": sum(1 for p in pair_results if p["newly_merged"]),
        }
