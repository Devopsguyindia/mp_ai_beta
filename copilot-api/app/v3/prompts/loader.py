from __future__ import annotations

from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=16)
def load_prompt(name: str) -> str:
    prompt_path = Path(__file__).resolve().parent / f"{name}.md"
    if not prompt_path.exists():
        return ""
    return prompt_path.read_text(encoding="utf-8").strip()
