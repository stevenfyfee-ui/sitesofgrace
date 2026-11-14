"""Future Saints search: screenshots and the browser checks.

    python tools/future_saints_search_screens.py <base_url> <out_dir>

Captures the homepage search with suggestions open (1440 and 390), the map search selecting a
story, the results page and the empty state, and checks the combobox, the map selection, the
"not on the map yet" note, privacy (no cookies, no storage, the query never leaves the browser
while typing) and the no-JavaScript form. Exits 1 if any check fails. Needs Playwright with
Chromium (the local sog-shots image) and the local sample stories.
"""
import os
import sys
from urllib.parse import quote

from playwright.sync_api import sync_playwright

HOME = "/future-saints/"
MAP = "/future-saints/map/"
SEARCH = "/future-saints/search/"


def main():
    base, out = sys.argv[1].rstrip("/"), sys.argv[2]
    os.makedirs(out, exist_ok=True)
    passed, failed = [], []

    def check(ok, label):
        (passed if ok else failed).append(label)
        print(("PASS " if ok else "FAIL ") + label)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        for width in (1440, 390):
            ctx = browser.new_context(viewport={"width": width, "height": 900}, device_scale_factor=2)
            page = ctx.new_page()
            sent = []
            page.on("request", lambda r: sent.append(r.url))
            page.goto(base + HOME, wait_until="networkidle")
            check(page.locator(".fs-search-link").is_visible(), f"{width}: the header search icon is visible")
            box = page.locator("#fs-home-search-q")
            check(box.get_attribute("role") == "combobox", f"{width}: the home box is a combobox")
            check(box.get_attribute("placeholder") == "Try Carlo, Fátima, or San Diego", f"{width}: placeholder")
            before = len(sent)
            box.click()
            box.type("car", delay=60)
            page.wait_for_selector("#fs-home-search-list:not([hidden]) [role=option]")
            page.wait_for_timeout(200)
            titles = page.locator("#fs-home-search-list [role=option] .fs-search-option-title").all_inner_texts()
            check(any("Carlo" in t for t in titles), f"{width}: 'car' suggests Carlo")
            check(box.get_attribute("aria-expanded") == "true", f"{width}: aria-expanded is true while open")
            status = page.locator(".fs-search--home [data-fs-search-status]").inner_text()
            check(status.endswith("found"), f"{width}: the live region announces the count ({status!r})")
            fetched = sent[before:]
            check(all(u.endswith("/future-saints/search/index/") for u in fetched) and len(fetched) <= 1,
                  f"{width}: typing sends nothing but one fetch of the index ({fetched})")
            # From the top of the page (the header's search icon) to the bottom of the open list.
            bottom = page.evaluate("() => { const r = document.querySelector('#fs-home-search-list').getBoundingClientRect();"
                                   " return r.bottom + window.scrollY; }")
            page.screenshot(path=f"{out}/home-search-{width}.png", full_page=True,
                            clip={"x": 0, "y": 0, "width": width, "height": bottom + 30})
            if width == 1440:
                box.press("ArrowDown")
                active = box.get_attribute("aria-activedescendant")
                check(bool(active) and page.locator(f"#{active}").get_attribute("aria-selected") == "true",
                      "keyboard: ArrowDown highlights the first suggestion")
                box.press("Escape")
                check(page.locator("#fs-home-search-list").is_hidden(), "keyboard: Escape closes the list")
                box.fill("")
                box.type("fatma", delay=40)
                page.wait_for_selector("#fs-home-search-list:not([hidden]) [role=option]")
                page.wait_for_timeout(200)
                titles = page.locator("#fs-home-search-list .fs-search-option-title").all_inner_texts()
                check(any("Fátima" in t for t in titles), "one letter off: 'fatma' finds Fátima")
                box.fill("")
                box.type("zzqx", delay=40)
                page.wait_for_timeout(400)
                check(page.locator(".fs-search--home [data-fs-search-status]").inner_text()
                      == "No stories found. Try another word!", "no match: the live region says so")
                box.fill("")
                box.type("lourd", delay=40)
                page.wait_for_selector("#fs-home-search-list:not([hidden]) [role=option]")
                page.wait_for_timeout(200)
                box.press("ArrowDown")
                with page.expect_navigation():
                    box.press("Enter")
                check("lourdes" in page.url, f"keyboard: Enter opens the story ({page.url})")
                storage = page.evaluate("() => [localStorage.length, sessionStorage.length, document.cookie]")
                check(storage == [0, 0, ""], f"privacy: no storage and no cookies ({storage})")
            ctx.close()

        # The map search selects and zooms to a story; one with no pin shows the note.
        ctx = browser.new_context(viewport={"width": 1440, "height": 1000}, device_scale_factor=2)
        page = ctx.new_page()
        page.goto(base + MAP, wait_until="networkidle")
        box = page.locator("#fs-map-search-q")
        box.click()
        box.type("lourdes", delay=50)
        page.wait_for_selector("#fs-map-search-list:not([hidden]) [role=option]")
        page.wait_for_timeout(200)
        page.locator("#fs-map-search-list [role=option]").first.click()
        page.wait_for_timeout(900)
        title = page.locator("[data-fs-card-title]").inner_text()
        check("Lourdes" in title, f"map: choosing Lourdes selects its card ({title!r})")
        level = float(page.locator(".fs-world-explore [data-fs-zoom]").get_attribute("data-fs-zoom-level") or 1)
        check(level > 1.5, f"map: and zooms to it ({level}x)")
        check("story=lourdes" in page.url, "map: the URL shares the story")
        page.evaluate("() => document.querySelector('.fs-search--map').scrollIntoView({block: 'start'})")
        page.wait_for_timeout(300)
        page.screenshot(path=f"{out}/map-search-1440.png")
        box.fill("")
        box.type("carlo", delay=50)
        page.wait_for_selector("#fs-map-search-list:not([hidden]) [role=option]")
        page.wait_for_timeout(200)
        page.locator("#fs-map-search-list [role=option]").first.click()
        page.wait_for_timeout(300)
        note = page.locator("[data-fs-search-note]")
        check(note.is_visible() and note.inner_text() == "This story isn't on the map yet.", "map: a story with no pin says so")
        page.evaluate("() => document.querySelector('.fs-search--map').scrollIntoView({block: 'start'})")
        page.screenshot(path=f"{out}/map-search-not-on-map-1440.png", clip={"x": 0, "y": 0, "width": 1440, "height": 420})
        box.fill("")
        box.type("san diego", delay=50)
        page.wait_for_selector("#fs-map-search-list:not([hidden]) [role=option]")
        page.wait_for_timeout(200)
        page.locator("#fs-map-search-list [role=option]").first.click()
        page.wait_for_timeout(900)
        level = float(page.locator(".fs-world-explore [data-fs-zoom]").get_attribute("data-fs-zoom-level") or 1)
        check(level > 1.5 and "San Diego" in page.locator("[data-fs-card-title]").inner_text(),
              f"map: a mission selects its card and zooms to the California callout ({level}x)")
        ctx.close()

        # The results page and the empty state, at both widths.
        for width in (1440, 390):
            ctx = browser.new_context(viewport={"width": width, "height": 900}, device_scale_factor=2)
            page = ctx.new_page()
            page.goto(base + SEARCH + "?q=" + quote("san diego"), wait_until="networkidle")
            check(page.locator(".fs-search-card").count() >= 1, f"{width}: the results page lists cards")
            page.screenshot(path=f"{out}/results-{width}.png", full_page=True)
            page.goto(base + SEARCH + "?q=zzqx", wait_until="networkidle")
            check(page.locator(".fs-search-empty-text").inner_text() == "No stories found. Try another word!",
                  f"{width}: the empty state")
            check(page.locator(".fs-search-suggest a").count() == 3, f"{width}: three suggestion links")
            page.screenshot(path=f"{out}/empty-{width}.png", full_page=True)
            ctx.close()

        # Without JavaScript: the box is a plain form; Enter shows the results page.
        ctx = browser.new_context(viewport={"width": 390, "height": 900}, java_script_enabled=False)
        page = ctx.new_page()
        page.goto(base + HOME, wait_until="networkidle")
        check(page.locator("#fs-home-search-q").get_attribute("role") is None, "no JS: a plain search field")
        page.locator("#fs-home-search-q").fill("lourdes")
        with page.expect_navigation():
            page.locator("#fs-home-search-q").press("Enter")
        check("/future-saints/search/?q=lourdes" in page.url and page.locator(".fs-search-card").count() >= 1,
              "no JS: Enter shows the results page")
        ctx.close()
        browser.close()

    print(f"\n{len(passed)} passed, {len(failed)} failed")
    for label in failed:
        print("  FAILED:", label)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
