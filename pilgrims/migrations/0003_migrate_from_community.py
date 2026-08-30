"""One-time absorption of the former `community` app.

Reads straight out of community_pilgrimprofile / community_journeyentry via
raw SQL (rather than historical models) so this migration doesn't need
`community` back in INSTALLED_APPS, and is a safe no-op on a fresh database
(e.g. the test runner's) where those tables were never created.

Field mapping decisions (see the phase-1 report for the full rationale):
  - PilgrimProfile.journey_visibility "public"/"private" -> is_private bool.
    newsletter_opt_in has no equivalent field in the new profile spec and is
    dropped.
  - JourneyEntry.status "visited" -> SiteVisit "visited"; "want" and "saved"
    both collapse to "want_to_go" (the new model only distinguishes visited
    vs. want-to-go; the old three-bucket saved/want/visited split has no
    button in the live UI that ever set "want", so nothing meaningful is
    lost).
  - Every existing auth.User gets a PilgrimProfile (not just ones that had a
    community profile row), with a generated handle, so no user is left
    without one after this migration.

After copying, the two legacy tables are dropped — this migration is the
last thing that ever reads them.
"""
import uuid

from django.conf import settings
from django.db import migrations
from django.utils.text import slugify

# Frozen copy of pilgrims.models.RESERVED_HANDLES as of this migration.
# Migrations must not depend on a currently-editable module, so this is
# duplicated rather than imported.
RESERVED_HANDLES = {
    "health", "django-admin", "admin", "documents", "search",
    "newsletter", "store", "accounts", "journey", "passport", "pilgrims",
    "u", "settings", "requests", "following", "followers",
    "staff", "api", "sites", "news", "support", "help", "about",
}


def _table_exists(schema_editor, table_name):
    return table_name in schema_editor.connection.introspection.table_names()


def _unique_handle(base, taken):
    base = (slugify(base) or "pilgrim")[:26]
    if base in RESERVED_HANDLES:
        base = f"{base}-pilgrim"
    handle = base
    suffix = 1
    while handle in RESERVED_HANDLES or handle in taken:
        suffix += 1
        handle = f"{base}{suffix}"[:30]
    return handle


def migrate_data(apps, schema_editor):
    PilgrimProfile = apps.get_model("pilgrims", "PilgrimProfile")
    SiteVisit = apps.get_model("pilgrims", "SiteVisit")
    User = apps.get_model(*settings.AUTH_USER_MODEL.split("."))

    cursor = schema_editor.connection.cursor()

    legacy_profiles = {}
    if _table_exists(schema_editor, "community_pilgrimprofile"):
        cursor.execute(
            "SELECT user_id, display_name, avatar, home_country, journey_visibility "
            "FROM community_pilgrimprofile"
        )
        for user_id, display_name, avatar, home_country, journey_visibility in cursor.fetchall():
            legacy_profiles[user_id] = {
                "display_name": display_name or "",
                "avatar": avatar or "",
                "home_country": home_country or "",
                "is_private": journey_visibility != "public",
            }

    taken_handles = set(PilgrimProfile.objects.values_list("handle", flat=True))

    for user in User.objects.all():
        if PilgrimProfile.objects.filter(user_id=user.pk).exists():
            continue
        legacy = legacy_profiles.get(user.pk, {})
        handle = _unique_handle(
            (user.email or user.username or "pilgrim").split("@")[0], taken_handles
        )
        taken_handles.add(handle)
        PilgrimProfile.objects.create(
            uuid=uuid.uuid4(),
            user_id=user.pk,
            handle=handle,
            display_name=legacy.get("display_name", ""),
            avatar=legacy.get("avatar", ""),
            home_country=legacy.get("home_country", ""),
            is_private=legacy.get("is_private", True),
        )

    if _table_exists(schema_editor, "community_journeyentry"):
        cursor.execute(
            "SELECT user_id, site_id, status, visited_date, notes "
            "FROM community_journeyentry"
        )
        for user_id, site_id, status, visited_date, notes in cursor.fetchall():
            new_status = "visited" if status == "visited" else "want_to_go"
            SiteVisit.objects.update_or_create(
                owner_id=user_id,
                site_id=site_id,
                defaults={
                    "uuid": uuid.uuid4(),
                    "status": new_status,
                    "visited_on": visited_date,
                    "notes": notes or "",
                },
            )

    cursor.execute("DROP TABLE IF EXISTS community_journeyentry")
    cursor.execute("DROP TABLE IF EXISTS community_pilgrimprofile")


class Migration(migrations.Migration):

    dependencies = [
        ("pilgrims", "0002_seed_badges"),
    ]

    operations = [
        migrations.RunPython(migrate_data, migrations.RunPython.noop),
    ]
