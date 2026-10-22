"""Local-only sample content for previewing the v2 pages.

    python manage.py v2_dev_sample

Refuses to run unless settings.DEBUG is True AND the database is a local
one (host db / localhost / 127.0.0.1, and not the production settings
module). Standing Rule 5: invented values live only here, and every row
this command creates has "(sample)" in its name.

Phase 1: fills the mockup's values into the local "Our Lady of Lourdes"
page -- only fields that are still blank (Rule 4) -- and creates, if
missing, a sample St. Bernadette saint (linked from Lourdes and the Nevers
convent where their principal saint is blank), two sample shrines within
40 miles for the Nearby cards, and three sample Plan Your Visit panels.
Safe to run repeatedly: a second run changes nothing.

If Lourdes has an unpublished draft (real editorial work), the draft is left
exactly as it is: the blank sample fields are written to the page row only
-- what the public page renders -- and no revision is created or published.
"""
from decimal import Decimal

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from wagtail.models import Page

from catalog.models import SacredSitePage, SaintPage, SiteTravelSection

LOCAL_DB_HOSTS = {"db", "localhost", "127.0.0.1", ""}

LOURDES_SLUG = "lourdes"
NEVERS_SLUG = "nevers"

LOURDES_FIELDS = {
    "address": "1 avenue Mgr Théas, 65100 Lourdes",
    "time_needed": "1 day minimum · 2–3 days ideal",
    "visit_length": "weekend",
    "admission": "Free",
    "reservation_required": "no",
    "accessibility_summary": "Step-free domain; free wheelchairs and helpers",
    "accessibility_level": "step-free",
    "worship_status": "active",
    "worship_note": "Daily Mass and Confession, several languages",
    "worship_schedule_url": "https://www.lourdes-france.com/",
    "recognition_year": 1862,
    "guide_level": "full",
    "account_tradition": "<p>Bernadette's own testimony, given repeatedly to clergy and civil officials "
                         "in 1858, and the accounts of witnesses present at the grotto.</p>",
    "account_church_judgment": "<p>Declared worthy of belief by the local bishop in 1862. The feast was "
                               "extended to the whole Church in 1907.</p>",
    "account_findings": "<p>Claimed cures are examined by the Lourdes Medical Bureau, founded in 1883, and "
                        "then by the bishop of the healed person. Around seventy have been declared "
                        "miraculous.</p>",
    "account_teaching": "<p>Approved private revelations are not required belief. They can help the "
                        "faithful live the Gospel; they add nothing to it.</p>",
    "prep_prayer": "<p>Our Lady of Lourdes, pray for us.<br>Saint Bernadette, pray for us.</p>",
    "prep_readings": "<ul><li>Luke 1:46–55, the Magnificat</li><li>John 5:2–9, the healing at the pool"
                     "</li><li>A short life of St. Bernadette</li><li>Bring an intention, and plan to "
                     "go to Confession</li></ul>",
    "primary_references": '<p><a href="https://www.lourdes-france.com/">Sanctuary of Our Lady of '
                          'Lourdes</a> · Diocese of Tarbes and Lourdes · <i>Norms for Proceeding in the '
                          'Discernment of Alleged Supernatural Phenomena</i> (DDF, 2024)</p>',
}

SAINT = {"slug": "st-bernadette-soubirous-sample", "title": "St. Bernadette Soubirous (sample)",
         "feast_day": "April 16"}

NEARBY = [
    {"slug": "betharram-sample", "title": "Sanctuary of Bétharram (sample)",
     "latitude": Decimal("43.095800"), "longitude": Decimal("-0.210700"),
     "summary_short": "A Marian sanctuary on the Gave de Pau, a pilgrim stop since the Middle Ages (sample)."},
    {"slug": "garaison-sample", "title": "Notre-Dame de Garaison (sample)",
     "latitude": Decimal("43.235300"), "longitude": Decimal("0.500900"),
     "summary_short": "A sixteenth-century apparition shrine in the Gascony hills (sample)."},
]
NEARBY_PARENT_SLUG = "shrines-and-basilicas"

TRAVEL = [
    ("how-long-should-i-stay", "Two nights is the honest minimum (sample)",
     "<p>Sample text: one day covers the grotto and the basilicas; two nights add the torchlight "
     "procession and the baths.</p>", False),
    ("getting-there", "Paris or Toulouse, then rail (sample)",
     "<p>Sample text: fly to Paris or Toulouse, then take the train to Lourdes.</p>", False),
    ("accessibility", "Built for pilgrims who are ill (sample)",
     "<p>Sample text: the domain is step-free, with wheelchairs and volunteer helpers.</p>", True),
]


def refuse_unless_local():
    if not settings.DEBUG:
        raise CommandError("v2_dev_sample only runs with DEBUG = True.")
    module = getattr(settings, "SETTINGS_MODULE", "") or ""
    host = connection.settings_dict.get("HOST") or ""
    if module.endswith("production") or host not in LOCAL_DB_HOSTS:
        raise CommandError(f"v2_dev_sample refuses to run against this database (host {host!r}).")


def publish(page):
    page.save_revision(log_action=True).publish()


class Command(BaseCommand):
    help = "Local-only v2 sample content (DEBUG and a local database required)."

    def handle(self, *args, **options):
        refuse_unless_local()
        lourdes = SacredSitePage.objects.filter(slug=LOURDES_SLUG).first()
        if lourdes is None:
            raise CommandError("No local SacredSitePage with slug 'lourdes'.")
        with transaction.atomic():
            saint = self._saint()
            filled = self._fill_lourdes(lourdes, saint)
            linked = self._link_nevers(saint)
            created_sites = self._nearby()
        self.stdout.write(
            f"v2_dev_sample: Lourdes fields filled: {filled or 'none'}; "
            f"Nevers linked: {linked}; sample sites created: {created_sites or 'none'}"
        )

    def _saint(self):
        saint = SaintPage.objects.filter(slug=SAINT["slug"]).first()
        if saint:
            return saint
        index = Page.objects.get(slug="saints")
        saint = SaintPage(title=SAINT["title"], slug=SAINT["slug"], feast_day=SAINT["feast_day"])
        index.add_child(instance=saint)
        publish(saint)
        return SaintPage.objects.get(pk=saint.pk)

    def _fill_lourdes(self, lourdes, saint):
        filled = [name for name, value in LOURDES_FIELDS.items() if not getattr(lourdes, name)]
        for name in filled:
            setattr(lourdes, name, LOURDES_FIELDS[name])
        if not lourdes.associated_saint_id:
            lourdes.associated_saint = saint
            filled.append("associated_saint")

        existing = {s.kind for s in lourdes.travel_sections.all()}
        sections = list(lourdes.travel_sections.all())
        for kind, teaser, body, confirm in TRAVEL:
            if kind not in existing:
                sections.append(SiteTravelSection(kind=kind, teaser=teaser, body=body, needs_confirmation=confirm))
                filled.append(f"travel:{kind}")
        if len(sections) != len(existing):
            lourdes.travel_sections = sections

        if not filled:
            return filled
        if lourdes.has_unpublished_changes:
            # Never publish over (or discard) someone's draft: write the row only.
            row_fields = [name for name in filled if not name.startswith("travel:")]
            lourdes.save(update_fields=row_fields)
            for section in sections:
                if section.pk is None:
                    section.page = lourdes
                    section.save()
            self.stdout.write("Lourdes has an unpublished draft: sample values written to the page row only; "
                              "the draft is untouched.")
        else:
            publish(lourdes)
        return filled

    def _link_nevers(self, saint):
        nevers = SacredSitePage.objects.filter(slug=NEVERS_SLUG).first()
        if nevers is None or nevers.associated_saint_id or nevers.has_unpublished_changes:
            return False
        nevers.associated_saint = saint
        publish(nevers)
        return True

    def _nearby(self):
        parent = Page.objects.get(slug=NEARBY_PARENT_SLUG)
        created = []
        for spec in NEARBY:
            if SacredSitePage.objects.filter(slug=spec["slug"]).exists():
                continue
            site = SacredSitePage(category="Shrine & Basilica", country="France", **spec)
            parent.add_child(instance=site)
            publish(site)
            created.append(spec["title"])
        return created
