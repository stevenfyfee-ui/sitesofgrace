"""Pricing / booking seam for the Plan page.

v1 computes the trip estimate client-side from seeded data (see plan.js), so the
estimate helpers below are NOT yet called — they mark the Phase 2 integration
point. When we wire Travelpayouts, fill these in and the page switches from
seed estimates to live fares + affiliate booking links without a redesign.
"""


def flight_estimate(region, origin=None, party=1):
    """Phase 2: live round-trip fare for `region` from `origin`, times party.
    v1 uses the seeded RegionFlightAssumption, computed client-side."""
    raise NotImplementedError("Phase 2 (Travelpayouts)")


def hotel_estimate(destination, nights, tier, rooms):
    """Phase 2: live nightly rate for `destination`.
    v1 uses the seeded DestinationCost, computed client-side."""
    raise NotImplementedError("Phase 2 (Travelpayouts)")


def booking_links(destination):
    """Affiliate 'Book now' links for a destination.
    v1: none yet -> returns []. Phase 2: Travelpayouts flight/hotel deep-links."""
    return []
