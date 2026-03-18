from __future__ import annotations

import re

from .schema_index import SchemaChunk, build_schema_index


def _tokenize(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-zA-Z0-9_]+", text.lower()) if t}


def retrieve_schema_chunks(*, question: str, copilot: str, max_chunks: int = 6) -> list[SchemaChunk]:
    q_tokens = _tokenize(question)
    all_chunks = build_schema_index()
    scored: list[tuple[int, SchemaChunk]] = []
    for chunk in all_chunks:
        if chunk.copilot != copilot:
            continue
        score = len(q_tokens.intersection(_tokenize(chunk.text)))
        # Keep a small positive bias for same-copilot chunks.
        scored.append((score + 1, chunk))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [c for _, c in scored[:max_chunks]]
