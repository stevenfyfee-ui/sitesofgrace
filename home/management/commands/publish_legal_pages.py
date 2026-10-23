"""Publish all ten legal pages together, or none (GO-LIVE step 3).

    python manage.py publish_legal_pages --dry-run
    python manage.py publish_legal_pages

Uses the same rule as the admin's publish guard (home/wagtail_hooks.py:
LegalPage.publish_problem): a page can't go live while a Settings > Legal
details value its text uses is blank. If any of the ten is missing or would
be blocked, the command lists every reason and publishes nothing. Pages that
are already live with no draft are left as they are.
"""
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from wagtail.models import Site

from home import legal
from home.models import LegalDetails, LegalPage


class Command(BaseCommand):
    help = "Publish the ten LegalPages together, or refuse and say why."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Check and report; publish nothing.")

    def handle(self, *args, **options):
        site = Site.objects.filter(is_default_site=True).first()
        details = LegalDetails.load(request_or_site=site)
        pages = {page.slug: page for page in LegalPage.objects.filter(slug__in=legal.LEGAL_SLUGS)}

        problems, to_publish, already = [], [], []
        for slug in legal.LEGAL_SLUGS:
            page = pages.get(slug)
            if page is None:
                problems.append(f"{slug}: no LegalPage (run create_legal_pages first)")
                continue
            if page.live and not page.has_unpublished_changes:
                already.append(slug)
                continue
            latest = page.get_latest_revision_as_object()
            problem = latest.publish_problem(details)
            if problem:
                problems.append(f"{slug}: {problem}")
            else:
                to_publish.append((page, latest))

        say = self.stdout.write
        if problems:
            say("Refusing: none of the legal pages were published.")
            for line in problems:
                say(f"  - {line}")
            raise CommandError(f"{len(problems)} legal page(s) can't be published yet.")

        prefix = "DRY RUN -- " if options["dry_run"] else ""
        say(f"{prefix}Already live: {', '.join(already) if already else 'none'}")
        say(f"{prefix}{'Would publish' if options['dry_run'] else 'Publishing'}: "
            f"{', '.join(p.slug for p, _ in to_publish) if to_publish else 'none'}")
        if options["dry_run"] or not to_publish:
            return
        with transaction.atomic():
            for page, latest in to_publish:
                latest.save_revision(log_action=True).publish()
        live = LegalPage.objects.live().filter(slug__in=legal.LEGAL_SLUGS).count()
        say(self.style.SUCCESS(f"Done: {live} of {len(legal.LEGAL_SLUGS)} legal pages are live."))
