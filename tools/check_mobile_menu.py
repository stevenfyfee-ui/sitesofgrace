"""Browser check for the mobile menu (900px and narrower).

    python tools/check_mobile_menu.py http://localhost:8000
    python tools/check_mobile_menu.py http://localhost:8000 --sessionid <key>   # also signed in
    python tools/check_mobile_menu.py http://localhost:8000 --shots /out        # 390px screenshots

Needs Playwright with Chromium (requirements-dev.txt). Writes nothing; exits
1 on the first failure. --sessionid is a Django session cookie for a test
pilgrim on the server being checked (never a real account's).

As an iPhone 13 and as a 360x640 Android phone (touch, coarse pointer),
signed out and, with --sessionid, signed in: open the menu, check every
section starts collapsed (unless it holds the current page) with an overview
link first, expand each section, then scroll the menu with finger swipes to
its last row (the last link, or Sign out) and check it's on screen and is the
element under a tap at its center. The page behind must not have scrolled.
On a page inside a section (--current), only that section starts open.
Keyboard (390 wide): Tab to the menu button, Enter
opens, a section toggles with Enter and Space, Esc closes and focus returns
to the menu button. Growing the window past 900px closes the menu. At 1440
the mobile menu stays hidden.
"""
import argparse
import sys

from playwright.sync_api import sync_playwright


def fail(msg):
    print("FAIL:", msg)
    sys.exit(1)


def last_row(page):
    """The menu's last tappable row: Sign out when signed in, else the last link."""
    signout = page.locator("#mobileNav .mobile-signout button")
    if signout.count():
        return signout, "Sign out"
    link = page.locator("#mobileNav .mobile-list:not(.mobile-account-list) > li > a").last
    return link, link.inner_text().strip()


def under_center(page, locator):
    return locator.evaluate("""el => {
        const b = el.getBoundingClientRect();
        const hit = document.elementFromPoint(b.left + b.width / 2, b.top + b.height / 2);
        return !!hit && (hit === el || el.contains(hit));
    }""")


def finger_tap(page, locator):
    """Tap at the element's center, as a finger would. (Locator.tap() first
    scrolls the element into view, which can scroll the page behind.)"""
    b = locator.bounding_box()
    page.touchscreen.tap(b["x"] + b["width"] / 2, b["y"] + b["height"] / 2)
    page.wait_for_timeout(200)


def reveal(locator):
    """Scroll the menu itself (not the page) so the element is near its top."""
    locator.evaluate("""el => { const nav = document.getElementById('mobileNav');
        nav.scrollTop += el.getBoundingClientRect().top - nav.getBoundingClientRect().top - 40; }""")


def swipe_up(page, cdp, x, y, distance=300, steps=20):
    """A finger drag upward (scrolls the content under it down)."""
    cdp.send("Input.dispatchTouchEvent", {"type": "touchStart", "touchPoints": [{"x": x, "y": y}]})
    for i in range(1, steps + 1):
        cdp.send("Input.dispatchTouchEvent", {"type": "touchMove", "touchPoints": [{"x": x, "y": y - distance * i / steps}]})
    cdp.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})
    page.wait_for_timeout(300)


def swipe_to(page, cdp, nav, row, label, row_name):
    """Swipe inside the menu until `row` is fully on screen and under a tap."""
    nb = nav.bounding_box()
    x, y = nb["x"] + nb["width"] / 2, nb["y"] + nb["height"] * 0.75
    for _ in range(15):
        rb = row.bounding_box()
        if rb and rb["y"] >= 0 and rb["y"] + rb["height"] <= page.viewport_size["height"] + 0.5 and under_center(page, row):
            return
        swipe_up(page, cdp, x, y)
    fail(f"{label}: the last row {row_name!r} can't be swiped onto the screen, or is covered")


def check_phone(p, base, device, spec, sessionid, shots):
    browser = p.chromium.launch()
    ctx = browser.new_context(**spec)
    if sessionid:
        host = base.split("://", 1)[1].split("/", 1)[0].split(":")[0]
        ctx.add_cookies([{"name": "sessionid", "value": sessionid, "domain": host, "path": "/"}])
    page = ctx.new_page()
    cdp = ctx.new_cdp_session(page)
    who = "signed in" if sessionid else "signed out"
    label = f"{device} {who}"
    page.goto(base + "/", wait_until="networkidle")
    if sessionid and not page.locator("#mobileNav .mobile-account").count():
        fail(f"{label}: no My account group (is the session valid?)")
    # Start part-way down a long page, so a scroll leaking to the page shows.
    page.evaluate("window.scrollTo(0, 300)")
    page.wait_for_timeout(500)
    # What the visitor sees: the element at the middle of the screen, and where.
    page.evaluate("""() => { const h = innerHeight / 2; let el = document.elementFromPoint(innerWidth / 2, h);
        window.__sogMark = el; window.__sogMarkTop = el.getBoundingClientRect().top; }""")
    if shots and not sessionid:
        page.screenshot(path=f"{shots}/menu-390-1-closed.png")

    toggle = page.locator(".nav-toggle")
    finger_tap(page, toggle)
    nav = page.locator("#mobileNav")
    if not nav.is_visible():
        fail(f"{label}: the menu didn't open")
    if not page.evaluate("document.body.classList.contains('nav-open')"):
        fail(f"{label}: body.nav-open not set")
    # Opening or expanding the menu makes the sticky header taller, and the
    # browser's scroll anchoring moves the page to keep its (covered) content
    # still. So the baseline is taken once the sections are open: swiping the
    # menu must not move the page, and closing must restore start_y.

    toggles = page.locator("#mobileNav [data-section-toggle]")
    for i in range(toggles.count()):
        t = toggles.nth(i)
        panel = page.locator("#" + t.get_attribute("aria-controls"))
        starts_open = t.get_attribute("data-start-open") is not None
        if (t.get_attribute("aria-expanded") == "true") != starts_open or panel.is_visible() != starts_open:
            fail(f"{label}: section {t.inner_text().strip()!r} should start {'open' if starts_open else 'collapsed'}")
        if t.bounding_box()["height"] < 44:
            fail(f"{label}: section row {t.inner_text().strip()!r} is {t.bounding_box()['height']:.0f}px tall (min 44)")
    if shots and not sessionid:
        page.screenshot(path=f"{shots}/menu-390-2-open-collapsed.png")

    sections = page.locator("#mobileNav .mobile-list:not(.mobile-account-list) > .mobile-section > [data-section-toggle]")
    if sections.count() < 2:
        fail(f"{label}: expected at least two sections (Explore, Catholic Faith/Learn), found {sections.count()}")
    row, row_name = last_row(page)
    names = []
    for i in range(sections.count()):
        t = sections.nth(i)
        names.append(t.inner_text().strip())
        reveal(t)
        if t.get_attribute("aria-expanded") != "true":
            finger_tap(page, t)
        panel = page.locator("#" + t.get_attribute("aria-controls"))
        if not panel.is_visible():
            fail(f"{label}: {names[-1]!r} didn't expand")
        first = panel.locator("a").first
        if first.get_attribute("class") != "mobile-overview" or not first.inner_text().startswith(f"All of {names[-1]}"):
            fail(f"{label}: {names[-1]!r} doesn't start with its overview link")
        if i == 0 and shots and not sessionid:
            swipe_to(page, cdp, nav, row, label, row_name)
            page.screenshot(path=f"{shots}/menu-390-3-explore-expanded-bottom.png")
    for a in page.locator("#mobileNav .mobile-list a:visible, #mobileNav [data-section-toggle]:visible, #mobileNav .mobile-signout button:visible").all():
        h = a.bounding_box()["height"]
        if h < 43.5:
            fail(f"{label}: {a.inner_text().strip()!r} is {h:.0f}px tall (min 44)")

    nav.evaluate("el => { el.scrollTop = 0; }")
    page.wait_for_timeout(200)
    open_y = page.evaluate("window.scrollY")
    swipe_to(page, cdp, nav, row, label, row_name)
    if page.evaluate("window.scrollY") != open_y:
        fail(f"{label}: the page behind scrolled ({open_y} -> {page.evaluate('window.scrollY')})")
    print(f"{label}: opened; sections {', '.join(names)} start collapsed and expand with an overview link first; "
          f"rows >= 44px; swiped to {row_name!r} (on screen, tappable); the page behind didn't move")

    finger_tap(page, toggle)
    if nav.is_visible() or page.evaluate("document.body.classList.contains('nav-open')"):
        fail(f"{label}: the menu button didn't close the menu")
    moved = page.evaluate("() => Math.round(window.__sogMark.getBoundingClientRect().top - window.__sogMarkTop)")
    if abs(moved) > 1:
        fail(f"{label}: after closing, the page content is {moved}px from where it was")

    # A tap on a link closes the menu and unlocks the page.
    finger_tap(page, toggle)
    link = page.locator("#mobileNav .mobile-list:not(.mobile-account-list) > li:not(.mobile-section) > a").first
    link.evaluate("el => el.addEventListener('click', e => e.preventDefault(), {once: true})")
    reveal(link)
    page.wait_for_timeout(200)
    finger_tap(page, link)
    if nav.is_visible() or page.evaluate("document.body.classList.contains('nav-open')"):
        fail(f"{label}: tapping a link didn't close the menu")
    print(f"{label}: the menu button and a link tap both close the menu; closing leaves the page where it was")
    browser.close()


def check_keyboard_and_resize(p, base):
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 390, "height": 844})
    page.goto(base + "/", wait_until="networkidle")
    btn = page.locator(".nav-toggle")
    for _ in range(40):
        page.keyboard.press("Tab")
        if page.evaluate("document.activeElement && document.activeElement.classList.contains('nav-toggle')"):
            break
    else:
        fail("keyboard: Tab never reached the menu button")
    page.keyboard.press("Enter")
    page.wait_for_timeout(200)
    if btn.get_attribute("aria-expanded") != "true":
        fail("keyboard: Enter didn't open the menu")
    first = page.locator("#mobileNav .mobile-list:not(.mobile-account-list) > .mobile-section > [data-section-toggle]").first
    for _ in range(40):
        page.keyboard.press("Tab")
        if page.evaluate("el => document.activeElement === el", first.element_handle()):
            break
    else:
        fail("keyboard: Tab never reached the first section")
    before = first.get_attribute("aria-expanded")
    page.keyboard.press("Enter")
    after_enter = first.get_attribute("aria-expanded")
    page.keyboard.press("Space")
    after_space = first.get_attribute("aria-expanded")
    if not (before != after_enter and after_space == before):
        fail(f"keyboard: Enter/Space didn't toggle the section ({before} -> {after_enter} -> {after_space})")
    page.keyboard.press("Escape")
    page.wait_for_timeout(200)
    if page.locator("#mobileNav").is_visible():
        fail("keyboard: Esc didn't close the menu")
    if not page.evaluate("document.activeElement && document.activeElement.classList.contains('nav-toggle')"):
        fail("keyboard: focus didn't return to the menu button")
    print("keyboard 390px: Tab to the menu button, Enter opens, Enter and Space toggle a section, Esc closes, focus back on the button")

    btn.click()
    page.wait_for_timeout(200)
    page.set_viewport_size({"width": 1024, "height": 844})
    page.wait_for_timeout(300)
    if page.locator("#mobileNav").is_visible() or page.evaluate("document.body.classList.contains('nav-open')"):
        fail("resize: the menu stayed open past 900px")
    print("resize: growing the window past 900px closes the menu and unlocks the page")
    page.close()

    page = browser.new_page(viewport={"width": 1440, "height": 900})
    page.goto(base + "/", wait_until="networkidle")
    if page.locator(".nav-toggle").is_visible() or page.locator("#mobileNav").is_visible():
        fail("1440px: the mobile menu button or menu is showing")
    if not page.locator(".primary-nav").is_visible():
        fail("1440px: the desktop nav is hidden")
    print("1440px: desktop nav shown; mobile menu button and menu hidden")
    browser.close()


def check_current_section(p, base, path):
    """On a page inside a section, that section starts open and the others closed."""
    browser = p.chromium.launch()
    page = browser.new_context(**p.devices["iPhone 13"]).new_page()
    page.goto(base + path, wait_until="networkidle")
    finger_tap(page, page.locator(".nav-toggle"))
    states = page.evaluate("""() => Array.from(document.querySelectorAll(
        '#mobileNav .mobile-list:not(.mobile-account-list) > .mobile-section > [data-section-toggle]'))
        .map(t => [t.textContent.trim(), t.getAttribute('aria-expanded'), !document.getElementById(t.getAttribute('aria-controls')).hidden])""")
    open_ = [name for name, expanded, shown in states if expanded == "true" and shown]
    if len(open_) != 1:
        fail(f"{path}: expected exactly one section open (the current page's), got {open_}")
    print(f"{path}: only {open_[0]!r} starts open")
    browser.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("base")
    ap.add_argument("--sessionid", default="", help="Session cookie for a test pilgrim, to check signed in too.")
    ap.add_argument("--shots", default="", help="Directory for the 390px screenshots (signed out).")
    ap.add_argument("--current", default="/explore/marian-apparitions/", help="A page inside a menu section.")
    args = ap.parse_args()
    base = args.base.rstrip("/")
    with sync_playwright() as p:
        iphone = p.devices["iPhone 13"]
        android = dict(p.devices["Pixel 5"], viewport={"width": 360, "height": 640}, screen={"width": 360, "height": 640})
        for device, spec in (("iPhone 13", iphone), ("Android 360x640", android)):
            for sid in ("", args.sessionid) if args.sessionid else ("",):
                check_phone(p, base, device, spec, sid, args.shots if device == "iPhone 13" else "")
        check_current_section(p, base, args.current)
        check_keyboard_and_resize(p, base)
    print("all checks passed")


if __name__ == "__main__":
    main()
