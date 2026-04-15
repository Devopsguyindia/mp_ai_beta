"""
One-off generator: writes PNG room plates into app/showcase/data/scene_backdrops/.
Run from repo root:  python scripts/build_scene_backdrops.py
Or from copilot-api:  python scripts/build_scene_backdrops.py
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

# Resolve package data dir
ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "app" / "showcase" / "data" / "scene_backdrops"
W, H = 1920, 1080


def _grad_vertical(top: tuple[int, int, int], bottom: tuple[int, int, int]) -> Image.Image:
    img = Image.new("RGB", (W, H))
    px = img.load()
    tr, tg, tb = top
    br, bg, bb = bottom
    hm = max(H - 1, 1)
    for y in range(H):
        f = y / hm
        r = int(tr + (br - tr) * f)
        g = int(tg + (bg - tg) * f)
        b = int(tb + (bb - tb) * f)
        for x in range(W):
            px[x, y] = (r, g, b)
    return img


def build_gallery_white_wall() -> Image.Image:
    img = _grad_vertical((248, 248, 246), (218, 216, 210))
    dr = ImageDraw.Draw(img)
    dr.rectangle((0, 0, int(W * 0.22), H), fill=(235, 236, 238))
    dr.rectangle((int(W * 0.18), int(H * 0.08), int(W * 0.2), int(H * 0.42)), fill=(210, 218, 232))
    dr.rectangle((0, int(H * 0.72), W, H), fill=(200, 198, 194))
    return img


def build_residential_living_warm() -> Image.Image:
    img = _grad_vertical((72, 58, 50), (38, 30, 26))
    dr = ImageDraw.Draw(img)
    dr.pieslice((int(W * 0.55), -200, int(W * 1.1), int(H * 0.55)), 180, 360, fill=(92, 72, 58))
    dr.rectangle((0, int(H * 0.78), W, H), fill=(48, 38, 32))
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d2 = ImageDraw.Draw(layer)
    d2.ellipse((int(W * 0.35), int(H * 0.12), int(W * 0.65), int(H * 0.38)), fill=(255, 190, 120, 40))
    layer = layer.filter(ImageFilter.GaussianBlur(40))
    return Image.alpha_composite(img.convert("RGBA"), layer).convert("RGB")


def build_residential_modern_cool() -> Image.Image:
    img = _grad_vertical((48, 56, 64), (26, 30, 36))
    dr = ImageDraw.Draw(img)
    dr.rectangle((int(W * 0.62), 0, W, int(H * 0.65)), fill=(56, 66, 76))
    dr.rectangle((0, int(H * 0.8), W, H), fill=(34, 38, 44))
    dr.line((int(W * 0.62), 0, int(W * 0.62), int(H * 0.65)), fill=(80, 92, 105), width=3)
    return img


def build_office_minimal() -> Image.Image:
    img = _grad_vertical((236, 238, 242), (214, 218, 226))
    dr = ImageDraw.Draw(img)
    for i in range(0, W, 56):
        dr.line((i, 0, i, int(H * 0.68)), fill=(226, 228, 232), width=1)
    dr.rectangle((0, int(H * 0.68), W, H), fill=(198, 202, 210))
    dr.rectangle((int(W * 0.08), int(H * 0.12), int(W * 0.28), int(H * 0.45)), fill=(200, 210, 225))
    return img


def build_hotel_lobby_luxury() -> Image.Image:
    img = _grad_vertical((96, 78, 62), (42, 34, 28))
    dr = ImageDraw.Draw(img)
    dr.pieslice((int(W * 0.4), -120, int(W * 0.92), int(H * 0.5)), 200, 340, fill=(120, 95, 72))
    dr.rectangle((0, int(H * 0.76), W, H), fill=(36, 30, 26))
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d2 = ImageDraw.Draw(layer)
    d2.ellipse((int(W * 0.42), int(H * 0.05), int(W * 0.58), int(H * 0.22)), fill=(255, 210, 150, 55))
    layer = layer.filter(ImageFilter.GaussianBlur(35))
    return Image.alpha_composite(img.convert("RGBA"), layer).convert("RGB")


def build_corridor_gallery() -> Image.Image:
    img = _grad_vertical((228, 228, 226), (188, 188, 184))
    dr = ImageDraw.Draw(img)
    cx = W // 2
    dr.polygon([(cx, int(H * 0.18)), (int(W * 0.92), H), (int(W * 0.08), H)], fill=(176, 176, 172))
    dr.line([(cx, int(H * 0.18)), (cx, H)], fill=(160, 160, 156), width=2)
    dr.rectangle((0, int(H * 0.82), W, H), fill=(168, 168, 164))
    return img


def build_studio_natural_north() -> Image.Image:
    img = _grad_vertical((236, 242, 248), (188, 198, 210))
    dr = ImageDraw.Draw(img)
    dr.rectangle((0, 0, int(W * 0.35), int(H * 0.55)), fill=(210, 224, 238))
    dr.rectangle((0, int(H * 0.72), W, H), fill=(200, 206, 214))
    return img


def build_pedestal_sculpture_spot() -> Image.Image:
    img = _grad_vertical((40, 40, 42), (12, 12, 14))
    dr = ImageDraw.Draw(img)
    dr.pieslice((int(W * 0.35), -80, int(W * 0.65), int(H * 0.35)), 0, 180, fill=(70, 70, 72))
    dr.ellipse((int(W * 0.38), int(H * 0.62), int(W * 0.62), int(H * 0.78)), fill=(28, 28, 30))
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d2 = ImageDraw.Draw(layer)
    d2.ellipse((int(W * 0.45), int(H * 0.08), int(W * 0.55), int(H * 0.2)), fill=(255, 255, 245, 70))
    layer = layer.filter(ImageFilter.GaussianBlur(25))
    return Image.alpha_composite(img.convert("RGBA"), layer).convert("RGB")


def build_cafe_brick_warm() -> Image.Image:
    img = _grad_vertical((92, 58, 44), (58, 36, 28))
    dr = ImageDraw.Draw(img)
    x0, y0, x1, y1 = int(W * 0.08), int(H * 0.10), int(W * 0.92), int(H * 0.72)
    dr.rectangle((x0, y0, x1, y1), fill=(138, 70, 50))
    row_h = 22
    for yy in range(y0, y1, row_h):
        dr.line((x0, yy, x1, yy), fill=(108, 56, 40), width=1)
    col_w = 46
    col = 0
    for xx in range(x0, x1, col_w):
        off = (row_h // 2) if col % 2 else 0
        dr.line((xx, y0 + off, xx, y1), fill=(98, 52, 36), width=1)
        col += 1
    dr.rectangle((0, int(H * 0.76), W, H), fill=(62, 42, 32))
    return img


def build_library_wood_study() -> Image.Image:
    img = _grad_vertical((42, 32, 24), (22, 16, 12))
    dr = ImageDraw.Draw(img)
    x0, y0, x1, y1 = int(W * 0.10), int(H * 0.07), int(W * 0.90), int(H * 0.70)
    dr.rectangle((x0, y0, x1, y1), fill=(72, 50, 34))
    for xx in range(x0 + 100, x1, 130):
        dr.line((xx, y0, xx, y1), fill=(54, 38, 26), width=2)
    dr.rectangle((0, int(H * 0.74), W, H), fill=(48, 36, 26))
    return img


def build_boutique_retail_wall() -> Image.Image:
    img = _grad_vertical((218, 216, 214), (188, 186, 184))
    dr = ImageDraw.Draw(img)
    x0, y0, x1, y1 = int(W * 0.24), int(H * 0.09), int(W * 0.76), int(H * 0.74)
    dr.rectangle((0, 0, W, int(H * 0.85)), fill=(210, 208, 206))
    dr.rectangle((x0 - 6, y0 - 6, x1 + 6, y1 + 6), outline=(175, 168, 158), width=8)
    dr.rectangle((x0, y0, x1, y1), fill=(248, 246, 242))
    dr.rectangle((0, int(H * 0.80), W, H), fill=(88, 84, 80))
    return img


def build_wellness_spa_calm() -> Image.Image:
    img = _grad_vertical((214, 224, 218), (188, 202, 194))
    dr = ImageDraw.Draw(img)
    x0, y0, x1, y1 = int(W * 0.12), int(H * 0.10), int(W * 0.88), int(H * 0.76)
    dr.rectangle((x0, y0, x1, y1), fill=(198, 210, 200))
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d2 = ImageDraw.Draw(layer)
    d2.ellipse((int(W * 0.22), int(H * 0.04), int(W * 0.78), int(H * 0.36)), fill=(255, 255, 255, 38))
    layer = layer.filter(ImageFilter.GaussianBlur(48))
    out = Image.alpha_composite(img.convert("RGBA"), layer).convert("RGB")
    dr = ImageDraw.Draw(out)
    dr.rectangle((0, int(H * 0.82), W, H), fill=(176, 186, 178))
    return out


def build_loft_concrete_raw() -> Image.Image:
    img = _grad_vertical((118, 118, 116), (72, 72, 70))
    dr = ImageDraw.Draw(img)
    x0, y0, x1, y1 = int(W * 0.07), int(H * 0.08), int(W * 0.93), int(H * 0.82)
    dr.rectangle((x0, y0, x1, y1), fill=(132, 132, 130))
    for yy in range(y0, y1, 28):
        dr.line((x0, yy, x1, yy), fill=(118, 118, 116), width=1)
    dr.rectangle((int(W * 0.02), int(H * 0.02), int(W * 0.055), int(H * 0.92)), fill=(86, 86, 84))
    dr.rectangle((0, int(H * 0.88), W, H), fill=(52, 52, 50))
    return img


def build_museum_salon_molding() -> Image.Image:
    img = _grad_vertical((210, 200, 182), (175, 165, 148))
    dr = ImageDraw.Draw(img)
    mx0, my0, mx1, my1 = int(W * 0.18), int(H * 0.08), int(W * 0.82), int(H * 0.78)
    dr.rectangle((mx0, my0, mx1, my1), fill=(225, 218, 202))
    x0, y0, x1, y1 = int(W * 0.26), int(H * 0.14), int(W * 0.74), int(H * 0.68)
    dr.rectangle((x0 - 8, y0 - 8, x1 + 8, y1 + 8), outline=(188, 172, 148), width=10)
    dr.rectangle((x0, y0, x1, y1), fill=(244, 238, 226))
    dr.rectangle((0, int(H * 0.84), W, H), fill=(165, 150, 130))
    return img


def build_bedroom_soft_neutral() -> Image.Image:
    img = _grad_vertical((228, 224, 218), (205, 200, 192))
    dr = ImageDraw.Draw(img)
    x0, y0, x1, y1 = int(W * 0.12), int(H * 0.06), int(W * 0.88), int(H * 0.58)
    dr.rectangle((x0, y0, x1, y1), fill=(236, 232, 226))
    dr.rectangle((int(W * 0.10), int(H * 0.56), int(W * 0.90), int(H * 0.68)), fill=(198, 190, 180))
    dr.rectangle((0, int(H * 0.68), W, H), fill=(188, 182, 174))
    return img


BUILDERS = {
    "gallery_white_wall": build_gallery_white_wall,
    "residential_living_warm": build_residential_living_warm,
    "residential_modern_cool": build_residential_modern_cool,
    "office_minimal": build_office_minimal,
    "hotel_lobby_luxury": build_hotel_lobby_luxury,
    "corridor_gallery": build_corridor_gallery,
    "studio_natural_north": build_studio_natural_north,
    "pedestal_sculpture_spot": build_pedestal_sculpture_spot,
    "cafe_brick_warm": build_cafe_brick_warm,
    "library_wood_study": build_library_wood_study,
    "boutique_retail_wall": build_boutique_retail_wall,
    "wellness_spa_calm": build_wellness_spa_calm,
    "loft_concrete_raw": build_loft_concrete_raw,
    "museum_salon_molding": build_museum_salon_molding,
    "bedroom_soft_neutral": build_bedroom_soft_neutral,
}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for sid, fn in BUILDERS.items():
        path = OUT / f"{sid}.png"
        im = fn()
        if im.size != (W, H):
            raise RuntimeError(f"{sid}: expected plate size {(W, H)}, got {im.size}")
        im.save(path, format="PNG", optimize=True)
        print("wrote", path.relative_to(ROOT))
    print("done.")


if __name__ == "__main__":
    main()
    sys.exit(0)
