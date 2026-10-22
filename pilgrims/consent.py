"""
The one server-side check every "make this public" action goes through.

Sharing a photo publicly (from the upload page or the photo page) needs:
  - the rights checkbox ("I took this photo or have permission..."),
    ticked on EVERY share -- it's about this photo, not the account;
  - the 18+ checkbox, once per account; afterwards
    PilgrimProfile.adult_confirmed_at is set and the box isn't shown again.

Making a profile public needs only the 18+ confirmation (see
ProfileSettingsForm). Staff hide/unhide is moderation, not a pilgrim's
choice, and isn't gated here.

Checkbox labels come from the "Legal notices" setting
(share_rights_checkbox, share_adult_checkbox).
"""
from django.utils import timezone

RIGHTS_FIELD = "share_rights"
ADULT_FIELD = "share_adult"

RIGHTS_REFUSAL = "please confirm you took this photo or have permission to share it."
ADULT_REFUSAL = "please confirm you're 18 or older to share photos publicly."


def needs_adult_confirmation(profile):
    return profile.adult_confirmed_at is None


def _ticked(data, field):
    return data.get(field) in ("on", "true", "1")


def share_refusal(data, profile):
    """Why a public photo share must be refused, or None. `data` is the
    request's POST data."""
    if not _ticked(data, RIGHTS_FIELD):
        return RIGHTS_REFUSAL
    if needs_adult_confirmation(profile) and not _ticked(data, ADULT_FIELD):
        return ADULT_REFUSAL
    return None


def adult_confirmed_in(data):
    return _ticked(data, ADULT_FIELD)


def record_adult_confirmation(profile):
    """Stamp adult_confirmed_at the first time; later calls do nothing."""
    if profile.adult_confirmed_at is None:
        profile.adult_confirmed_at = timezone.now()
        profile.save(update_fields=["adult_confirmed_at"])
