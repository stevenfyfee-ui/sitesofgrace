"""Turn a signed-out "I'm interested" click into a TourInterest at sign-in.

tours.views.tour_interest parks {"site", "at"} in the session for a
signed-out visitor. Django keeps session data across login, so on the
user_logged_in signal the pending entry is popped (always) and the interest
created only if it is still within PENDING_INTEREST_SECONDS and the site is
live. Nothing is read from the URL.
"""
from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver
from django.utils import timezone

from .models import PENDING_INTEREST_KEY, PENDING_INTEREST_SECONDS, TourInterest


@receiver(user_logged_in)
def create_pending_tour_interest(sender, request, user, **kwargs):
    session = getattr(request, "session", None)
    if session is None:
        return
    pending = session.pop(PENDING_INTEREST_KEY, None)
    if not isinstance(pending, dict):
        return
    try:
        site_id, at = int(pending["site"]), float(pending["at"])
    except (KeyError, TypeError, ValueError):
        return
    if timezone.now().timestamp() - at > PENDING_INTEREST_SECONDS:
        return
    from catalog.models import SacredSitePage

    site = SacredSitePage.objects.live().filter(pk=site_id).first()
    if site is not None:
        TourInterest.objects.get_or_create(user=user, site=site)
