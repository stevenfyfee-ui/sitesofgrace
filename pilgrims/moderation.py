"""
The auto-hide policy — one well-named function, so this stays the single
place the policy lives rather than being re-derived per call site.

NOTE for future volume changes: if report volume ever argues for
PRE-APPROVAL (nothing goes public until a human looks at it) instead of
hide-after-report, that's a small, obvious swap here: gate share_photo()
itself on a "needs_review" state rather than reacting to reports after the
fact. Nothing else in the app — the report flow, ModerationAction, the
gallery query — needs to change for that switch.
"""
from .models import PhotoReport
from .sharing import hide_photo

# The three reasons serious enough that a single report hides the photo
# before any human looks at it.
IMMEDIATE_HIDE_REASONS = {
    PhotoReport.REASON_SEXUAL,
    PhotoReport.REASON_MINOR_SAFETY,
    PhotoReport.REASON_VIOLENCE,
}

# Any other reason needs this many DISTINCT reporters (distinct user, or
# distinct IP hash for anonymous ones) before the photo auto-hides.
OTHER_REASON_DISTINCT_REPORTER_THRESHOLD = 2


def _reporter_identity(report):
    """A hashable identity for "who filed this" — the whole reason
    reporter_ip_hash exists is so two anonymous reports from the same
    visitor don't count as two distinct reporters."""
    return ("user", report.reporter_id) if report.reporter_id else ("ip", report.reporter_ip_hash)


def apply_auto_hide_policy(photo):
    """Call after saving a new PhotoReport for `photo`. Idempotent — a
    no-op if the photo is already hidden."""
    if photo.hidden_by_staff:
        return False

    reports = list(PhotoReport.objects.filter(photo=photo))

    if any(report.reason in IMMEDIATE_HIDE_REASONS for report in reports):
        hide_photo(photo, reason="Automatically hidden: a serious-violation report was filed.")
        return True

    distinct_reporters = {
        _reporter_identity(report) for report in reports if report.reason not in IMMEDIATE_HIDE_REASONS
    }
    if len(distinct_reporters) >= OTHER_REASON_DISTINCT_REPORTER_THRESHOLD:
        hide_photo(photo, reason="Automatically hidden: multiple pilgrims reported this photo.")
        return True

    return False
