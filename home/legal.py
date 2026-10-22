"""
Legal pages and on-page notices: the one place runtime tokens are filled.

Legal text carries tokens like {{CONTACT_EMAIL}} that are filled from the
"Legal details" setting (home.LegalDetails) at render time, so the operator's
name, address, and DMCA agent never live in page bodies or in git. Every
caller -- LegalPage bodies, the notices, Stripe's checkout text -- goes
through fill_tokens() below, which HTML-escapes every value.

An unknown token is a bug in the content, never something to paper over, so
it raises UnknownTokenError. A known token whose value is blank renders as
"" (with a warning logged): LegalPage's publish guard keeps that from
happening on purpose, and a visitor must never see "{{...}}".
"""
import logging
import re

from django.utils.html import escape
from django.utils.text import slugify

logger = logging.getLogger(__name__)

# Token name -> LegalDetails field name.
TOKENS = {
    "OPERATOR_NAME": "operator_name",
    "CONTACT_EMAIL": "contact_email",
    "MAILING_ADDRESS": "mailing_address",
    "DMCA_AGENT_NAME": "dmca_agent_name",
    "DMCA_AGENT_ADDRESS": "dmca_agent_address",
    "DMCA_AGENT_PHONE": "dmca_agent_phone",
    "DMCA_AGENT_EMAIL": "dmca_agent_email",
}
EMAIL_TOKENS = {"CONTACT_EMAIL", "DMCA_AGENT_EMAIL"}

TOKEN_RE = re.compile(r"\{\{\s*([A-Za-z0-9_:]+)\s*\}\}")

# The ten pages create_legal_pages makes, in footer-ish order. Slug -> the
# label used when something links to the page by name.
LEGAL_SLUGS = (
    "privacy-policy",
    "terms-of-use",
    "affiliate-disclosure",
    "travel-disclaimer",
    "catholic-content-notice",
    "community-policy",
    "copyright-policy",
    "support-and-billing",
    "cookie-notice",
    "accessibility",
)

_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")
_SAFE_URL_RE = re.compile(r"^(/|https://|http://|mailto:)")
_H2_RE = re.compile(r"<h2([^>]*)>(.*?)</h2>", re.S)
_TAG_RE = re.compile(r"<[^>]+>")


class UnknownTokenError(ValueError):
    """Legal text used a {{TOKEN}} that LegalDetails doesn't define."""


def tokens_in(text):
    """Every token name used in `text`. Raises UnknownTokenError on one
    that isn't in TOKENS."""
    names = set(TOKEN_RE.findall(text or ""))
    unknown = names - TOKENS.keys()
    if unknown:
        raise UnknownTokenError(f"Unknown legal token(s): {', '.join(sorted(unknown))}")
    return names


def missing_fields(text, details):
    """Verbose names of the LegalDetails fields `text` uses but are blank."""
    missing = []
    for name in sorted(tokens_in(text)):
        field_name = TOKENS[name]
        if not str(getattr(details, field_name, "") or "").strip():
            missing.append(str(details._meta.get_field(field_name).verbose_name))
    return missing


def _token_value(name, details, *, html):
    value = str(getattr(details, TOKENS[name], "") or "").strip()
    if not value:
        logger.warning("Legal token {{%s}} rendered blank: LegalDetails.%s is empty.", name, TOKENS[name])
        return ""
    if not html:
        return value
    if name in EMAIL_TOKENS:
        return f'<a href="mailto:{escape(value)}">{escape(value)}</a>'
    return "<br>".join(escape(line.strip()) for line in value.splitlines() if line.strip())


def fill_tokens(text, details, *, html=True):
    """`text` with every {{TOKEN}} replaced from `details` (a LegalDetails).

    html=True: values are HTML-escaped, emails become mailto links, and
    multi-line addresses get <br>s. html=False: plain values, for places
    that aren't HTML (Stripe's checkout text).
    """
    tokens_in(text)
    return TOKEN_RE.sub(lambda m: _token_value(m.group(1), details, html=html), text or "")


def _render_link(match, legal_urls):
    label, url = match.group(1), match.group(2)
    if not _SAFE_URL_RE.match(url):
        return match.group(0)
    slug = url.strip("/")
    if url.startswith("/") and slug in LEGAL_SLUGS:
        # A legal page is linked only once it's live; until then the
        # label stays as plain text.
        live_url = legal_urls.get(slug, "")
        return f'<a href="{live_url}">{label}</a>' if live_url else label
    return f'<a href="{url}">{label}</a>'


def render_notice(text, details, legal_urls, *, amount=None):
    """Notice text -> safe HTML.

    Escapes everything first, then converts only **bold** and [text](url),
    then fills {amount} (when given) and the runtime tokens. `legal_urls`
    maps a legal page's slug to its live URL (see live_legal_urls).
    """
    out = escape(text or "")
    out = _BOLD_RE.sub(r"<strong>\1</strong>", out)
    out = _LINK_RE.sub(lambda m: _render_link(m, legal_urls), out)
    if amount is not None:
        out = out.replace("{amount}", f'<span data-notice-amount>{escape(amount)}</span>')
    return fill_tokens(out, details)


def notice_plain(text, details, *, amount=None):
    """Notice text as plain text: markup dropped, link labels kept."""
    out = _BOLD_RE.sub(r"\1", text or "")
    out = _LINK_RE.sub(r"\1", out)
    if amount is not None:
        out = out.replace("{amount}", amount)
    return fill_tokens(out, details, html=False)


def live_legal_urls(request=None):
    """{slug: url} for every live, public legal page -- root-relative when
    the page is on the request's own site."""
    from home.models import LegalPage

    return {
        page.slug: page.get_url(request)
        for page in LegalPage.objects.live().public().filter(slug__in=LEGAL_SLUGS)
    }


def add_heading_ids(html):
    """(html, [(id, text), ...]): every <h2> gets a slug id, for the "On this
    page" list. Ids are unique within the page."""
    toc = []
    seen = set()

    def replace(match):
        attrs, inner = match.group(1), match.group(2)
        text = _TAG_RE.sub("", inner).strip()
        base = slugify(text) or "section"
        anchor, n = base, 2
        while anchor in seen:
            anchor, n = f"{base}-{n}", n + 1
        seen.add(anchor)
        toc.append((anchor, text))
        attrs = re.sub(r'\s+id="[^"]*"', "", attrs)
        return f'<h2{attrs} id="{anchor}">{inner}</h2>'

    return _H2_RE.sub(replace, html), toc


# --- Markdown -> rich text (create_legal_pages) ---------------------------

_ITALIC_RE = re.compile(r"(?<![*\w])\*(?!\*)(.+?)(?<!\*)\*(?![*\w])")
_UL_RE = re.compile(r"^[-*]\s+(.*)$")
_OL_RE = re.compile(r"^\d+\.\s+(.*)$")


def _inline(text):
    out = escape(text)
    out = _BOLD_RE.sub(r"<b>\1</b>", out)
    out = _ITALIC_RE.sub(r"<i>\1</i>", out)
    return _LINK_RE.sub(lambda m: f'<a href="{m.group(2)}">{m.group(1)}</a>', out)


def markdown_to_richtext(body):
    """The small Markdown subset the legal content uses -> Wagtail rich text
    HTML: ## / ### headings, paragraphs, **bold**, *italic*, [links](url),
    and - / 1. lists. Tokens pass through untouched."""
    blocks = []
    paragraph = []
    list_tag, items = None, []

    def flush_paragraph():
        if paragraph:
            blocks.append(f"<p>{_inline(' '.join(paragraph))}</p>")
            paragraph.clear()

    def flush_list():
        nonlocal list_tag
        if list_tag:
            blocks.append(f"<{list_tag}>" + "".join(f"<li>{_inline(i)}</li>" for i in items) + f"</{list_tag}>")
            list_tag = None
            items.clear()

    for raw in (body or "").splitlines():
        line = raw.strip()
        ul, ol = _UL_RE.match(line), _OL_RE.match(line)
        if not line:
            flush_paragraph()
            flush_list()
        elif line.startswith("### ") or line.startswith("## "):
            flush_paragraph()
            flush_list()
            level = 3 if line.startswith("### ") else 2
            blocks.append(f"<h{level}>{_inline(line[level + 1:].strip())}</h{level}>")
        elif ul or ol:
            flush_paragraph()
            tag = "ul" if ul else "ol"
            if list_tag != tag:
                flush_list()
                list_tag = tag
            items.append((ul or ol).group(1))
        else:
            flush_list()
            paragraph.append(line)
    flush_paragraph()
    flush_list()
    return "".join(blocks)


def parse_content_file(text):
    """(title, body markdown) from a legal content file whose first line is
    "# Title"."""
    lines = (text or "").splitlines()
    if not lines or not lines[0].startswith("# "):
        raise ValueError('The first line must be "# Title".')
    return lines[0][2:].strip(), "\n".join(lines[1:]).strip()


def first_paragraph_text(body):
    """The first paragraph of a Markdown body that uses no {{TOKEN}}, as
    plain text with markup stripped -- used for search_description. (The
    Privacy Policy's first paragraph is the "Operator: {{OPERATOR_NAME}}"
    line, which would read badly with the name left out.)"""
    for chunk in re.split(r"\n\s*\n", body or ""):
        lines = [line.strip() for line in chunk.strip().splitlines()]
        lines = [line for line in lines if line and not line.startswith("#")]
        if not lines or _UL_RE.match(lines[0]) or _OL_RE.match(lines[0]):
            continue
        text = " ".join(lines)
        if TOKEN_RE.search(text):
            continue
        text = _BOLD_RE.sub(r"\1", text)
        text = _LINK_RE.sub(r"\1", text)
        return re.sub(r"\s{2,}", " ", text).strip()
    return ""


def parse_notices(text):
    """{key: text} from notices.md's "## key" sections."""
    notices = {}
    key = None
    for line in (text or "").splitlines():
        if line.startswith("## "):
            key = line[3:].strip()
            notices[key] = []
        elif key is not None:
            notices[key].append(line)
    return {k: "\n".join(v).strip() for k, v in notices.items()}
