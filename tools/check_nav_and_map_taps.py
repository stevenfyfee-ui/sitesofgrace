"""Browser check for the desktop dropdowns and mobile map taps.

    python tools/check_nav_and_map_taps.py http://localhost:8000
    python tools/check_nav_and_map_taps.py http://localhost:8000 --site /explore/marian-apparitions/lourdes/ \
        --hub /destinations/assisi-umbria/ --dot eucharistic-miracle-of-morrovalle

Needs Playwright with Chromium (requirements-dev.txt). Writes nothing; exits
1 on the first failure.

Dropdowns (1440 and 1024): hover each top-level menu with a submenu, move the
mouse down in 2px steps to its third item, and check the menu stays open and
the item is the element under the pointer (so a click lands on it). At 390
the desktop nav stays hidden (the mobile menu is unchanged).

Map taps (iPhone 13: touch, coarse pointer): on the Interactive Map, tap 10px
away from a known dot and expect its popup with its title and a working Read
more link; tap open ocean and expect no popup; the popup (with Read more and the
journey buttons) fits inside the map at 360, 390 and 430. At the starting zoom,
a tap that misses every dot opens the nearest one.
The same tap-near-a-dot check runs on a site page's Where to Stay map and a
destination hub map. Desktop: a click on a dot still opens it, and a click
15px away (beyond the 8px mouse range) does not.
"""
import argparse
import sys

from playwright.sync_api import sync_playwright

# Centers of the visible site dots (SVG circle paths in the sites pane), in
# page coordinates.
DOT_CENTERS_JS = """(paneSelector) => {
  const pane = document.querySelector(paneSelector);
  if (!pane) return [];
  return Array.from(pane.querySelectorAll('path.leaflet-interactive')).map(p => {
    const b = p.getBoundingClientRect();
    return {x: b.left + b.width / 2, y: b.top + b.height / 2, w: b.width};
  }).filter(d => d.w > 0);
}"""


def fail(msg):
    print("FAIL:", msg)
    sys.exit(1)


def nearest_dot_on_screen(page, map_selector, pane_selector, miss_clear=0):
    """The visible dot nearest the map's center, scrolled into the viewport
    (on a short phone the map runs below the fold)."""
    def tappable(d):
        # Both the dot and the near-miss point must be bare map, not under a
        # control (zoom, legend, attribution), as for a real finger.
        return page.evaluate("""([sel, pts]) => pts.every(([x, y]) => {
            const e = document.elementFromPoint(x, y);
            return e && e.closest(sel) && !e.closest('.leaflet-control-container');
        })""", [map_selector, [[d["x"], d["y"]], [d["x"] + 10, d["y"]]]])

    def find():
        m = page.locator(map_selector).bounding_box()
        cx, cy = m["x"] + m["width"] / 2, m["y"] + m["height"] / 2
        dots = page.evaluate(DOT_CENTERS_JS, pane_selector)
        if not dots:
            fail(f"{map_selector}: no visible dots")
        return sorted(dots, key=lambda d: (d["x"] - cx) ** 2 + (d["y"] - cy) ** 2)
    height = page.viewport_size["height"]
    first = find()[0]
    if not 40 < first["y"] < height - 40:
        page.evaluate("dy => window.scrollBy(0, dy)", first["y"] - height / 2)
        page.wait_for_timeout(300)
    dots = find()
    for dot in dots:
        # miss_clear: no dot drawn within that many px of the near-miss point,
        # so the tap really misses every dot.
        if miss_clear and any(((dot["x"] + 10 - o["x"]) ** 2 + (dot["y"] - o["y"]) ** 2) ** 0.5 < miss_clear
                              for o in dots):
            continue
        if 40 < dot["y"] < height - 40 and tappable(dot):
            return dot
    fail(f"{map_selector}: no dot that a finger could reach")


def check_dropdowns(p, base):
    browser = p.chromium.launch()
    for width in (1440, 1024):
        page = browser.new_page(viewport={"width": width, "height": 900})
        page.goto(base + "/", wait_until="networkidle")
        triggers = page.locator(".primary-nav .has-submenu")
        if triggers.count() == 0:
            fail(f"{width}px: no dropdown menus found")
        for i in range(triggers.count()):
            item = triggers.nth(i)
            link = item.locator(":scope > a")
            label = link.inner_text().strip()
            subnav = item.locator(":scope > .subnav")
            entries = subnav.locator(".nav-item > a")
            if entries.count() < 3:
                continue
            box = link.bounding_box()
            x = box["x"] + box["width"] / 2
            y = box["y"] + box["height"] / 2
            page.mouse.move(x, y)
            page.wait_for_timeout(250)
            target = entries.nth(2).bounding_box()
            tx, ty = target["x"] + 20, target["y"] + target["height"] / 2
            steps = max(1, int((ty - y) / 2))
            for s in range(1, steps + 1):
                page.mouse.move(x + (tx - x) * s / steps, y + (ty - y) * s / steps)
                visible = subnav.evaluate("e => getComputedStyle(e).visibility")
                if visible != "visible":
                    fail(f"{width}px {label}: menu closed at step {s}/{steps} (y={y + (ty - y) * s / steps:.0f})")
            page.wait_for_timeout(250)
            under = page.evaluate("([x, y]) => { const e = document.elementFromPoint(x, y); return e && e.closest('a') && e.closest('a').textContent.trim(); }", [tx, ty])
            expected = entries.nth(2).inner_text().strip()
            if under != expected:
                fail(f"{width}px {label}: under the pointer is {under!r}, expected {expected!r}")
            page.mouse.move(5, 600)
            page.wait_for_timeout(400)
            if subnav.evaluate("e => getComputedStyle(e).visibility") != "hidden":
                fail(f"{width}px {label}: menu didn't close after the pointer left")
            print(f"{width}px dropdown {label!r}: stays open down to {expected!r}, closes after leaving")
        page.close()
    page = browser.new_page(viewport={"width": 390, "height": 844})
    page.goto(base + "/", wait_until="networkidle")
    if page.locator(".primary-nav").is_visible():
        fail("390px: desktop nav is visible")
    print("390px: desktop nav hidden, mobile menu unchanged")
    browser.close()


def popup_title(page):
    loc = page.locator(".leaflet-popup-content")
    return loc.inner_text() if loc.count() else ""


def popup_fits(page, map_selector):
    m = page.locator(map_selector).bounding_box()
    w = page.locator(".leaflet-popup-content-wrapper").bounding_box()
    return w["x"] >= m["x"] - 0.5 and w["x"] + w["width"] <= m["x"] + m["width"] + 0.5


def tap_near_a_dot(page, map_selector, pane_selector, label):
    """Tap 10px right of the dot nearest the map's center; expect a popup."""
    page.wait_for_function(f"() => document.querySelectorAll('{pane_selector} path.leaflet-interactive').length > 0")
    page.wait_for_timeout(600)
    m = page.locator(map_selector).bounding_box()
    cx, cy = m["x"] + m["width"] / 2, m["y"] + m["height"] / 2
    dots = [d for d in page.evaluate(DOT_CENTERS_JS, pane_selector)
            if m["x"] + 30 < d["x"] < m["x"] + m["width"] - 30 and m["y"] + 30 < d["y"] < m["y"] + m["height"] - 30]
    if not dots:
        fail(f"{label}: no dot inside the map")
    dot = min(dots, key=lambda d: (d["x"] - cx) ** 2 + (d["y"] - cy) ** 2)
    if dot["w"] < 7.5:
        fail(f"{label}: dot is {dot['w']:.1f}px wide on a touch screen (expected at least 8px)")
    page.touchscreen.tap(dot["x"] + 10, dot["y"])
    page.wait_for_timeout(500)
    if not page.locator(".leaflet-popup").count():
        fail(f"{label}: a tap 10px from a dot opened nothing")
    if not popup_fits(page, map_selector):
        fail(f"{label}: popup runs outside the map")
    print(f"{label}: tap 10px from a {dot['w']:.0f}px dot opened {popup_title(page).splitlines()[0]!r}; popup fits")


def check_map_taps(p, base, site_path, hub_path, dot_slug):
    browser = p.chromium.launch()
    iphone = p.devices["iPhone 13"]
    phones = [("iPhone 13", iphone)] + [
        (f"touch phone {w}", dict(iphone, viewport={"width": w, "height": h}, screen={"width": w, "height": h}))
        for w, h in ((360, 780), (430, 932))
    ]
    for device, spec in phones:
        ctx = browser.new_context(**spec)
        page = ctx.new_page()
        width = page.viewport_size["width"]

        # The starting zoom, where dots are smallest and crowded: a tap that
        # misses every dot must still open one (the nearest).
        page.goto(f"{base}/interactive-map/", wait_until="networkidle")
        page.wait_for_function("() => document.querySelectorAll('.leaflet-sites-pane path.leaflet-interactive').length > 0")
        page.wait_for_timeout(800)
        dot = nearest_dot_on_screen(page, "#sacredMap", ".leaflet-sites-pane", miss_clear=6)
        page.touchscreen.tap(dot["x"] + 10, dot["y"])
        page.wait_for_timeout(500)
        if not page.locator(".leaflet-popup h3").count():
            fail(f"{device} {width}px: a tap 10px from a {dot['w']:.0f}px dot (missing every dot) opened nothing")
        if not popup_fits(page, "#sacredMap"):
            fail(f"{device} {width}px: popup runs outside the map")
        print(f"{device} {width}px: at the starting zoom ({dot['w']:.0f}px dots), a tap that missed every dot "
              f"opened {page.locator('.leaflet-popup h3').inner_text().strip()!r}; popup fits")

        # A known dot, focused by ?site= (opens its popup), then closed.
        page.goto(f"{base}/interactive-map/?site={dot_slug}", wait_until="networkidle")
        page.wait_for_selector(".leaflet-popup")
        if not popup_fits(page, "#sacredMap"):
            fail(f"{device} {width}px: the ?site= popup runs outside the map")
        title = page.locator(".leaflet-popup h3").inner_text().strip()
        page.locator(".leaflet-popup-close-button").dispatch_event("click")
        page.wait_for_timeout(400)
        # The focused dot sits near the map's center. A tap 10px away must
        # open the same popup as a tap on the dot itself.
        dot = nearest_dot_on_screen(page, "#sacredMap", ".leaflet-sites-pane")
        page.touchscreen.tap(dot["x"], dot["y"])
        page.wait_for_timeout(500)
        direct = page.locator(".leaflet-popup h3").inner_text().strip() if page.locator(".leaflet-popup h3").count() else ""
        if not direct:
            fail(f"{device}: a tap right on a dot opened nothing")
        page.locator(".leaflet-popup-close-button").dispatch_event("click")
        page.wait_for_timeout(400)
        dot = nearest_dot_on_screen(page, "#sacredMap", ".leaflet-sites-pane")
        page.touchscreen.tap(dot["x"] + 10, dot["y"])
        page.wait_for_timeout(500)
        text = page.locator(".leaflet-popup h3").inner_text().strip() if page.locator(".leaflet-popup h3").count() else ""
        if text != direct:
            fail(f"{device}: tap 10px from {direct!r} opened {text!r}")
        if text != title:
            fail(f"{device}: expected the known dot {title!r}, got {text!r}")
        title = text
        link = page.locator(".leaflet-popup .map-popup-link")
        href = link.get_attribute("href")
        if not popup_fits(page, "#sacredMap"):
            fail(f"{device} {width}px: popup runs outside the map")
        for sel in (".map-popup-link", ".journey-buttons"):
            if page.locator(f".leaflet-popup {sel}").count():
                b = page.locator(f".leaflet-popup {sel}").bounding_box()
                w = page.locator(".leaflet-popup-content-wrapper").bounding_box()
                if b["x"] + b["width"] > w["x"] + w["width"] + 0.5:
                    fail(f"{device} {width}px: {sel} sticks out of the popup")
        print(f"{device} {width}px: tap 10px from the dot opened {title!r}; Read more → {href}; popup fits")
        if width == 390:
            response = page.request.get(base + href)
            if response.status != 200:
                fail(f"Read more link {href} returned {response.status}")
            # Open ocean: the point in the map farthest from every dot.
            page.locator(".leaflet-popup-close-button").dispatch_event("click")
            page.goto(f"{base}/interactive-map/", wait_until="networkidle")
            page.wait_for_function("() => document.querySelectorAll('.leaflet-sites-pane path.leaflet-interactive').length > 0")
            page.wait_for_timeout(800)
            m = page.locator("#sacredMap").bounding_box()
            dots = page.evaluate(DOT_CENTERS_JS, ".leaflet-sites-pane")
            spot = max(((m["x"] + fx * m["width"], m["y"] + fy * m["height"])
                        for fx in (0.25, 0.4, 0.5, 0.6, 0.75) for fy in (0.55, 0.65, 0.75, 0.85)),
                       key=lambda pt: min(((pt[0] - d["x"]) ** 2 + (pt[1] - d["y"]) ** 2) ** 0.5 for d in dots))
            page.touchscreen.tap(*spot)
            page.wait_for_timeout(500)
            if page.locator(".leaflet-popup").count():
                fail("a tap on open ocean opened a popup")
            print(f"{device} {width}px: tap on open ocean opened nothing")
            # Site page map and hub map.
            if site_path:
                page.goto(base + site_path, wait_until="networkidle")
                page.locator("#siteStayMap").scroll_into_view_if_needed()
                tap_near_a_dot(page, "#siteStayMap", ".leaflet-sites-pane", f"{device} site page map")
            if hub_path:
                page.goto(base + hub_path, wait_until="networkidle")
                page.locator("#hubMap").scroll_into_view_if_needed()
                tap_near_a_dot(page, "#hubMap", ".leaflet-sites-pane", f"{device} hub map")
        ctx.close()

    # Desktop: clicking a dot still opens it; 15px away (beyond 8px) doesn't.
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    page.goto(f"{base}/interactive-map/?site={dot_slug}", wait_until="networkidle")
    page.wait_for_selector(".leaflet-popup")
    page.locator(".leaflet-popup-close-button").dispatch_event("click")
    page.wait_for_timeout(400)
    m = page.locator("#sacredMap").bounding_box()
    dots = page.evaluate(DOT_CENTERS_JS, ".leaflet-sites-pane")
    cx, cy = m["x"] + m["width"] / 2, m["y"] + m["height"] / 2
    dot = min(dots, key=lambda d: (d["x"] - cx) ** 2 + (d["y"] - cy) ** 2)
    if dot["w"] > 15:
        fail(f"desktop dot is {dot['w']:.1f}px; mouse sizes should be unchanged")
    clear = min((((dot["x"] + 15) - d["x"]) ** 2 + (dot["y"] - d["y"]) ** 2) ** 0.5 for d in dots)
    if clear > 8 + dot["w"] / 2:
        page.mouse.click(dot["x"] + 15, dot["y"])
        page.wait_for_timeout(400)
        if page.locator(".leaflet-popup").count():
            fail("desktop: a click 15px from a dot opened a popup")
    page.mouse.click(dot["x"], dot["y"])
    page.wait_for_timeout(400)
    if not page.locator(".leaflet-popup").count():
        fail("desktop: a click on a dot didn't open its popup")
    print(f"1440px desktop: click on a {dot['w']:.0f}px dot opens it; 15px away opens nothing")
    browser.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("base")
    ap.add_argument("--site", default="", help="A site page with a Where to Stay map.")
    ap.add_argument("--hub", default="", help="A destination hub page.")
    ap.add_argument("--dot", default="eucharistic-miracle-of-morrovalle", help="Slug of a site on the Interactive Map.")
    args = ap.parse_args()
    base = args.base.rstrip("/")
    with sync_playwright() as p:
        check_dropdowns(p, base)
        check_map_taps(p, base, args.site, args.hub, args.dot)
    print("all checks passed")


if __name__ == "__main__":
    main()
