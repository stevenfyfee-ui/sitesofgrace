"""One-off content fixes, October 2026 (v2 go-live, Part B).

    python manage.py apply_content_fixes_2026_10 --dry-run
    python manage.py apply_content_fixes_2026_10
    python manage.py apply_content_fixes_2026_10 --verify
    python manage.py apply_content_fixes_2026_10 --akita revert --dry-run   (then without --dry-run)

  1115 Basilica of St. Francis, Assisi   location_link -> https://basilica.sanfrancesco.org/
  1153 Brussels                          the_story: three paragraphs, unsupported windows
                                         sentence out, April 2026 plaque paragraph in
  1101 Medjugorje                        coordinates -> 43.19056, 17.6775
  1094 Knock                             coordinates -> 53.79231, -8.91956 (status untouched)
  1263 St. Paul Outside the Walls        duplicate of 1139: unpublished, with a permanent
       (Saints & Tombs)                  redirect from its URL to 1139
  1102 Akita (only with --akita)         its one pending draft: "publish" it, or "revert"
                                         (publish the live version as a revision, dropping
                                         the draft)

Every change is checked against the value it replaces: a field already at
its new value is "already correct", a field at the expected old value is
changed, and anything else is a conflict that skips the page (Standing
Rule 4). A page that isn't live or has an unpublished draft is skipped and
reported. Each changed page gets one new revision, saved and published as
--user (default: the only active superuser), so it shows in page history.
1263 is unpublished only if nothing points to it: no links in other pages'
text, no menu items, and no visits, photos, posts, tour stops, tour
interest, hub rows or day trips. Running it again changes nothing.
"""
import json
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.utils.html import strip_tags
from wagtail.contrib.redirects.models import Redirect
from wagtail.models import Page

from catalog.models import SacredSitePage

BRUSSELS_OLD = (
    "<p>The so-called Sacrament of Miracle of Brussels concerns consecrated hosts once venerated in the Cathedral of St. Michael and St. Gudula. According to the late-medieval account, hosts stolen from a Brussels church in 1370 were profaned and were said to have bled when pierced \u2014 an event then celebrated as a miracle and commemorated in the cathedral for centuries, including in a famous series of sixteenth-century stained-glass windows.\n"
    "\n"
    "The historical reality behind the legend is tragic. The accusation of desecration was directed against the Jewish community of Brussels, and several Jews were tortured and executed in 1370. Modern historical scholarship regards the episode as a host-desecration libel \u2014 one of the many false accusations leveled against Jewish communities in medieval Europe \u2014 rather than a genuine Eucharistic miracle.\n"
    "\n"
    "The Church has formally distanced itself from the cult. In the years after the Second Vatican Council and its declaration Nostra Aetate, the Archdiocese of Mechelen-Brussels ended promotion of the devotion, and a plaque installed in the cathedral in 1977 acknowledged the tendentious nature of the accusation and the legendary character of the miracle. In April 2026, Archbishop Luc Terlinden dedicated new plaques in the cathedral explicitly acknowledging the antisemitic nature of the legend and apologizing for the persecution it caused.\n"
    "\n"
    "The stained-glass windows remain in the cathedral as artifacts of history, now presented with explanatory context. For Catholics, the story of the Brussels 'miracle' is not an object of devotion but a call to truth and repentance: faith in the Real Presence of Christ in the Eucharist rests on the words of Christ and the teaching of the Church, never on legends born of injustice against the Jewish people.</p>"
)

BRUSSELS_NEW = (
    "<p>The so-called Sacrament of Miracle of Brussels concerns consecrated hosts once venerated in the "
    "Cathedral of St. Michael and St. Gudula. According to the late-medieval account, hosts stolen from a "
    "Brussels church in 1370 were profaned and were said to have bled when pierced — an event then "
    "celebrated as a miracle and commemorated in the cathedral for centuries, including in a famous series "
    "of sixteenth-century stained-glass windows. The historical reality behind the legend is tragic. The "
    "accusation of desecration was directed against the Jewish community of Brussels, and several Jews "
    "were tortured and executed in 1370. Modern historical scholarship regards the episode as a "
    "host-desecration libel — one of the many false accusations leveled against Jewish communities in "
    "medieval Europe — rather than a genuine Eucharistic miracle.</p>"
    "<p>The Church has formally distanced itself from the cult. In the years after the Second Vatican "
    "Council and its declaration Nostra Aetate, the Archdiocese of Mechelen-Brussels ended promotion of "
    "the devotion, and a plaque installed in the cathedral in 1977 acknowledged the tendentious nature of "
    "the accusation and the legendary character of the miracle.</p>"
    "<p>In April 2026, Archbishop Luc Terlinden unveiled a new plaque in the cathedral, written together "
    "with representatives of Brussels' Jewish community. It replaces the 1977 plaque, clearly acknowledges "
    "the antisemitic nature of the legend, and apologizes for the persecution it caused. The Church has "
    "also asked that the \"miracle\" no longer be publicly venerated. For Catholics, the story of the "
    "Brussels 'miracle' is not an object of devotion but a call to truth and repentance: faith in the "
    "Real Presence of Christ in the Eucharist rests on the words of Christ and the teaching of the Church, "
    "never on legends born of injustice against the Jewish people.</p>"
)

# (page id, title, {field: (expected old value, new value)})
FIELD_FIXES = [
    (1115, "Basilica of St. Francis of Assisi", {
        "location_link": ("https://www.sanfrancescoassisi.org/html/ita/index.php", "https://basilica.sanfrancesco.org/"),
    }),
    (1153, "Eucharistic Miracle of Brussels", {
        "the_story": (BRUSSELS_OLD, BRUSSELS_NEW),
    }),
    (1101, "Our Lady of Medjugorje (Queen of Peace)", {
        "latitude": (Decimal("43.190800"), Decimal("43.190560")),
        "longitude": (Decimal("17.678900"), Decimal("17.677500")),
    }),
    (1094, "Our Lady of Knock", {
        "latitude": (Decimal("53.790600"), Decimal("53.792310")),
        "longitude": (Decimal("-8.921100"), Decimal("-8.919560")),
    }),
]

DUPLICATE = (1263, "Basilica of St. Paul Outside the Walls")
DUPLICATE_OF = (1139, "Basilica of St. Paul Outside the Walls")
AKITA = (1102, "Our Lady of Akita")

# Relations that mean someone or something still uses 1263. Its own travel
# sections are its content, not a reference.
OWN_RELATIONS = {"travel_sections", "map_points", "lodgings"}
# Wagtail's own bookkeeping (history, permissions, search) isn't a use of the page.
BOOKKEEPING_APPS = {"wagtailcore", "wagtailadmin", "wagtailsearch"}


class Skip(Exception):
    pass


def old_path(page):
    """The page's public path, as a redirect's old_path ("/explore/.../slug")."""
    return Redirect.normalise_path(page.get_url_parts()[2])


def plain_paragraphs(html):
    return [" ".join(strip_tags(part).split()) for part in str(html or "").replace("</p>", "</p>\n\n").split("\n\n")
            if strip_tags(part).strip()]


class Command(BaseCommand):
    help = "Apply the October 2026 content fixes (Assisi link, Brussels text, coordinates, 1263, Akita)."

    def add_arguments(self, parser):
        mode = parser.add_mutually_exclusive_group()
        mode.add_argument("--dry-run", action="store_true", help="Report what would change; write nothing.")
        mode.add_argument("--verify", action="store_true", help="Check every fix is in place; write nothing.")
        parser.add_argument("--user", help="Username for the revisions (default: the only active superuser).")
        parser.add_argument("--akita", choices=["publish", "revert"],
                            help="Resolve 1102's pending draft (only this, nothing else, runs).")

    # ------------------------------------------------------------- helpers

    def _user(self, username):
        users = get_user_model().objects.filter(is_active=True)
        if username:
            user = users.filter(username=username).first()
            if user is None:
                raise CommandError(f"No active user {username!r}.")
            return user
        supers = list(users.filter(is_superuser=True))
        if len(supers) != 1:
            raise CommandError(f"{len(supers)} active superusers; pass --user.")
        return supers[0]

    def _page(self, pk, title):
        page = SacredSitePage.objects.filter(pk=pk).first()
        if page is None:
            raise Skip("page not found")
        if page.title != title:
            raise Skip(f"title is {page.title!r}, expected {title!r}")
        return page

    def _publishable(self, page):
        if not page.live:
            raise Skip("page is not live")
        if page.has_unpublished_changes:
            raise Skip("page has unpublished changes (draft)")

    def _references(self, page):
        """[(what, count)] of things that still point at this page."""
        found = []
        for model in (SacredSitePage, Page):
            for rel in model._meta.related_objects:
                name = rel.get_accessor_name()
                if (name in OWN_RELATIONS or rel.parent_link or rel.one_to_one
                        or rel.related_model._meta.app_label in BOOKKEEPING_APPS):
                    continue
                if rel.many_to_many:
                    count = getattr(page, name).count()
                else:
                    count = rel.related_model.objects.filter(**{rel.field.name: page.pk}).count()
                if count:
                    found.append((f"{rel.related_model._meta.label}.{rel.field.name}", count))
        needles = [f'id="{page.pk}"', page.url_path]
        for other in Page.objects.live().exclude(pk=page.pk).specific().iterator():
            for field in other._meta.concrete_fields:
                if field.is_relation:
                    continue
                value = getattr(other, field.name, None)
                if value is None or isinstance(value, (bool, int, float, Decimal)):
                    continue
                text = json.dumps(list(value.raw_data), cls=DjangoJSONEncoder) if hasattr(value, "raw_data") else str(value)
                if field.name != "url_path" and any(n in text for n in needles):
                    found.append((f"link in {other.pk} {other.title} ({field.name})", 1))
        return found

    # ---------------------------------------------------------------- fixes

    def _field_fix(self, pk, title, fields, user, dry_run, w):
        page = self._page(pk, title)
        changes, done = {}, 0
        for name, (old, new) in fields.items():
            current = getattr(page, name)
            if current == new:
                done += 1
            elif current == old:
                changes[name] = new
            else:
                raise Skip(f"{name} is neither the expected old value nor the new one (conflict)")
        if not changes:
            w(f"  already correct {pk} {title}")
            return "correct"
        self._publishable(page)
        w(f"  {'would change' if dry_run else 'changed'} {pk} {title}: {', '.join(sorted(changes))}")
        for name, new in changes.items():
            old = fields[name][0]
            if name == "the_story":
                w("    BEFORE:")
                for n, para in enumerate(plain_paragraphs(old), 1):
                    w(f"      [{n}] {para}")
                w("    AFTER:")
                for n, para in enumerate(plain_paragraphs(new), 1):
                    w(f"      [{n}] {para}")
            else:
                w(f"    {name}: {old} -> {new}")
        if not dry_run:
            with transaction.atomic():
                for name, new in changes.items():
                    setattr(page, name, new)
                page.save_revision(user=user, log_action=True).publish(user=user)
        return "changed"

    def _duplicate(self, user, dry_run, w):
        page = self._page(*DUPLICATE)
        target = self._page(*DUPLICATE_OF)
        if not target.live:
            raise Skip(f"redirect target {target.pk} is not live")
        path = old_path(page)
        existing = Redirect.objects.filter(old_path=path).first()
        if not page.live and existing and existing.redirect_page_id == target.pk and existing.is_permanent:
            w(f"  already correct {page.pk}: not live; {path} -> 301 {target.pk}")
            return "correct"
        if existing and existing.redirect_page_id != target.pk:
            raise Skip(f"a redirect from {path} already exists to something else (conflict)")
        self._publishable(page)
        refs = self._references(page)
        if refs:
            raise Skip("still referenced: " + "; ".join(f"{what} x{n}" for what, n in refs))
        w(f"  {'would unpublish' if dry_run else 'unpublished'} {page.pk} {page.title} ({page.url}); "
          f"nothing points to it")
        w(f"    redirect {path} -> 301 {target.pk} {target.title} ({target.url})")
        if not dry_run:
            with transaction.atomic():
                page.unpublish(user=user, log_action=True)
                if existing is None:
                    # All sites, so it works on the app address as well as the domain.
                    Redirect.add_redirect(path, redirect_to=target, is_permanent=True, site=None)
        return "changed"

    def _akita(self, choice, user, dry_run, w):
        page = self._page(*AKITA)
        if not page.live:
            raise Skip("page is not live")
        if not page.has_unpublished_changes:
            w(f"  already resolved {page.pk} {page.title}: no pending draft")
            return
        draft = page.latest_revision
        w(f"  {'would ' if dry_run else ''}{choice} {page.pk} {page.title}: draft revision {draft.pk} "
          f"of {draft.created_at:%Y-%m-%d}")
        if dry_run:
            return
        with transaction.atomic():
            if choice == "publish":
                draft.publish(user=user)
            else:
                # The page row is what's live; save it as a revision and
                # publish that, so the draft is superseded and history shows it.
                SacredSitePage.objects.get(pk=page.pk).save_revision(user=user, log_action=True).publish(user=user)

    # --------------------------------------------------------------- verify

    def _verify(self, w):
        problems = []
        for pk, title, fields in FIELD_FIXES:
            page = SacredSitePage.objects.filter(pk=pk).first()
            if page is None or page.title != title:
                problems.append(f"{pk}: page missing or retitled")
                continue
            for name, (_, new) in fields.items():
                if getattr(page, name) != new:
                    problems.append(f"{pk} {title}: {name} is not the new value")
            if not page.live or page.has_unpublished_changes:
                problems.append(f"{pk} {title}: not live, or has a draft")
        page = SacredSitePage.objects.get(pk=DUPLICATE[0])
        path = old_path(page)
        redirect = Redirect.objects.filter(old_path=path).first()
        if page.live:
            problems.append(f"{page.pk}: still live")
        if not redirect or redirect.redirect_page_id != DUPLICATE_OF[0] or not redirect.is_permanent:
            problems.append(f"{page.pk}: no permanent redirect from {path} to {DUPLICATE_OF[0]}")
        w(f"Verify: {len(FIELD_FIXES) + 1} fixes checked, {len(problems)} problem(s)")
        for problem in problems:
            w(f"  - {problem}")
        if problems:
            raise CommandError(f"{len(problems)} fix(es) not in place.")

    # ----------------------------------------------------------------- main

    def handle(self, *args, **options):
        w = self.stdout.write
        if options["verify"]:
            return self._verify(w)
        dry_run = options["dry_run"]
        user = self._user(options["user"])
        w(("DRY RUN -- nothing will be written. " if dry_run else "") + f"Revisions by {user.get_username()}")
        if options["akita"]:
            try:
                self._akita(options["akita"], user, dry_run, w)
            except Skip as skip:
                w(f"  skipped {AKITA[0]}: {skip}")
            return
        totals, skipped = {"changed": 0, "correct": 0}, []
        jobs = [(pk, title, lambda pk=pk, title=title, fields=fields:
                 self._field_fix(pk, title, fields, user, dry_run, w)) for pk, title, fields in FIELD_FIXES]
        jobs.append((DUPLICATE[0], DUPLICATE[1], lambda: self._duplicate(user, dry_run, w)))
        for pk, title, job in jobs:
            try:
                totals[job()] += 1
            except Skip as skip:
                skipped.append((pk, title, str(skip)))
        w("")
        w(f"{'Would change' if dry_run else 'Changed'}: {totals['changed']}")
        w(f"Already correct: {totals['correct']}")
        w(f"Skipped: {len(skipped)}")
        for pk, title, reason in skipped:
            w(f"  - {pk} {title}: {reason}")
