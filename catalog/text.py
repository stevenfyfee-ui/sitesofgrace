"""Name folding shared by the catalog import commands and the liturgy app.

Lives outside management/commands so importing it never drags in a
command's own dependencies (link_site_saints needs openpyxl, which the
home page has no business loading).
"""
import re
import unicodedata

LIGATURES = {"æ": "ae", "Æ": "AE", "œ": "oe", "Œ": "OE", "ø": "o", "ł": "l"}
HONORIFIC = re.compile(r"\b(sts?|saints?|blessed|bl|pope)\b", re.I)


def s(value):
    return "" if value is None else str(value).strip()


def fold(name):
    """Normalise a saint name for matching.

    The Site_Saint_Links tab was written with plain-ASCII names, while the
    imported pages carry restored diacritics ("St. Catherine Labouré"), so
    both sides have to be folded before they will compare equal.
    """
    text = s(name)
    for a, b in LIGATURES.items():
        text = text.replace(a, b)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"[^A-Za-z0-9 ]", " ", text)
    text = HONORIFIC.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip().lower()
