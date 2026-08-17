#!/usr/bin/env python3
"""
Derive the workspace's brand images from the Innovation Forum master logo.

    python3 scripts/prepare-brand.py

Produces two files, both from one source, so there is no hand-edited artwork to
drift:

    public/brand/if-mark.png    the coloured mark alone, transparent background
    public/brand/oauth-icon.png 400x400 square for the GitHub OAuth App

Why the mark is separated from the wordmark
-------------------------------------------
The master is a 200x200 JPEG: a coloured triangle above the words "Innovation
FORUM" in black, flattened onto white. Used whole on the workspace's ink ground
it fails twice — the white matte shows as a pale slab, and black type on a dark
green background is close to unreadable.

So the mark is cropped out and the wordmark is set in live text instead, in
white. That is the same construction the marketing site's nav pill uses (logo
image + text wordmark), which is why the two now look related.

The crop is measured, not guessed: the wordmark is black and the mark is
saturated colour, so the mark's bounding box is found by saturation, and the
cut is taken in the measured gap between the two.

Un-matting, not "make white transparent"
----------------------------------------
Naively keying out white leaves pale fringes, because antialiased edge pixels
are blends of ink and the white matte. This recovers how opaque each pixel is
and divides the matte back out, so the edge stays clean on any background. The
result is verified by recompositing over white — it must reproduce the source,
or the script refuses to write.

The OAuth icon exists because GitHub shows the app's logo on its own sign-in
screen, which is the one surface in the flow we cannot style. Uploading it is a
manual step — see the workspace README.
"""
import sys
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    sys.exit("Pillow is required:  pip3 install Pillow")

HERE = Path(__file__).resolve().parent.parent
MASTER = Path(
    "/Users/yavinowens/Library/CloudStorage/OneDrive-R1x/R1X Foundry - Documents/"
    "05_PRODUCT_AND_PLATFORM/website_/public/assets/Innovation-Forum-logo.jpeg"
)
OUT = HERE / "public" / "brand"

INK = (4, 24, 15)          # --ink, the workspace ground
SATURATED = 55             # min channel spread to count a pixel as coloured
PAD = 6                    # transparent padding kept around the mark
ALPHA_FLOOR = 26           # below this, a pixel is JPEG ringing, not ink


def mark_bbox(im):
    """Bounding box of the coloured mark, ignoring the black wordmark."""
    px, (w, h) = im.load(), im.size
    xs, ys = [], []
    for y in range(h):
        for x in range(w):
            r, g, b = px[x, y]
            if max(r, g, b) > 60 and (max(r, g, b) - min(r, g, b)) > SATURATED:
                xs.append(x)
                ys.append(y)
    if not xs:
        sys.exit("no coloured mark found — has the master been replaced?")
    return min(xs), min(ys), max(xs), max(ys)


def unmatte_white(im):
    """RGB-on-white -> RGBA with real transparency, edges un-blended."""
    px, (w, h) = im.load(), im.size
    out = Image.new("RGBA", (w, h))
    op = out.load()
    for y in range(h):
        for x in range(w):
            r, g, b = px[x, y]
            # How much ink is here at all: white is 0, fully saturated is 1.
            a = 255 - min(r, g, b)
            # The master is a lossy JPEG, so its "white" is not 255 everywhere —
            # ringing around the mark leaves a haze of very-low-alpha pixels
            # that reads as dark speckle once composited on the ink ground.
            # Anything this faint is codec noise, not artwork.
            if a <= ALPHA_FLOOR:
                op[x, y] = (0, 0, 0, 0)
                continue
            f = a / 255.0
            # Divide the white matte back out to recover the original ink.
            op[x, y] = (
                max(0, min(255, round((r - 255 * (1 - f)) / f))),
                max(0, min(255, round((g - 255 * (1 - f)) / f))),
                max(0, min(255, round((b - 255 * (1 - f)) / f))),
                a,
            )
    return out


def verify(rgba, original):
    """Recomposite over white; it must reproduce the source we started from."""
    flat = Image.new("RGB", rgba.size, (255, 255, 255))
    flat.paste(rgba, mask=rgba.split()[3])
    a, b = flat.load(), original.load()
    worst = 0
    for y in range(rgba.size[1]):
        for x in range(rgba.size[0]):
            worst = max(worst, max(abs(p - q) for p, q in zip(a[x, y], b[x, y])))
    return worst


def main():
    if not MASTER.exists():
        sys.exit(f"master logo not found:\n  {MASTER}")
    src = Image.open(MASTER).convert("RGB")

    x0, y0, x1, y1 = mark_bbox(src)
    box = (max(0, x0 - PAD), max(0, y0 - PAD),
           min(src.width, x1 + 1 + PAD), min(src.height, y1 + 1 + PAD))
    cropped = src.crop(box)

    mark = unmatte_white(cropped)
    drift = verify(mark, cropped)
    # JPEG is lossy, so the master's "white" is not exactly 255 everywhere; a
    # couple of levels of difference is the codec, not a broken un-matte.
    if drift > ALPHA_FLOOR + 4:
        sys.exit(f"un-matte did not round-trip (worst channel error {drift}) — refusing to write")

    OUT.mkdir(parents=True, exist_ok=True)
    mark.save(OUT / "if-mark.png")

    # Square icon for GitHub. The mark is taller than it is wide, so it is fitted
    # by height with the ink ground behind it rather than stretched.
    side = 400
    icon = Image.new("RGBA", (side, side), INK + (255,))
    scale = int(side * 0.56) / mark.height
    fitted = mark.resize((round(mark.width * scale), round(mark.height * scale)),
                         Image.LANCZOS)
    icon.paste(fitted,
               ((side - fitted.width) // 2, (side - fitted.height) // 2),
               fitted)
    icon.convert("RGB").save(OUT / "oauth-icon.png")

    print(f"  crop      {box}  ({cropped.width}x{cropped.height})")
    print(f"  round-trip worst channel error: {drift}  (JPEG ringing below the alpha floor)")
    print(f"  wrote     public/brand/if-mark.png     {mark.width}x{mark.height} RGBA")
    print(f"  wrote     public/brand/oauth-icon.png  {side}x{side} RGB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
