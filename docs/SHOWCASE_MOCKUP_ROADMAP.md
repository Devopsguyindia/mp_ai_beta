# Showcase mockup roadmap (ERP vs Smartist-class apps)

This document records **product and technical decisions** for closing the gap with consumer in-situ mockup tools, and what is implemented in-repo as of phase 2.

## 1. Wall placement strategy (prioritized)

| Approach | Status | Notes |
|----------|--------|--------|
| **Per-scene `focal_wall_rect`** (normalized ROI on output canvas) | **Shipped** | Art is centered and scaled inside this rectangle instead of the full 1200×900 plate. Defined in [`scene_library_manifest.json`](../copilot-api/app/showcase/data/scene_library_manifest.json). |
| **Per-scene `placement_quad`** (4 corners, TL→TR→BR→BL, normalized) | **Shipped** | Perspective warp (PIL) of mat+art into the quad. Example: `corridor_gallery`. Disabled for pedestal scenes (axis layout kept). |
| **Request overrides** | **Shipped** | `POST /showcase/render` and batch accept optional `focal_wall_rect`, `placement_quad`, `wall_span_cm` (see models). |
| **User quad editor in widget** | **Future** | API ready; UI for dragging corners not built. |
| **ML wall / plane detection** | **Out of scope (v1)** | High cost; revisit if AR or uploaded-room photos become core. |

## 2. Calibration: `wall_span_cm`

**Problem:** `physical_width_cm` with a fictional default “whole canvas = 400 cm wall” felt arbitrary.

**Shipped behavior:**

- Optional **`wall_span_cm`** on render/batch: real-world width in **centimeters** of the **focal wall region** (the horizontal extent you care about—typically matching the bottom edge of `focal_wall_rect` on the real wall).
- When **`wall_span_cm`** and **`physical_width_cm`** are both set, max art width in pixels follows `(physical_width_cm / wall_span_cm) * focal_region_width_px` with margin constants in `_max_art_box` ([`compositor.py`](../copilot-api/app/showcase/compositor.py)).

If `wall_span_cm` is omitted, the compositor keeps the previous **`wall_width_cm` / env default** scaling, scaled by focal region width vs full canvas.

Env defaults remain: `SHOWCASE_STUDIO_WALL_WIDTH_CM`, `SHOWCASE_STUDIO_WALL_HEIGHT_CM`.

## 3. Export / resolution presets

**Current:** PNG size follows `SHOWCASE_COMPOSITOR_CANVAS_W` × `SHOWCASE_COMPOSITOR_CANVAS_H` (default 1200×900).

**Recommended presets (documentation only until a dedicated export endpoint exists):**

| Use | Canvas (W×H) | Env / note |
|-----|----------------|------------|
| Web preview | 1200 × 900 | Default |
| Sharper web / light print | 2400 × 1800 | Double env dimensions |
| Instagram square | 1080 × 1080 | Requires post-crop or square canvas env |
| Instagram portrait | 1080 × 1350 | 4:5 |
| Story | 1080 × 1920 | 9:16 |

A future **`POST /showcase/render/export`** could accept `preset: instagram_square | ...` and optional `dpi`.

## 4. AR / mobile scope

**Decision for ERP v1:** **AR “view on my wall” and native mobile mockup flows are explicitly out of scope** for the embedded showcase panel. The ERP remains the system of record; optional future work:

- Deep-link to a companion app, or
- WebXR / `model-viewer` experiments, only if product commits to mobile parity.

## 5. Files touched (implementation reference)

- [`compositor_geometry.py`](../copilot-api/app/showcase/compositor_geometry.py) — homography coefficients, ROI helpers.
- [`compositor.py`](../copilot-api/app/showcase/compositor.py) — focal rect path, perspective path, `wall_span_cm` in `_max_art_box`.
- [`models.py`](../copilot-api/app/showcase/models.py) — `SceneInfo` + request fields.
- [`render_service.py`](../copilot-api/app/showcase/render_service.py) — cache key includes placement + calibration.
- [`manifest_loader.py`](../copilot-api/app/showcase/manifest_loader.py) — loads optional manifest keys safely.
