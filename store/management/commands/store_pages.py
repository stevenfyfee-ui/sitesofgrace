"""Report which page is actually serving the store, and what's in it.

    python manage.py store_pages

There are two store page types in this project -- home.StorePage (the original
stub) and store.StoreIndexPage (the richer one). Both now render the product
listing, but only one of them is live at /store/. This says which.
"""

from django.core.management.base import BaseCommand

from store.models import ProductCategory, StoreIndexPage, StoreProduct


def page_models():
    models = []
    try:
        from home.models import StorePage

        models.append((StorePage, "home.StorePage"))
    except ImportError:  # pragma: no cover - the stub may have been removed
        pass
    models.append((StoreIndexPage, "store.StoreIndexPage"))
    return models


class Command(BaseCommand):
    help = "Show which store page is live and summarize the catalog behind it."

    def handle(self, *args, **options):
        rows = []
        for model, label in page_models():
            for page in model.objects.all():
                try:
                    url = page.get_url() or "(not routable)"
                except Exception:
                    url = "(not routable)"
                rows.append((label, page.pk, page.title, url, page.live))

        self.stdout.write(self.style.MIGRATE_HEADING("Store pages in the tree"))
        if not rows:
            self.stdout.write(
                self.style.WARNING(
                    "  None. Add one in the admin: Pages -> Home -> Add child page -> Store index page."
                )
            )
        for label, pk, title, url, live in rows:
            status = "live" if live else "DRAFT"
            self.stdout.write(f"  [{status:5}] {label:22} id={pk:<4} {url:<28} {title}")

        if len(rows) > 1:
            self.stdout.write("")
            self.stdout.write(
                self.style.WARNING(
                    "  More than one store page exists. Whichever URL is in your main menu is the\n"
                    "  one visitors see; the other can be unpublished or deleted in the admin."
                )
            )

        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING("Catalog"))
        total = StoreProduct.objects.count()
        live_count = StoreProduct.objects.filter(live=True).count()
        self.stdout.write(f"  Products: {live_count} live / {total} total")
        uncategorized = StoreProduct.objects.filter(category__isnull=True).count()
        if uncategorized:
            self.stdout.write(
                self.style.WARNING(
                    f"  {uncategorized} product(s) have no category and won't appear under any bucket."
                )
            )
        for category in ProductCategory.objects.all():
            flag = "" if category.live else "  (hidden)"
            self.stdout.write(
                f"    {category.name:32} slug={category.slug:26} "
                f"{category.product_count()} live product(s){flag}"
            )
        if not ProductCategory.objects.exists():
            self.stdout.write(
                self.style.WARNING("  No categories yet -- add them under Store -> Categories.")
            )
