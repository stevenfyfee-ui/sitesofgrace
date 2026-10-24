"""Make /contact/ the real Contact page (GO-LIVE step 3), as one command.

    python manage.py swap_contact_page --dry-run
    python manage.py swap_contact_page

If a live ContactPage already exists, nothing happens. Otherwise, under the
default site's home page:
  - the existing /contact/ StandardPage (if any) is unpublished and its slug
    changed to "contact-old" (a draft revision records the new slug, so
    publishing that draft later can't take /contact/ back);
  - a draft ContactPage at /contact/ is published, or a new one is created
    with its defaults and published.
Anything else at /contact/, or a page already at /contact-old/, stops the
command without changing anything.
"""
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from wagtail.models import Page, Site

from home.models import ContactPage, StandardPage

OLD_SLUG = "contact-old"


class Command(BaseCommand):
    help = "Unpublish the old /contact/ StandardPage (slug contact-old) and publish a ContactPage."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Say what would happen; change nothing.")

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        say = self.stdout.write
        prefix = "DRY RUN -- nothing will be changed. " if dry_run else ""

        if ContactPage.objects.live().exists():
            page = ContactPage.objects.live().first()
            say(f"{prefix}Nothing to do: a live ContactPage already exists at {page.url_path}.")
            return

        site = Site.objects.filter(is_default_site=True).select_related("root_page").first()
        if site is None:
            raise CommandError("No default Wagtail site.")
        home = site.root_page
        current = Page.objects.child_of(home).filter(slug="contact").first()
        if current is not None:
            current = current.specific
        if current is not None and not isinstance(current, (StandardPage, ContactPage)):
            raise CommandError(f"/contact/ is a {type(current).__name__}, not a StandardPage. Nothing changed.")
        if isinstance(current, StandardPage) and Page.objects.child_of(home).filter(slug=OLD_SLUG).exists():
            raise CommandError(f"A page already has the slug {OLD_SLUG!r}. Nothing changed.")

        steps = []
        if isinstance(current, StandardPage):
            steps.append(f"unpublish the StandardPage at /contact/ (id {current.pk}) and change its slug to {OLD_SLUG}")
        draft = current if isinstance(current, ContactPage) else ContactPage.objects.child_of(home).first()
        if draft is not None:
            steps.append(f"publish the existing ContactPage draft (id {draft.pk}) at /contact/")
        else:
            steps.append("create a ContactPage at /contact/ with its defaults and publish it")
        for step in steps:
            say(f"{prefix}{'Would' if dry_run else 'Will'} {step}.")
        if dry_run:
            return

        with transaction.atomic():
            if isinstance(current, StandardPage):
                if current.live:
                    current.unpublish(log_action=True)
                current.refresh_from_db()
                current.slug = OLD_SLUG
                current.save()
                current.save_revision(log_action=True)
            if draft is None:
                draft = ContactPage(title="Contact", slug="contact", live=False)
                home.add_child(instance=draft)
            elif draft.slug != "contact":
                draft.slug = "contact"
                draft.save()
            draft.save_revision(log_action=True).publish()
        live = ContactPage.objects.live().get(pk=draft.pk)
        say(self.style.SUCCESS(f"Done: ContactPage {live.pk} is live at {live.url_path}."))
