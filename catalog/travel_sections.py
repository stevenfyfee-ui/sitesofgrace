"""
Single source of truth for the "Plan Your Visit" travel sections on site pages.

The `kind` key of each section is ALSO its URL anchor -- a deep link like
/explore/marian-apparitions/lourdes/#where-to-stay is built from it. Renaming a
key silently breaks every shared and indexed link to that panel, so treat the
keys as permanent and change only the labels.

Reading order and cluster membership come from TRAVEL_CLUSTERS, not from the
inline's sort_order, so every site page presents the same twelve in the same
shape. A reader who learns the layout on Lourdes finds it unchanged on Fatima.
"""

# (cluster key, cluster label, [(section key / anchor, section label), ...])
TRAVEL_CLUSTERS = [
    ("plan-the-trip", "Plan the trip", [
        ("how-long-should-i-stay", "How Long Should I Stay?"),
        ("best-time-to-visit", "Best Time to Visit"),
        ("getting-there", "Getting There From the United States"),
    ]),
    ("on-the-ground", "On the ground", [
        ("getting-around", "Getting Around"),
        ("where-to-stay", "Where to Stay"),
        ("accessibility", "Accessibility"),
    ]),
    ("what-to-do", "What to do", [
        ("most-important-things", "Most Important Things to Do"),
        ("suggested-itinerary", "Suggested Pilgrimage Itinerary"),
        ("mass-confession-prayer", "Mass, Confession & Prayer"),
    ]),
    ("practical", "Practical", [
        ("what-to-bring", "What to Bring"),
        ("before-you-go", "Before You Go"),
        ("additional-information", "Additional Information"),
    ]),
]

TRAVEL_SECTION_CHOICES = [
    (key, label)
    for _, _, items in TRAVEL_CLUSTERS
    for key, label in items
]

TRAVEL_LABELS = dict(TRAVEL_SECTION_CHOICES)

# Canonical reading position, 0-based, keyed by section key.
TRAVEL_ORDER = {key: index for index, (key, _) in enumerate(TRAVEL_SECTION_CHOICES)}

# Where migrated legacy pilgrimage_info text lands.
LEGACY_SECTION_KIND = "additional-information"
