"""Draw assets/icon.png (1024x1024), matching web/favicon.svg. Needs Pillow."""
from pathlib import Path

from PIL import Image, ImageDraw

SIZE = 1024
S = SIZE / 64  # the SVG is drawn on a 64x64 grid
STOPS = [(0.0, (0xF5, 0x85, 0x29)), (0.5, (0xDD, 0x2A, 0x7B)), (1.0, (0x81, 0x34, 0xAF))]


def color_at(t):
    for (t0, c0), (t1, c1) in zip(STOPS, STOPS[1:]):
        if t <= t1:
            f = (t - t0) / (t1 - t0)
            return tuple(round(a + (b - a) * f) for a, b in zip(c0, c1))
    return STOPS[-1][1]


def main():
    grad = Image.new("RGB", (SIZE, SIZE))
    px = grad.load()
    for y in range(SIZE):
        for x in range(SIZE):
            px[x, y] = color_at((x + y) / (2 * (SIZE - 1)))

    mask = Image.new("L", (SIZE, SIZE), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, SIZE - 1, SIZE - 1], radius=16 * S, fill=255)
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    img.paste(grad, (0, 0), mask)

    # Music note from the SVG path, shifted by translate(-1 4).
    def p(x, y):
        return ((x - 1) * S, (y + 4) * S)

    d = ImageDraw.Draw(img)
    white = (255, 255, 255, 255)
    d.polygon([p(22, 18), p(42, 13), p(42, 17), p(22, 22)], fill=white)  # beam
    d.rectangle([p(22, 18), p(26, 40.5)], fill=white)  # left stem
    d.rectangle([p(38, 14), p(42, 36.5)], fill=white)  # right stem
    for cx, cy in ((19.5, 40.5), (35.5, 36.5)):  # note heads
        d.ellipse([p(cx - 6.5, cy - 6.5), p(cx + 6.5, cy + 6.5)], fill=white)

    out = Path(__file__).resolve().parent.parent / "assets" / "icon.png"
    out.parent.mkdir(exist_ok=True)
    img.save(out)
    print("wrote", out)


if __name__ == "__main__":
    main()
