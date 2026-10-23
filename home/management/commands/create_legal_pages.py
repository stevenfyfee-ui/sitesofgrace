"""Create the ten legal pages as unpublished drafts under the home page.

    python manage.py create_legal_pages [--update] [--effective YYYY-MM-DD]

Reads legal/content/<slug>.md: line 1 is "# Title", the rest is the body in
a small Markdown subset (home/legal.py: markdown_to_richtext). Nothing here
ever publishes: an editor reviews each draft and publishes it in the admin,
once Settings > Legal details is filled in.

  - A page already at a slug is left alone, unless --update is given; then
    a new draft revision is saved and the live version is untouched.
  - Draft LegalPages at the old slugs "privacy" and "terms" are moved to
    "privacy-policy" and "terms-of-use". If either is live, nothing is
    changed and the command stops.
  - Permanent redirects /privacy/ and /terms/ point at the new pages.
"""
import datetime

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from wagtail.models import Page, Site

from home import legal
from home.models import HomePage, LegalPage

CONTENT_DIR = settings.BASE_DIR / "legal" / "content"
OLD_SLUGS = {"privacy": "privacy-policy", "terms": "terms-of-use"}


class Command(BaseCommand):
    help = "Create the legal pages as unpublished drafts from legal/content/*.md."

    def add_arguments(self, parser):
        parser.add_argument(
            "--update", action="store_true",
            help="Save a new draft revision for pages that already exist.",
        )
        parser.add_argument(
            "--effective", metavar="YYYY-MM-DD",
            help="Effective date for every page (default: today).",
        )

    def handle(self, *args, **options):
        effective = self._effective_date(options["effective"])
        home = self._home_page()
        content = self._read_content()

        created, updated, skipped = [], [], []
        with transaction.atomic():
            self._move_old_slugs(home)
            for slug in legal.LEGAL_SLUGS:
                title, body_md = content[slug]
                fields = {
                    "title": title,
                    "effective_date": effective,
                    "body": legal.markdown_to_richtext(body_md),
                    "search_description": legal.first_paragraph_text(body_md),
                }
                existing = Page.objects.child_of(home).filter(slug=slug).first()
                if existing is None:
                    page = LegalPage(slug=slug, live=False, **fields)
                    home.add_child(instance=page)
                    page.save_revision()
                    created.append(slug)
                elif not options["update"]:
                    skipped.append(slug)
                else:
                    self._update(existing, fields)
                    updated.append(slug)
            redirects = self._redirects()

        for label, slugs in (("Created (draft)", created), ("Updated (new draft revision)", updated),
                             ("Skipped (already exists)", skipped)):
            self.stdout.write(f"{label}: {', '.join(slugs) if slugs else 'none'}")
        if redirects:
            self.stdout.write(f"Redirects: {', '.join(redirects)}")
        self.stdout.write(self.style.SUCCESS(
            "Nothing was published. Review the drafts in the admin and publish them there."
        ))

    def _effective_date(self, raw):
        if not raw:
            return datetime.date.today()
        try:
            return datetime.date.fromisoformat(raw)
        except ValueError:
            raise CommandError(f"--effective must be YYYY-MM-DD, not {raw!r}.")

    def _home_page(self):
        site = Site.objects.filter(is_default_site=True).select_related("root_page").first()
        root = site.root_page.specific if site else None
        if not isinstance(root, HomePage):
            raise CommandError("The default site's root page isn't a HomePage.")
        return root

    def _read_content(self):
        content = {}
        for slug in legal.LEGAL_SLUGS:
            path = CONTENT_DIR / f"{slug}.md"
            if not path.exists():
                raise CommandError(f"Missing {path}.")
            title, body = legal.parse_content_file(path.read_text(encoding="utf-8"))
            legal.tokens_in(body)  # raises on an unknown token
            if legal.TOKEN_RE.search(title):
                raise CommandError(f"{path.name}: the title can't contain a token.")
            content[slug] = (title, body)
        return content

    def _move_old_slugs(self, home):
        for old, new in OLD_SLUGS.items():
            page = Page.objects.child_of(home).filter(slug=old).first()
            if page is None:
                continue
            if page.live:
                raise CommandError(
                    f'The page at "/{old}/" is live. Nothing was changed. Unpublish it, or move '
                    f'it to "{new}" yourself, then run this again.'
                )
            if not isinstance(page.specific, LegalPage):
                raise CommandError(
                    f'The draft at "/{old}/" is a {page.specific_class.__name__}, not a LegalPage. '
                    "Nothing was changed."
                )
            if Page.objects.child_of(home).filter(slug=new).exists():
                raise CommandError(f'Both "/{old}/" and "/{new}/" exist. Nothing was changed.')
            page = page.specific
            page.slug = new
            page.save()
            page.save_revision()
            self.stdout.write(f'Moved draft "{old}" to "{new}".')

    def _update(self, page, fields):
        page = page.specific
        if not isinstance(page, LegalPage):
            raise CommandError(
                f'"/{page.slug}/" is a {type(page).__name__}, not a LegalPage. Nothing was changed.'
            )
        draft = page.get_latest_revision_as_object()
        for name, value in fields.items():
            setattr(draft, name, value)
        if not page.live:
            draft.save()
        # On a live page, save_revision() writes only the revision and the
        # page's draft bookkeeping, so what visitors see doesn't change.
        draft.save_revision()

    def _redirects(self):
        if "wagtail.contrib.redirects" not in settings.INSTALLED_APPS:
            return []
        from wagtail.contrib.redirects.models import Redirect

        made = []
        for old, new in OLD_SLUGS.items():
            target = LegalPage.objects.filter(slug=new).first()
            if target is None:
                continue
            old_path = Redirect.normalise_path(f"/{old}/")
            _, was_created = Redirect.objects.update_or_create(
                old_path=old_path, site=None,
                defaults={"redirect_page": target, "redirect_link": "", "is_permanent": True},
            )
            made.append(f"/{old}/ -> /{new}/" + (" (created)" if was_created else " (kept)"))
        return made
