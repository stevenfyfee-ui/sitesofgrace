"""Future Saints Phase 1 browser QA: screenshots plus keyboard/cookie/network checks.

    python tools/future_saints_screens.py <base_url> <out_dir> [comp_png]

Run against a local server with SOG_FUTURE_SAINTS=on after
`manage.py future_saints_dev_sample`. Needs Playwright with Chromium (the
local sog-shots image has both). Set FS_STAFF_SESSION to a local staff
sessionid to also capture the staff view. Writes PNGs to out_dir only; exits
1 if any check fails.

Checks: the four subject cards share one row at >=1024px (2x2 at 768, one
column at <=430) with the Holy Land card full width below; the <=900px menu
opens from the keyboard, closes on Esc and returns focus; the page works
without JavaScript; an anonymous visit sets no cookie and requests nothing
from any other host.
"""
import base64
import json
import os
import sys
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright

HOME = "/future-saints/"
SAINTS = "/future-saints/saints/"
HOME_WIDTHS = (1440, 1024, 768, 390, 360)
INDEX_WIDTHS = (1440, 390)

CARD_BOXES_JS = """() => Array.from(document.querySelectorAll('[data-fs-subject-cards] > li'))
  .map(li => { const b = li.getBoundingClientRect(); return {top: Math.round(b.top), left: Math.round(b.left), width: Math.round(b.width)}; })"""
FEATURE_JS = """() => { const f = document.querySelector('[data-fs-feature]').getBoundingClientRect();
  const row = document.querySelector('[data-fs-subject-cards]').getBoundingClientRect();
  return {feature: Math.round(f.width), row: Math.round(row.width), below: f.top > row.bottom - 1}; }"""


def main():
    base, out = sys.argv[1].rstrip("/"), sys.argv[2]
    comp = sys.argv[3] if len(sys.argv) > 3 else ""
    os.makedirs(out, exist_ok=True)
    host = urlparse(base).netloc
    failures, notes = [], []

    def check(ok, label):
        (notes if ok else failures).append(("PASS " if ok else "FAIL ") + label)

    with sync_playwright() as p:
        browser = p.chromium.launch()

        def context(width, height=900):
            return browser.new_context(viewport={"width": width, "height": height}, device_scale_factor=2)

        # Screenshots + card layout
        for width in HOME_WIDTHS:
            ctx = context(width)
            page = ctx.new_page()
            foreign = []
            page.on("request", lambda r: foreign.append(r.url) if urlparse(r.url).netloc != host and not r.url.startswith("data:") else None)
            page.goto(base + HOME, wait_until="networkidle")
            page.screenshot(path=f"{out}/home-{width}.png", full_page=True)
            boxes = page.evaluate(CARD_BOXES_JS)
            tops = {b["top"] for b in boxes}
            lefts = {b["left"] for b in boxes}
            if width >= 1024:
                check(len(boxes) == 4 and len(tops) == 1, f"{width}: four subject cards in one row ({len(tops)} row(s))")
            elif width == 768:
                check(len(tops) == 2 and len(lefts) == 2, f"{width}: subject cards 2x2")
            else:
                check(len(lefts) == 1, f"{width}: subject cards one column")
            feature = page.evaluate(FEATURE_JS)
            check(feature["below"] and abs(feature["feature"] - feature["row"]) <= 2,
                  f"{width}: Holy Land card full width below the four ({feature})")
            check(not foreign, f"{width}: no third-party requests {foreign[:3]}")
            check(ctx.cookies() == [], f"{width}: no cookies after an anonymous visit")
            ctx.close()

        for width in INDEX_WIDTHS:
            ctx = context(width)
            page = ctx.new_page()
            page.goto(base + SAINTS, wait_until="networkidle")
            page.screenshot(path=f"{out}/saints-index-{width}.png", full_page=True)
            check(ctx.cookies() == [], f"saints index {width}: no cookies")
            ctx.close()

        # Mobile menu: keyboard open, Esc closes, focus returns
        ctx = context(390)
        page = ctx.new_page()
        page.goto(base + HOME, wait_until="networkidle")
        button = page.locator("[data-fs-menu-button]")
        check(button.is_visible() and not page.locator("#fs-nav").is_visible(), "390: menu collapsed behind a visible button")
        for _ in range(4):
            page.keyboard.press("Tab")
            if page.evaluate("() => document.activeElement.hasAttribute('data-fs-menu-button')"):
                break
        check(page.evaluate("() => document.activeElement.hasAttribute('data-fs-menu-button')"), "menu button reachable by Tab")
        page.keyboard.press("Enter")
        check(button.get_attribute("aria-expanded") == "true" and page.locator("#fs-nav").is_visible(), "Enter opens the menu")
        page.screenshot(path=f"{out}/home-390-menu-open.png")
        page.keyboard.press("Tab")
        page.keyboard.press("Escape")
        check(button.get_attribute("aria-expanded") == "false" and not page.locator("#fs-nav").is_visible(), "Esc closes the menu")
        check(page.evaluate("() => document.activeElement.hasAttribute('data-fs-menu-button')"), "focus returns to the menu button")
        ctx.close()

        # Without JavaScript the page still works
        ctx = browser.new_context(viewport={"width": 1440, "height": 900}, java_script_enabled=False)
        page = ctx.new_page()
        page.goto(base + HOME)
        check(page.locator("#fs-nav").is_visible(), "no-JS: section nav visible at 1440")
        ctx.close()

        # Staff view (optional)
        session = os.environ.get("FS_STAFF_SESSION", "")
        if session:
            ctx = context(1440)
            ctx.add_cookies([{"name": "sessionid", "value": session, "url": base}])
            page = ctx.new_page()
            page.goto(base + HOME, wait_until="networkidle")
            page.screenshot(path=f"{out}/home-1440-staff.png", full_page=True)
            check(page.locator("[data-fs-phase4]").count() == 2, "staff: Phase 4 map + quiz placeholders shown")
            check(page.get_by_text("(coming soon)").count() == 1, "staff: Map shown as coming soon")
            page.goto(base + SAINTS, wait_until="networkidle")
            page.screenshot(path=f"{out}/saints-index-1440-staff.png", full_page=True)
            check(page.get_by_text("Stories are on the way!").count() == 1, "staff: empty index message")
            ctx.close()

        # Side by side with comp 01 at 1440 (first screen only)
        if comp:
            ctx = browser.new_context(viewport={"width": 1440, "height": 960}, device_scale_factor=1)
            page = ctx.new_page()
            page.goto(base + HOME, wait_until="networkidle")
            build = base64.b64encode(page.screenshot()).decode()
            ref = base64.b64encode(open(comp, "rb").read()).decode()
            page.set_content(
                "<body style='margin:0;font:16px sans-serif;background:#ddd;display:flex;gap:16px;padding:16px'>"
                f"<figure style='margin:0;flex:1'><figcaption><b>Comp 01</b> (reference, 'Kids' = Future Saints)</figcaption><img style='width:100%' src='data:image/png;base64,{ref}'></figure>"
                f"<figure style='margin:0;flex:1'><figcaption><b>Phase 1 build</b>, 1440 wide, first screen</figcaption><img style='width:100%' src='data:image/png;base64,{build}'></figure></body>"
            )
            page.set_viewport_size({"width": 2400, "height": 1000})
            page.screenshot(path=f"{out}/home-1440-vs-comp01.png", full_page=True)
            ctx.close()

        browser.close()

    print(json.dumps({"passed": notes, "failed": failures}, indent=1))
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
