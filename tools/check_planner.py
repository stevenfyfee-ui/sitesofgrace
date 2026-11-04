"""Browser check for Trip Planner v2 at 1440 and 390 px wide.

    python tools/check_planner.py http://localhost:8000

Needs Playwright with Chromium (requirements-dev.txt) and a local server with
SOG_PLANNER_V2=on and the planner content imported. For each width it:
starts from an empty /plan/, adds Rome by search with the keyboard (listbox),
adds Assisi from Popular, reorders the stops, changes nights, checks the
budget and the URL followed along, copies the share link, then opens that
link in a fresh page and checks the plan is the same. Writes nothing. Exits 1
on the first failure.
"""
import re
import sys

from playwright.sync_api import expect, sync_playwright

WIDTHS = (1440, 390)


def stops(page):
    return page.locator(".pv2-stop .pv2-stop-name").all_inner_texts()


def nights(page):
    return page.locator(".pv2-stop .pv2-nights-n").all_inner_texts()


def wait_settled(page):
    page.wait_for_function("() => !document.getElementById('pv2').hasAttribute('aria-busy')")


def run(base, width):
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport={"width": width, "height": 900}, permissions=["clipboard-read", "clipboard-write"])
        page = ctx.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(base + "/plan/", wait_until="networkidle")
        expect(page.locator(".pv2-empty")).to_be_visible()

        # Add by search, keyboard only.
        box = page.locator("#pv2-add-input")
        box.click()
        box.type("rome", delay=40)
        expect(page.locator("#pv2-results [role=option]").first).to_be_visible()
        expect(box).to_have_attribute("aria-expanded", "true")
        box.press("ArrowDown")
        box.press("ArrowUp")
        box.press("Enter")
        wait_settled(page)
        expect(page.locator(".pv2-stop")).to_have_count(1)
        assert stops(page) == ["Rome / Vatican City"], stops(page)

        # Add from Popular.
        page.locator(".pv2-chips a", has_text="Assisi").click()
        wait_settled(page)
        expect(page.locator(".pv2-stop")).to_have_count(2)
        assert stops(page) == ["Rome / Vatican City", "Assisi"], stops(page)

        # Reorder: Assisi earlier, then back.
        page.locator('.pv2-stop:nth-child(2) [data-action="up"]').click()
        wait_settled(page)
        assert stops(page) == ["Assisi", "Rome / Vatican City"], stops(page)
        page.locator('.pv2-stop:nth-child(1) [data-action="down"]').click()
        wait_settled(page)
        assert stops(page) == ["Rome / Vatican City", "Assisi"], stops(page)

        # Change nights: Rome to 4 (from its default), Assisi to 3.
        def set_nights(i, target):
            for _ in range(25):
                n = int(re.match(r"\d+", nights(page)[i]).group())
                if n == target:
                    return
                page.locator(f'.pv2-stop:nth-child({i + 1}) [data-action="{"inc" if n < target else "dec"}"]').click()
                wait_settled(page)
            raise AssertionError(f"couldn't set nights for stop {i}")

        set_nights(0, 4)
        set_nights(1, 3)
        page.select_option("#pv2-party", "2")
        page.select_option("#pv2-tier", "mid")
        page.fill("#pv2-date", "2027-05-10")
        page.locator("#pv2-date").dispatch_event("change")
        page.wait_for_timeout(400)
        wait_settled(page)
        assert "t=rome-vatican-city.4,assisi.3&d=2027-05-10&p=2&l=mid&pace=3" in page.url, page.url
        total = page.locator(".pv2-total td").inner_text()
        assert total == "$4,265", total
        assert "$4,265" in page.locator("#pv2-live").inner_text()
        assert "$4,265" in page.locator("#pv2-mbar-total").inner_text()

        # Copy the share link, then open it fresh.
        page.locator("[data-share]").first.click()
        expect(page.locator("#pv2-toast")).to_be_visible()
        link = page.evaluate("navigator.clipboard.readText()")
        assert link.startswith(base) and "t=rome-vatican-city.4,assisi.3" in link, link
        days_before = page.locator("#pv2-days").inner_text()

        fresh = ctx.new_page()
        fresh.goto(link, wait_until="networkidle")
        assert stops(fresh) == ["Rome / Vatican City", "Assisi"], stops(fresh)
        assert nights(fresh) == ["4 nights", "3 nights"], nights(fresh)
        assert fresh.locator(".pv2-total td").inner_text() == "$4,265"
        assert fresh.locator("#pv2-days").inner_text() == days_before, "reloaded plan differs"

        # Without JavaScript the shared link renders the same plan.
        nojs = browser.new_context(viewport={"width": width, "height": 900}, java_script_enabled=False).new_page()
        nojs.goto(link)
        assert stops(nojs) == ["Rome / Vatican City", "Assisi"], stops(nojs)
        assert nojs.locator(".pv2-total td").inner_text() == "$4,265"

        assert not errors, errors
        browser.close()
    print(f"{width}px: ok (search, Popular, reorder, nights, share link, reload, no-JS)")


def main():
    base = (sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000").rstrip("/")
    for width in WIDTHS:
        run(base, width)


if __name__ == "__main__":
    main()
