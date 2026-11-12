"""Future Saints Phase 3 browser QA: the California Missions hub, the projects
guide and Build This Mission.

    python tools/future_saints_phase3_screens.py <base_url> <out_dir> [comp02_png]

Run against a local server with SOG_FUTURE_SAINTS=on after `manage.py
seed_mission_hub` (then publishing the index) and `manage.py
future_saints_dev_sample`. Needs Playwright with Chromium (the local sog-shots
image has both). Writes PNGs and PDFs to out_dir; exits 1 if any check fails.

Screenshots (device scale factor 2): the hub at 1440/1024/768/430/390/360;
its first screen at 1440 beside comp 02; the close-pin chooser at 390 (touch);
the projects guide at 1440 and 390; the mission sample's Build This Mission
section at 1440. PDFs: the three project print views and the guide's
checklist, each on US Letter and A4.

Checks: 200, no cookies, nothing requested from another host; 21 pins; the
selected panel never overlaps the map (beside it at >=1024, below it under
1024); keyboard: Tab walks the pins in founding order and Enter selects one
(aria-pressed, the panel and ?mission= update); touch: a tap between two close
pins opens the chooser, and choosing selects that mission; without JavaScript
a pin press reloads with that mission selected; the three lists hold 21 each;
every print view is exactly one page on Letter and on A4.
"""
import base64
import os
import re
import sys
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright

HUB = "/future-saints/california-missions/"
GUIDE = "/future-saints/california-missions/projects/"
MISSION = "/future-saints/california-missions/mission-san-diego-de-alcala-sample/"
VIEWPORTS = (1440, 1024, 768, 430, 390, 360)

PINS_JS = """() => Array.from(document.querySelectorAll('[data-fs-pin]')).map(b => {
  const r = b.getBoundingClientRect(); return {slug: b.value, x: r.left + r.width / 2, y: r.top + r.height / 2,
  pressed: b.getAttribute('aria-pressed'), label: b.getAttribute('aria-label')}; })"""
BOXES_JS = """() => { const m = document.querySelector('.fs-map').getBoundingClientRect();
  const p = document.querySelector('#mission-panel').getBoundingClientRect();
  return {map: [m.left, m.top, m.right, m.bottom], panel: [p.left, p.top, p.right, p.bottom]}; }"""


def pdf_pages(data):
    return len(re.findall(rb"/Type\s*/Page[^s]", data))


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

        # The hub at every viewport: status, cookies, hosts, pins, panel placement.
        for width in VIEWPORTS:
            ctx = context(width)
            page = ctx.new_page()
            foreign = []
            page.on("request", lambda r: foreign.append(r.url) if urlparse(r.url).netloc not in (host, "") and not r.url.startswith("data:") else None)
            response = page.goto(base + HUB, wait_until="networkidle")
            check(response.status == 200, f"hub {width}: 200")
            check(ctx.cookies() == [], f"hub {width}: no cookies")
            check(not foreign, f"hub {width}: nothing from another host {foreign[:3]}")
            pins = page.evaluate(PINS_JS)
            check(len(pins) == 21, f"hub {width}: 21 pins")
            boxes = page.evaluate(BOXES_JS)
            m, pn = boxes["map"], boxes["panel"]
            overlap = not (pn[0] >= m[2] - .5 or pn[2] <= m[0] + .5 or pn[1] >= m[3] - .5 or pn[3] <= m[1] + .5)
            check(not overlap, f"hub {width}: the panel never covers the map")
            if width >= 1024:
                check(pn[0] >= m[2] - .5, f"hub {width}: panel to the right of the map")
            else:
                check(pn[1] >= m[3] - .5, f"hub {width}: panel below the map")
            page.screenshot(path=f"{out}/hub-{width}.png", full_page=True)
            ctx.close()

        # Keyboard: Tab order = founding order; Enter selects and updates the URL.
        ctx = context(1440)
        page = ctx.new_page()
        page.goto(base + HUB, wait_until="networkidle")
        page.focus("[data-fs-pin]")
        order = [page.evaluate("() => document.activeElement.value")]
        for _ in range(20):
            page.keyboard.press("Tab")
            order.append(page.evaluate("() => document.activeElement.value"))
        numbers = [int(re.search(r"Founding number (\d+)", pin["label"]).group(1)) for pin in page.evaluate(PINS_JS)]
        slugs_by_number = {n: pin["slug"] for n, pin in zip(numbers, page.evaluate(PINS_JS))}
        check(order == [slugs_by_number[n] for n in range(1, 22)], "keyboard: Tab walks the pins in founding order")
        page.focus(f'[data-fs-pin][value="{slugs_by_number[12]}"]')
        page.keyboard.press("Enter")
        page.wait_for_timeout(200)
        check(page.get_attribute(f'[data-fs-pin][value="{slugs_by_number[12]}"]', "aria-pressed") == "true", "keyboard: Enter selects (aria-pressed)")
        check(f"mission={slugs_by_number[12]}" in page.url, "keyboard: the URL shares the selection (?mission=)")
        check("Santa Cruz" in page.inner_text("[data-fs-panel-name]"), "keyboard: the panel shows the selection")
        check(page.evaluate("() => sessionStorage.length + localStorage.length") == 0 and ctx.cookies() == [], "hub: stores nothing")
        ctx.close()

        # Touch: a tap between Santa Clara (#8) and San José (#14) opens the chooser.
        ctx = context(390, 844, has_touch=True, is_mobile=True)
        page = ctx.new_page()
        page.goto(base + HUB, wait_until="networkidle")
        check(page.evaluate("() => matchMedia('(pointer: coarse)').matches"), "touch: pointer is coarse")
        pins = {int(re.search(r"Founding number (\d+)", pin["label"]).group(1)): pin for pin in page.evaluate(PINS_JS)}
        a, b = pins[8], pins[14]
        page.locator(".fs-map").scroll_into_view_if_needed()
        pins = {int(re.search(r"Founding number (\d+)", pin["label"]).group(1)): pin for pin in page.evaluate(PINS_JS)}
        a, b = pins[8], pins[14]
        page.mouse.click((a["x"] + b["x"]) / 2, (a["y"] + b["y"]) / 2)
        page.wait_for_timeout(200)
        chooser_open = page.is_visible("[data-fs-chooser]")
        check(chooser_open, "touch: a tap near two pins opens the chooser")
        if chooser_open:
            choices = page.locator(".fs-pin-choice").all_inner_texts()
            check(len(choices) >= 2, f"touch: the chooser lists the close pins {choices}")
            page.locator(".fs-map").screenshot(path=f"{out}/hub-390-close-pin-chooser.png")
            page.locator(".fs-pin-choice", has_text="#14").click()
            page.wait_for_timeout(200)
            check("San José" in page.inner_text("[data-fs-panel-name]") and page.is_hidden("[data-fs-chooser]"),
                  "touch: choosing selects that mission and closes the chooser")
        ctx.close()

        # Without JavaScript: a pin press reloads with that mission; three lists of 21.
        ctx = context(1440, java_script_enabled=False)
        page = ctx.new_page()
        page.goto(base + HUB, wait_until="networkidle")
        target = page.locator("[data-fs-pin]").nth(9)
        slug = target.get_attribute("value")
        target.click()
        page.wait_for_load_state("networkidle")
        check(f"mission={slug}" in page.url and page.get_attribute(f'[data-fs-pin][value="{slug}"]', "aria-pressed") == "true",
              "no JavaScript: a pin press reloads with that mission selected")
        for list_id in ("list-order", "list-ns", "list-az"):
            check(page.locator(f"#{list_id} li").count() == 21, f"no JavaScript: {list_id} has 21")
        ctx.close()

        # Comp 02 side by side.
        if comp:
            ctx = context(1440, 1000)
            page = ctx.new_page()
            page.goto(base + HUB, wait_until="networkidle")
            build = base64.b64encode(page.screenshot()).decode()
            ref = base64.b64encode(open(comp, "rb").read()).decode()
            page.set_content(
                "<body style='margin:0;display:flex;gap:16px;font:16px sans-serif;padding:16px;background:#eee'>"
                f"<figure style='margin:0;flex:1'><figcaption><b>Comp 02</b> (layout and style reference only; not a pin dataset)</figcaption><img style='width:100%' src='data:image/png;base64,{ref}'></figure>"
                f"<figure style='margin:0;flex:1'><figcaption><b>Phase 3 hub</b>, 1440 wide, first screen, sample text, pins from canonical lat/lng</figcaption><img style='width:100%' src='data:image/png;base64,{build}'></figure></body>"
            )
            page.screenshot(path=f"{out}/hub-1440-vs-comp02.png", full_page=True)
            ctx.close()

        # The projects guide and the Build This Mission sample.
        for width in (1440, 390):
            ctx = context(width)
            page = ctx.new_page()
            check(page.goto(base + GUIDE, wait_until="networkidle").status == 200, f"guide {width}: 200")
            page.screenshot(path=f"{out}/projects-guide-{width}.png", full_page=True)
            ctx.close()
        ctx = context(1440)
        page = ctx.new_page()
        check(page.goto(base + MISSION, wait_until="networkidle").status == 200, "mission sample: 200")
        check(page.locator(".fs-lcards a[href='#build']").count() == 1, "mission sample: the fourth card goes to the project")
        page.locator("#build").screenshot(path=f"{out}/san-diego-sample-project-1440.png")

        # Print views: exactly one page on Letter and on A4.
        sheets = [(MISSION + "?print=materials", "project-materials"), (MISSION + "?print=steps", "project-steps"),
                  (MISSION + "?print=factcard", "project-fact-card"), (GUIDE + "?print=checklist", "guide-checklist")]
        for url, name in sheets:
            page.goto(base + url, wait_until="networkidle")
            for fmt in ("Letter", "A4"):
                data = page.pdf(format=fmt, print_background=True)
                with open(f"{out}/{name}-{fmt.lower()}.pdf", "wb") as fh:
                    fh.write(data)
                check(pdf_pages(data) == 1, f"print {name} on {fmt}: one page ({pdf_pages(data)})")
        ctx.close()
        browser.close()

    print(f"\n{len(passed)} passed, {len(failed)} failed")
    for label in failed:
        print("  FAILED:", label)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
