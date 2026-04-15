"""Packaged PNG room plates under data/scene_backdrops/ (see scripts/build_scene_backdrops.py)."""

from __future__ import annotations

from pathlib import Path


def packaged_scene_backdrop_path(scene_id: str) -> Path | None:
    p = Path(__file__).resolve().parent / "data" / "scene_backdrops" / f"{scene_id}.png"
    return p if p.is_file() else None
