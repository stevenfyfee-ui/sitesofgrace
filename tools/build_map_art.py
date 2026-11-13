"""Web-optimize Steven's map art for the Future Saints maps (run by hand when the art changes).

    python tools/build_map_art.py "C:/Users/steve/OneDrive/Pictures/SitesofGrace/map-art"

Reads the source folder (never writes to it) and picks each file by the number at the end of
its name ("...-3.png" is piece 3). Writes sitesofgrace/static/future_saints/map-art/:

- the two textures (1, 2) at their own 1254 px, as JPEG quality 82: the source PNGs are about
  2.3 MB each, and the textures are opaque, so JPEG keeps them soft at a tenth of the weight;
- the eight transparent pieces (3-10), resized to WIDTH_PX (2x their largest display size: their
  width in map units x 0.707 px per unit on the widest map x 4 for California's 4x zoom x 2 for
  high-density screens) and saved as 256-colour PNG with transparency.

Standard library and Pillow only.
"""
import os
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "sitesofgrace" / "static" / "future_saints" / "map-art"
TEXTURES = {1: "land-texture.jpg", 2: "ocean-texture.jpg"}
PIECES = {
    3: "mountain-range.png", 4: "tall-mountain.png", 5: "oak-tree.png", 6: "redwoods.png", 7: "palm-tree.png",
    8: "poppies.png", 9: "sailing-ship.png", 10: "whale-waves.png",
}
# Largest display width in map units (future_saints.missions.CALIFORNIA_ART), x 0.707 x 4 x 2.
WIDTH_UNITS = {3: 170, 4: 70, 5: 46, 6: 52, 7: 34, 8: 110, 9: 90, 10: 120}


def main(source):
    files = {}
    for name in os.listdir(source):
        stem, ext = os.path.splitext(name)
        if ext.lower() == ".png" and "-" in stem and stem.rsplit("-", 1)[1].isdigit():
            files[int(stem.rsplit("-", 1)[1])] = Path(source) / name
    missing = sorted((set(TEXTURES) | set(PIECES)) - set(files))
    if missing:
        raise SystemExit(f"missing pieces: {missing}")
    OUT.mkdir(parents=True, exist_ok=True)
    total = 0
    for n, name in TEXTURES.items():
        target = OUT / name
        Image.open(files[n]).convert("RGB").save(target, "JPEG", quality=82, optimize=True, progressive=True)
        total += target.stat().st_size
        print(f"{n:2} {files[n].name} -> {name} {Image.open(target).size} {target.stat().st_size // 1024} KB")
    for n, name in PIECES.items():
        image = Image.open(files[n]).convert("RGBA")
        width = min(image.width, round(WIDTH_UNITS[n] * 0.707 * 4 * 2))
        height = round(image.height * width / image.width)
        resized = image.resize((width, height), Image.LANCZOS)
        target = OUT / name
        resized.quantize(256, method=Image.Quantize.FASTOCTREE, dither=Image.Dither.FLOYDSTEINBERG).save(target, optimize=True)
        total += target.stat().st_size
        print(f"{n:2} {files[n].name} -> {name} {image.size} -> {width}x{height} {target.stat().st_size // 1024} KB")
    print(f"total {total // 1024} KB in {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main(sys.argv[1])
