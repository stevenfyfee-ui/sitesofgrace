"""Report how well feast_day / date_display values parse. Read-only.

    python manage.py audit_feast_dates

Covers every saint and site page, published or not, so a stub can be fixed
before it goes live. Unpublished pages are marked; only live, public pages
ever reach the home page card.
"""
from datetime import date, timedelta

from django.core.management.base import BaseCommand
from django.urls import reverse

from catalog.models import SacredSitePage, SaintPage
from liturgy.calendar import celebrations_on
from liturgy.feasts import parse_anniversaries, parse_feast_text


class Command(BaseCommand):
    help = "Audit which saint and site feast dates the Today in the Church card can read."

    def handle(self, *args, **options):
        unparseable = {}
        counts = {}
        fixed_days, movable_keys = set(), set()

        for label, model in (("saints", SaintPage), ("sites", SacredSitePage)):
            ok = bad = blank = 0
            for page in model.objects.order_by("title"):
                value = (page.feast_day or "").strip()
                if not value:
                    blank += 1
                    continue
                tokens = parse_feast_text(value)
                if not tokens:
                    bad += 1
                    unparseable.setdefault(value, []).append(page)
                    continue
                ok += 1
                if page.live:
                    for token in tokens:
                        if token[0] == "fixed":
                            fixed_days.add((token[1], token[2]))
                        else:
                            movable_keys.add(token[1])
            counts[label] = (ok, bad, blank)

        self.stdout.write("Feast day values (all pages, live or not)")
        for label, (ok, bad, blank) in counts.items():
            self.stdout.write(f"  {label:<6} parseable {ok:>4}   unparseable {bad:>4}   blank {blank:>4}")

        self.stdout.write("")
        self.stdout.write(f"Unparseable values ({len(unparseable)} distinct)")
        for value in sorted(unparseable, key=str.lower):
            self.stdout.write(f"  {value!r}")
            for page in unparseable[value]:
                state = "" if page.live else "  [unpublished]"
                url = reverse("wagtailadmin_pages:edit", args=[page.pk])
                self.stdout.write(f"      {page.title}{state}  {url}")

        self.stdout.write("")
        anniversaries = []
        for page in SacredSitePage.objects.order_by("title"):
            for month, day, year in parse_anniversaries(page.date_display):
                anniversaries.append((page, month, day, year))
                if page.live:
                    fixed_days.add((month, day))
        self.stdout.write(f"Sites with a parseable anniversary in date_display: {len(anniversaries)}")
        for page, month, day, year in anniversaries:
            self.stdout.write(f"  {page.title}: {date(year, month, day):%B} {day}, {year}  ({page.date_display!r})")

        # A leap year, so February 29 is one of the 366 days counted.
        year = 2028
        empty = 0
        day = date(year, 1, 1)
        while day.year == year:
            hit = (day.month, day.day) in fixed_days
            if not hit and movable_keys:
                hit = any(e.get("event_key") in movable_keys for e in celebrations_on(day))
            empty += not hit
            day += timedelta(days=1)
        self.stdout.write("")
        self.stdout.write(
            f"Days of the year with zero matched live pages: {empty} of 366 "
            f"(movable feasts placed using the {year} calendar)"
        )
