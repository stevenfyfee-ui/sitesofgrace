"""Local-only sample content for reviewing the Future Saints Phase 1 shell.

    python manage.py future_saints_dev_sample

Refuses to run unless settings.DEBUG is True and the database is local.
Builds the tree with create_future_saints_tree if it isn't there, fills only
BLANK card lines with "(sample)" placeholder text, picks a live saint for
Saint of the Week by slug (never by page ID), and publishes the six Future
Saints pages locally. No canonical page is changed and no fact is written:
every sample string says "(sample)".
"""
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

from catalog.models import SaintPage
from future_saints.models import FutureSaintsHomePage, FutureSaintsIndexPage

LOCAL_DB_HOSTS = {"db", "localhost", "127.0.0.1", ""}

SAINT_OF_WEEK_SLUG = "st-francis-of-assisi"
SAMPLE_LINE = "A short line for children goes here (sample)"
SAMPLE_INTRO = "A short welcome for this subject goes here (sample)"


def refuse_unless_local():
    if not settings.DEBUG:
        raise CommandError("future_saints_dev_sample only runs with DEBUG = True.")
    module = getattr(settings, "SETTINGS_MODULE", "") or ""
    host = connection.settings_dict.get("HOST") or ""
    if module.endswith("production") or host not in LOCAL_DB_HOSTS:
        raise CommandError(f"future_saints_dev_sample refuses to run against this database (host {host!r}).")


def publish(page):
    page.save_revision(log_action=True).publish()


class Command(BaseCommand):
    help = "Local-only Future Saints sample content (DEBUG and a local database required)."

    def handle(self, *args, **options):
        refuse_unless_local()
        if not FutureSaintsHomePage.objects.exists():
            call_command("create_future_saints_tree", stdout=self.stdout)

        with transaction.atomic():
            home = FutureSaintsHomePage.objects.get()
            for field in ("card_1_line", "card_2_line", "card_3_line", "card_4_line", "holy_land_line"):
                if not getattr(home, field):
                    setattr(home, field, SAMPLE_LINE)
            if home.saint_of_week_id is None:
                saint = (SaintPage.objects.live().filter(slug=SAINT_OF_WEEK_SLUG).first()
                         or SaintPage.objects.live().order_by("title").first())
                home.saint_of_week = saint
                if not home.saint_of_week_line:
                    home.saint_of_week_line = SAMPLE_LINE
            publish(home)
            for index in FutureSaintsIndexPage.objects.child_of(home):
                if not index.intro:
                    index.intro = SAMPLE_INTRO
                publish(index)

        saint = home.saint_of_week
        self.stdout.write(f"Saint of the Week: {saint.title if saint else 'none'} "
                          f"(portrait shown: {'yes' if saint and saint.portrait_id and saint.portrait_credit else 'no, placeholder'})")
        self.stdout.write(self.style.SUCCESS(
            "Published the Future Saints home page and indexes locally. They render only when "
            "SOG_FUTURE_SAINTS allows the request."
        ))
