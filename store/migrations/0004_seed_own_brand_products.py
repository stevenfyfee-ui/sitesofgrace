from django.db import migrations

PRODUCTS = [
    {
        "title": "The Pilgrim's Box",
        "category": "Subscriptions",
        "kind": "own",
        "layout": "feature",
        "ribbon_text": "Quarterly Subscription",
        "spotlight_title": "Autumn 2026 · Lourdes, France",
        "spotlight_note": "Shipping the first week of October",
        "long_description": (
            "<p>Four times a year, a package arrives from a different holy place — real "
            "devotionals sourced from the shrine itself, with a letter that tells the story "
            "behind them.</p>"
        ),
        "fine_print": "Gift subscriptions include a printed announcement card and never auto-renew.",
        "cta_mode": "waitlist",
        "sort_order": 0,
        "inclusions": [
            ("A blessed rosary", "from the featured shrine"),
            ("Holy water or blessed oil", "in a keepsake vial"),
            ("A book or devotional", "tied to the season's site or saint"),
            ("A keepsake", "— medal, prayer card set, or hand-poured candle"),
            (
                "The Pilgrim Letter",
                "our quarterly newsletter spotlighting the place and its saint, stories from "
                "pilgrims who've been, and events there this season",
            ),
        ],
        "price_options": [
            ("Quarterly", "$54", "/box", "Cancel anytime", False),
            ("Full Year · 4 boxes", "$196", "/yr", "Save $20 + free shipping", True),
            ("Gift a Year", "$196", "", "Card mailed to recipient", False),
        ],
    },
    {
        "title": "The Liturgical Year Calendar & Planner",
        "category": "Calendars & Planners",
        "kind": "own",
        "layout": "feature",
        "ribbon_text": "New for 2027",
        "spotlight_title": "",
        "spotlight_note": "",
        "long_description": (
            "<p>A full-color calendar and weekly planner built on the Church's year, not just "
            "the civil one.</p>"
        ),
        "fine_print": (
            "Ships November 2026, ahead of the First Sunday of Advent. Parish and school "
            "bulk pricing available."
        ),
        "cta_mode": "waitlist",
        "sort_order": 1,
        "inclusions": [
            ("Liturgical seasons", "color-coded across every page"),
            ("Feast days", "of prominent saints with a short line on who they were"),
            ("Anniversaries", "of Marian apparitions and major Eucharistic miracles"),
            ("Twelve full-color plates", "of shrines, sacred art, and pilgrimage landscapes"),
            (
                "The planner edition",
                "adds weekly layouts, Sunday readings at a glance, and pilgrimage journal pages",
            ),
        ],
        "price_options": [
            ("Wall Calendar", "$28", "", "12 × 12 in.", False),
            ("Planner", "$42", "", "Hardbound, 7 × 9", False),
            ("The Set", "$62", "", "Save $8", True),
        ],
    },
]

TITLES = [p["title"] for p in PRODUCTS]


def seed_products(apps, schema_editor):
    StoreProduct = apps.get_model("store", "StoreProduct")
    ProductInclusion = apps.get_model("store", "ProductInclusion")
    ProductPriceOption = apps.get_model("store", "ProductPriceOption")

    for entry in PRODUCTS:
        product, created = StoreProduct.objects.get_or_create(
            title=entry["title"],
            defaults={
                "category": entry["category"],
                "kind": entry["kind"],
                "layout": entry["layout"],
                "ribbon_text": entry["ribbon_text"],
                "spotlight_title": entry["spotlight_title"],
                "spotlight_note": entry["spotlight_note"],
                "long_description": entry["long_description"],
                "fine_print": entry["fine_print"],
                "cta_mode": entry["cta_mode"],
                "sort_order": entry["sort_order"],
                "live": True,
            },
        )
        if not created:
            continue

        for i, (lead_in, text) in enumerate(entry["inclusions"]):
            ProductInclusion.objects.create(product=product, lead_in=lead_in, text=text, sort_order=i)

        for i, (label, amount, unit, note, is_default) in enumerate(entry["price_options"]):
            ProductPriceOption.objects.create(
                product=product, label=label, amount=amount, unit=unit, note=note,
                is_default=is_default, sort_order=i,
            )


def unseed_products(apps, schema_editor):
    StoreProduct = apps.get_model("store", "StoreProduct")
    StoreProduct.objects.filter(title__in=TITLES).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("store", "0003_storeproduct_cta_mode_storeproduct_fine_print_and_more"),
    ]

    operations = [
        migrations.RunPython(seed_products, unseed_products),
    ]
