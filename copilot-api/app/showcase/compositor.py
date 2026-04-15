from __future__ import annotations

import hashlib
import io
import logging
import os
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageOps

from .backdrop_assets import packaged_scene_backdrop_path
from .compositor_geometry import (
    focal_rect_to_pixels,
    pil_perspective_coeffs,
    quad_bbox_wh,
    quad_norm_to_pixels,
    valid_focal_rect,
    valid_placement_quad,
)
from .models import SceneInfo
from .picture_stream import fetch_remote_image_bytes

logger = logging.getLogger(__name__)

_PROCEDURAL_SCENES: Final[dict[str, tuple[tuple[int, int, int], tuple[int, int, int]]]] = {
    "gallery_white_wall": ((245, 245, 242), (220, 218, 214)),
    "residential_living_warm": ((82, 64, 56), (45, 36, 32)),
    "residential_modern_cool": ((58, 68, 78), (32, 38, 46)),
    "office_minimal": ((235, 237, 240), (210, 214, 220)),
    "hotel_lobby_luxury": ((88, 72, 58), (42, 34, 28)),
    "corridor_gallery": ((228, 228, 226), (198, 198, 196)),
    "studio_natural_north": ((232, 238, 244), (175, 186, 198)),
    "pedestal_sculpture_spot": ((48, 48, 48), (16, 16, 16)),
    "cafe_brick_warm": ((92, 58, 44), (58, 36, 28)),
    "library_wood_study": ((42, 32, 24), (22, 16, 12)),
    "boutique_retail_wall": ((232, 230, 228), (188, 186, 184)),
    "wellness_spa_calm": ((214, 224, 218), (188, 202, 194)),
    "loft_concrete_raw": ((118, 118, 116), (72, 72, 70)),
    "museum_salon_molding": ((210, 200, 182), (175, 165, 148)),
    "bedroom_soft_neutral": ((228, 224, 218), (205, 200, 192)),
}


@dataclass(frozen=True)
class CompositeParams:
    frame_style: str | None = None
    """Wood / modern finish preset (server-drawn moulding). When set for wall art, overrides `frame_style` drawing."""
    frame_finish: str | None = None
    """thick | thin — scales custom frame moulding width."""
    frame_profile: str | None = None
    lighting: str | None = None
    placement: str | None = None
    layout_variant: int | None = None
    cutout: bool = False
    physical_width_cm: float | None = None
    physical_height_cm: float | None = None
    wall_width_cm: float | None = None
    wall_span_cm: float | None = None
    focal_wall_rect_override: tuple[float, float, float, float] | None = None
    placement_quad_override: list[tuple[float, float]] | None = None
    art_spotlight: str | None = None


def _cutout_enabled() -> bool:
    return os.getenv("SHOWCASE_CUTOUT_ENABLED", "0") in {"1", "true", "TRUE", "yes", "YES"}


def _vertical_gradient(size: tuple[int, int], top: tuple[int, int, int], bottom: tuple[int, int, int]) -> Image.Image:
    w, h = size
    img = Image.new("RGB", size)
    draw = ImageDraw.Draw(img)
    tr, tg, tb = top
    br, bg_, bb = bottom
    hm = max(h - 1, 1)
    for y in range(h):
        f = y / hm
        r = int(tr + (br - tr) * f)
        g = int(tg + (bg_ - tg) * f)
        b = int(tb + (bb - tb) * f)
        draw.line((0, y, w, y), fill=(r, g, b))
    return img


def _procedural_background(scene_id: str, size: tuple[int, int]) -> Image.Image:
    pair = _PROCEDURAL_SCENES.get(scene_id, ((236, 236, 236), (210, 210, 210)))
    return _vertical_gradient(size, pair[0], pair[1])


def _cover_crop_to_size(img: Image.Image, target: tuple[int, int]) -> Image.Image:
    tw, th = target
    if tw < 1 or th < 1:
        return img
    iw, ih = img.size
    if iw < 1 or ih < 1:
        return Image.new("RGB", target, (128, 128, 128))
    scale = max(tw / iw, th / ih)
    nw, nh = max(int(iw * scale), 1), max(int(ih * scale), 1)
    img = img.resize((nw, nh), Image.Resampling.LANCZOS)
    left = max((nw - tw) // 2, 0)
    top = max((nh - th) // 2, 0)
    return img.crop((left, top, left + tw, top + th))


def _contain_size(
    img: Image.Image,
    max_w: int,
    max_h: int,
    *,
    allow_upscale: bool = False,
    max_upscale_factor: float = 8.0,
) -> Image.Image:
    if max_w < 1 or max_h < 1:
        return img
    iw, ih = img.size
    if iw < 1 or ih < 1:
        return img
    scale = min(max_w / iw, max_h / ih)
    if not allow_upscale:
        scale = min(scale, 1.0)
    else:
        scale = min(scale, max_upscale_factor)
    nw, nh = max(int(iw * scale), 1), max(int(ih * scale), 1)
    if nw == iw and nh == ih:
        return img
    return img.resize((nw, nh), Image.Resampling.LANCZOS)


def _prepare_loaded_art_rgba(art: Image.Image) -> Image.Image:
    """Apply EXIF orientation, normalize to RGBA, flatten near-invisible alpha for compositing."""
    try:
        art = ImageOps.exif_transpose(art)
    except Exception:
        pass
    if art.mode == "CMYK":
        art = art.convert("RGB")
    art = art.convert("RGBA")
    alpha = art.getchannel("A")
    a_min, a_max = alpha.getextrema()
    if a_max < 12:
        base = Image.new("RGB", art.size, (252, 251, 248))
        base.paste(art, (0, 0), art)
        return base.convert("RGBA")
    if a_min < 250:
        base = Image.new("RGB", art.size, (255, 255, 255))
        base.paste(art, (0, 0), art)
        return base.convert("RGBA")
    return art


def _art_rgb_for_paste(art: Image.Image) -> Image.Image:
    """
    PIL paste(self, im, box, mask=im) with RGBA can drop pixels when alpha is odd;
    flatten onto white and paste RGB only so the artwork is always visible.
    """
    if art.mode != "RGBA":
        return art.convert("RGB")
    r, g, b, a = art.split()
    if a.getextrema() == (255, 255):
        return Image.merge("RGB", (r, g, b))
    rgb = Image.new("RGB", art.size, (255, 255, 255))
    rgb.paste(art, (0, 0), art)
    return rgb


def _load_background_rgba(
    scene: SceneInfo,
    size: tuple[int, int],
    *,
    timeout_s: float,
    max_fetch_bytes: int,
) -> Image.Image:
    u = (scene.preview_asset_url or "").strip()
    if u.startswith(("http://", "https://")):
        try:
            body, _ct = fetch_remote_image_bytes(u, timeout_s=timeout_s, max_bytes=max_fetch_bytes)
            bg = Image.open(io.BytesIO(body)).convert("RGB")
            return _cover_crop_to_size(bg, size).convert("RGBA")
        except Exception as e:
            logger.warning("showcase compositor: scene preview_asset_url fetch failed %s: %s", u[:80], e)
    pkg = packaged_scene_backdrop_path(scene.scene_id)
    if pkg is not None:
        try:
            bg = Image.open(pkg).convert("RGB")
            return _cover_crop_to_size(bg, size).convert("RGBA")
        except Exception as e:
            logger.warning("showcase compositor: packaged backdrop failed %s: %s", pkg, e)
    rgb = _procedural_background(scene.scene_id, size)
    return rgb.convert("RGBA")


def _maybe_rembg(art: Image.Image) -> Image.Image:
    if not _cutout_enabled():
        return art
    try:
        from rembg import remove  # type: ignore[import-untyped]

        buf = io.BytesIO()
        art.convert("RGB").save(buf, format="PNG")
        out = remove(buf.getvalue())
        return Image.open(io.BytesIO(out)).convert("RGBA")
    except ImportError:
        logger.info("showcase cutout: rembg not installed; skipping")
        return art
    except Exception as e:
        logger.warning("showcase cutout failed: %s", e)
        return art


def _layout_offsets(*, cw: int, ch: int, layout_variant: int) -> tuple[int, int]:
    """Return nominal pixel offsets on the full canvas; caller scales by region/canvas when pasting into a focal ROI."""
    lv = max(0, min(7, layout_variant))
    ox = oy = 0
    # Strong enough to read on1200×900 plates after scaling into tight focal_wall_rects (~10–12 % of region).
    if lv == 1:
        ox = -int(cw * 0.11)
    elif lv == 2:
        ox = int(cw * 0.11)
    elif lv == 3:
        oy = int(ch * 0.10)
    elif lv == 4:
        oy = -int(ch * 0.09)
    elif lv == 5:
        ox, oy = -int(cw * 0.07), int(ch * 0.06)
    elif lv == 6:
        ox, oy = int(cw * 0.07), -int(ch * 0.06)
    elif lv == 7:
        ox, oy = 0, int(ch * 0.14)
    return ox, oy


def _nudge_quad_pts_layout(
    pts: Sequence[tuple[float, float]],
    *,
    cw: int,
    ch: int,
    layout_variant: int,
) -> list[tuple[float, float]]:
    """Translate perspective quad in pixel space so layout offset applies to warped placement too."""
    ox, oy = _layout_offsets(cw=cw, ch=ch, layout_variant=layout_variant)
    bw, bh = quad_bbox_wh(pts)
    dx = int(ox * (bw / max(cw, 1)))
    dy = int(oy * (bh / max(ch, 1)))
    if dx == 0 and dy == 0:
        return list(pts)
    out: list[tuple[float, float]] = []
    for px, py in pts:
        nx = max(0.0, min(float(cw - 1), px + dx))
        ny = max(0.0, min(float(ch - 1), py + dy))
        out.append((nx, ny))
    return out


def _max_art_box(
    cw: int,
    ch: int,
    *,
    art_frac: float,
    params: CompositeParams,
    scene: SceneInfo | None = None,
    region_w: int | None = None,
    region_h: int | None = None,
) -> tuple[int, int]:
    """Compute maximum artwork bounding box (pixels) inside the focal wall region.

    Priority for wall span (width calibration):
      1. params.wall_span_cm  — explicit request override
      2. scene.wall_span_cm   — manifest value for this scene
      3. params.wall_width_cm — legacy field
      4. SHOWCASE_STUDIO_WALL_WIDTH_CM env
    """
    rw = region_w if region_w is not None else cw
    rh = region_h if region_h is not None else ch
    # Resolve span / wall dimensions
    span = params.wall_span_cm or (scene.wall_span_cm if scene else None)
    wall_w = params.wall_width_cm or float(os.getenv("SHOWCASE_STUDIO_WALL_WIDTH_CM", "400"))
    wall_h = float(os.getenv("SHOWCASE_STUDIO_WALL_HEIGHT_CM", "280"))
    # Width scaling
    if params.physical_width_cm and span and span > 0:
        max_w = int((params.physical_width_cm / span) * rw * 0.92)
    elif params.physical_width_cm and wall_w > 0:
        max_w = int((params.physical_width_cm / wall_w) * cw * 0.88 * (rw / max(cw, 1)))
    else:
        max_w = int(rw * art_frac)
    # Height scaling
    if params.physical_height_cm and wall_h > 0:
        max_h = int((params.physical_height_cm / wall_h) * ch * 0.72 * (rh / max(ch, 1)))
    else:
        max_h = int(rh * art_frac)
    max_w = max(80, min(max_w, rw))
    max_h = max(80, min(max_h, rh))
    return max_w, max_h


def _resolved_placement_quad(scene: SceneInfo, p: CompositeParams) -> list[tuple[float, float]] | None:
    q = p.placement_quad_override or scene.placement_quad
    if q and valid_placement_quad(q):
        return q
    return None


def _resolved_focal_rect(scene: SceneInfo, p: CompositeParams) -> tuple[float, float, float, float] | None:
    r = p.focal_wall_rect_override or scene.focal_wall_rect
    if r and valid_focal_rect(r):
        return r
    return None


_SPOTLIGHT_OK: Final[frozenset[str]] = frozenset({"off", "top", "bottom", "left", "right", "lr", "tb", "quad"})


def _normalize_art_spotlight(raw: str | None) -> str:
    if not raw or not str(raw).strip():
        return "off"
    s = str(raw).strip().lower().replace(" ", "_").replace("-", "_")
    aliases = {
        "none": "off",
        "no": "off",
        "sides": "lr",
        "left_right": "lr",
        "horizontal": "lr",
        "top_bottom": "tb",
        "vertical": "tb",
        "all": "quad",
        "all_sides": "quad",
        "rim": "quad",
        "cross": "quad",
    }
    s = aliases.get(s, s)
    return s if s in _SPOTLIGHT_OK else "off"


def _draw_spotlight_fixture(
    dr: ImageDraw.ImageDraw,
    cx: int,
    cy: int,
    *,
    rx: int = 16,
    ry: int = 11,
) -> None:
    """Small track-head style lamp: housing ring + bright lens + hot core."""
    rx = max(6, rx)
    ry = max(5, ry)
    dr.ellipse(
        (cx - int(rx * 1.85), cy - int(ry * 1.85), cx + int(rx * 1.85), cy + int(ry * 1.85)),
        fill=(255, 248, 220, 50),
    )
    dr.ellipse(
        (cx - int(rx * 1.25), cy - int(ry * 1.25), cx + int(rx * 1.25), cy + int(ry * 1.25)),
        fill=(38, 40, 44, 215),
    )
    dr.ellipse((cx - rx, cy - ry, cx + rx, cy + ry), fill=(255, 252, 238, 250))
    dr.ellipse(
        (cx - max(4, rx // 2), cy - max(3, ry // 2), cx + max(4, rx // 2), cy + max(3, ry // 2)),
        fill=(255, 255, 255, 255),
    )


def _beam_trapezoid_soft(
    size: tuple[int, int],
    quad: tuple[tuple[int, int], tuple[int, int], tuple[int, int], tuple[int, int]],
    *,
    fill: tuple[int, int, int, int],
    blur_r: float = 14.0,
) -> Image.Image:
    """Filled trapezoid on transparent layer, blurred for a soft cone of light."""
    w, h = size
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    dr = ImageDraw.Draw(layer)
    dr.polygon(list(quad), fill=fill)
    if blur_r > 0.5:
        layer = layer.filter(ImageFilter.GaussianBlur(radius=blur_r))
    return layer


def _apply_art_spotlight(
    base: Image.Image,
    *,
    bbox: tuple[int, int, int, int],
    spotlight: str | None,
    cw: int,
    ch: int,
) -> Image.Image:
    """Track-style accent: visible fixtures, soft beams, bright pool on the framed area."""
    key = _normalize_art_spotlight(spotlight)
    if key == "off":
        return base
    x0, y0, x1, y1 = bbox
    x0 = max(0, min(cw - 1, x0))
    y0 = max(0, min(ch - 1, y0))
    x1 = max(x0 + 1, min(cw, x1))
    y1 = max(y0 + 1, min(ch, y1))
    w, h = x1 - x0, y1 - y0
    if w < 4 or h < 4:
        return base
    cx = (x0 + x1) // 2
    cy = (y0 + y1) // 2
    warm = (255, 248, 228)
    beam_fill = (255, 250, 230, 105)
    ov = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))

    spread = max(28, int(w * 0.22))
    inset = max(8, int(min(w, h) * 0.04))
    lamp_rx = max(11, int(min(w, h) * 0.045))
    lamp_ry = max(8, int(lamp_rx * 0.72))

    def paste_beam(quad_pts: tuple[tuple[int, int], tuple[int, int], tuple[int, int], tuple[int, int]]) -> None:
        nonlocal ov
        beam = _beam_trapezoid_soft((cw, ch), quad_pts, fill=beam_fill, blur_r=16.0)
        ov = Image.alpha_composite(ov, beam)

    # --- Soft beams from hardware toward artwork (drawn first, under surface wash) ---
    if key in {"top", "tb", "quad"}:
        ly = max(2, y0 - 14 - int(min(100, h * 0.14)))
        paste_beam(((x0 - 50, ly), (x1 + 50, ly), (x1 + inset, y0 + 8), (x0 - inset, y0 + 8)))
    if key in {"bottom", "tb", "quad"}:
        ly = min(ch - 3, y1 + 14 + int(min(100, h * 0.14)))
        paste_beam(((x0 - inset, y1 - 8), (x1 + inset, y1 - 8), (x1 + 50, ly), (x0 - 50, ly)))
    if key in {"left", "lr", "quad"}:
        lx = max(2, x0 - 14 - int(min(100, w * 0.14)))
        paste_beam(((lx, y0 - 50), (lx, y1 + 50), (x0 + 8, y1 + inset), (x0 + 8, y0 - inset)))
    if key in {"right", "lr", "quad"}:
        lx = min(cw - 3, x1 + 14 + int(min(100, w * 0.14)))
        paste_beam(((x1 - 8, y0 - inset), (x1 - 8, y1 + inset), (lx, y1 + 50), (lx, y0 - 50)))

    # --- Stronger directional rim + bright center pool on the framed region ---
    max_edge = 210
    edge_pow = 1.95
    cxn = (x0 + x1) / 2.0
    cyn = (y0 + y1) / 2.0
    rx_ellipse = max(w, h) * 0.48
    ry_ellipse = max(w, h) * 0.42
    pool_peak = 195
    pix = ov.load()
    assert pix is not None
    for yy in range(y0, y1):
        v = (yy - y0) / max(h - 1, 1)
        for xx in range(x0, x1):
            u = (xx - x0) / max(w - 1, 1)
            rim = 0.0
            if key in {"top", "tb", "quad"}:
                rim = max(rim, max_edge * ((1.0 - v) ** edge_pow))
            if key in {"bottom", "tb", "quad"}:
                rim = max(rim, max_edge * (v**edge_pow))
            if key in {"left", "lr", "quad"}:
                rim = max(rim, max_edge * ((1.0 - u) ** edge_pow))
            if key in {"right", "lr", "quad"}:
                rim = max(rim, max_edge * (u**edge_pow))
            dx = (xx - cxn) / max(rx_ellipse, 1.0)
            dy = (yy - cyn) / max(ry_ellipse, 1.0)
            dist = (dx * dx + dy * dy) ** 0.5
            pool = pool_peak * max(0.0, 1.0 - dist**1.65) if dist <= 1.0 else 0.0
            a = min(255, int(max(rim, pool)))
            if a > 0:
                pr, pg, pb = warm
                pix[xx, yy] = (pr, pg, pb, a)

    # --- Visible lamp hardware on top of beams (track heads) ---
    dr = ImageDraw.Draw(ov)
    if key in {"top", "tb", "quad"}:
        ly = max(2, y0 - 14 - int(min(100, h * 0.14)))
        _draw_spotlight_fixture(dr, cx - spread, ly, rx=lamp_rx, ry=lamp_ry)
        _draw_spotlight_fixture(dr, cx + spread, ly, rx=lamp_rx, ry=lamp_ry)
        dr.line(
            [cx - spread - lamp_rx, ly, cx + spread + lamp_rx, ly],
            fill=(55, 58, 62, 200),
            width=4,
        )
    if key in {"bottom", "tb", "quad"}:
        ly = min(ch - 3, y1 + 14 + int(min(100, h * 0.14)))
        _draw_spotlight_fixture(dr, cx - spread, ly, rx=lamp_rx, ry=lamp_ry)
        _draw_spotlight_fixture(dr, cx + spread, ly, rx=lamp_rx, ry=lamp_ry)
    if key in {"left", "lr", "quad"}:
        lx = max(2, x0 - 14 - int(min(100, w * 0.14)))
        _draw_spotlight_fixture(dr, lx, cy - spread // 2, rx=lamp_ry, ry=lamp_rx)
        _draw_spotlight_fixture(dr, lx, cy + spread // 2, rx=lamp_ry, ry=lamp_rx)
    if key in {"right", "lr", "quad"}:
        lx = min(cw - 3, x1 + 14 + int(min(100, w * 0.14)))
        _draw_spotlight_fixture(dr, lx, cy - spread // 2, rx=lamp_ry, ry=lamp_rx)
        _draw_spotlight_fixture(dr, lx, cy + spread // 2, rx=lamp_ry, ry=lamp_rx)

    return Image.alpha_composite(base, ov)


def _layer_to_png_bytes(layer: Image.Image, scene: SceneInfo, p: CompositeParams, cw: int, ch: int) -> bytes:
    lit_key = _normalize_lighting_key(p.lighting)
    out_rgb = Image.alpha_composite(Image.new("RGBA", (cw, ch), (255, 255, 255, 255)), layer).convert("RGB")
    out_rgb = _apply_lighting(out_rgb, lit_key, scene.scene_id)
    buf = io.BytesIO()
    out_rgb.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def _draw_quad_frame_outline(
    layer: Image.Image,
    pts: Sequence[tuple[float, float]],
    *,
    frame_style: str,
    is_pedestal: bool,
) -> None:
    if frame_style in {"none", "minimal_plinth"} or is_pedestal:
        return
    dr = ImageDraw.Draw(layer, "RGBA")
    loop = list(pts) + [pts[0]]
    m = min(layer.size)
    if frame_style in {"thin_black", "floater_modern"}:
        w0 = max(3, int(m * 0.005))
        dr.line(loop, fill=(60, 62, 68, 220), width=w0 + 4)
        dr.line(loop, fill=(12, 12, 14, 255), width=w0)
    elif frame_style == "gallery_white":
        w0 = max(8, int(m * 0.012))
        dr.line(loop, fill=(180, 178, 175, 255), width=w0 + 6)
        dr.line(loop, fill=(252, 252, 250, 255), width=w0)
        dr.line(loop, fill=(95, 95, 92, 255), width=2)
    elif frame_style == "gold_ornate":
        w0 = max(9, int(m * 0.014))
        dr.line(loop, fill=(60, 45, 22, 255), width=w0 + 8)
        dr.line(loop, fill=(240, 200, 110, 255), width=w0)
        dr.line(loop, fill=(255, 235, 180, 255), width=max(3, w0 // 4))
        dr.line(loop, fill=(120, 85, 40, 255), width=2)
    else:
        w0 = max(7, int(m * 0.01))
        dr.line(loop, fill=(28, 26, 24, 240), width=w0 + 5)
        dr.line(loop, fill=(245, 242, 236, 255), width=w0)
        dr.line(loop, fill=(80, 78, 74, 255), width=2)


def _frame_style_norm(fs: str | None) -> str:
    s = (fs or "").strip().lower().replace(" ", "_")
    if not s:
        return "traditional_matted"
    return s


def _draw_frame_molding_ring(
    dr: ImageDraw.ImageDraw,
    x0: int,
    y0: int,
    x1: int,
    y1: int,
    t: int,
    fill: tuple[int, int, int, int],
) -> None:
    """Filled frame band outside the art window (x0,y0)-(x1,y1); does not cover the artwork."""
    o = t * 2
    ax0, ay0, ax1, ay1 = x0 - o, y0 - o, x1 + o, y1 + o
    if ax1 <= ax0 or ay1 <= ay0:
        return
    # Top, bottom, left, right strips (interior [x0,x1]×[y0,y1] stays clear for the image).
    dr.rectangle((ax0, ay0, ax1, y0), fill=fill)
    dr.rectangle((ax0, y1, ax1, ay1), fill=fill)
    dr.rectangle((ax0, y0, x0, y1), fill=fill)
    dr.rectangle((x1, y0, ax1, y1), fill=fill)


def _draw_frame(
    layer: Image.Image,
    *,
    box: tuple[int, int, int, int],
    frame_style: str,
    is_pedestal: bool,
) -> None:
    x0, y0, x1, y1 = box
    dr = ImageDraw.Draw(layer, "RGBA")
    if frame_style in {"none", "minimal_plinth"} or is_pedestal:
        return
    w = max(x1 - x0, 1)
    h = max(y1 - y0, 1)
    if frame_style in {"thin_black", "floater_modern"}:
        t = max(int(min(w, h) * 0.014), 3)
        dr.rectangle((x0 - t - 3, y0 - t - 3, x1 + t + 3, y1 + t + 3), outline=(70, 72, 78, 180), width=2)
        dr.rectangle((x0 - t, y0 - t, x1 + t, y1 + t), outline=(10, 10, 12, 255), width=max(2, t // 2))
    elif frame_style == "gallery_white":
        t = max(int(min(w, h) * 0.026), 8)
        _draw_frame_molding_ring(dr, x0, y0, x1, y1, t, (250, 250, 248, 255))
        dr.rectangle((x0 - t, y0 - t, x1 + t, y1 + t), outline=(140, 138, 134, 255), width=3)
        dr.rectangle((x0 - 2, y0 - 2, x1 + 2, y1 + 2), outline=(220, 218, 212, 200), width=1)
    elif frame_style == "gold_ornate":
        t = max(int(min(w, h) * 0.032), 10)
        _draw_frame_molding_ring(dr, x0, y0, x1, y1, t, (228, 190, 105, 255))
        _draw_frame_molding_ring(dr, x0 + 2, y0 + 2, x1 - 2, y1 - 2, max(4, t // 3), (255, 236, 190, 230))
        dr.rectangle((x0 - t, y0 - t, x1 + t, y1 + t), outline=(85, 62, 30, 255), width=3)
    else:
        t = max(int(min(w, h) * 0.024), 7)
        _draw_frame_molding_ring(dr, x0, y0, x1, y1, t, (248, 246, 240, 255))
        dr.rectangle((x0 - t, y0 - t, x1 + t, y1 + t), outline=(55, 52, 48, 255), width=3)
        dr.rectangle((x0 - 1, y0 - 1, x1 + 1, y1 + 1), outline=(210, 205, 196, 160), width=1)


_FRAME_FINISH_WOOD: Final[
    dict[str, tuple[tuple[int, int, int], tuple[int, int, int], tuple[int, int, int]]]
] = {
    "rosewood": ((72, 48, 38), (115, 75, 58), (155, 105, 82)),
    "oakwood": ((120, 86, 55), (166, 124, 82), (205, 160, 115)),
    "walnut": ((72, 52, 36), (105, 75, 50), (138, 100, 72)),
    "maple": ((198, 160, 118), (228, 195, 155), (248, 228, 200)),
    "cherry": ((118, 62, 48), (155, 88, 68), (190, 120, 95)),
    "mahogany": ((85, 42, 30), (118, 58, 42), (150, 78, 58)),
    "teak": ((150, 105, 68), (188, 138, 95), (218, 172, 125)),
    "pine": ((195, 168, 125), (225, 200, 160), (240, 220, 185)),
    "cedar": ((165, 125, 85), (195, 155, 115), (218, 185, 145)),
}

_FRAME_FINISH_MODERN: Final[frozenset[str]] = frozenset(
    {"thin_black_metal", "white_frame", "sleek_silver", "acrylic_floating", "shadow_box"}
)

_FRAME_FINISH_ALL: Final[frozenset[str]] = frozenset(_FRAME_FINISH_WOOD.keys()) | _FRAME_FINISH_MODERN

_FINISH_ALIASES: Final[dict[str, str]] = {
    "oak": "oakwood",
    "oak_wood": "oakwood",
    "rose_wood": "rosewood",
    "maple_wood": "maple",
    "thin_black": "thin_black_metal",
    "metal": "thin_black_metal",
    "silver": "sleek_silver",
    "aluminum": "sleek_silver",
    "aluminium": "sleek_silver",
    "acrylic": "acrylic_floating",
    "floating": "acrylic_floating",
    "shadowbox": "shadow_box",
}


def _normalize_frame_finish(raw: str | None) -> str | None:
    if not raw or not str(raw).strip():
        return None
    s = str(raw).strip().lower().replace(" ", "_").replace("-", "_")
    s = _FINISH_ALIASES.get(s, s)
    return s if s in _FRAME_FINISH_ALL else None


def _normalize_frame_profile(raw: str | None) -> str:
    if not raw or not str(raw).strip():
        return "thin"
    s = str(raw).strip().lower()
    return "thick" if s in {"thick", "heavy", "wide"} else "thin"


def _frame_profile_mult(profile: str) -> float:
    return 1.52 if profile == "thick" else 0.78


def _custom_frame_active(p: CompositeParams, is_pedestal: bool) -> bool:
    return (not is_pedestal) and (_normalize_frame_finish(p.frame_finish) is not None)


def _draw_custom_frame_rect(
    layer: Image.Image,
    box: tuple[int, int, int, int],
    *,
    finish_key: str,
    profile: str,
) -> None:
    x0, y0, x1, y1 = box
    w = max(x1 - x0, 1)
    h = max(y1 - y0, 1)
    mult = _frame_profile_mult(profile)
    dr = ImageDraw.Draw(layer, "RGBA")
    base_t = max(int(min(w, h) * 0.022 * mult), 4)

    if finish_key in _FRAME_FINISH_WOOD:
        dark, mid, hi = _FRAME_FINISH_WOOD[finish_key]
        bt = max(base_t, 6)
        _draw_frame_molding_ring(dr, x0, y0, x1, y1, bt, (*mid, 255))
        dr.rectangle(
            (x0 - bt, y0 - bt, x1 + bt, y1 + bt),
            outline=(*dark, 255),
            width=max(2, bt // 4),
        )
        dr.rectangle((x0 - 1, y0 - 1, x1 + 1, y1 + 1), outline=(*hi, 220), width=1)
    elif finish_key == "thin_black_metal":
        t = max(int(min(w, h) * 0.012 * mult), 3)
        dr.rectangle((x0 - t - 2, y0 - t - 2, x1 + t + 2, y1 + t + 2), outline=(55, 58, 62, 255), width=2)
        dr.rectangle((x0 - t, y0 - t, x1 + t, y1 + t), outline=(22, 24, 28, 255), width=max(2, t // 2))
        dr.rectangle((x0 - t, y0 - t, x1 + t, y1 + t), outline=(160, 165, 175, 180), width=1)
    elif finish_key == "white_frame":
        t = max(int(min(w, h) * 0.024 * mult), 7)
        _draw_frame_molding_ring(dr, x0, y0, x1, y1, t, (252, 252, 250, 255))
        dr.rectangle((x0 - t, y0 - t, x1 + t, y1 + t), outline=(130, 128, 124, 255), width=3)
    elif finish_key == "sleek_silver":
        t = max(int(min(w, h) * 0.016 * mult), 4)
        dr.rectangle((x0 - t, y0 - t, x1 + t, y1 + t), outline=(110, 112, 118, 255), width=t // 2 + 2)
        dr.rectangle(
            (x0 - t + 1, y0 - t + 1, x1 + t - 1, y1 + t - 1),
            outline=(210, 212, 218, 255),
            width=2,
        )
        dr.rectangle((x0 - 1, y0 - 1, x1 + 1, y1 + 1), outline=(165, 168, 175, 255), width=1)
    elif finish_key == "acrylic_floating":
        gap = max(3, int(min(w, h) * 0.008 * mult))
        t = max(int(min(w, h) * 0.006 * mult), 2)
        ox0, oy0, ox1, oy1 = x0 - gap - t, y0 - gap - t, x1 + gap + t, y1 + gap + t
        dr.rectangle((ox0, oy0, ox1, oy1), outline=(230, 232, 238, 200), width=2)
        dr.rectangle((x0 - gap, y0 - gap, x1 + gap, y1 + gap), outline=(180, 182, 190, 120), width=1)
    elif finish_key == "shadow_box":
        ot = max(int(min(w, h) * 0.038 * mult), 10)
        it = max(4, ot // 4)
        _draw_frame_molding_ring(dr, x0, y0, x1, y1, ot, (34, 34, 38, 255))
        dr.rectangle((x0 - ot, y0 - ot, x1 + ot, y1 + ot), outline=(60, 60, 66, 255), width=3)
        _draw_frame_molding_ring(dr, x0 + 2, y0 + 2, x1 - 2, y1 - 2, it, (220, 218, 212, 255))


def _draw_quad_custom_frame(
    layer: Image.Image,
    pts: Sequence[tuple[float, float]],
    *,
    finish_key: str,
    profile: str,
) -> None:
    dr = ImageDraw.Draw(layer, "RGBA")
    loop = list(pts) + [pts[0]]
    m = min(layer.size)
    mult = _frame_profile_mult(profile)
    base_w = max(4, int(m * 0.009 * mult))
    if finish_key in _FRAME_FINISH_WOOD:
        dark, mid, hi = _FRAME_FINISH_WOOD[finish_key]
        dr.line(loop, fill=(*dark, 255), width=base_w + 6)
        dr.line(loop, fill=(*mid, 255), width=base_w + 2)
        dr.line(loop, fill=(*hi, 240), width=max(2, base_w // 2))
    elif finish_key == "thin_black_metal":
        dr.line(loop, fill=(50, 52, 56, 255), width=base_w + 5)
        dr.line(loop, fill=(18, 20, 24, 255), width=base_w)
        dr.line(loop, fill=(150, 155, 165, 160), width=1)
    elif finish_key == "white_frame":
        dr.line(loop, fill=(175, 173, 170, 255), width=base_w + 6)
        dr.line(loop, fill=(252, 252, 250, 255), width=base_w + 1)
    elif finish_key == "sleek_silver":
        dr.line(loop, fill=(95, 97, 102, 255), width=base_w + 5)
        dr.line(loop, fill=(205, 207, 212, 255), width=base_w)
    elif finish_key == "acrylic_floating":
        dr.line(loop, fill=(200, 202, 210, 150), width=max(2, base_w // 2))
    elif finish_key == "shadow_box":
        dr.line(loop, fill=(28, 28, 32, 255), width=base_w + 10)
        dr.line(loop, fill=(55, 55, 60, 255), width=base_w + 4)
        dr.line(loop, fill=(225, 223, 218, 230), width=max(2, base_w // 2))


def _normalize_lighting_key(lighting: str | None) -> str:
    raw = (lighting or "").strip().lower().replace(" ", "_").replace("-", "_")
    if not raw:
        return "gallery_track_wash"
    aliases = {
        "morning_sun": "morning_sunlight_beam",
        "sunbeam": "morning_sunlight_beam",
        "sun_beam": "morning_sunlight_beam",
        "tres_shade": "tree_shade",
        "trees_shade": "tree_shade",
        "dappled_shade": "tree_shade",
        "dappled": "tree_shade",
    }
    return aliases.get(raw, raw)


def _alpha_composite_rgb(base_rgb: Image.Image, overlay_rgba: Image.Image) -> Image.Image:
    base = base_rgb.convert("RGBA")
    return Image.alpha_composite(base, overlay_rgba).convert("RGB")


def _lighting_morning_sunlight_beam(img: Image.Image) -> Image.Image:
    w, h = img.size
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    dr = ImageDraw.Draw(layer)
    quad = (
        (-int(w * 0.25), -int(h * 0.18)),
        (int(w * 0.62), -int(h * 0.02)),
        (int(w * 0.38), int(h * 1.15)),
        (-int(w * 0.1), int(h * 1.02)),
    )
    dr.polygon(list(quad), fill=(255, 238, 205, 92))
    blur = max(16.0, (w + h) / 72.0)
    layer = layer.filter(ImageFilter.GaussianBlur(radius=blur))
    out = _alpha_composite_rgb(img, layer)
    return ImageEnhance.Brightness(out).enhance(1.05)


def _lighting_oblique_shadow(img: Image.Image) -> Image.Image:
    w, h = img.size
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    dr = ImageDraw.Draw(layer)
    quad = (
        (int(w * 0.32), -int(h * 0.22)),
        (int(w * 1.28), int(h * 0.12)),
        (int(w * 1.12), int(h * 1.22)),
        (int(w * 0.18), int(h * 0.92)),
    )
    dr.polygon(list(quad), fill=(18, 22, 32, 125))
    blur = max(20.0, (w + h) / 58.0)
    layer = layer.filter(ImageFilter.GaussianBlur(radius=blur))
    out = _alpha_composite_rgb(img, layer)
    return ImageEnhance.Contrast(out).enhance(1.04)


def _lighting_sunset(img: Image.Image) -> Image.Image:
    out = ImageEnhance.Color(img).enhance(1.24)
    out = ImageEnhance.Brightness(out).enhance(0.93)
    w, h = out.size
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    dr = ImageDraw.Draw(layer)
    dr.rectangle((0, int(h * 0.52), w, h), fill=(255, 118, 62, 62))
    dr.polygon(
        [
            (-int(w * 0.05), int(h * 0.35)),
            (int(w * 1.05), int(h * 0.42)),
            (w, int(h * 0.55)),
            (0, int(h * 0.48)),
        ],
        fill=(255, 185, 120, 48),
    )
    blur = max(14.0, h / 28.0)
    layer = layer.filter(ImageFilter.GaussianBlur(radius=blur))
    return _alpha_composite_rgb(out, layer)


def _lighting_tree_shade(img: Image.Image) -> Image.Image:
    w, h = img.size
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    dr = ImageDraw.Draw(layer)
    for i in range(16):
        hx = hashlib.sha256(f"tree:{i}:{w}:{h}".encode()).hexdigest()
        cx = 24 + int(hx[0:4], 16) % max(1, w - 48)
        cy = 24 + int(hx[4:8], 16) % max(1, h - 48)
        rx = 22 + int(hx[8:10], 16) % max(28, w // 10)
        ry = 16 + int(hx[10:12], 16) % max(22, h // 10)
        alpha = 20 + int(hx[12:14], 16) % 32
        dr.ellipse((cx - rx, cy - ry, cx + rx, cy + ry), fill=(0, 8, 28, alpha))
    fleck = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    fd = ImageDraw.Draw(fleck)
    for i in range(10):
        hx = hashlib.sha256(f"treef:{i}:{w}:{h}".encode()).hexdigest()
        cx = int(hx[0:4], 16) % max(1, w - 16) + 8
        cy = int(hx[4:8], 16) % max(1, h - 16) + 8
        r = 4 + int(hx[8:10], 16) % 10
        fd.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(255, 252, 230, 38))
    blur_dark = max(12.0, (w + h) / 95.0)
    blur_fleck = max(3.0, (w + h) / 220.0)
    layer = layer.filter(ImageFilter.GaussianBlur(radius=blur_dark))
    fleck = fleck.filter(ImageFilter.GaussianBlur(radius=blur_fleck))
    base = _alpha_composite_rgb(img, layer)
    return _alpha_composite_rgb(base, fleck)


def _lighting_hazy(img: Image.Image) -> Image.Image:
    out = ImageEnhance.Brightness(img).enhance(1.06)
    out = ImageEnhance.Contrast(out).enhance(0.86)
    out = ImageEnhance.Color(out).enhance(0.87)
    return out.filter(ImageFilter.GaussianBlur(radius=0.6))


def _lighting_warm(img: Image.Image) -> Image.Image:
    out = ImageEnhance.Brightness(img).enhance(1.08)
    out = ImageEnhance.Color(out).enhance(1.28)
    out = ImageEnhance.Contrast(out).enhance(0.96)
    w, h = out.size
    wash = Image.new("RGBA", (w, h), (255, 243, 215, 32))
    return _alpha_composite_rgb(out, wash)


def _lighting_cool(img: Image.Image) -> Image.Image:
    out = ImageEnhance.Color(img).enhance(0.80)
    out = ImageEnhance.Brightness(out).enhance(1.04)
    out = ImageEnhance.Contrast(out).enhance(1.05)
    w, h = out.size
    wash = Image.new("RGBA", (w, h), (218, 232, 255, 38))
    return _alpha_composite_rgb(out, wash)


def _lighting_bamboo_shadow(img: Image.Image) -> Image.Image:
    w, h = img.size
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    dr = ImageDraw.Draw(layer)
    step = max(16, min(w, h) // 22)
    for j in range(-w - h, w + h, step):
        dr.line([(j, 0), (j + int(h * 0.95), h)], fill=(6, 10, 8, 72), width=max(8, step // 2))
    blur = max(10.0, (w + h) / 70.0)
    layer = layer.filter(ImageFilter.GaussianBlur(radius=blur))
    return _alpha_composite_rgb(img, layer)


def _lighting_flower_shadow(img: Image.Image) -> Image.Image:
    w, h = img.size
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    dr = ImageDraw.Draw(layer)
    for i in range(8):
        hx = hashlib.sha256(f"flower:{i}:{w}:{h}".encode()).hexdigest()
        cx = 20 + int(hx[0:4], 16) % max(1, w - 40)
        cy = 20 + int(hx[4:8], 16) % max(1, h - 40)
        rx = 36 + int(hx[8:10], 16) % max(40, w // 4)
        ry = 28 + int(hx[10:12], 16) % max(32, h // 4)
        alpha = 35 + int(hx[12:14], 16) % 45
        dr.ellipse((cx - rx, cy - ry, cx + rx, cy + ry), fill=(12, 10, 22, alpha))
    blur = max(18.0, (w + h) / 55.0)
    layer = layer.filter(ImageFilter.GaussianBlur(radius=blur))
    return _alpha_composite_rgb(img, layer)


def _apply_lighting(rgb: Image.Image, lighting: str | None, scene_id: str) -> Image.Image:
    key = _normalize_lighting_key(lighting)
    img = rgb
    if key in {"pedestal_spot", "gallery_track_wash"}:
        img = ImageEnhance.Brightness(img).enhance(1.12 if key == "pedestal_spot" else 1.05)
        img = ImageEnhance.Contrast(img).enhance(1.08 if key == "pedestal_spot" else 1.05)
    elif key == "warm_ambient":
        img = ImageEnhance.Brightness(img).enhance(1.09)
        img = ImageEnhance.Color(img).enhance(1.22)
        img = ImageEnhance.Contrast(img).enhance(0.97)
    elif key == "daylight_north":
        img = ImageEnhance.Color(img).enhance(0.90)
        img = ImageEnhance.Brightness(img).enhance(1.06)
        img = ImageEnhance.Contrast(img).enhance(1.06)
    elif key == "morning_sunlight_beam":
        img = _lighting_morning_sunlight_beam(img)
    elif key == "oblique_shadow":
        img = _lighting_oblique_shadow(img)
    elif key == "sunset":
        img = _lighting_sunset(img)
    elif key == "tree_shade":
        img = _lighting_tree_shade(img)
    elif key == "hazy":
        img = _lighting_hazy(img)
    elif key == "warm":
        img = _lighting_warm(img)
    elif key == "cool":
        img = _lighting_cool(img)
    elif key == "bamboo_shadow":
        img = _lighting_bamboo_shadow(img)
    elif key == "flower_shadow":
        img = _lighting_flower_shadow(img)
    if scene_id == "pedestal_sculpture_spot" or key == "pedestal_spot":
        img = ImageEnhance.Brightness(img).enhance(1.05)
    return img


def load_artwork_rgba(
    artwork_url: str,
    *,
    timeout_s: float,
    max_fetch_bytes: int,
    max_art_input_dim: int,
    params: CompositeParams,
) -> Image.Image:
    art_body, _ct = fetch_remote_image_bytes(artwork_url, timeout_s=timeout_s, max_bytes=max_fetch_bytes)
    art = Image.open(io.BytesIO(art_body))
    art = _prepare_loaded_art_rgba(art)
    if art.width > max_art_input_dim or art.height > max_art_input_dim:
        art = _contain_size(art, max_art_input_dim, max_art_input_dim, allow_upscale=False)
    if params.cutout:
        art = _maybe_rembg(art)
    return art


def load_artwork_rgba_first_available(
    urls: Sequence[str],
    *,
    timeout_s: float,
    max_fetch_bytes: int,
    max_art_input_dim: int,
    params: CompositeParams,
) -> Image.Image:
    """Try each URL in order (folder prefix vs bucket root, etc.) until a fetch and decode succeeds."""
    ordered: list[str] = []
    seen: set[str] = set()
    for u in urls:
        t = (u or "").strip()
        if t and t not in seen:
            seen.add(t)
            ordered.append(t)
    if not ordered:
        raise OSError("no artwork URLs to fetch")
    last_err: Exception | None = None
    for u in ordered:
        try:
            return load_artwork_rgba(
                u,
                timeout_s=timeout_s,
                max_fetch_bytes=max_fetch_bytes,
                max_art_input_dim=max_art_input_dim,
                params=params,
            )
        except Exception as e:
            last_err = e
            logger.info("showcase compositor: artwork fetch failed %s: %s", u[:96], e)
    assert last_err is not None
    raise last_err


def run_pixel_composite_from_art(
    art: Image.Image,
    scene: SceneInfo,
    *,
    timeout_s: float,
    max_fetch_bytes: int,
    canvas_size: tuple[int, int] | None = None,
    art_frac: float = 0.55,
    max_art_input_dim: int = 2800,
    params: CompositeParams | None = None,
) -> bytes:
    p = params or CompositeParams()
    art_work = art.copy()
    cw = int(os.getenv("SHOWCASE_COMPOSITOR_CANVAS_W", "1200"))
    ch = int(os.getenv("SHOWCASE_COMPOSITOR_CANVAS_H", "900"))
    if canvas_size:
        cw, ch = canvas_size
    cw, ch = max(cw, 320), max(ch, 240)

    is_pedestal = scene.scene_id == "pedestal_sculpture_spot" or (scene.placement_hint or "") == "pedestal_center"
    eff_layout = scene.layout_index if p.layout_variant is None else max(0, min(7, p.layout_variant))
    # Vertical anchor: where artwork centre sits inside the focal rect (0=top, 1=bottom)
    eye_frac = scene.eye_level_fraction if not is_pedestal else 0.30

    bg = _load_background_rgba(scene, (cw, ch), timeout_s=timeout_s, max_fetch_bytes=max_fetch_bytes)

    quad = _resolved_placement_quad(scene, p)
    if quad and not is_pedestal:
        pts = quad_norm_to_pixels(quad, cw, ch)
        pts = _nudge_quad_pts_layout(pts, cw=cw, ch=ch, layout_variant=eff_layout)
        bw, bh = quad_bbox_wh(pts)
        max_aw, max_ah = _max_art_box(cw, ch, art_frac=art_frac, params=p, scene=scene, region_w=bw, region_h=bh)
        art_sized = _contain_size(art_work, max_aw, max_ah, allow_upscale=True)
        art_rgb = _art_rgb_for_paste(art_sized)
        aw, ah = art_rgb.width, art_rgb.height
        mat = max(int(min(cw, ch) * 0.012), 8)
        mw, mh = aw + 2 * mat, ah + 2 * mat
        layer_rect = Image.new("RGBA", (mw, mh), (0, 0, 0, 0))
        md = ImageDraw.Draw(layer_rect)
        fill_mat = (252, 251, 248, 255)
        outline_mat = (0, 0, 0, 35)
        md.rectangle((0, 0, mw, mh), fill=fill_mat, outline=outline_mat, width=1)
        r, g, b = art_rgb.split()
        opaque = Image.new("L", art_rgb.size, 255)
        art_rgba = Image.merge("RGBA", (r, g, b, opaque))
        layer_rect.paste(art_rgba, (mat, mat))
        src_quad = [(0.0, 0.0), (float(mw), 0.0), (float(mw), float(mh)), (0.0, float(mh))]
        try:
            coeffs = pil_perspective_coeffs(pts, src_quad)
            warped = layer_rect.transform(
                (cw, ch), Image.PERSPECTIVE, coeffs, Image.Resampling.BICUBIC, fillcolor=(0, 0, 0, 0)
            )
            layer = Image.alpha_composite(bg, warped)
            use_cf = _custom_frame_active(p, False)
            fs = _frame_style_norm(p.frame_style)
            if use_cf:
                fk = _normalize_frame_finish(p.frame_finish)
                prof = _normalize_frame_profile(p.frame_profile)
                if fk:
                    frame_layer = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
                    _draw_quad_custom_frame(frame_layer, pts, finish_key=fk, profile=prof)
                    layer = Image.alpha_composite(layer, frame_layer)
            elif fs not in {"none", "minimal_plinth"}:
                frame_layer = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
                _draw_quad_frame_outline(frame_layer, pts, frame_style=fs, is_pedestal=False)
                layer = Image.alpha_composite(layer, frame_layer)
            pad = max(6, int(min(cw, ch) * 0.01))
            bx0 = max(0, int(min(p[0] for p in pts) - pad))
            by0 = max(0, int(min(p[1] for p in pts) - pad))
            bx1 = min(cw, int(max(p[0] for p in pts) + pad))
            by1 = min(ch, int(max(p[1] for p in pts) + pad))
            layer = _apply_art_spotlight(layer, bbox=(bx0, by0, bx1, by1), spotlight=p.art_spotlight, cw=cw, ch=ch)
            return _layer_to_png_bytes(layer, scene, p, cw, ch)
        except (ValueError, OSError, ZeroDivisionError) as e:
            logger.warning("showcase compositor: perspective failed, using focal/axis layout: %s", e)

    focal = _resolved_focal_rect(scene, p)
    if focal:
        rx0, ry0, rx1, ry1 = focal_rect_to_pixels(focal, cw, ch)
    else:
        rx0, ry0, rx1, ry1 = 0, 0, cw, ch

    rect_w = max(1, rx1 - rx0)
    rect_h = max(1, ry1 - ry0)
    max_aw, max_ah = _max_art_box(cw, ch, art_frac=art_frac, params=p, scene=scene, region_w=rect_w, region_h=rect_h)
    art_sized = _contain_size(art_work, max_aw, max_ah, allow_upscale=True)
    art_rgb = _art_rgb_for_paste(art_sized)

    aw, ah = art_rgb.width, art_rgb.height
    # Centre artwork horizontally inside the focal rect
    px = rx0 + (rect_w - aw) // 2
    if is_pedestal:
        # Artwork rests ON the plinth: anchor bottom of art to ry1 (plinth top surface).
        # focal_wall_rect bottom = plinth surface; art appears floating above it.
        py = ry1 - ah
        # Allow slight upward nudge only (keep bottom at plinth)
        oy_nudge = _layout_offsets(cw=cw, ch=ch, layout_variant=eff_layout)[1]
        py += int(oy_nudge * (rect_h / max(ch, 1)))
        py = max(ry0, py)  # don't go above focal rect top
    else:
        # Anchor artwork vertically using eye_level_fraction:
        #   eye_frac=0.48 → artwork centre sits at 48 % down the focal rect
        art_centre_y = int(ry0 + rect_h * eye_frac)
        py = art_centre_y - ah // 2
        # Apply layout nudge (scaled to focal rect, not full canvas)
        ox, oy = _layout_offsets(cw=cw, ch=ch, layout_variant=eff_layout)
        px += int(ox * (rect_w / max(cw, 1)))
        py += int(oy * (rect_h / max(ch, 1)))
    # Clamp so artwork stays inside focal rect
    px = max(rx0, min(px, rx1 - aw))
    py = max(ry0, min(py, ry1 - ah))

    mat = max(int(min(cw, ch) * 0.012), 8)
    mx0, my0 = px - mat, py - mat
    mx1, my1 = px + aw + mat, py + ah + mat

    mat_layer = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    md = ImageDraw.Draw(mat_layer)
    # Pedestal: thin neutral mat so artwork rests cleanly on the plinth without a dark overlay.
    fill_mat = (252, 251, 248, 255)
    outline_mat = (0, 0, 0, 35)
    md.rectangle((mx0, my0, mx1, my1), fill=fill_mat, outline=outline_mat, width=1)

    layer = Image.alpha_composite(bg, mat_layer)

    shadow = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    if is_pedestal:
        # Drop shadow directly below the artwork onto the plinth top surface
        sx0 = max(px + 6, 0)
        sy0 = max(py + ah - 4, 0)
        sx1 = min(px + aw - 6, cw - 1)
        sy1 = min(py + ah + 10, ch - 1)
        shadow_alpha = 120
    else:
        sx0, sy0 = max(px + 2, 0), max(py + 4, 0)
        sx1 = min(px + aw - 2, cw - 1)
        sy1 = min(py + ah + 4, ch - 1)
        shadow_alpha = 95
    if sx1 > sx0 and sy1 > sy0:
        sd.rectangle((sx0, sy0, sx1, sy1), fill=(0, 0, 0, shadow_alpha))
    shadow = shadow.filter(ImageFilter.GaussianBlur(radius=6))
    layer = Image.alpha_composite(layer, shadow)

    r, g, b = art_rgb.split()
    opaque = Image.new("L", art_rgb.size, 255)
    art_rgba = Image.merge("RGBA", (r, g, b, opaque))
    art_slot = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    art_slot.paste(art_rgba, (px, py))
    layer = Image.alpha_composite(layer, art_slot)

    fs = _frame_style_norm(p.frame_style)
    use_cf = _custom_frame_active(p, is_pedestal)
    if use_cf:
        fk = _normalize_frame_finish(p.frame_finish)
        prof = _normalize_frame_profile(p.frame_profile)
        if fk:
            frame_layer = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
            _draw_custom_frame_rect(frame_layer, (px, py, px + aw, py + ah), finish_key=fk, profile=prof)
            layer = Image.alpha_composite(layer, frame_layer)
    elif fs not in {"none", "minimal_plinth"}:
        frame_layer = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
        _draw_frame(frame_layer, box=(px, py, px + aw, py + ah), frame_style=fs, is_pedestal=is_pedestal)
        layer = Image.alpha_composite(layer, frame_layer)

    t_spot = 0
    if not is_pedestal and (use_cf or fs not in {"none", "minimal_plinth"}):
        t_spot = max(int(min(aw, ah) * 0.034), 10)
    bx0 = max(0, mx0 - t_spot)
    by0 = max(0, my0 - t_spot)
    bx1 = min(cw, mx1 + t_spot)
    by1 = min(ch, my1 + t_spot)
    layer = _apply_art_spotlight(layer, bbox=(bx0, by0, bx1, by1), spotlight=p.art_spotlight, cw=cw, ch=ch)

    return _layer_to_png_bytes(layer, scene, p, cw, ch)


def run_pixel_composite(
    *,
    artwork_urls: Sequence[str],
    scene: SceneInfo,
    timeout_s: float,
    max_fetch_bytes: int,
    canvas_size: tuple[int, int] | None = None,
    art_frac: float = 0.55,
    max_art_input_dim: int = 2800,
    params: CompositeParams | None = None,
) -> bytes:
    p = params or CompositeParams()
    art = load_artwork_rgba_first_available(
        artwork_urls,
        timeout_s=timeout_s,
        max_fetch_bytes=max_fetch_bytes,
        max_art_input_dim=max_art_input_dim,
        params=p,
    )
    return run_pixel_composite_from_art(
        art,
        scene,
        timeout_s=timeout_s,
        max_fetch_bytes=max_fetch_bytes,
        canvas_size=canvas_size,
        art_frac=art_frac,
        max_art_input_dim=max_art_input_dim,
        params=p,
    )
