"""Create the Future Saints pages that are missing, as unpublished drafts.

    python manage.py create_future_saints_tree

/future-saints/ goes under the site's home page, with saints/, marian-apparitions/,
eucharistic-miracles/, holy-land/ and california-missions/ under it. The home
page's subject cards are linked to the new indexes by object, never by page ID
(local and production IDs differ). Nothing is published: an editor reviews
and publishes in the admin, and the pages still 404 unless SOG_FUTURE_SAINTS
allows the request.

Also sets up review: a "Future Saints reviewers" group (no members; it can
edit and publish only inside /future-saints/) and a "Future Saints editorial
review" workflow on the subtree, using Wagtail's built-in moderation.

Idempotent: it creates only what's missing (the home page, any of the five
indexes, and the World Discovery Map at /future-saints/map/), each as an
unpublished draft, and links a new index to its homepage card only if that card
is empty. Existing pages are never changed. A run with nothing missing writes
nothing. The review group and workflow are set up only with a new home page.

    python manage.py create_future_saints_tree --dry-run

makes the same checks, prints each page it would create (type, slug, path,
parent) and the review setup, and writes nothing.
"""
from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from wagtail.models import GroupApprovalTask, GroupPagePermission, Page, Site, Workflow, WorkflowPage, WorkflowTask

from future_saints.models import FutureSaintsHomePage, FutureSaintsIndexPage, WorldMapPage
from home.models import HomePage

HOME_SLUG = "future-saints"
MAP_SLUG = "map"
MAP_TITLE = "World Discovery Map"
REVIEW_GROUP = "Future Saints reviewers"
WORKFLOW_NAME = "Future Saints editorial review"

# (content_kind, slug, title, accent); the home page card that links to it.
INDEXES = [
    ("saint", "saints", "Saints", "sage", "card_1_page"),
    ("marian_apparition", "marian-apparitions", "Mary & Apparitions", "blue", "card_2_page"),
    ("eucharistic_miracle", "eucharistic-miracles", "Eucharistic Miracles", "gold", "card_3_page"),
    ("california_mission", "california-missions", "California Missions", "terracotta", "card_4_page"),
    ("holy_land", "holy-land", "The Holy Land", "sand", "holy_land_page"),
]


class Command(BaseCommand):
    help = "Create the missing Future Saints pages (home, five indexes, World Discovery Map) as unpublished drafts."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Print the pages it would create (type, slug, path, parent) and write nothing.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        fs_home = FutureSaintsHomePage.objects.first()
        if fs_home is None:
            home = self._home_page()
            if Page.objects.child_of(home).filter(slug=HOME_SLUG).exists():
                raise CommandError(f"Another page already uses the slug {HOME_SLUG!r} under the home page.")
        if dry_run:
            self.stdout.write("Dry run: nothing will be written.")

        with transaction.atomic():
            created, workflow_note = [], ""
            if fs_home is None:
                fs_path = f"{home.url_path}{HOME_SLUG}/"
                created.append(f"FutureSaintsHomePage  title 'Future Saints'  slug '{HOME_SLUG}'  path {fs_path}  "
                               f"parent {home.url_path} ({home.title}, {type(home).__name__})")
                if not dry_run:
                    fs_home = FutureSaintsHomePage(title="Future Saints", slug=HOME_SLUG, live=False, show_in_menus=False)
                    home.add_child(instance=fs_home)
                    fs_home.save_revision()
            else:
                fs_path = fs_home.url_path
            children = set(Page.objects.child_of(fs_home).values_list("slug", flat=True)) if fs_home and fs_home.pk else set()

            linked = False
            for kind, slug, title, accent, card_field in INDEXES:
                if slug in children or (fs_home and fs_home.pk and
                                        FutureSaintsIndexPage.objects.child_of(fs_home).filter(content_kind=kind).exists()):
                    continue
                card_note = f"  linked from {card_field}" if not (fs_home and getattr(fs_home, f"{card_field}_id", None)) else ""
                created.append(f"FutureSaintsIndexPage  title '{title}'  slug '{slug}'  path {fs_path}{slug}/  "
                               f"parent {fs_path}  content_kind {kind}{card_note}")
                if not dry_run:
                    index = FutureSaintsIndexPage(title=title, slug=slug, content_kind=kind, accent=accent,
                                                  live=False, show_in_menus=False)
                    fs_home.add_child(instance=index)
                    index.save_revision()
                    if getattr(fs_home, f"{card_field}_id", None) is None:
                        setattr(fs_home, card_field, index)
                        linked = True

            if MAP_SLUG not in children and not (fs_home and fs_home.pk and WorldMapPage.objects.child_of(fs_home).exists()):
                created.append(f"WorldMapPage  title '{MAP_TITLE}'  slug '{MAP_SLUG}'  path {fs_path}{MAP_SLUG}/  parent {fs_path}")
                if not dry_run:
                    world = WorldMapPage(title=MAP_TITLE, slug=MAP_SLUG, live=False, show_in_menus=False)
                    fs_home.add_child(instance=world)
                    world.save_revision()

            if not dry_run and linked:
                fs_home.save()
                fs_home.save_revision()
            if any(line.startswith("FutureSaintsHomePage") for line in created):
                if dry_run:
                    group_exists = Group.objects.filter(name=REVIEW_GROUP).exists()
                    workflow_exists = Workflow.objects.filter(name=WORKFLOW_NAME).exists()
                    workflow_note = (
                        f'Would set up review: group "{REVIEW_GROUP}" ({"exists" if group_exists else "would be created, no members"}), '
                        f'workflow "{WORKFLOW_NAME}" ({"exists" if workflow_exists else "would be created"}) on {fs_path}.')
                else:
                    workflow_note = self._review_workflow(fs_home)

        if not created:
            self.stdout.write(f"Nothing to create: the Future Saints pages under {fs_path} all exist. Nothing was changed.")
            return
        for line in created:
            self.stdout.write(f"{'Would create' if dry_run else 'Created'} (draft): {line}")
        if workflow_note:
            self.stdout.write(workflow_note)
        if dry_run:
            self.stdout.write("Run again without --dry-run to create these drafts.")
            return
        self.stdout.write(self.style.SUCCESS(
            "Nothing was published. Review the drafts in the admin and publish them there; "
            "they still 404 unless SOG_FUTURE_SAINTS allows the request."
        ))

    def _home_page(self):
        site = Site.objects.filter(is_default_site=True).first()
        if site is None:
            raise CommandError("No default Site is configured.")
        root = site.root_page.specific
        if not isinstance(root, HomePage):
            raise CommandError(f"The default site's root page is a {type(root).__name__}, not a HomePage.")
        return root

    def _review_workflow(self, fs_home):
        group, group_created = Group.objects.get_or_create(name=REVIEW_GROUP)
        if group_created:
            group.permissions.add(Permission.objects.get(content_type__app_label="wagtailadmin", codename="access_admin"))
            for codename in ("add_page", "change_page", "publish_page"):
                GroupPagePermission.objects.get_or_create(
                    group=group, page=fs_home,
                    permission=Permission.objects.get(content_type__app_label="wagtailcore", codename=codename),
                )

        workflow, _ = Workflow.objects.get_or_create(name=WORKFLOW_NAME)
        if not workflow.workflow_tasks.exists():
            task = GroupApprovalTask.objects.create(name=f"{REVIEW_GROUP} approval")
            task.groups.set([group])
            WorkflowTask.objects.create(workflow=workflow, task=task, sort_order=0)
        WorkflowPage.objects.update_or_create(page=fs_home, defaults={"workflow": workflow})
        return (f'Review: group "{REVIEW_GROUP}" ({"created, no members" if group_created else "already existed"}), '
                f'workflow "{WORKFLOW_NAME}" on {fs_home.url_path}.')
