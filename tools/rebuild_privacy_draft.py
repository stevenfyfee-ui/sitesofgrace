"""Rebuild the Privacy Policy draft (LegalPage 2502) from legal/content/privacy-policy.md.

One-off, November 2026: the draft had drifted from the source file (no
prayer-requests bullet, old section 8 retention, header tokens typed in as
text), and the saved-trips additions (docs/planner/privacy-addition.md) go
in with it. Saves one new draft revision; never publishes. Run with
`manage.py shell`, the source file given by path (the deployed copy may be
older than the reviewed one):

    SOG_MD=/tmp/privacy-policy.md SOG_MODE=dry   python manage.py shell < tools/rebuild_privacy_draft.py
    SOG_MD=/tmp/privacy-policy.md SOG_MODE=apply SOG_USER=<username> python manage.py shell < ...
    SOG_MD=/tmp/privacy-policy.md SOG_MODE=verify python manage.py shell < ...

dry: prints a block diff against the current draft and writes the rendered
text (Legal details filled in) to /tmp/privacy_rendered.txt. apply: refuses
if the page is live or its latest revision isn't the one reviewed
(SOG_EXPECT_REVISION, default 1054). verify: the latest draft matches the
file and the page is still not live.
"""
import difflib
import html
import os
import re

from django.contrib.auth import get_user_model
from wagtail.models import Site

from home import legal
from home.models import LegalDetails, LegalPage

PAGE_ID = 2502
mode = os.environ.get("SOG_MODE", "dry")
expect_revision = int(os.environ.get("SOG_EXPECT_REVISION", "1054"))
title, body_md = legal.parse_content_file(open(os.environ["SOG_MD"], encoding="utf-8").read())
new_body = legal.markdown_to_richtext(body_md)


def blocks(markup):
    markup = re.sub(r' data-block-key="[^"]*"', "", str(markup))
    return [html.unescape(b) for b in re.split(r"(?=<(?:h2|h3|p|li|ul|ol)>)", markup) if b.strip()]


def plain(markup):
    text = re.sub(r"<br\s*/?>", "\n", markup)
    text = re.sub(r"</(p|li|h2|h3)>", "\n", text)
    text = re.sub(r"<li>", "  - ", text)
    text = re.sub(r"<h2>", "\n## ", text)
    text = re.sub(r"<h3>", "\n### ", text)
    return html.unescape(re.sub(r"<[^>]+>", "", text))


page = LegalPage.objects.get(pk=PAGE_ID)
draft = page.get_latest_revision_as_object()
details = LegalDetails.load(request_or_site=Site.objects.filter(is_default_site=True).first())
print(f"page {page.pk} {page.slug}: live={page.live} latest revision={page.latest_revision_id} "
      f"effective={draft.effective_date}")

if mode == "dry":
    for line in difflib.unified_diff(blocks(draft.body), blocks(new_body), "draft", "source", n=0, lineterm=""):
        print(line)
    with open("/tmp/privacy_rendered.txt", "w", encoding="utf-8") as fh:
        fh.write(f"# {title}\nEffective {draft.effective_date} (unchanged)\n" + plain(legal.fill_tokens(new_body, details)))
    print("missing Legal details for publishing:", ", ".join(legal.missing_fields(new_body, details)) or "none")
    print("DRY RUN -- nothing saved. Rendered text: /tmp/privacy_rendered.txt")
elif mode == "apply":
    if page.live:
        raise SystemExit("Refusing: the page is live. Nothing was saved.")
    if page.latest_revision_id != expect_revision:
        raise SystemExit(f"Refusing: latest revision is {page.latest_revision_id}, reviewed {expect_revision}. Nothing was saved.")
    user = get_user_model().objects.get(username=os.environ["SOG_USER"])
    draft.title = title
    draft.body = new_body
    draft.search_description = legal.first_paragraph_text(body_md)
    revision = draft.save_revision(user=user, log_action=True)
    page.refresh_from_db()
    print(f"Saved draft revision {revision.pk} by {user.username}; live={page.live}. Nothing was published.")
elif mode == "verify":
    ok = blocks(draft.body) == blocks(new_body) and not page.live
    print("verify:", "draft matches the file, page not live" if ok else "MISMATCH")
    if not ok:
        raise SystemExit(1)
