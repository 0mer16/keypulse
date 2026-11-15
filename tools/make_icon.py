"""Generates keypulse/resources/icon.ico and icon.png (spectrum bars on a gradient tile)."""
from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parent.parent / "keypulse" / "resources"
S = 512


def tile():
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    grad = Image.new("RGBA", (S, S))
    top, bottom = (122, 92, 255), (255, 0, 200)
    px = grad.load()
    for y in range(S):
        for x in range(S):
            t = (x + y) / (2 * S)
            px[x, y] = tuple(int(a + (b - a) * t) for a, b in zip(top, bottom)) + (255,)
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle((16, 16, S - 16, S - 16), radius=110, fill=255)
    img.paste(grad, (0, 0), mask)
    d = ImageDraw.Draw(img)
    heights = [0.35, 0.6, 0.9, 0.55, 0.75, 0.4]
    bw, gap = 46, 22
    x0 = (S - (len(heights) * bw + (len(heights) - 1) * gap)) // 2
    base = S - 120
    for i, h in enumerate(heights):
        x = x0 + i * (bw + gap)
        d.rounded_rectangle((x, base - int(h * 290), x + bw, base), radius=18, fill=(255, 255, 255, 240))
    return img


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    img = tile()
    img.save(OUT / "icon.png")
    img.save(OUT / "icon.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print("wrote", OUT / "icon.ico")
