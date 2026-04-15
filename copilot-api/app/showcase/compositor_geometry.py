"""Perspective and focal-wall helpers for showcase compositor (no NumPy)."""

from __future__ import annotations

from typing import Final, Sequence


def clamp01(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


def focal_rect_to_pixels(
    rect_norm: tuple[float, float, float, float],
    cw: int,
    ch: int,
) -> tuple[int, int, int, int]:
    """Normalized [left, top, right, bottom] on canvas -> pixel ints."""
    nl, nt, nr, nb = rect_norm
    l = int(round(clamp01(nl) * cw))
    t = int(round(clamp01(nt) * ch))
    r = int(round(clamp01(nr) * cw))
    b = int(round(clamp01(nb) * ch))
    if r <= l + 4:
        r = min(cw, l + 8)
    if b <= t + 4:
        b = min(ch, t + 8)
    return l, t, r, b


def quad_norm_to_pixels(
    quad: Sequence[tuple[float, float]],
    cw: int,
    ch: int,
) -> list[tuple[float, float]]:
    return [(clamp01(p[0]) * cw, clamp01(p[1]) * ch) for p in quad]


def quad_bbox_wh(pts: Sequence[tuple[float, float]]) -> tuple[int, int]:
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return max(1, int(max(xs) - min(xs))), max(1, int(max(ys) - min(ys)))


def _cross(ax: float, ay: float, bx: float, by: float) -> float:
    return ax * by - ay * bx


def quad_signed_area(pts: Sequence[tuple[float, float]]) -> float:
    if len(pts) != 4:
        return 0.0
    s = 0.0
    for i in range(4):
        x0, y0 = pts[i]
        x1, y1 = pts[(i + 1) % 4]
        s += x0 * y1 - x1 * y0
    return s * 0.5


def is_simple_quad(pts: Sequence[tuple[float, float]]) -> bool:
    """Non-degenerate quadrilateral (shoelace area), order TL→TR→BR→BL on canvas."""
    if len(pts) != 4:
        return False
    return abs(quad_signed_area(pts)) > 1e-6


def _gaussian_solve_8(aug: list[list[float]]) -> list[float]:
    """Solve 8x8 linear system; aug[i] is row i, length 9 (A|b)."""
    n = 8
    a = [row[:] for row in aug]
    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(a[r][col]))
        a[col], a[pivot] = a[pivot], a[col]
        if abs(a[col][col]) < 1e-12:
            raise ValueError("singular_homography")
        inv = 1.0 / a[col][col]
        for j in range(col, n + 1):
            a[col][j] *= inv
        for row in range(n):
            if row == col:
                continue
            f = a[row][col]
            if abs(f) < 1e-15:
                continue
            for j in range(col, n + 1):
                a[row][j] -= f * a[col][j]
    return [a[i][n] for i in range(n)]


def pil_perspective_coeffs(
    dst_quad: Sequence[tuple[float, float]],
    src_quad: Sequence[tuple[float, float]],
) -> tuple[float, float, float, float, float, float, float, float]:
    """
    Coefficients for PIL Image.transform(..., Image.PERSPECTIVE, data).
    Maps each output pixel (x,y) to input sample (X,Y) with:
      X = (a*x + b*y + c) / (g*x + h*y + 1)
      Y = (d*x + e*y + f) / (g*x + h*y + 1)
    """
    if len(dst_quad) != 4 or len(src_quad) != 4:
        raise ValueError("need_4_points")
    aug: list[list[float]] = []
    for (dx, dy), (sx, sy) in zip(dst_quad, src_quad, strict=True):
        aug.append([dx, dy, 1.0, 0.0, 0.0, 0.0, -dx * sx, -dy * sx, sx])
        aug.append([0.0, 0.0, 0.0, dx, dy, 1.0, -dx * sy, -dy * sy, sy])
    sol = _gaussian_solve_8(aug)
    return (sol[0], sol[1], sol[2], sol[3], sol[4], sol[5], sol[6], sol[7])


_EPS: Final[float] = 1e-6


def valid_focal_rect(rect: tuple[float, float, float, float] | None) -> bool:
    if rect is None:
        return False
    l, t, r, b = rect
    return r - l > _EPS and b - t > _EPS and l >= -_EPS and t >= -_EPS and r <= 1.0 + _EPS and b <= 1.0 + _EPS


def valid_placement_quad(quad: Sequence[tuple[float, float]] | None) -> bool:
    if quad is None or len(quad) != 4:
        return False
    pts = [(clamp01(p[0]), clamp01(p[1])) for p in quad]
    return is_simple_quad(pts)


def parse_quad_from_json(raw: object) -> list[tuple[float, float]] | None:
    if not isinstance(raw, list) or len(raw) != 4:
        return None
    out: list[tuple[float, float]] = []
    for item in raw:
        if not isinstance(item, (list, tuple)) or len(item) != 2:
            return None
        out.append((float(item[0]), float(item[1])))
    return out


def parse_focal_rect_from_json(raw: object) -> tuple[float, float, float, float] | None:
    if not isinstance(raw, (list, tuple)) or len(raw) != 4:
        return None
    return tuple(float(x) for x in raw)  # type: ignore[return-value]
