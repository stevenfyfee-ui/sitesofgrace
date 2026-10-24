"""Publish destination hubs that have text (GO-LIVE step 6).

    python manage.py publish_hubs --dry-run
    python manage.py publish_hubs
    python manage.py publish_hubs --slug assisi-umbria --slug portugal

A hub is published (its latest draft revision) only if that draft has an
intro; empty hubs are skipped and listed. The Destinations index is
published too, the first time a hub goes live, so "All destinations" has
somewhere to go. Hubs that are already live with no draft are left alone.
"""
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from destinations.models import DestinationHubPage, DestinationIndexPage


class Command(BaseCommand):
    help = "Publish destination hubs whose draft has an intro; skip and list empty ones."

    def add_arguments(self, parser):
        parser.add_argument("--slug", action="append", default=[], help="Only this hub (repeatable).")
        parser.add_argument("--dry-run", action="store_true", help="Report only; publish nothing.")

    def handle(self, *args, **options):
        hubs = DestinationHubPage.objects.order_by("path")
        if options["slug"]:
            hubs = hubs.filter(slug__in=options["slug"])
            missing = sorted(set(options["slug"]) - set(hubs.values_list("slug", flat=True)))
            if missing:
                raise CommandError(f"No destination hub with slug: {', '.join(missing)}")
        ready, empty, already = [], [], []
        for hub in hubs:
            if hub.live and not hub.has_unpublished_changes:
                already.append(hub.title)
                continue
            latest = hub.get_latest_revision_as_object()
            if (latest.intro or "").strip():
                ready.append((hub, latest))
            else:
                empty.append(latest.title)
        index = DestinationIndexPage.objects.first()
        publish_index = bool(ready) and index is not None and not index.live

        prefix = "DRY RUN -- " if options["dry_run"] else ""
        say = self.stdout.write
        say(f"{prefix}{'Would publish' if options['dry_run'] else 'Publishing'}: "
            f"{', '.join(latest.title for _, latest in ready) if ready else 'none'}")
        if publish_index:
            say(f"{prefix}{'Would publish' if options['dry_run'] else 'Publishing'} the Destinations index too")
        say(f"Skipped (no intro yet): {', '.join(empty) if empty else 'none'}")
        say(f"Already live: {', '.join(already) if already else 'none'}")
        if options["dry_run"] or not ready:
            return
        with transaction.atomic():
            if publish_index:
                index.get_latest_revision_as_object().save_revision(log_action=True).publish()
            for hub, latest in ready:
                latest.save_revision(log_action=True).publish()
        say(self.style.SUCCESS(f"Done: {DestinationHubPage.objects.live().count()} hub(s) live."))
