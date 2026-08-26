"""
Shared helpers for the "On this page" section navigation.

Two kinds of page feed the same rail component:

* Pages whose sections are structured records (LearnPage sections, the fixed
  narrative fields on SacredSitePage). Those build their nav directly.
* Pages whose body is one freeform rich-text field (SaintPage). Those need the
  headings pulled out of the rendered HTML, which is what `headings_with_anchors`
  below does -- it injects a stable `id` on every heading it finds and hands back
  both the rewritten HTML and the list of headings.

Anchors are slugified from the heading text so they stay readable and shareable,
with a numeric suffix only when the same heading appears twice on a page.
"""
from bs4 import BeautifulSoup
from django.utils.safestring import mark_safe
from django.utils.text import slugify
from wagtail.rich_text import expand_db_html

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


def headings_with_anchors(rich_text_value, levels=("h2",)):
    """
    Return `(html, headings)` for a RichTextField value.

    `html` is the expanded rich text with an `id` and the `section-anchor` class
    added to every heading at `levels`. `headings` is a list of
    `{"id": ..., "label": ...}` ready for the nav rail. Both are empty when the
    field is blank.
    """
    html = expand_db_html(rich_text_value or "")
    if not html.strip():
        return mark_safe(""), []

    soup = BeautifulSoup(html, "html.parser")
    anchors = AnchorFactory()
    headings = []

    for tag in soup.find_all(list(levels)):
        label = tag.get_text(strip=True)
        if not label:
            continue
        anchor = anchors.make(label)
        tag["id"] = anchor
        existing_classes = tag.get("class") or []
        tag["class"] = [*existing_classes, "section-anchor"]
        headings.append({"id": anchor, "label": label})

    return mark_safe(str(soup)), headings
