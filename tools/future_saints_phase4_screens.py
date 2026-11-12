"""Future Saints Phase 4 browser QA: the World Discovery Map and the homepage blocks.

    python tools/future_saints_phase4_screens.py <base_url> <out_dir> [comp01_png]

Run against a local server with SOG_FUTURE_SAINTS=on after `manage.py
future_saints_dev_sample` (which publishes the map and schedules this week's saint).
Needs Playwright with Chromium (the local sog-shots image has both). Writes PNGs to
out_dir; exits 1 if any check fails.

Checks: the map at 1440/1024/768/430/390/360 (200, no cookies, nothing from another host,
the story card never over the map, beside it at >=1024 and below it under; no two markers
overlap at 1440); keyboard: Tab walks the markers in list order and Enter selects one
(aria-pressed, the card and ?story= update); filters hide markers and list items together and
"Show all" brings them back; touch: a tap between two close markers opens "Which story?";
without JavaScript a marker press reloads with that story in the card and the list is all
there; the homepage shows the map preview, the quiz block and a linked Saint of the Week.
"""
import base64
import os
import sys
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright

MAP = "/future-saints/map/"
HOME = "/future-saints/"
VIEWPORTS = (1440, 1024, 768, 430, 390, 360)
MARKERS_JS = """() => Array.from(document.querySelectorAll('[data-fs-world-pin]')).filter(b => !b.closest('[data-fs-kind]').hidden)
  .map(b => { const r = b.querySelector('.fs-wm-disc').getBoundingClientRect();
  return {key: b.value, box: [r.left, r.top, r.right, r.bottom], pressed: b.getAttribute('aria-pressed')}; })"""
BOXES_JS = """() => { const m = document.querySelector('.fs-wmap').getBoundingClientRect();
  const c = document.querySelector('#story-card').getBoundingClientRect();
  return {map: [m.left, m.top, m.right, m.bottom], card: [c.left, c.top, c.right, c.bottom]}; }"""


def boxes_overlap(a, b):
    return not (a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1])


def main():
    base, out = sys.argv[1].rstrip("/"), sys.argv[2]
    comp = sys.argv[3] if len(sys.argv) > 3 else ""
    os.makedirs(out, exist_ok=True)
    host = urlparse(base).netloc
    passed, failed = [], []

    def check(ok, label):
        (passed if ok else failed).append(label)
        print(("PASS " if ok else "FAIL ") + label)

    with sync_playwright() as p:
        browser = p.chromium.launch()

        def context(width, height=900, **kw):
            return browser.new_context(viewport={"width": width, "height": height}, device_scale_factor=2, **kw)

        for width in VIEWPORTS:
            ctx = context(width)
            page = ctx.new_page()
            foreign = []
            page.on("request", lambda r: foreign.append(r.url) if urlparse(r.url).netloc not in (host, "") and not r.url.startswith("data:") else None)
            check(page.goto(base + MAP, wait_until="networkidle").status == 200, f"map {width}: 200")
            check(ctx.cookies() == [], f"map {width}: no cookies")
            check(not foreign, f"map {width}: nothing from another host {foreign[:3]}")
            markers = page.evaluate(MARKERS_JS)
            check(len(markers) >= 3, f"map {width}: markers drawn ({len(markers)})")
            b = page.evaluate(BOXES_JS)
            check(not boxes_overlap(b["map"], b["card"]), f"map {width}: the story card never covers the map")
            if width >= 1024:
                check(b["card"][0] >= b["map"][2] - .5, f"map {width}: card to the right of the map")
            else:
                check(b["card"][1] >= b["map"][3] - .5, f"map {width}: card below the map")
            if width == 1440:
                clashes = [(m["key"], n["key"]) for i, m in enumerate(markers) for n in markers[i + 1:] if boxes_overlap(m["box"], n["box"])]
                check(not clashes, f"map 1440: no two markers overlap {clashes}")
            page.screenshot(path=f"{out}/map-{width}.png", full_page=True)
            ctx.close()

        # Keyboard, filters, comp 01.
        ctx = context(1440)
        page = ctx.new_page()
        page.goto(base + MAP, wait_until="networkidle")
        keys = [m["key"] for m in page.evaluate(MARKERS_JS)]
        page.focus("[data-fs-world-pin]")
        order = [page.evaluate("() => document.activeElement.value")]
        for _ in range(len(keys) - 1):
            page.keyboard.press("Tab")
            order.append(page.evaluate("() => document.activeElement.value"))
        check(order == keys, "keyboard: Tab walks the markers in list order")
        target = keys[-1]
        page.focus(f'[data-fs-world-pin][value="{target}"]')
        page.keyboard.press("Enter")
        page.wait_for_timeout(200)
        check(page.get_attribute(f'[data-fs-world-pin][value="{target}"]', "aria-pressed") == "true", "keyboard: Enter selects")
        check(f"story={target}" in page.url, "keyboard: ?story= shares the selection")
        check(page.is_visible("[data-fs-world-filters]"), "filters: shown with JavaScript")
        page.screenshot(path=f"{out}/map-1440-filters-all.png")
        page.click('[data-fs-filter="marian_apparition"]')
        hidden = page.evaluate("""() => ({markers: Array.from(document.querySelectorAll('.fs-wm-marker[data-fs-kind="marian_apparition"]')).every(e => e.hidden),
            items: Array.from(document.querySelectorAll('#all-stories [data-fs-kind="marian_apparition"]')).every(e => e.hidden),
            others: Array.from(document.querySelectorAll('.fs-wm-marker:not([data-fs-kind="marian_apparition"])')).every(e => !e.hidden)})""")
        check(hidden["markers"] and hidden["items"] and hidden["others"], "filters: one type off hides its markers and list items together")
        for kind in ("saint", "eucharistic_miracle", "holy_land", "california_mission"):
            page.click(f'[data-fs-filter="{kind}"]')
        page.click('[data-fs-filter="marian_apparition"]')
        page.screenshot(path=f"{out}/map-1440-filter-one-type.png")
        page.click("[data-fs-filter-all]")
        check(page.evaluate("() => Array.from(document.querySelectorAll('.fs-world [data-fs-kind]')).every(e => !e.hidden)"),
              "filters: Show all brings everything back")
        if comp:
            build = base64.b64encode(page.screenshot()).decode()
            ref = base64.b64encode(open(comp, "rb").read()).decode()
            page.set_content(
                "<body style='margin:0;display:flex;gap:16px;font:16px sans-serif;padding:16px;background:#eee'>"
                f"<figure style='margin:0;flex:1'><figcaption><b>Comp 01</b> (map hero style reference only)</figcaption><img style='width:100%' src='data:image/png;base64,{ref}'></figure>"
                f"<figure style='margin:0;flex:1'><figcaption><b>Phase 4 World Discovery Map</b>, 1440 wide, first screen, sample data</figcaption><img style='width:100%' src='data:image/png;base64,{build}'></figure></body>")
            page.screenshot(path=f"{out}/map-1440-vs-comp01.png", full_page=True)
        ctx.close()

        # Touch: a tap between Lourdes and Lanciano (close at 390) opens the chooser.
        ctx = context(390, 844, has_touch=True, is_mobile=True)
        page = ctx.new_page()
        page.goto(base + MAP, wait_until="networkidle")
        page.locator(".fs-wmap").scroll_into_view_if_needed()
        ms = {m["key"]: m["box"] for m in page.evaluate(MARKERS_JS)}
        near = [k for k in ms if "lourdes" in k] + [k for k in ms if "lanciano" in k]
        if len(near) == 2:
            a, b = ms[near[0]], ms[near[1]]
            page.mouse.click((a[0] + a[2] + b[0] + b[2]) / 4, (a[1] + a[3] + b[1] + b[3]) / 4)
            page.wait_for_timeout(200)
            check(page.is_visible("[data-fs-chooser]"), "touch: a tap near two markers opens Which story?")
            page.locator(".fs-wmap").screenshot(path=f"{out}/map-390-chooser.png")
            page.locator(".fs-pin-choice").first.click()
            page.wait_for_timeout(200)
            check(page.is_hidden("[data-fs-chooser]"), "touch: choosing closes the chooser")
        else:
            check(False, f"touch: Lourdes and Lanciano markers found ({near})")
        ctx.close()

        # No JavaScript.
        ctx = context(1440, java_script_enabled=False)
        page = ctx.new_page()
        page.goto(base + MAP, wait_until="networkidle")
        pin = page.locator("[data-fs-world-pin]").nth(1)
        key = pin.get_attribute("value")
        pin.click()
        page.wait_for_load_state("networkidle")
        check(f"story={key}" in page.url and page.get_attribute(f'[data-fs-world-pin][value="{key}"]', "aria-pressed") == "true",
              "no JavaScript: a marker press reloads with that story")
        check(page.locator("#all-stories li").count() >= 5, "no JavaScript: the list is all there")
        ctx.close()

        # Homepage blocks.
        for width in (1440, 390):
            ctx = context(width)
            page = ctx.new_page()
            check(page.goto(base + HOME, wait_until="networkidle").status == 200, f"home {width}: 200")
            check(page.locator("[data-fs-world-preview]").count() == 1, f"home {width}: the map preview")
            check(page.locator("[data-fs-quiz-card]").count() == 1, f"home {width}: the quiz block")
            check(page.locator("[data-fs-saint] a").count() >= 1, f"home {width}: Saint of the Week links to the story")
            check(ctx.cookies() == [], f"home {width}: no cookies")
            page.screenshot(path=f"{out}/home-{width}.png", full_page=True)
            if width == 1440:
                page.locator("[data-fs-saint-row]").screenshot(path=f"{out}/home-1440-saint-of-week-and-quiz.png")
                page.locator("[data-fs-world-preview]").screenshot(path=f"{out}/home-1440-map-preview.png")
            ctx.close()
        browser.close()

    print(f"\n{len(passed)} passed, {len(failed)} failed")
    for label in failed:
        print("  FAILED:", label)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
