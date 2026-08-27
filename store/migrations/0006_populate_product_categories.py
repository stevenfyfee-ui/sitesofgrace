"""Turn the hardcoded category strings into ProductCategory rows.

Every distinct value already stored on a product becomes a category, plus the
seven buckets the store shipped with, so nothing disappears from the store page.
"""

from django.db import migrations
from django.utils.text import slugify

SEED_CATEGORIES = [
    "Books",
    "Films",
    "Devotionals & Sacramentals",
    "Clothing",
    "Gifts",
    "Subscriptions",
    "Calendars & Planners",
]


def make_slug(name, taken):
    base = slugify(name)[:56] or "category"
    slug = base
    n = 2
    while slug in taken:
        slug = "%s-%d" % (base, n)
        n += 1
    taken.add(slug)
    return slug


def forwards(apps, schema_editor):
    ProductCategory = apps.get_model("store", "ProductCategory")
    StoreProduct = apps.get_model("store", "StoreProduct")

    names = list(SEED_CATEGORIES)
    in_use = (
        StoreProduct.objects.exclude(category="")
        .values_list("category", flat=True)
        .distinct()
    )
    for name in in_use:
        if name and name not in names:
            names.append(name)

    taken = set(ProductCategory.objects.values_list("slug", flat=True))
    by_name = {c.name: c for c in ProductCategory.objects.all()}

    for i, name in enumerate(names):
        if name in by_name:
            continue
        by_name[name] = ProductCategory.objects.create(
            name=name,
            slug=make_slug(name, taken),
            sort_order=i * 10,
            live=True,
        )

    for product in StoreProduct.objects.all():
        category = by_name.get(product.category)
        if category is not None:
            product.category_ref = category
            product.save(update_fields=["category_ref"])


def backwards(apps, schema_editor):
    StoreProduct = apps.get_model("store", "StoreProduct")
    for product in StoreProduct.objects.select_related("category_ref"):
        product.category = product.category_ref.name if product.category_ref else ""
        product.save(update_fields=["category"])


class Migration(migrations.Migration):

    dependencies = [
        ("store", "0005_productcategory"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
