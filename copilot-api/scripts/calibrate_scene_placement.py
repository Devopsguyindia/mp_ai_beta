"""
AI-powered wall-placement calibration for showcase backdrops.

For each scene backdrop PNG, sends the image to GPT-4o Vision and asks it to
identify the primary flat surface (wall / plinth) where artwork should be
displayed.  The detected normalized coordinates are written back into
scene_library_manifest.json as focal_wall_rect and (for perspective walls)
placement_quad.

Usage
-----
    # from copilot-api/ folder:
    python scripts/calibrate_scene_placement.py

    # Dry-run (prints result, does not write manifest):
    python scripts/calibrate_scene_placement.py --dry-run

    # Re-calibrate only specific scenes:
    python scripts/calibrate_scene_placement.py --scenes gallery_white_wall corridor_gallery

    # Skip scenes that already have focal_wall_rect set:
    python scripts/calibrate_scene_placement.py --skip-existing

Environment
-----------
    OPENAI_API_KEY   (required)
    OPENAI_BASE_URL  (optional, for Azure / proxy)

The script uses .env in the copilot-api root if present.
"""
from __future__ import annotations

import argparse
import base64
import json
import logging
import os
import sys
import textwrap
from pathlib import Path

# ---------------------------------------------------------------------------
# Bootstrap path so we can import app.showcase helpers
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(REPO_ROOT / ".env", override=False)
    load_dotenv(REPO_ROOT / ".env.example", override=False)
except ImportError:
    pass

MANIFEST_PATH = REPO_ROOT / "app" / "showcase" / "data" / "scene_library_manifest.json"
BACKDROPS_DIR = REPO_ROOT / "app" / "showcase" / "data" / "scene_backdrops"

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger("calibrate")

# ---------------------------------------------------------------------------
# GPT-4o prompt
# ---------------------------------------------------------------------------
_SYSTEM = textwrap.dedent(
    """
    You are an expert art installation consultant and computer vision analyst.
    Your task: analyze room / studio backdrop images and locate the best
    rectangular region for displaying framed 2D artwork or a 3D sculpture on a
    plinth.

    Rules
    -----
    - ALL coordinates are normalized 0.0–1.0 relative to image width (x) and
      height (y).  (0,0) = top-left corner.
    - focal_wall_rect: [left, top, right, bottom]  — the tight bounding box
      of the primary flat display surface (wall panel, accent wall, alcove,
      clean wall behind a sofa, etc.).  Exclude floor, ceiling, furniture that
      would be in front of the artwork.  Be as tight as reasonably possible —
      do NOT return the full image bounds unless the wall really does fill the
      frame.
    - placement_quad (optional): only return this when the wall surface is
      clearly NOT axis-aligned (e.g. a corridor with a vanishing point, an
      angled wall, a perspective-heavy wide shot).  Four corners [x,y] in
      order: top-left, top-right, bottom-right, bottom-left.
    - wall_span_cm: estimated real-world width of the focal wall region in
      centimetres.  Use architectural norms:
        gallery / hotel  → 300–500 cm
        living room      → 180–320 cm
        office           → 200–350 cm
        studio           → 300–450 cm
        corridor wall    → 250–400 cm
        pedestal area    → 60–120 cm   (the plinth top, not the room)
    - For a pedestal scene: focal_wall_rect should cover the plinth top surface
      (small rectangle, low in the frame).  placement_quad is not needed.
    - eye_level_fraction: a number 0.0–1.0 that describes what fraction down
      from the top of focal_wall_rect the vertical centre of the artwork should
      sit.  For eye-level hang: typically 0.40–0.55.  For above-sofa: 0.35–0.50.
      For pedestal: 0.30 (artwork sits on top of plinth).
    - confidence: integer 0–100.

    Output ONLY a JSON object — no markdown, no prose:
    {
      "focal_wall_rect": [left, top, right, bottom],
      "placement_quad": [[x,y],[x,y],[x,y],[x,y]] | null,
      "wall_span_cm": number,
      "eye_level_fraction": number,
      "confidence": integer,
      "notes": "one short sentence"
    }
    """
).strip()

_USER_TEMPLATE = textwrap.dedent(
    """
    Scene: {scene_id}
    Label: {label}
    Placement hint: {placement_hint}
    Description: {description}

    Analyse the attached image and return placement coordinates as JSON.
    """
).strip()


def _encode_image(path: Path) -> tuple[str, str]:
    """Return (base64_data, media_type)."""
    data = path.read_bytes()
    ext = path.suffix.lower()
    mime = "image/jpeg" if ext in {".jpg", ".jpeg"} else "image/png"
    return base64.b64encode(data).decode(), mime


def _call_vision_api(
    scene_id: str,
    label: str,
    placement_hint: str,
    description: str,
    image_path: Path,
    client,  # openai.OpenAI
) -> dict:
    b64, mime = _encode_image(image_path)
    user_text = _USER_TEMPLATE.format(
        scene_id=scene_id,
        label=label,
        placement_hint=placement_hint,
        description=description,
    )
    resp = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": _SYSTEM},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_text},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime};base64,{b64}", "detail": "high"},
                    },
                ],
            },
        ],
        max_tokens=512,
        temperature=0.0,
    )
    raw = resp.choices[0].message.content or ""
    raw = raw.strip()
    if raw.startswith("```"):
        raw = "\n".join(raw.splitlines()[1:])
    if raw.endswith("```"):
        raw = raw.rsplit("```", 1)[0]
    return json.loads(raw.strip())


def _validate_focal_rect(r) -> list[float] | None:
    if not isinstance(r, (list, tuple)) or len(r) != 4:
        return None
    vals = [float(v) for v in r]
    left, top, right, bottom = vals
    if not (0.0 <= left < right <= 1.0 and 0.0 <= top < bottom <= 1.0):
        return None
    # Reject near-full-image rects — that means the model didn't find anything specific
    if (right - left) > 0.98 and (bottom - top) > 0.95:
        return None
    return vals


def _validate_quad(q) -> list[list[float]] | None:
    if q is None:
        return None
    if not isinstance(q, (list, tuple)) or len(q) != 4:
        return None
    pts = [[float(x), float(y)] for x, y in q]
    for x, y in pts:
        if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
            return None
    return pts


# ---------------------------------------------------------------------------
# Scene fallback heuristics (used when no backdrop image found or API fails)
# ---------------------------------------------------------------------------
_FALLBACK: dict[str, dict] = {
    # Gallery: broad flat wall, moderate margins, centered artwork zone
    "gallery_white_wall":        {"focal_wall_rect": [0.05, 0.07, 0.95, 0.88], "wall_span_cm": 400, "eye_level_fraction": 0.48},
    # Living room: artwork hangs on back wall above furniture, narrower vertical band
    "residential_living_warm":   {"focal_wall_rect": [0.12, 0.08, 0.88, 0.70], "wall_span_cm": 300, "eye_level_fraction": 0.45},
    "residential_modern_cool":   {"focal_wall_rect": [0.12, 0.08, 0.88, 0.68], "wall_span_cm": 290, "eye_level_fraction": 0.44},
    # Office: wall behind desk / side wall; tight
    "office_minimal":            {"focal_wall_rect": [0.10, 0.06, 0.90, 0.72], "wall_span_cm": 320, "eye_level_fraction": 0.46},
    # Hotel lobby: usually a feature wall panel — narrower width, tall
    "hotel_lobby_luxury":        {"focal_wall_rect": [0.15, 0.06, 0.85, 0.78], "wall_span_cm": 380, "eye_level_fraction": 0.42},
    # Corridor: perspective wall — quad required
    "corridor_gallery": {
        "focal_wall_rect": [0.06, 0.08, 0.94, 0.82],
        "placement_quad": [[0.07, 0.10], [0.93, 0.08], [0.94, 0.80], [0.06, 0.82]],
        "wall_span_cm": 350,
        "eye_level_fraction": 0.48,
    },
    # Studio: plain wall behind easel — wide, generous
    "studio_natural_north":      {"focal_wall_rect": [0.06, 0.05, 0.94, 0.90], "wall_span_cm": 420, "eye_level_fraction": 0.50},
    # Pedestal: plinth top surface — small, low-centre
    "pedestal_sculpture_spot":   {"focal_wall_rect": [0.32, 0.55, 0.68, 0.82], "wall_span_cm": 80,  "eye_level_fraction": 0.30},
}


def _find_backdrop(scene_id: str) -> Path | None:
    for ext in (".png", ".jpg", ".jpeg", ".webp"):
        p = BACKDROPS_DIR / f"{scene_id}{ext}"
        if p.exists():
            return p
    return None


def calibrate_scene(
    scene: dict,
    *,
    dry_run: bool,
    skip_existing: bool,
    client,
) -> dict | None:
    """Return a dict of fields to merge into the scene entry, or None to skip."""
    sid = scene["scene_id"]

    if skip_existing and scene.get("focal_wall_rect"):
        log.info("  SKIP %s (already has focal_wall_rect)", sid)
        return None

    fb = _FALLBACK.get(sid, {})
    image_path = _find_backdrop(sid)

    if image_path is None:
        log.warning("  %s — no backdrop image found in %s; using fallback heuristics", sid, BACKDROPS_DIR)
        return fb or None

    log.info("  %s — calling GPT-4o Vision on %s …", sid, image_path.name)
    try:
        result = _call_vision_api(
            scene_id=sid,
            label=scene.get("label", sid),
            placement_hint=scene.get("placement_hint", "wall_eye_level"),
            description=scene.get("description", ""),
            image_path=image_path,
            client=client,
        )
        log.info("    → raw: %s", json.dumps(result))
    except Exception as exc:
        log.warning("    API call failed: %s — using fallback heuristics", exc)
        return fb or None

    out: dict = {}

    fr = _validate_focal_rect(result.get("focal_wall_rect"))
    if fr:
        out["focal_wall_rect"] = fr
        log.info("    focal_wall_rect = %s", fr)
    else:
        fallback_fr = fb.get("focal_wall_rect")
        if fallback_fr:
            out["focal_wall_rect"] = fallback_fr
            log.info("    focal_wall_rect rejected, using fallback %s", fallback_fr)

    q = _validate_quad(result.get("placement_quad"))
    if q:
        out["placement_quad"] = q
        log.info("    placement_quad = %s", q)
    elif fb.get("placement_quad"):
        out["placement_quad"] = fb["placement_quad"]
        log.info("    using fallback placement_quad")

    span = result.get("wall_span_cm")
    if span and float(span) > 0:
        out["wall_span_cm"] = float(span)
    elif fb.get("wall_span_cm"):
        out["wall_span_cm"] = fb["wall_span_cm"]

    elf = result.get("eye_level_fraction")
    if elf is not None:
        out["eye_level_fraction"] = float(elf)
    elif fb.get("eye_level_fraction") is not None:
        out["eye_level_fraction"] = fb["eye_level_fraction"]

    conf = result.get("confidence", 0)
    if conf:
        out["_calibration_confidence"] = int(conf)
    notes = result.get("notes", "")
    if notes:
        out["_calibration_notes"] = notes

    return out or None


def main() -> None:
    parser = argparse.ArgumentParser(description="AI wall-placement calibration for showcase scenes")
    parser.add_argument("--dry-run", action="store_true", help="Print results but do not write manifest")
    parser.add_argument("--skip-existing", action="store_true", help="Skip scenes that already have focal_wall_rect")
    parser.add_argument("--scenes", nargs="*", metavar="SCENE_ID", help="Calibrate only these scene IDs")
    args = parser.parse_args()

    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        log.error("OPENAI_API_KEY not set — cannot call GPT-4o Vision.")
        sys.exit(1)

    try:
        import openai
        client = openai.OpenAI(api_key=api_key, base_url=os.getenv("OPENAI_BASE_URL") or None)
    except ImportError:
        log.error("openai package not installed (pip install openai)")
        sys.exit(1)

    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    scenes: list[dict] = manifest["scenes"]

    filter_ids = set(args.scenes) if args.scenes else None
    changed = 0

    for scene in scenes:
        sid = scene["scene_id"]
        if filter_ids and sid not in filter_ids:
            continue

        log.info("Scene: %s", sid)
        updates = calibrate_scene(
            scene,
            dry_run=args.dry_run,
            skip_existing=args.skip_existing,
            client=client,
        )
        if updates is None:
            continue

        if args.dry_run:
            print(f"\n{sid}:")
            print(json.dumps(updates, indent=2))
        else:
            scene.update(updates)
            changed += 1
            log.info("  ✓ manifest updated for %s", sid)

    if not args.dry_run and changed:
        manifest["pipeline_version"] = "scene-lib-2026-04-ai-calibrated"
        MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        log.info("\n✓ Manifest saved (%d scene(s) updated): %s", changed, MANIFEST_PATH)
    elif not changed:
        log.info("No scenes updated.")


if __name__ == "__main__":
    main()
