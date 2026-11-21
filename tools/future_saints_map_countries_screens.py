"""Browser QA for the World Discovery Map's size, country borders and names, and full screen.

    python tools/future_saints_map_countries_screens.py <base_url> <out_dir>

Run against a local server with SOG_FUTURE_SAINTS=on (published stories on the map). Needs Playwright
with Chromium (the local sog-shots image has both). Writes PNGs to out_dir and exits 1 if any check fails.

Checks:
- size: the map's box at 1440x900, 1024x768, 768x1024, 390x844 and 360x800 (full content width;
  clamp(560px, 70vh, 820px) at >= 1024, max(360px, 60vh) below), the card below the map, no page
  scrolling sideways, and how the map opens (1x on desktop; filling the height under 1024);
- names: at 1x, 2x, 4x and 6x (centred on Europe, the densest part) at 1440 and 390, no shown name
  touches a visible marker's 44px button or another name (rendered boxes);
- constant on screen: the border's stroke and each name's font size, times the map's scale, stay
  0.8px and 13px / 11px at every zoom;
- full screen: opens and closes with the keyboard (Enter on the button; Enter on "Close"; Esc), focus
  goes to "Close" and back, nothing below the map moves; the button is hidden without the API;
- without JavaScript: the borders and some names show, and the list shows "Country:" lines.
"""
import os
import sys
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright

MAP = "/future-saints/map/"
SIZES = [(1440, 900), (1024, 768), (768, 1024), (390, 844), (360, 800)]
EUROPE = (520.0, 95.0)          # map units
ROME = (530.4, 94.2)
STATE_JS = """() => { const vp = document.querySelector('[data-fs-zoom]'); const s = vp.fsZoom.state();
  return {z: s.z, scale: s.scale}; }"""
GEOM_JS = """() => {
  const vp = document.querySelector('[data-fs-zoom]').getBoundingClientRect();
  const inVp = r => r.right > vp.left && r.left < vp.right && r.bottom > vp.top && r.top < vp.bottom;
  const pins = Array.from(document.querySelectorAll('[data-fs-world-pin]')).filter(b => !b.closest('[data-fs-kind]').hidden)
    .map(b => b.getBoundingClientRect()).filter(inVp).map(r => [r.left, r.top, r.right, r.bottom]);
  const labels = Array.from(document.querySelectorAll('.fs-wm-label.is-on')).map(t => { const r = t.getBoundingClientRect();
    return {name: t.textContent, box: [r.left, r.top, r.right, r.bottom], font: parseFloat(getComputedStyle(t).fontSize),
            big: t.classList.contains('fs-wm-label--big')}; });
  const border = parseFloat(getComputedStyle(document.querySelector('.fs-wm-borders')).strokeWidth);
  return {pins, labels, border};
}"""


def overlap(a, b, slack=0.5):
    return not (a[2] <= b[0] + slack or b[2] <= a[0] + slack or a[3] <= b[1] + slack or b[3] <= a[1] + slack)


def main():
    base, out = sys.argv[1].rstrip("/"), sys.argv[2]
    os.makedirs(out, exist_ok=True)
    passed, failed = [], []

    def check(ok, label):
        (passed if ok else failed).append(label)
        print(("PASS " if ok else "FAIL ") + label)

    with sync_playwright() as p:
        browser = p.chromium.launch()

        def page(w, h, **kw):
            ctx = browser.new_context(viewport={"width": w, "height": h}, reduced_motion="reduce", **kw)
            pg = ctx.new_page()
            errors = []
            pg.on("pageerror", lambda e: errors.append(str(e)))
            pg.goto(base + MAP, wait_until="networkidle")
            pg.wait_for_timeout(500)
            return ctx, pg, errors

        # ---- sizes ----
        for w, h in SIZES:
            ctx, pg, errors = page(w, h)
            g = pg.evaluate("""() => { const f = document.querySelector('.fs-wmap-frame').getBoundingClientRect();
              const wrap = document.querySelector('.fs-world-explore'); const cs = getComputedStyle(wrap);
              const c = document.querySelector('#story-card').getBoundingClientRect();
              return {w: f.width, h: f.height, content: wrap.clientWidth - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight),
                      mapBottom: f.bottom + scrollY, cardTop: c.top + scrollY, cardLeft: c.left, frameLeft: f.left,
                      docw: document.documentElement.scrollWidth, vw: innerWidth}; }""")
            st = pg.evaluate(STATE_JS)
            want_h = min(820, max(560, 0.7 * h)) if w >= 1024 else max(360, 0.6 * h)
            print(f"  {w}x{h}: map {g['w']:.1f} x {g['h']:.1f} (content {g['content']:.1f}), opens at {st['z']:.2f}x, "
                  f"{st['scale']:.3f} px/unit, card top {g['cardTop']:.0f} (map bottom {g['mapBottom']:.0f})")
            check(abs(g["w"] - g["content"]) < 1, f"{w}: the map has the full content width")
            check(abs(g["h"] - want_h) < 1.5, f"{w}: the map is {want_h:.0f}px tall")
            check(g["cardTop"] >= g["mapBottom"] and abs(g["cardLeft"] - g["frameLeft"]) < 1, f"{w}: the card is below the map")
            check(g["docw"] <= g["vw"], f"{w}: no sideways scroll")
            check((abs(st["z"] - 1) < 0.01) if w >= 1024 else st["z"] > 1.5, f"{w}: opens {'whole' if w >= 1024 else 'filling the height'}")
            check(not errors, f"{w}: no page errors {errors}")
            if w == 1440:
                pg.locator(".fs-wmap").screenshot(path=f"{out}/world-1440-after.png")
            if w == 390:
                pg.locator(".fs-wmap").screenshot(path=f"{out}/world-390-after.png")
            if w == 1024:
                pg.locator(".fs-wmap").screenshot(path=f"{out}/world-1024.png")
            ctx.close()

        # ---- names vs pins and each other, constant sizes, at 1x / 2x / 4x / 6x ----
        for w, h in ((1440, 900), (390, 844)):
            ctx, pg, _ = page(w, h)
            for z in (1, 2, 4, 6):
                pg.evaluate(f"() => {{ const a = document.querySelector('[data-fs-zoom]').fsZoom; a.reset(false); a.focus({EUROPE[0]}, {EUROPE[1]}, {z}); }}")
                pg.wait_for_timeout(300)
                st = pg.evaluate(STATE_JS)
                g = pg.evaluate(GEOM_JS)
                clash = [(lab["name"], "pin") for lab in g["labels"] for pin in g["pins"] if overlap(lab["box"], pin)]
                clash += [(a["name"], b["name"]) for i, a in enumerate(g["labels"]) for b in g["labels"][i + 1:] if overlap(a["box"], b["box"])]
                check(not clash, f"{w} at {z}x: {len(g['labels'])} names, none touches a pin or another name {clash[:4]}")
                sizes = {round(lab["font"] * st["scale"], 2) for lab in g["labels"]}
                check(sizes <= {13.0, 11.0} and all(lab["font"] * st["scale"] >= 10.99 for lab in g["labels"]),
                      f"{w} at {z}x: names are 13px / 11px on screen {sorted(sizes)}")
                check(abs(g["border"] * st["scale"] - 0.8) < 0.01, f"{w} at {z}x: borders {g['border'] * st['scale']:.3f}px on screen")
            ctx.close()

        # ---- regions and stories, zoomed (screenshots) ----
        ctx, pg, _ = page(1440, 900)
        pg.click("[data-fs-region]:has-text('Europe')")
        pg.wait_for_timeout(600)
        pg.locator(".fs-wmap").screenshot(path=f"{out}/europe-1440.png")
        pg.click("[data-fs-region]:has-text('Holy Land')")
        pg.wait_for_timeout(600)
        pg.locator(".fs-wmap").screenshot(path=f"{out}/holy-land-1440.png")
        pg.evaluate(f"() => {{ const a = document.querySelector('[data-fs-zoom]').fsZoom; a.reset(false); a.focus({ROME[0]}, {ROME[1]}, 6); }}")
        pg.wait_for_timeout(600)
        shown = pg.evaluate("() => Array.from(document.querySelectorAll('.fs-wm-label.is-on')).map(t => t.textContent)")
        print("  Italy at 6x shows:", ", ".join(shown))
        pg.locator(".fs-wmap").screenshot(path=f"{out}/italy-6x-1440.png")
        link = pg.locator(".fs-world-show[href*='eucharistic-miracle-of-lanciano']")
        if link.count():
            link.first.click()
            pg.wait_for_timeout(600)
        card = pg.locator("#story-card")
        country = card.locator("[data-fs-card-country]")
        check(country.is_visible() and country.inner_text().startswith("Country: "), f"the card shows {country.inner_text()!r}")
        card.screenshot(path=f"{out}/card-country-1440.png")
        ctx.close()

        # ---- full screen with the keyboard ----
        ctx, pg, _ = page(1440, 900)
        before = pg.evaluate("() => [document.querySelector('#all-stories').getBoundingClientRect().top + scrollY, scrollY]")
        btn = pg.locator("[data-fs-fullscreen]")
        check(btn.is_visible() and btn.get_attribute("aria-label") == "Show the map full screen", "the full-screen button shows, 44px, labelled")
        box = btn.bounding_box()
        check(round(box["width"]) == 44 and round(box["height"]) == 44, f"full-screen button is 44px ({box['width']}x{box['height']})")
        btn.focus()
        pg.keyboard.press("Enter")
        pg.wait_for_timeout(700)
        on = pg.evaluate("() => document.fullscreenElement && document.fullscreenElement.id")
        check(on == "world-map", f"Enter opens full screen ({on})")
        check(pg.evaluate("() => document.activeElement.hasAttribute('data-fs-fullscreen-close')"), "focus moves to Close")
        pg.screenshot(path=f"{out}/fullscreen-1440.png")
        pg.keyboard.press("Enter")
        pg.wait_for_timeout(700)
        check(pg.evaluate("() => !document.fullscreenElement"), "Enter on Close leaves full screen")
        check(pg.evaluate("() => document.activeElement.hasAttribute('data-fs-fullscreen')"), "focus returns to the button")
        pg.keyboard.press("Enter")
        pg.wait_for_timeout(700)
        pg.keyboard.press("Escape")
        pg.wait_for_timeout(700)
        check(pg.evaluate("() => !document.fullscreenElement"), "Esc leaves full screen")
        after = pg.evaluate("() => [document.querySelector('#all-stories').getBoundingClientRect().top + scrollY, scrollY]")
        check(abs(before[0] - after[0]) < 1, f"nothing below the map moved ({before[0]:.0f} -> {after[0]:.0f})")
        ctx.close()

        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        ctx.add_init_script("""Object.defineProperty(Document.prototype, 'fullscreenEnabled', {get: () => false});
          Object.defineProperty(Document.prototype, 'webkitFullscreenEnabled', {get: () => false});
          delete Element.prototype.requestFullscreen; Element.prototype.webkitRequestFullscreen = undefined;""")
        pg = ctx.new_page()
        pg.goto(base + MAP, wait_until="networkidle")
        check(pg.locator("[data-fs-fullscreen]").is_hidden(), "the button is hidden without the Fullscreen API")
        ctx.close()

        # ---- without JavaScript ----
        for w, h in ((1440, 900), (390, 844)):
            ctx = browser.new_context(viewport={"width": w, "height": h}, java_script_enabled=False)
            pg = ctx.new_page()
            pg.goto(base + MAP, wait_until="networkidle")
            pg.wait_for_timeout(500)
            visible = sorted(t.text_content() for t in pg.locator(".fs-wm-label").all() if t.is_visible())
            # The server placed each name for this width band, clear of the pins (pins always win: on a
            # phone-width whole world the 44px buttons can cover every name that would fit).
            band = "e" if w >= 1240 else "d" if w >= 1030 else "c" if w >= 760 else "b" if w >= 510 else "a"
            placed = sorted(t.text_content() for t in pg.locator(f".fs-wm-label.is-{band}").all())
            check(pg.locator(".fs-wm-borders").is_visible(), f"no JS {w}: the borders show")
            check(visible == placed and (len(visible) >= 5 or w < 1024),
                  f"no JS {w}: {len(visible)} names show, as placed for band {band} ({', '.join(visible[:8])})")
            check(pg.locator("#all-stories .fs-world-country").count() > 0, f"no JS {w}: the list shows the countries")
            pg.locator(".fs-wmap").screenshot(path=f"{out}/world-{w}-no-js.png")
            ctx.close()

        # ---- page weight (first load at 1440, nothing cached) ----
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        pg = ctx.new_page()
        total = {"all": 0, "borders": 0}

        def on_resp(r):
            try:
                n = len(r.body())
            except Exception:
                return
            total["all"] += n
            if "world-borders" in r.url:
                total["borders"] += n
        pg.on("response", on_resp)
        pg.goto(base + MAP, wait_until="networkidle")
        pg.wait_for_timeout(500)
        print(f"  page weight at 1440 (first load): {total['all'] / 1024:.0f} KB, of which borders {total['borders'] / 1024:.0f} KB")
        ctx.close()
        browser.close()

    print(f"\n{len(passed)} passed, {len(failed)} failed")
    for f in failed:
        print("FAILED:", f)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
