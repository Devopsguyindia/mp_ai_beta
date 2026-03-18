from __future__ import annotations

from ..models import SchemaContext
from ..prompts.loader import load_prompt
from ..rag.retriever import retrieve_schema_chunks
from ..rag.schema_index import (
    get_all_column_definitions,
    get_column_definitions_for_tables,
    get_critical_notes_for_tables,
    load_schema_registry,
)


def retrieve_schema_context(*, question: str, copilot: str) -> SchemaContext:
    strict_schema_prompt = load_prompt("schema")
    chunks = retrieve_schema_chunks(question=question, copilot=copilot, max_chunks=6)
    relations = sorted({r for c in chunks for r in c.relations})
    context_chunks: list[str] = []

    # Column definitions: use relation_candidates, or ALL tables when RAG returns none
    column_defs = get_column_definitions_for_tables(relations) if relations else get_all_column_definitions()
    if column_defs:
        context_chunks.extend(column_defs)
        context_chunks.append("Use ONLY columns listed above. Do not invent column names.")

    registry = load_schema_registry()
    global_critical_note = registry.get("critical_note")
    if isinstance(global_critical_note, str) and global_critical_note.strip():
        context_chunks.append(global_critical_note.strip())
    global_notes = registry.get("global_critical_notes")
    if isinstance(global_notes, list):
        for n in global_notes:
            if isinstance(n, str) and n.strip():
                context_chunks.append(n.strip())

    # Table-level critical notes for tables in use (or all if relations empty)
    tables_for_notes = relations if relations else [
        str(t.get("table", "")).strip()
        for t in registry.get("tables", [])
        if isinstance(t, dict) and t.get("table")
    ]
    table_notes = get_critical_notes_for_tables(tables_for_notes)
    if table_notes:
        context_chunks.append("Critical table notes:")
        context_chunks.extend(table_notes)

    if strict_schema_prompt:
        context_chunks.insert(0, strict_schema_prompt)

    context_chunks.extend(c.text for c in chunks)
    return SchemaContext(
        relation_candidates=relations,
        context_chunks=context_chunks,
    )
