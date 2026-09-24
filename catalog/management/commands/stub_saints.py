"""Publish or unpublish the auto-generated saint stubs.

import_catalog creates pages live, so a bulk import puts every stub straight
into the public saints directory with no narrative on it. Run this right after
an import to take them back out of sight, then publish each one as its content
gets written.

    python manage.py stub_saints                      # report only
    python manage.py stub_saints --unpublish          # hide every stub
    python manage.py stub_saints --publish --ready    # publish the ones that now have content
"""
from django.core.management.base import BaseCommand

from catalog.models import SaintPage

STUB_PREFIX = "stub-"


class Command(BaseCommand):
    help = "Publish or unpublish saint pages whose data_status marks them as stubs."

    def add_arguments(self, parser):
        group = parser.add_mutually_exclusive_group()
        group.add_argument("--unpublish", action="store_true",
                           help="Set live=False on every stub saint.")
        group.add_argument("--publish", action="store_true",
                           help="Set live=True on stub saints.")
        parser.add_argument("--ready", action="store_true",
                            help="With --publish, only pages that have significance or body, "
                                 "and clear their stub data_status as they go live.")

    def handle(self, *args, **options):
        stubs = SaintPage.objects.filter(data_status__startswith=STUB_PREFIX)
        total = stubs.count()
        with_content = stubs.exclude(significance="").count() or 0

        if not (options["unpublish"] or options["publish"]):
            self.stdout.write(f"stub saints: {total}")
            self.stdout.write(f"  live now:        {stubs.filter(live=True).count()}")
            self.stdout.write(f"  hidden:          {stubs.filter(live=False).count()}")
            self.stdout.write(f"  have a summary:  {with_content}")
            self.stdout.write("\nNothing changed. Pass --unpublish or --publish.")
            self.result = {
                "total": total,
                "live": stubs.filter(live=True).count(),
                "hidden": stubs.filter(live=False).count(),
                "with_content": with_content,
            }
            return

        if options["unpublish"]:
            n = 0
            for saint in stubs.filter(live=True):
                saint.live = False
                saint.save(update_fields=["live"])
                n += 1
            self.stdout.write(self.style.SUCCESS(f"hid {n} stub saint pages"))
            self.result = {"hidden": n}
            return

        queryset = stubs.filter(live=False)
        if options["ready"]:
            queryset = queryset.exclude(significance="")
        eligible = queryset.count()
        self.stdout.write(f"publishing: {eligible} eligible")
        self.stdout.flush()
        n = 0
        published_titles = []
        for saint in queryset:
            saint.live = True
            if options["ready"]:
                saint.data_status = ""
            saint.save(update_fields=["live", "data_status"])
            n += 1
            published_titles.append(saint.title)
            if n % 50 == 0 or n == eligible:
                self.stdout.write(f"  ...{n}/{eligible} published")
                self.stdout.flush()
        self.stdout.write(self.style.SUCCESS(f"published {n} saint pages"))
        if options["ready"]:
            self.stdout.write("their data_status was cleared, so they are no longer stubs")
        self.result = {"published": n, "published_titles": published_titles}
