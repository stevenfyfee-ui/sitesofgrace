from django.db import migrations

OLD_SACRED_SITES_BLURB = (
    "Explore saints' tombs, shrines, basilicas, relic sites, and historic Catholic places."
)
NEW_SACRED_SITES_BLURB = (
    "Explore saints' tombs, shrines, basilicas, relic sites, Holy Land locations, "
    "and historic Catholic places."
)

OLD_COMMUNITY_INTRO = (
    "Create your personal pilgrim profile, track the sacred places you have "
    "visited, save future destinations, and share the moments that deepened "
    "your faith."
)
NEW_COMMUNITY_INTRO = (
    "Create your personal pilgrim profile, track the sacred places you have "
    "visited, save future destinations, upload photos, and share the moments "
    "that deepened your faith."
)

OLD_COMMUNITY_CTA_LINK = "#"
NEW_COMMUNITY_CTA_LINK = "/accounts/signup/"


def update_copy(apps, schema_editor):
    HomePage = apps.get_model("home", "HomePage")
    FeatureCard = apps.get_model("home", "FeatureCard")

    HomePage.objects.filter(community_intro=OLD_COMMUNITY_INTRO).update(
        community_intro=NEW_COMMUNITY_INTRO
    )
    HomePage.objects.filter(community_cta_link=OLD_COMMUNITY_CTA_LINK).update(
        community_cta_link=NEW_COMMUNITY_CTA_LINK
    )
    FeatureCard.objects.filter(title="Sacred Sites", blurb=OLD_SACRED_SITES_BLURB).update(
        blurb=NEW_SACRED_SITES_BLURB
    )


def revert_copy(apps, schema_editor):
    HomePage = apps.get_model("home", "HomePage")
    FeatureCard = apps.get_model("home", "FeatureCard")

    HomePage.objects.filter(community_intro=NEW_COMMUNITY_INTRO).update(
        community_intro=OLD_COMMUNITY_INTRO
    )
    HomePage.objects.filter(community_cta_link=NEW_COMMUNITY_CTA_LINK).update(
        community_cta_link=OLD_COMMUNITY_CTA_LINK
    )
    FeatureCard.objects.filter(title="Sacred Sites", blurb=NEW_SACRED_SITES_BLURB).update(
        blurb=OLD_SACRED_SITES_BLURB
    )


class Migration(migrations.Migration):

    dependencies = [
        ("home", "0006_explore_hub_and_category_directory_layouts"),
    ]

    operations = [
        migrations.RunPython(update_copy, revert_copy),
    ]
