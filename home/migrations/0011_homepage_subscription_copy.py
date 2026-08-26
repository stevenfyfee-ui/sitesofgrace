"""Bring the existing HomePage row in line with the new bucket layout.

Schema defaults only apply to columns as they are added, so the one live
HomePage still carries the old "Featured Sacred Sites" heading and has no
subscription bullets. Both are fixed here, and only where the editor has not
already customised them.
"""
from django.db import migrations

OLD_SITES_HEADING = "Featured Sacred Sites"
NEW_SITES_HEADING = "Featured Sites and Saints"

DEFAULT_BULLETS = [
    "A blessed rosary or medal from the featured shrine",
    "Holy water or blessed oil in a keepsake vial",
    "A book or devotional tied to the season's site or saint",
    "The Pilgrim Letter, our quarterly guide to praying with the place",
]


def forwards(apps, schema_editor):
    HomePage = apps.get_model("home", "HomePage")
    SubscriptionBullet = apps.get_model("home", "SubscriptionBullet")

    HomePage.objects.filter(featured_sites_heading=OLD_SITES_HEADING).update(
        featured_sites_heading=NEW_SITES_HEADING
    )

    for home_page in HomePage.objects.all():
        if SubscriptionBullet.objects.filter(page=home_page).exists():
            continue
        for index, text in enumerate(DEFAULT_BULLETS):
            SubscriptionBullet.objects.create(page=home_page, text=text, sort_order=index)


def backwards(apps, schema_editor):
    HomePage = apps.get_model("home", "HomePage")
    SubscriptionBullet = apps.get_model("home", "SubscriptionBullet")

    HomePage.objects.filter(featured_sites_heading=NEW_SITES_HEADING).update(
        featured_sites_heading=OLD_SITES_HEADING
    )
    SubscriptionBullet.objects.filter(text__in=DEFAULT_BULLETS).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("home", "0010_remove_homepage_featured_saints_heading_and_more"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
