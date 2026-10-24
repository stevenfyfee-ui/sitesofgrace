"""Check that no page scrolls sideways on phones (360, 390 and 430 px wide).

    python tools/check_overflow.py http://localhost:8000
    python tools/check_overflow.py http://localhost:8000 /explore/marian-apparitions/lourdes/ /destinations/

Needs Playwright with Chromium (the local screenshot image has both). Run it
against a local server with SOG_V2_ENABLED=on. With no paths, every page in
the server's /sitemap.xml is checked. A page fails when the document is
wider than the viewport; the elements that stick out past the right edge
(and aren't inside a scrolling or clipping box) are listed. Exits 1 if any
page fails. Writes nothing.
"""
import re
import sys
import urllib.parse
import urllib.request

from playwright.sync_api import sync_playwright

WIDTHS = (360, 390, 430)

OVERFLOW_JS = """() => {
  const width = document.documentElement.clientWidth;
  const culprits = [];
  for (const el of document.querySelectorAll('body *')) {
    const box = el.getBoundingClientRect();
    if (!box.width || box.right <= width + 0.5) continue;
    let clipped = false;
    for (let a = el.parentElement; a && a !== document.body; a = a.parentElement) {
      if (getComputedStyle(a).overflowX !== 'visible') { clipped = true; break; }
    }
    if (!clipped) culprits.push(`${el.tagName.toLowerCase()}.${String(el.className).trim().split(/\\s+/).join('.')} right=${Math.round(box.right)}`);
  }
  return {scrollWidth: document.documentElement.scrollWidth, width, culprits: culprits.slice(0, 8)};
}"""


def sitemap_paths(base):
    with urllib.request.urlopen(base.rstrip("/") + "/sitemap.xml", timeout=30) as response:
        xml = response.read().decode("utf-8")
    return [urllib.parse.urlsplit(loc).path for loc in re.findall(r"<loc>([^<]+)</loc>", xml)]


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    base = sys.argv[1].rstrip("/")
    paths = sys.argv[2:] or sitemap_paths(base)
    failures = 0
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for width in WIDTHS:
            page = browser.new_page(viewport={"width": width, "height": 900})
            for path in paths:
                response = page.goto(base + path, wait_until="networkidle")
                page.wait_for_timeout(300)
                result = page.evaluate(OVERFLOW_JS)
                if result["scrollWidth"] > result["width"]:
                    failures += 1
                    print(f"FAIL {width}px {path} ({response.status}): {result['scrollWidth']} > {result['width']}")
                    for culprit in result["culprits"]:
                        print(f"     {culprit}")
            page.close()
        browser.close()
    print(f"{len(paths)} page(s) x {len(WIDTHS)} widths: {failures} with sideways scroll")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
