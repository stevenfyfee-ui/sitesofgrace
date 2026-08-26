"""
Shared helper for the "On this page" section navigation.

Pages that carry the rail build their own section list -- LearnPage from its
section records, SacredSitePage from its fixed narrative fields -- and hand it
to `includes/_section_nav.html`. All they need in common is a way to turn
heading text into an anchor id that is readable, shareable, and unique within
the page, which is what AnchorFactory does.
"""
from django.utils.text import slugify

# Anchor ids longer than this get unwieldy in a URL bar.
MAX_ANCHOR_LENGTH = 60


class AnchorFactory:
    """Hands out unique, readable anchor ids within one page."""

    def __init__(self):
        self._used = {}

    def make(self, text, fallback="section"):
        base = slugify(text or "")[:MAX_ANCHOR_LENGTH] or fallback
        count = self._used.get(base, 0) + 1
        self._used[base] = count
        return base if count == 1 else f"{base}-{count}"
