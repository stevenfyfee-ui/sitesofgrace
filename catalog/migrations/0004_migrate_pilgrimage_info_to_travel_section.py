"""Move existing `pilgrimage_info` text into a "Plan Your Visit" panel.

The old "Visiting & Pilgrimage" narrative section is retired in this release;
its text becomes an "Additional Information" travel section so nothing an
editor wrote is lost or hidden.

`pilgrimage_info` is deliberately NOT dropped here. It stays on the model for
one deploy so a rollback cannot lose text; retire it in a follow-up once the
pages have been eyeballed.

Wagtail note: this writes the live child rows directly. A page whose draft
revision predates the migration still carries an empty `travel_sections` list,
so re-publishing from that stale draft would wipe the panel. Pages edited and
published after this deploy are fine. If a page loses its panel, the text is
still in `pilgrimage_info` until the follow-up removes it.
"""

from django.db import migrations

LEGACY_KIND = "additional-information"


def forwards(apps, schema_editor):
    SacredSitePage = apps.get_model("catalog", "SacredSitePage")
    SiteTravelSection = apps.get_model("catalog", "SiteTravelSection")

    created = 0
    pages = SacredSitePage.objects.exclude(pilgrimage_info="").exclude(
        pilgrimage_info__isnull=True
    )
    for page in pages.iterator():
        if SiteTravelSection.objects.filter(page_id=page.pk, kind=LEGACY_KIND).exists():
            continue
        SiteTravelSection.objects.create(
            page_id=page.pk,
            kind=LEGACY_KIND,
            teaser="",
            body=page.pilgrimage_info,
            sort_order=0,
        )
        created += 1

    if created:
        print(f"  migrated pilgrimage_info into {created} travel section(s)")


def backwards(apps, schema_editor):
    """Remove only the rows this migration created.

    Matching on body == pilgrimage_info means a panel an editor has since
    rewritten is left alone rather than silently deleted.
    """
    SacredSitePage = apps.get_model("catalog", "SacredSitePage")
    SiteTravelSection = apps.get_model("catalog", "SiteTravelSection")

    removed = 0
    for page in SacredSitePage.objects.exclude(pilgrimage_info="").iterator():
        removed += SiteTravelSection.objects.filter(
            page_id=page.pk,
            kind=LEGACY_KIND,
            body=page.pilgrimage_info,
        ).delete()[0]

    if removed:
        print(f"  removed {removed} migrated travel section(s)")


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0003_sacredsitepage_quick_accessibility_and_more"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
