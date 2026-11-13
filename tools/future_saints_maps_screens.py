"""Future Saints maps: before/after screenshots and the zoom QA.

    python tools/future_saints_maps_screens.py <base_url> <out_dir> <before|after> [comp02_png]

"before" captures the World Discovery Map and the California Missions hub at 1440 and 390
(the map and its panel, and California beside comp 02). "after" captures the same, plus
Europe and the Holy Land zoomed on the world map and California at 3x, and runs the zoom
checks (exits 1 if any fails). Needs Playwright with Chromium (the local sog-shots image).
"""
import base64
import os
import sys

from playwright.sync_api import sync_playwright

WORLD = "/future-saints/map/"
HUB = "/future-saints/california-missions/"


def side_by_side(page, comp, shot, title, path):
    ref = base64.b64encode(open(comp, "rb").read()).decode()
    build = base64.b64encode(shot).decode()
    page.set_content(
        "<body style='margin:0;display:flex;gap:16px;font:16px sans-serif;padding:16px;background:#eee'>"
        f"<figure style='margin:0;flex:1'><figcaption><b>Comp 02</b> (layout and style reference only)</figcaption><img style='width:100%' src='data:image/png;base64,{ref}'></figure>"
        f"<figure style='margin:0;flex:1'><figcaption><b>{title}</b></figcaption><img style='width:100%' src='data:image/png;base64,{build}'></figure></body>")
    page.screenshot(path=path, full_page=True)


def main():
    base, out, mode = sys.argv[1].rstrip("/"), sys.argv[2], sys.argv[3]
    comp = sys.argv[4] if len(sys.argv) > 4 else ""
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
            page.goto(base + WORLD, wait_until="networkidle")
            page.locator(".fs-world-explore").screenshot(path=f"{out}/world-{width}-{mode}.png")
            page.goto(base + HUB, wait_until="networkidle")
            page.locator(".fs-hub-explore").screenshot(path=f"{out}/california-{width}-{mode}.png")
            if width == 1440 and comp:
                page.set_viewport_size({"width": 1440, "height": 1000})
                shot = page.screenshot()
                side_by_side(page, comp, shot, f"California hub, 1440, {mode} the map art", f"{out}/california-1440-{mode}-vs-comp02.png")
            ctx.close()
        if mode == "after":
            run_after(browser, base, out, check)
        browser.close()
    if mode == "after":
        print(f"\n{len(passed)} passed, {len(failed)} failed")
        for label in failed:
            print("  FAILED:", label)
        sys.exit(1 if failed else 0)


STATE_JS = """sel => { const vp = document.querySelector(sel + ' [data-fs-zoom]'); const s = vp.fsZoom.state();
  const r = vp.getBoundingClientRect(); return {z: s.z, tx: s.tx, ty: s.ty, w: vp.clientWidth, h: vp.clientHeight,
  left: r.left, top: r.top, nudge: getComputedStyle(vp).getPropertyValue('--nudge').trim()}; }"""
MARKER_JS = """key => { const b = document.querySelector('[data-fs-world-pin][value="' + key + '"]');
  const d = b.querySelector('.fs-wm-disc').getBoundingClientRect(); const m = b.closest('.fs-wm-marker').getBoundingClientRect();
  return {disc: [d.width, d.height], spot: [m.left, m.top], x: parseFloat(b.dataset.x), y: parseFloat(b.dataset.y)}; }"""


def run_after(browser, base, out, check):
    ctx = browser.new_context(viewport={"width": 1440, "height": 1000}, device_scale_factor=2)
    page = ctx.new_page()
    page.goto(base + WORLD, wait_until="networkidle")
    check(page.is_visible("[data-fs-zoom-controls]") and page.is_visible("[data-fs-regions]"), "world: controls and regions shown with JavaScript")
    keys = page.eval_on_selector_all("[data-fs-world-pin]", "els => els.map(e => e.value)")
    lourdes = next(k for k in keys if "lourdes" in k)
    lanciano = next(k for k in keys if "lanciano" in k)
    before = page.evaluate(MARKER_JS, lourdes)

    # No page scroll hijack: the wheel over an unfocused map scrolls the page.
    page.mouse.move(400, 500)
    scroll0 = page.evaluate("() => window.scrollY")
    box = page.locator("#world-map [data-fs-zoom]").bounding_box()
    page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    page.mouse.wheel(0, 300)
    page.wait_for_timeout(300)
    check(page.evaluate(STATE_JS, "#world-map")["z"] == 1 and page.evaluate("() => window.scrollY") != scroll0,
          "no hijack: the wheel scrolls the page until the map is clicked or focused")
    page.evaluate("() => window.scrollTo(0, 0)")

    # Keyboard: + zooms, arrows pan (clamped), 0 resets; limits 1x-6x.
    page.focus("#world-map [data-fs-zoom]")
    page.keyboard.press("+")
    check(abs(page.evaluate(STATE_JS, "#world-map")["z"] - 1.5) < .01, "keyboard: + zooms in")
    for _ in range(10):
        page.keyboard.press("+")
    s = page.evaluate(STATE_JS, "#world-map")
    check(abs(s["z"] - 6) < .01, f"limit: the world map stops at 6x ({s['z']:.2f})")
    for _ in range(40):
        page.keyboard.press("ArrowLeft")
    s = page.evaluate(STATE_JS, "#world-map")
    check(s["tx"] <= 0.01 and abs(s["tx"]) < 0.01, f"pan clamp: can't drag past the left edge (tx {s['tx']:.1f})")
    for _ in range(80):
        page.keyboard.press("ArrowRight")
    s = page.evaluate(STATE_JS, "#world-map")
    check(abs(s["tx"] - (s["w"] - s["w"] * s["z"])) < 0.01, "pan clamp: can't drag past the right edge")
    check(page.evaluate("() => Array.from(document.querySelectorAll('#world-map [data-fs-detail]')).every(u => u.getAttribute('href').includes('world-outline-50m'))"),
          "detail: the 1:50m outline is used past 2x")
    check(s["nudge"] in ("0", "0.0"), f"offsets fade out above 2x (--nudge {s['nudge']})")
    page.keyboard.press("0")
    page.wait_for_timeout(500)
    s = page.evaluate(STATE_JS, "#world-map")
    check(s["z"] == 1 and s["tx"] == 0 and s["ty"] == 0, "keyboard: 0 resets")
    for _ in range(10):
        page.keyboard.press("-")
    check(page.evaluate(STATE_JS, "#world-map")["z"] == 1, "limit: never below 1x")

    # Markers keep their size and their true spots at any zoom.
    page.locator("#world-map [data-fs-zoom-in]").click()
    page.locator("#world-map [data-fs-zoom-in]").click()
    page.locator("#world-map [data-fs-zoom-in]").click()
    page.wait_for_timeout(500)
    s = page.evaluate(STATE_JS, "#world-map")
    after = page.evaluate(MARKER_JS, lourdes)
    check(abs(after["disc"][0] - before["disc"][0]) < .6, f"markers keep their screen size ({before['disc'][0]:.1f} -> {after['disc'][0]:.1f} px at {s['z']:.2f}x)")
    ex = s["left"] + s["tx"] + after["x"] / 1000 * s["w"] * s["z"]
    ey = s["top"] + s["ty"] + after["y"] / 445 * s["h"] * s["z"]
    check(abs(after["spot"][0] - ex) < 1.5 and abs(after["spot"][1] - ey) < 1.5, "pins stay on their true spots when zoomed")

    # Region shortcuts frame their stories.
    def inside(key):
        m = page.evaluate(MARKER_JS, key)
        vp = page.locator("#world-map [data-fs-zoom]").bounding_box()
        return vp["x"] <= m["spot"][0] <= vp["x"] + vp["width"] and vp["y"] <= m["spot"][1] <= vp["y"] + vp["height"]

    regions = page.eval_on_selector_all("[data-fs-region]", "els => els.map(e => e.textContent.trim())")
    page.click("[data-fs-region] >> text=Europe")
    page.wait_for_timeout(600)
    check(inside(lourdes) and inside(lanciano), "Europe: Lourdes and Lanciano in view")
    page.locator(".fs-world-explore").screenshot(path=f"{out}/world-1440-europe.png")
    page.click("[data-fs-region] >> text=Holy Land")
    page.wait_for_timeout(600)
    sepulchre = next(k for k in keys if "sepulchre" in k)
    check(inside(sepulchre), "Holy Land: the Holy Sepulchre in view")
    page.locator(".fs-world-explore").screenshot(path=f"{out}/world-1440-holy-land.png")
    page.click("[data-fs-region] >> text=The Americas")
    page.wait_for_timeout(600)
    check(inside("california-missions"), "The Americas: the California callout in view")
    page.click("[data-fs-region-all]")
    page.wait_for_timeout(600)
    check(page.evaluate(STATE_JS, "#world-map")["z"] == 1, "Whole World resets")
    check(regions == ["Europe", "Holy Land", "The Americas"], f"the region shortcuts {regions}")

    # Selecting from the list zooms to the story.
    page.click(f'.fs-world-show[href*="story={lanciano}"]')
    page.wait_for_timeout(700)
    check(page.evaluate(STATE_JS, "#world-map")["z"] >= 2.4 and inside(lanciano), "list: Show on the map zooms to the story")
    ctx.close()

    # Reduced motion: it jumps, no animation.
    ctx = browser.new_context(viewport={"width": 1440, "height": 1000}, reduced_motion="reduce")
    page = ctx.new_page()
    page.goto(base + WORLD + f"?story={lanciano}", wait_until="networkidle")
    check(page.evaluate("() => getComputedStyle(document.querySelector('.fs-zoom-stage')).transitionDuration") in ("0s", ""),
          "reduced motion: no zoom animation")
    check(page.evaluate(STATE_JS, "#world-map")["z"] >= 2.4, "?story= arrives zoomed to the story")
    ctx.close()

    # Touch: the chooser still works when zoomed.
    ctx = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, has_touch=True, is_mobile=True)
    page = ctx.new_page()
    page.goto(base + WORLD, wait_until="networkidle")
    page.locator("#world-map").scroll_into_view_if_needed()
    page.evaluate("() => document.querySelector('#world-map [data-fs-zoom]').fsZoom.zoomBy(1.4)")
    page.wait_for_timeout(300)
    a, b = page.evaluate(MARKER_JS, lourdes)["spot"], page.evaluate(MARKER_JS, lanciano)["spot"]
    page.mouse.click((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
    page.wait_for_timeout(300)
    check(page.is_visible("#world-map [data-fs-chooser]"), "touch: Which story? still opens when zoomed")
    page.locator(".fs-world-explore").screenshot(path=f"{out}/world-390-zoomed-chooser.png")
    ctx.close()

    # California: 1x-4x, pins keep their size, the art at 3x.
    ctx = browser.new_context(viewport={"width": 1440, "height": 1000}, device_scale_factor=2)
    page = ctx.new_page()
    page.goto(base + HUB, wait_until="networkidle")
    bell = lambda: page.evaluate("() => document.querySelector('[data-fs-pin] .fs-pin-bell').getBoundingClientRect().width")
    b1 = bell()
    page.focus("#mission-map [data-fs-zoom]")
    for _ in range(8):
        page.keyboard.press("+")
    page.wait_for_timeout(600)          # let the zoom animation finish before measuring
    check(abs(page.evaluate(STATE_JS, "#mission-map")["z"] - 4) < .01, "limit: California stops at 4x")
    check(abs(bell() - b1) < .6, "California: pins keep their screen size")
    page.keyboard.press("0")
    page.wait_for_timeout(500)
    page.evaluate("() => document.querySelector('#mission-map [data-fs-zoom]').fsZoom.focus(260, 520, 3)")
    page.wait_for_timeout(600)
    page.locator(".fs-hub-explore").screenshot(path=f"{out}/california-1440-3x.png")
    ctx.close()


if __name__ == "__main__":
    main()
