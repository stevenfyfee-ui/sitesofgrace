"""Measure the missions map as rendered: the map box, each pin's bell and each
Founding # badge, at the six QA widths (CSS pixels, relative to the map's
top-left). Used to choose badge offsets and city-label positions.

    python tools/measure_mission_map.py <base_url> > measurements.json
"""
import json
import sys

from playwright.sync_api import sync_playwright

WIDTHS = (1440, 1024, 768, 430, 390, 360)
JS = """() => { const m = document.querySelector('.fs-map').getBoundingClientRect();
  const rel = r => [r.left - m.left, r.top - m.top, r.right - m.left, r.bottom - m.top];
  return {map: [m.width, m.height], pins: Array.from(document.querySelectorAll('[data-fs-pin]')).map(b => ({
    number: +b.querySelector('.fs-pin-num').textContent, bell: rel(b.querySelector('.fs-pin-bell').getBoundingClientRect()),
    badge: rel(b.querySelector('.fs-pin-num').getBoundingClientRect())}))}; }"""


def main():
    base = sys.argv[1].rstrip("/")
    out = {}
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for width in WIDTHS:
            page = browser.new_page(viewport={"width": width, "height": 900})
            page.goto(base + "/future-saints/california-missions/", wait_until="networkidle")
            out[width] = page.evaluate(JS)
            page.close()
        browser.close()
    print(json.dumps(out))


if __name__ == "__main__":
    main()
