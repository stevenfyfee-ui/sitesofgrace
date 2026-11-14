"""World map card picture + marker spreading: browser checks and screenshots.

    python tools/future_saints_card_screens.py <base_url> <out_dir>

Card picture: for every published story, each way of selecting it (its marker, the list's
"Show on the map", the map search, ?story= server-rendered, and the touch chooser) must show
that story's picture (src and alt from the page's own data: index thumbnail, else hero) or the
placeholder frame, never the previous story's picture. The same for every mission on the
California Missions hub panel.

Markers: no two discs touch at 1440, 1024 and 390 wide, at zoom 1, 1.5, 2, 3 and 6, and every
marker's true spot is exactly where its latitude/longitude puts it.

Screenshots: the card after selecting two different stories, and the Italy area at 1440 and
390. Exits 1 if any check fails. Needs Playwright (the local sog-shots image) and production-like
data (Lourdes, Assisi, Lanciano, Jerusalem).
"""
import itertools
import json
import os
import sys

from playwright.sync_api import sync_playwright

WORLD = "/future-saints/map/"
HUB = "/future-saints/california-missions/"
CARD_ART = """sel => { const c = document.querySelector(sel); const img = c.querySelector('.fs-art img');
  return img ? {src: img.getAttribute('src'), alt: img.getAttribute('alt')}
             : {placeholder: !!c.querySelector('.fs-art--placeholder'), count: c.querySelectorAll('.fs-art').length}; }"""
DISCS = """() => [...document.querySelectorAll('[data-fs-world-pin]')].filter(b => b.offsetParent).map(b => {
  const r = b.querySelector('.fs-wm-disc').getBoundingClientRect();
  return {key: b.value, x: r.left + r.width / 2, y: r.top + r.height / 2, r: r.width / 2}; })"""
TRUE_SPOTS = """() => { const vp = document.querySelector('.fs-world-explore [data-fs-zoom]'); const v = vp.getBoundingClientRect();
  const s = vp.fsZoom.state(); const w = vp.clientWidth, h = vp.clientHeight;
  const vbw = +vp.dataset.fsVbW, vbh = +vp.dataset.fsVbH;
  return [...document.querySelectorAll('[data-fs-world-pin]')].map(b => {
    const m = b.closest('.fs-wm-marker').getBoundingClientRect();
    return {key: b.value, dx: m.left - (v.left + s.tx + b.dataset.x / vbw * w * s.z),
            dy: m.top - (v.top + s.ty + b.dataset.y / vbh * h * s.z)}; }); }"""


def expected(art):
    return {"src": art["src"], "alt": art["alt"]} if art else {"placeholder": True, "count": 1}


def main():
    base, out = sys.argv[1].rstrip("/"), sys.argv[2]
    os.makedirs(out, exist_ok=True)
    passed, failed = [], []

    def check(ok, label):
        (passed if ok else failed).append(label)
        print(("PASS " if ok else "FAIL ") + label)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport={"width": 1440, "height": 1000}, device_scale_factor=2)
        page = ctx.new_page()
        page.goto(base + WORLD, wait_until="networkidle")
        stories = json.loads(page.locator("#fs-world-data").text_content())
        pinned = [s for s in stories if page.locator(f'[data-fs-world-pin][value="{s["key"]}"]').count()]
        with_art = [s for s in stories if s["art"]]
        check(len(with_art) >= 2 and any(not s["art"] for s in stories), "the data has pictures and placeholders to test")

        # 1. Each story by its marker, alternating with a story that has a picture, so a stale one would show.
        anchor = with_art[0]
        for s in pinned:
            for key in (anchor["key"], s["key"]):
                if page.locator(f'[data-fs-world-pin][value="{key}"]').count():
                    page.locator(f'[data-fs-world-pin][value="{key}"]').click()
            check(page.evaluate(CARD_ART, "[data-fs-world-card]") == expected(s["art"]), f"marker: {s['title']}")
        # 2. From the list ("Show on the map").
        for s in pinned:
            link = page.locator(f'.fs-world-show[href*="story={s["key"]}"]')
            if link.count():
                page.locator(f'[data-fs-world-pin][value="{anchor["key"]}"]').click()
                link.click()
                page.wait_for_timeout(150)
                check(page.evaluate(CARD_ART, "[data-fs-world-card]") == expected(s["art"]), f"list: {s['title']}")
        # 3. From the map search.
        box = page.locator("#fs-map-search-q")
        if box.count():
            for s in stories:
                if not s["key"] or s["key"] == "california-missions":
                    continue
                page.locator(f'[data-fs-world-pin][value="{anchor["key"]}"]').click()
                box.fill("")
                box.type(s["title"][:20], delay=10)
                page.wait_for_selector("#fs-map-search-list:not([hidden]) [role=option]")
                page.wait_for_timeout(150)
                option = page.locator("#fs-map-search-list [role=option]", has_text=s["title"]).first
                if option.count():
                    option.click()
                    page.wait_for_timeout(150)
                    check(page.evaluate(CARD_ART, "[data-fs-world-card]") == expected(s["art"]), f"search: {s['title']}")
        # Screenshots: the card after two different stories.
        for n, s in enumerate(with_art[:1] + [x for x in stories if x["key"] != with_art[0]["key"] and x["art"]][:1]):
            page.locator(f'[data-fs-world-pin][value="{s["key"]}"]').click()
            page.wait_for_timeout(300)
            page.locator("[data-fs-world-card]").screenshot(path=f"{out}/card-after-{n + 1}-{s['key']}.png")
        ctx.close()

        # 4. ?story= server-rendered, with no JavaScript (the server's own card).
        ctx = browser.new_context(viewport={"width": 1440, "height": 1000}, java_script_enabled=False)
        page = ctx.new_page()
        for s in stories:
            page.goto(base + WORLD + "?story=" + s["key"], wait_until="networkidle")
            check(page.evaluate(CARD_ART, "[data-fs-world-card]") == expected(s["art"]), f"?story= server: {s['title']}")
        ctx.close()

        # 5. The touch chooser (390, coarse pointer): every story it offers shows its own picture.
        ctx = browser.new_context(viewport={"width": 390, "height": 900}, has_touch=True, is_mobile=True, device_scale_factor=2)
        page = ctx.new_page()
        page.goto(base + WORLD, wait_until="networkidle")
        page.evaluate("() => document.querySelector('.fs-world-explore [data-fs-zoom]').fsZoom.focus(535, 92, 1)")
        by_key = {s["key"]: s for s in stories}
        for s in pinned:
            page.locator(f'[data-fs-world-pin][value="{s["key"]}"]').tap()
            page.wait_for_timeout(150)
            if page.locator("[data-fs-chooser]:not([hidden])").count():
                choices = page.locator("[data-fs-chooser]:not([hidden]) .fs-pin-choice")
                choices.first.click()
            selected = page.locator('[data-fs-world-pin][aria-pressed="true"]').get_attribute("value")
            check(page.evaluate(CARD_ART, "[data-fs-world-card]") == expected(by_key[selected]["art"]),
                  f"touch: {by_key[selected]['title']}")
        ctx.close()

        # 6. Markers never touch; true spots never move.
        for width in (1440, 1024, 390):
            ctx = browser.new_context(viewport={"width": width, "height": 900}, device_scale_factor=2)
            page = ctx.new_page()
            page.goto(base + WORLD, wait_until="networkidle")
            page.wait_for_timeout(200)
            for z in (1, 1.5, 2, 3, 6):
                if z > 1:
                    page.evaluate("z => document.querySelector('.fs-world-explore [data-fs-zoom]').fsZoom.focus(535, 92, z)", z)
                    page.wait_for_timeout(700)
                discs = page.evaluate(DISCS)
                touching = [(a["key"], c["key"]) for a, c in itertools.combinations(discs, 2)
                            if ((a["x"] - c["x"]) ** 2 + (a["y"] - c["y"]) ** 2) ** .5 < a["r"] + c["r"] + 2]
                check(not touching, f"{width} at {z}x: no two markers touch {touching or ''}")
                drift = [s for s in page.evaluate(TRUE_SPOTS) if abs(s["dx"]) > 1 or abs(s["dy"]) > 1]
                check(not drift, f"{width} at {z}x: true spots unchanged {drift or ''}")
            page.evaluate("() => document.querySelector('.fs-world-explore [data-fs-zoom]').fsZoom.reset(false)")
            page.wait_for_timeout(300)
            page.locator(".fs-world-explore").scroll_into_view_if_needed()
            page.evaluate("() => document.querySelector('.fs-world-explore').scrollIntoView({block: 'center'})")
            page.wait_for_timeout(200)
            box = page.locator('[data-fs-world-pin][value="carlo-acutis"]').bounding_box() or \
                page.locator("[data-fs-world-pin]").first.bounding_box()
            half = 150 if width > 500 else 110
            page.screenshot(path=f"{out}/italy-{width}.png",
                            clip={"x": max(0, box["x"] - half), "y": max(0, box["y"] - half), "width": 2 * half, "height": 2 * half})
            ctx.close()

        # 7. California hub panel: every mission shows its own story's picture, or the placeholder.
        ctx = browser.new_context(viewport={"width": 1440, "height": 1000})
        page = ctx.new_page()
        page.goto(base + HUB, wait_until="networkidle")
        missions = json.loads(page.locator("#fs-mission-data").text_content())
        art_first = next((m for m in missions if m["art"]), None)
        press = "slug => document.querySelector('[data-fs-pin][value=\"' + slug + '\"]').click()"   # as a keyboard press does
        for m in missions:
            if art_first:
                page.evaluate(press, art_first["slug"])
            page.evaluate(press, m["slug"])
            check(page.evaluate(CARD_ART, "[data-fs-panel]") == expected(m["art"]), f"hub: #{m['number']} {m['name']}")
        ctx.close()
        browser.close()

    print(f"\n{len(passed)} passed, {len(failed)} failed")
    for label in failed:
        print("  FAILED:", label)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
