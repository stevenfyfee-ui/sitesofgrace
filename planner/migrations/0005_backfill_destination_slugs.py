"""Fill DestinationCost.slug from city for rows that don't have one.

Never overwrites a slug that is already set. The overrides are copied here
(not imported from planner.models) so this migration keeps working if the
model's list changes later.
"""
from django.db import migrations
from django.utils.text import slugify

SLUG_OVERRIDES = {
    "Mexico City (Guadalupe)": "mexico-city",
}


def backfill_slugs(apps, schema_editor):
    DestinationCost = apps.get_model("planner", "DestinationCost")
    taken = set(DestinationCost.objects.exclude(slug__isnull=True).exclude(slug="").values_list("slug", flat=True))
    for dest in DestinationCost.objects.filter(slug__isnull=True) | DestinationCost.objects.filter(slug=""):
        base = SLUG_OVERRIDES.get(dest.city) or slugify(dest.city) or f"destination-{dest.pk}"
        slug, n = base, 2
        while slug in taken:
            slug, n = f"{base}-{n}", n + 1
        taken.add(slug)
        dest.slug = slug
        dest.save(update_fields=["slug"])


class Migration(migrations.Migration):

    dependencies = [
        ("planner", "0004_planner_v2_models"),
    ]

    operations = [
        migrations.RunPython(backfill_slugs, migrations.RunPython.noop),
    ]
