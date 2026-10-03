"""Generates icon.png and icon.ico (needs Pillow; only used to (re)build the icon)."""
from pathlib import Path

from PIL import Image, ImageDraw

ACCENT = "#7C5CFF"
BG = "#1E1F22"
LIGHT = "#DBDEE1"
S = 1024  # supersampled canvas


def build() -> Image.Image:
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, S - 1, S - 1), radius=220, fill=BG)

    # gamepad silhouette: body + two grips
    d.rounded_rectangle((150, 290, 874, 600), radius=150, fill=ACCENT)
    d.ellipse((170, 440, 430, 800), fill=ACCENT)
    d.ellipse((594, 440, 854, 800), fill=ACCENT)
    # d-pad and buttons cut out of the silhouette
    d.rounded_rectangle((258, 400, 408, 450), radius=14, fill=BG)
    d.rounded_rectangle((308, 350, 358, 500), radius=14, fill=BG)
    d.ellipse((650, 380, 722, 452), fill=BG)
    d.ellipse((738, 450, 810, 522), fill=BG)

    # clock badge, bottom right
    cx, cy = 740, 750
    d.ellipse((cx - 205, cy - 205, cx + 205, cy + 205), fill=BG)
    d.ellipse((cx - 175, cy - 175, cx + 175, cy + 175), fill=ACCENT)
    d.ellipse((cx - 135, cy - 135, cx + 135, cy + 135), fill=BG)
    d.line((cx, cy, cx, cy - 95), fill=LIGHT, width=30)
    d.line((cx, cy, cx + 70, cy + 30), fill=LIGHT, width=30)
    d.ellipse((cx - 22, cy - 22, cx + 22, cy + 22), fill=LIGHT)
    return img


if __name__ == "__main__":
    here = Path(__file__).parent
    big = build()
    big.resize((256, 256), Image.LANCZOS).save(here / "icon.png")
    big.save(here / "icon.ico", sizes=[(16, 16), (32, 32), (48, 48), (256, 256)])
