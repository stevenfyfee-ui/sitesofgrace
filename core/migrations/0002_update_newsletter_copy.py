from django.db import migrations

OLD_TEXT = "Sacred-site spotlights, Catholic teaching, and pilgrimage ideas each week."
NEW_TEXT = "Receive sacred site spotlights, Catholic teaching, pilgrimage ideas, and prayers each week."


def update_copy(apps, schema_editor):
    SiteSettings = apps.get_model("core", "SiteSettings")
    SiteSettings.objects.filter(newsletter_text=OLD_TEXT).update(newsletter_text=NEW_TEXT)


def revert_copy(apps, schema_editor):
    SiteSettings = apps.get_model("core", "SiteSettings")
    SiteSettings.objects.filter(newsletter_text=NEW_TEXT).update(newsletter_text=OLD_TEXT)


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(update_copy, revert_copy),
    ]
