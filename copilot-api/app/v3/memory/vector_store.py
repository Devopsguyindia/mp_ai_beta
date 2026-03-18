from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any


@dataclass
class VectorSearchResult:
    payload: dict[str, Any]
    score: float


class VectorMemoryStore:
    """
    Configurable pgvector placeholder.
    Phase-2 starts logs-first; pgvector can be enabled later via env.
    """

    def __init__(self) -> None:
        self.enabled = os.getenv("V3_MEMORY_PGVECTOR_ENABLED", "0").strip() in {"1", "true", "TRUE", "yes", "YES"}

    def upsert(self, *, payload: dict[str, Any]) -> None:
        if not self.enabled:
            return
        # Intentionally no-op in current phase.
        return

    def search(self, *, query: str, idcompany: int, top_k: int = 5) -> list[VectorSearchResult]:
        if not self.enabled:
            return []
        # Intentionally no-op in current phase.
        _ = (query, idcompany, top_k)
        return []
