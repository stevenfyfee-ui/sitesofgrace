"""Future Saints Phase 2a browser QA: the five learning templates.

    python tools/future_saints_phase2_screens.py <base_url> <out_dir> [comp03_png]

Run against a local server with SOG_FUTURE_SAINTS=on after
`manage.py future_saints_dev_sample`. Needs Playwright with Chromium (the
local sog-shots image has both). Set FS_STAFF_SESSION to a local staff
sessionid to also check staff-only slots. Writes PNGs and one PDF to out_dir;
exits 1 if any check fails.

Screenshots (device scale factor 2): the saint sample at 1440/1024/768/390
and its first screen at 1440 beside comp 03; each other type at 1440 and 390;
the Saints index; a Letter print preview as PDF.

Checks, on every type: 200, no cookies, nothing requested from another host,
four learning cards in one row at 1440 each linking to a section on the page.
On the saint sample: the reading-level pill works from the keyboard
(aria-pressed, body class, ?level=, sessionStorage, no cookie) and switching
moves nothing; the cards and the print link are keyboard links; the quiz runs
start to finish from the keyboard with feedback in an aria-live region,
storing and sending nothing.
"""
import base64
import json
import os
import sys
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright

PAGES = {
    "saint": "/future-saints/saints/st-francis-of-assisi-sample/",
    "marian": "/future-saints/marian-apparitions/lourdes-sample/",
    "eucharistic": "/future-saints/eucharistic-miracles/eucharistic-miracle-of-lanciano-sample/",
    "holy-land": "/future-saints/holy-land/church-of-the-holy-sepulchre-sample/",
    "mission": "/future-saints/california-missions/mission-san-diego-de-alcala-sample/",
}
SAINTS_INDEX = "/future-saints/saints/"

CARDS_JS = """() => Array.from(document.querySelectorAll('.fs-lcards .fs-lcard')).map(a => {
  const b = a.getBoundingClientRect(); const id = a.getAttribute('href').slice(1);
  return {top: Math.round(b.top + window.scrollY), target: !!document.getElementById(id), href: a.getAttribute('href')}; })"""


def main():
    base, out = sys.argv[1].rstrip("/"), sys.argv[2]
    comp = sys.argv[3] if len(sys.argv) > 3 else ""
    os.makedirs(out, exist_ok=True)
    host = urlparse(base).netloc
    passed, failed = [], []

    def check(ok, label):
        (passed if ok else failed).append(label)

    with sync_playwright() as p:
        browser = p.chromium.launch()

        def context(width, height=900, **kw):
            return browser.new_context(viewport={"width": width, "height": height}, device_scale_factor=2, **kw)

        # Every type: status, cookies, hosts, cards; screenshots at 1440 and 390.
        for name, path in PAGES.items():
            widths = (1440, 1024, 768, 390) if name == "saint" else (1440, 390)
            for width in widths:
                ctx = context(width)
                page = ctx.new_page()
                foreign = []
                page.on("request", lambda r: foreign.append(r.url)
                        if urlparse(r.url).netloc != host and not r.url.startswith("data:") else None)
                response = page.goto(base + path, wait_until="networkidle")
                page.screenshot(path=f"{out}/{name}-{width}.png", full_page=True)
                if width == 1440:
                    check(response.status == 200, f"{name}: 200")
                    cards = page.evaluate(CARDS_JS)
                    check(len(cards) == 4 and len({c["top"] for c in cards}) == 1,
                          f"{name} 1440: four learning cards in one row")
                    check(all(c["target"] for c in cards), f"{name}: every card links to a section on the page {[c['href'] for c in cards]}")
                check(not foreign, f"{name} {width}: nothing requested from another host {foreign[:2]}")
                check(ctx.cookies() == [], f"{name} {width}: no cookies")
                ctx.close()

        ctx = context(1440)
        page = ctx.new_page()
        page.goto(base + SAINTS_INDEX, wait_until="networkidle")
        page.screenshot(path=f"{out}/saints-index-1440.png", full_page=True)
        check(page.locator(".fs-cards--three a.fs-card").count() >= 1, "Saints index lists its sample as a card")
        ctx.close()

        # Saint sample: reading level, keyboard, layout stays put.
        ctx = context(1440)
        page = ctx.new_page()
        page.goto(base + PAGES["saint"], wait_until="networkidle")
        explorer = page.locator('.fs-pill [data-fs-level][value="explorer"]')
        researcher = page.locator('.fs-pill [data-fs-level][value="researcher"]')
        check(explorer.get_attribute("aria-pressed") == "true", "pill: Grades 2–3 pressed by default")
        before = page.evaluate(CARDS_JS)
        researcher.focus()
        page.keyboard.press("Enter")
        check(researcher.get_attribute("aria-pressed") == "true" and explorer.get_attribute("aria-pressed") == "false",
              "pill: Enter on Grades 4–5 sets aria-pressed")
        check(page.evaluate("() => document.body.classList.contains('fs-level-researcher')"), "pill: body switches to researcher")
        check(page.locator('#story [data-level="researcher"]').is_visible() and not page.locator('#story [data-level="explorer"]').is_visible(),
              "pill: the story shows the researcher text only")
        after = page.evaluate(CARDS_JS)
        check([c["top"] for c in before] == [c["top"] for c in after], "pill: switching level moves nothing above the fold")
        check("level=researcher" in page.url, "pill: ?level= in the address")
        check(page.evaluate("() => sessionStorage.getItem('fs-reading-level')") == "researcher", "pill: sessionStorage holds the level")
        check(page.evaluate("() => document.cookie") == "" and ctx.cookies() == [], "pill: no cookie")
        explorer.focus()
        page.keyboard.press("Space")
        check(explorer.get_attribute("aria-pressed") == "true", "pill: Space on Grades 2–3 switches back")

        first_card = page.locator(".fs-lcard").first
        first_card.focus()
        check(page.evaluate("() => document.activeElement.classList.contains('fs-lcard')"), "cards: reachable by keyboard")
        page.keyboard.press("Enter")
        check(page.url.endswith("#story"), "cards: Enter jumps to the section")

        page.evaluate("() => { window.__printed = 0; window.print = () => { window.__printed += 1; }; }")
        page.locator("[data-fs-print]").focus()
        page.keyboard.press("Enter")
        check(page.evaluate("() => window.__printed") == 1, "print link: Enter opens the print dialog")
        ctx.close()

        # Quiz from the keyboard; nothing stored or sent.
        ctx = context(1440)
        page = ctx.new_page()
        page.goto(base + PAGES["saint"] + "#quiz", wait_until="networkidle")
        requests_after_load = []
        page.on("request", lambda r: requests_after_load.append(r.url))
        storage_before = page.evaluate("() => JSON.stringify(Object.keys(sessionStorage).concat(Object.keys(localStorage)))")
        check(page.locator("[data-fs-quiz]").is_visible(), "quiz: shown with JavaScript")
        check(page.locator("[data-fs-quiz-feedback]").get_attribute("aria-live") == "polite", "quiz: feedback is an aria-live region")
        for n in range(5):
            choice = page.locator(".fs-quiz-choice").nth(n % 4)
            choice.focus()
            page.keyboard.press("Enter")
            check(page.locator("[data-fs-quiz-feedback]").inner_text().strip() != "", f"quiz: feedback after answer {n + 1}")
            if n < 4:
                check(page.evaluate("() => document.activeElement.hasAttribute('data-fs-quiz-next')"), f"quiz: focus moves to Next after {n + 1}")
                page.keyboard.press("Enter")
            else:
                check(page.evaluate("() => document.activeElement.hasAttribute('data-fs-quiz-finish')"), "quiz: focus moves to Finish")
                page.keyboard.press("Enter")
        check("out of 5" in page.locator("[data-fs-quiz-prompt]").inner_text(), "quiz: score shown in the page")
        page.locator("[data-fs-quiz-retry]").focus()
        page.keyboard.press("Enter")
        check("Question 1 of 5" in page.locator("[data-fs-quiz-progress]").inner_text(), "quiz: Try again starts over")
        check(not requests_after_load, f"quiz: sent nothing {requests_after_load[:2]}")
        storage_after = page.evaluate("() => JSON.stringify(Object.keys(sessionStorage).concat(Object.keys(localStorage)))")
        check(storage_before == storage_after and ctx.cookies() == [], "quiz: stored nothing")
        ctx.close()

        # Staff-only slots (optional).
        session = os.environ.get("FS_STAFF_SESSION", "")
        if session:
            ctx = context(1440)
            ctx.add_cookies([{"name": "sessionid", "value": session, "url": base}])
            page = ctx.new_page()
            page.goto(base + PAGES["mission"], wait_until="networkidle")
            check(page.locator("#build").count() == 1, "staff: Build This Mission slot shown as coming soon")
            check(page.get_by_text("Art needed: hero portrait (3:4)").count() == 1, "staff: art-needed label on the hero frame")
            page.screenshot(path=f"{out}/mission-1440-staff.png", full_page=True)
            ctx.close()
        anon = browser.new_context()
        page = anon.new_page()
        page.goto(base + PAGES["mission"], wait_until="networkidle")
        check(page.locator("#build").count() == 0 and page.get_by_text("Art needed").count() == 0,
              "visitors: no Build slot and no art-needed labels")
        anon.close()

        # Print preview (US Letter) as a PDF.
        ctx = browser.new_context()
        page = ctx.new_page()
        page.goto(base + PAGES["saint"], wait_until="networkidle")
        page.emulate_media(media="print")
        page.pdf(path=f"{out}/saint-research-sheet-letter.pdf", format="Letter", print_background=True)
        check(page.locator(".fs-print-sheet").is_visible() and not page.locator(".fs-lcards").is_visible(),
              "print: the research sheet shows; cards, nav and quiz are hidden")
        ctx.close()

        # Comp 03 beside the saint sample's first screen at 1440.
        if comp:
            ctx = browser.new_context(viewport={"width": 1440, "height": 960}, device_scale_factor=1)
            page = ctx.new_page()
            page.goto(base + PAGES["saint"], wait_until="networkidle")
            build = base64.b64encode(page.screenshot()).decode()
            ref = base64.b64encode(open(comp, "rb").read()).decode()
            page.set_content(
                "<body style='margin:0;font:16px sans-serif;background:#ddd;display:flex;gap:16px;padding:16px'>"
                f"<figure style='margin:0;flex:1'><figcaption><b>Comp 03</b> (reference; 'Kids' = Future Saints)</figcaption><img style='width:100%' src='data:image/png;base64,{ref}'></figure>"
                f"<figure style='margin:0;flex:1'><figcaption><b>Phase 2a saint template</b>, 1440 wide, first screen, sample data</figcaption><img style='width:100%' src='data:image/png;base64,{build}'></figure></body>"
            )
            page.set_viewport_size({"width": 2400, "height": 1000})
            page.screenshot(path=f"{out}/saint-1440-vs-comp03.png", full_page=True)
            ctx.close()
        browser.close()

    print(json.dumps({"passed": len(passed), "failed": failed}, indent=1))
    for line in passed:
        print("PASS", line)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
