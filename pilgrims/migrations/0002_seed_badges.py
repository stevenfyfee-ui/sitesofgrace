"""Seed the three placeholder badges so the profile shelf isn't empty in dev.

Nothing awards these yet — that logic arrives in a later phase.
"""
from django.db import migrations

PLACEHOLDER_BADGES = [
    {"name": "First Pilgrimage", "slug": "first-pilgrimage", "sort_order": 1},
    {"name": "Marian Pilgrim", "slug": "marian-pilgrim", "sort_order": 2},
    {"name": "Eucharistic Pilgrim", "slug": "eucharistic-pilgrim", "sort_order": 3},
]


def seed_badges(apps, schema_editor):
    Badge = apps.get_model("pilgrims", "Badge")
    for data in PLACEHOLDER_BADGES:
        Badge.objects.get_or_create(slug=data["slug"], defaults=data)


def remove_badges(apps, schema_editor):
    Badge = apps.get_model("pilgrims", "Badge")
    Badge.objects.filter(slug__in=[data["slug"] for data in PLACEHOLDER_BADGES]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("pilgrims", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_badges, remove_badges),
    ]
