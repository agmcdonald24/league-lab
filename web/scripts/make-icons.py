"""Draw the home-screen icons (web/public/icons/*.png) with Pillow: `python3 scripts/make-icons.py`.
A plain monogram on the app's green; the maskable variant keeps the mark inside the 80% safe zone."""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parents[1] / "public" / "icons"
GREEN, WHITE = (21, 128, 61), (255, 255, 255)
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def icon(size: int, maskable: bool = False, radius: float = 0.0) -> Image.Image:
    scale = 4
    s = size * scale
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    if radius:
        d.rounded_rectangle([0, 0, s - 1, s - 1], radius=int(s * radius), fill=GREEN)
    else:
        d.rectangle([0, 0, s, s], fill=GREEN)
    mark = 0.36 if maskable else 0.46
    font = ImageFont.truetype(FONT, int(s * mark))
    text = "LL"
    box = d.textbbox((0, 0), text, font=font)
    w, h = box[2] - box[0], box[3] - box[1]
    d.text(((s - w) / 2 - box[0], (s - h) / 2 - box[1] - s * 0.02), text, font=font, fill=WHITE)
    # a thin underline: the "lab" bench line
    y = (s + h) / 2 + s * 0.05
    d.rounded_rectangle([s * 0.3, y, s * 0.7, y + s * 0.035], radius=int(s * 0.02), fill=WHITE)
    return img.resize((size, size), Image.LANCZOS)


OUT.mkdir(parents=True, exist_ok=True)
icon(192).save(OUT / "icon-192.png")
icon(512).save(OUT / "icon-512.png")
icon(512, maskable=True).save(OUT / "icon-maskable-512.png")
icon(180).convert("RGB").save(OUT / "apple-touch-icon.png")
icon(64, radius=0.2).save(OUT / "favicon-64.png")
print("icons written to", OUT)
