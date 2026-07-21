from django.db import migrations

# slug -> (layout, teaser)
PAGE_LAYOUTS = {
    "explore": ("explore_hub", ""),
    "marian-apparitions": (
        "category_directory",
        "Places where the Blessed Virgin Mary is believed to have appeared.",
    ),
    "eucharistic-miracles": (
        "category_directory",
        "Miracles of the Eucharist that point to Christ's Real Presence.",
    ),
    "saints-and-tombs": (
        "category_directory",
        "Tombs, relics, and places tied to the lives of the saints.",
    ),
    "holy-lands": (
        "category_directory",
        "The places of Jesus' life, death, and Resurrection.",
    ),
    "shrines-and-basilicas": (
        "category_directory",
        "Great shrines and basilicas that draw pilgrims worldwide.",
    ),
    "pilgrimage-routes": (
        "category_directory",
        "New pilgrimage routes and itineraries are coming soon.",
    ),
    "saints": (
        "saints_directory",
        "Explore the lives of the saints — feast days, patronage, and their stories.",
    ),
}


def set_layouts(apps, schema_editor):
    StandardPage = apps.get_model("home", "StandardPage")
    for slug, (layout, teaser) in PAGE_LAYOUTS.items():
        StandardPage.objects.filter(slug=slug).update(layout=layout, teaser=teaser)


def unset_layouts(apps, schema_editor):
    StandardPage = apps.get_model("home", "StandardPage")
    StandardPage.objects.filter(slug__in=PAGE_LAYOUTS.keys()).update(layout="default", teaser="")


class Migration(migrations.Migration):

    dependencies = [
        ("home", "0005_standardpage_card_image_standardpage_layout_and_more"),
    ]

    operations = [
        migrations.RunPython(set_layouts, unset_layouts),
    ]
