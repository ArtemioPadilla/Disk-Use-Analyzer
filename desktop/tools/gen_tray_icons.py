#!/usr/bin/env python3
"""Generate the macOS menu-bar tray icons for the three disk-pressure states.

Each icon is a rounded rectangle: a neutral "track" background, a colored
fill proportional to how full the disk is for that state, and a dark
outline traced on top of a white halo. The halo+outline pair is what keeps
the shape legible against both a light and a dark menu bar — a translucent
macOS menu bar sits over arbitrary wallpaper, so a single-color outline
would vanish against a background close to its own color.

Run with:
    venv-web/bin/python3 desktop/tools/gen_tray_icons.py

Regenerate whenever the palette or fill ratios change; the PNGs in
desktop/src-tauri/assets/tray/ are the committed output of this script, not
hand-edited.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

OUT_DIR = Path(__file__).resolve().parent.parent / "src-tauri" / "assets" / "tray"

# Supersample factor: draw big, then downsample with LANCZOS for clean
# anti-aliased edges at the tiny final sizes (22px / 44px).
SUPERSAMPLE = 8

# (state name, fill color, fraction of the bar considered "used")
# Ratios are illustrative of the state, not a literal live reading — this is
# a static tray icon per Estado, not a live gauge.
STATES = [
    ("ok", (52, 199, 89, 255), 0.25),  # Apple system green, mostly empty
    ("aviso", (255, 159, 10, 255), 0.60),  # Apple system amber, tightening
    ("critico", (255, 59, 48, 255), 0.90),  # Apple system red, nearly full
]

TRACK_COLOR = (235, 235, 235, 255)  # neutral "unused capacity" background
HALO_COLOR = (255, 255, 255, 230)  # near-opaque white halo for dark backgrounds
OUTLINE_COLOR = (20, 20, 20, 255)  # dark outline for light backgrounds


def render(size: int, fill_color: tuple[int, int, int, int], fill_ratio: float) -> Image.Image:
    big = size * SUPERSAMPLE
    canvas = Image.new("RGBA", (big, big), (0, 0, 0, 0))

    # Margins scale with size so the halo/outline stay proportionally
    # consistent between the 22px and 44px renders.
    halo_margin = big * 0.06
    stroke_w = max(big * 0.05, 1)
    shape_margin = halo_margin + stroke_w * 0.6
    radius = big * 0.28

    draw = ImageDraw.Draw(canvas)

    # 1. White halo: a slightly larger rounded rect, drawn first, so the
    #    dark outline traced on top of it reads even against a black menu bar.
    draw.rounded_rectangle(
        [halo_margin, halo_margin, big - halo_margin, big - halo_margin],
        radius=radius,
        fill=HALO_COLOR,
    )

    # 2. Track: the main shape's "empty" background.
    shape_box = [shape_margin, shape_margin, big - shape_margin, big - shape_margin]
    inner_radius = radius * 0.9
    draw.rounded_rectangle(shape_box, radius=inner_radius, fill=TRACK_COLOR)

    # 3. Proportional fill, clipped to the rounded shape via a mask so the
    #    fill respects the corner radius instead of poking out square.
    shape_mask = Image.new("L", (big, big), 0)
    ImageDraw.Draw(shape_mask).rounded_rectangle(shape_box, radius=inner_radius, fill=255)

    band_mask = Image.new("L", (big, big), 0)
    fill_top = shape_box[3] - (shape_box[3] - shape_box[1]) * fill_ratio
    ImageDraw.Draw(band_mask).rectangle([0, fill_top, big, big], fill=255)

    from PIL import ImageChops

    combined_mask = ImageChops.darker(shape_mask, band_mask)

    fill_layer = Image.new("RGBA", (big, big), fill_color)
    canvas = Image.composite(fill_layer, canvas, combined_mask)

    # 4. Outline on top, traced over the halo so it stays crisp regardless
    #    of what's beneath the icon on screen.
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle(shape_box, radius=inner_radius, outline=OUTLINE_COLOR, width=int(stroke_w))

    return canvas.resize((size, size), Image.LANCZOS)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for name, color, ratio in STATES:
        icon_1x = render(22, color, ratio)
        icon_1x.save(OUT_DIR / f"{name}.png")

        icon_2x = render(44, color, ratio)
        icon_2x.save(OUT_DIR / f"{name}@2x.png")

        print(f"wrote {name}.png (22x22) and {name}@2x.png (44x44)")


if __name__ == "__main__":
    main()
