import json

import pytest

from app.showcase.manifest_loader import load_scene_manifest


def test_load_scene_manifest_from_env_json(monkeypatch: pytest.MonkeyPatch):
    payload = {
        "pipeline_version": "test-pipe-1",
        "scenes": [
            {
                "scene_id": "a",
                "label": "A",
                "tags": ["2d"],
            }
        ],
    }
    monkeypatch.setenv("SHOWCASE_SCENE_MANIFEST_JSON", json.dumps(payload))
    v, scenes = load_scene_manifest()
    assert v == "test-pipe-1"
    assert len(scenes) == 1
    assert scenes[0].scene_id == "a"
    assert scenes[0].tags == ["2d"]
