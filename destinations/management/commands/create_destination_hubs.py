"""Create the Destinations index and the first four hubs, as unpublished drafts.

    python manage.py create_destination_hubs

Titles only -- no text is written; fill them in the admin or with
import_hubs, then publish when ready. Safe to run again: pages that already
exist (by slug) are left exactly as they are. The same pattern as
create_legal_pages.
"""
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from wagtail.models import Site

from destinations.models import DestinationHubPage, DestinationIndexPage

INDEX = ("Destinations", "destinations")
HUBS = [
    ("Rome & Vatican City", "rome-vatican-city"),
    ("Assisi & Umbria", "assisi-umbria"),
    ("Paris & Northern France", "paris-northern-france"),
    ("Portugal", "portugal"),
]


class Command(BaseCommand):
    help = "Create the Destinations index and four hub drafts (titles only, unpublished)."

    def handle(self, *args, **options):
        site = Site.objects.filter(is_default_site=True).select_related("root_page").first()
        if site is None:
            raise CommandError("No default Wagtail site.")
        home = site.root_page.specific
        created = []
        with transaction.atomic():
            index = DestinationIndexPage.objects.first()
            if index is None:
                index = DestinationIndexPage(title=INDEX[0], slug=INDEX[1], live=False)
                home.add_child(instance=index)
                index.save_revision(log_action=True)
                created.append(f"{INDEX[0]} (index)")
            for title, slug in HUBS:
                if DestinationHubPage.objects.child_of(index).filter(slug=slug).exists():
                    continue
                hub = DestinationHubPage(title=title, slug=slug, live=False)
                index.add_child(instance=hub)
                hub.save_revision(log_action=True)
                created.append(title)
        self.stdout.write(
            ("created (unpublished): " + ", ".join(created)) if created else "nothing to do: all pages exist"
        )
