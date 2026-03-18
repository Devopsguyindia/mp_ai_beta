from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class SchemaChunk:
    source: str
    copilot: str
    text: str
    relations: tuple[str, ...]


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _schema_registry_path() -> Path:
    return _repo_root() / "prompt_coverage" / "schema_registry.json"


def load_schema_registry() -> dict[str, Any]:
    """Load schema_registry.json. Returns empty dict if missing or invalid."""
    path = _schema_registry_path()
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def get_column_definitions_for_tables(tables: list[str]) -> list[str]:
    """
    Return formatted column-definition strings for the given tables.
    Each string: "table_name: col1, col2, col3 (use ONLY these columns)"
    Returns empty list if registry missing or invalid.
    """
    registry = load_schema_registry()
    tables_data = registry.get("tables")
    if not isinstance(tables_data, list):
        return []
    table_map: dict[str, dict[str, Any]] = {
        str(t.get("table", "")).strip(): t for t in tables_data if isinstance(t, dict) and t.get("table")
    }
    result: list[str] = []
    for t in tables:
        t_clean = str(t).strip()
        if not t_clean:
            continue
        entry = table_map.get(t_clean)
        if not entry or not isinstance(entry.get("columns"), list):
            continue
        cols = [str(c.get("name", "")).strip() for c in entry["columns"] if isinstance(c, dict) and c.get("name")]
        if cols:
            result.append(f"{t_clean}: {', '.join(cols)} (use ONLY these columns)")
    return result


def get_all_column_definitions() -> list[str]:
    """
    Return column definitions for ALL tables in the registry.
    Use when relation_candidates is empty or when full schema is needed (e.g. V2, retries).
    """
    registry = load_schema_registry()
    tables_data = registry.get("tables")
    if not isinstance(tables_data, list):
        return []
    tables = [str(t.get("table", "")).strip() for t in tables_data if isinstance(t, dict) and t.get("table")]
    return get_column_definitions_for_tables(tables)


def get_critical_notes_for_tables(tables: list[str]) -> list[str]:
    """
    Return critical notes for the given tables from the registry.
    Each table can have critical_notes (list) or critical_note (string).
    Returns empty list if none found.
    """
    registry = load_schema_registry()
    tables_data = registry.get("tables")
    if not isinstance(tables_data, list):
        return []
    table_map: dict[str, dict[str, Any]] = {
        str(t.get("table", "")).strip(): t for t in tables_data if isinstance(t, dict) and t.get("table")
    }
    result: list[str] = []
    for t in tables:
        t_clean = str(t).strip()
        if not t_clean:
            continue
        entry = table_map.get(t_clean)
        if not entry:
            continue
        notes = entry.get("critical_notes")
        if isinstance(notes, list):
            for n in notes:
                if isinstance(n, str) and n.strip():
                    result.append(f"[{t_clean}] {n.strip()}")
        elif isinstance(entry.get("critical_note"), str):
            n = entry["critical_note"].strip()
            if n:
                result.append(f"[{t_clean}] {n}")
    return result


def build_schema_from_registry(copilot: str | None = None) -> str:
    """
    Build a full schema block from the registry for use when schema_from_context is empty.
    Used by V2 path, validator retry, and LLM fallback.
    Returns empty string if registry is empty.
    """
    registry = load_schema_registry()
    if not registry:
        return ""
    parts: list[str] = []
    column_defs = get_all_column_definitions()
    if column_defs:
        parts.extend(column_defs)
        parts.append("Use ONLY columns listed above. Do not invent column names.")
    global_note = registry.get("critical_note")
    if isinstance(global_note, str) and global_note.strip():
        parts.append(global_note.strip())
    global_notes = registry.get("global_critical_notes")
    if isinstance(global_notes, list):
        for n in global_notes:
            if isinstance(n, str) and n.strip():
                parts.append(n.strip())
    table_notes = get_critical_notes_for_tables(
        [str(t.get("table", "")).strip() for t in registry.get("tables", []) if isinstance(t, dict) and t.get("table")]
    )
    if table_notes:
        parts.append("Critical table notes:")
        parts.extend(table_notes)
    return "\n".join(parts) if parts else ""


def build_schema_index() -> list[SchemaChunk]:
    root = _repo_root()
    prompt_coverage = root / "prompt_coverage"
    chunks: list[SchemaChunk] = []

    intent_catalog_path = prompt_coverage / "intent_catalog.json"
    contracts_path = prompt_coverage / "prompt_to_sql_contracts.json"

    if intent_catalog_path.exists():
        payload = json.loads(intent_catalog_path.read_text(encoding="utf-8"))
        copilots = payload.get("copilots", {}) if isinstance(payload, dict) else {}
        if isinstance(copilots, dict):
            for copilot, intents in copilots.items():
                if isinstance(intents, list):
                    text = f"copilot={copilot}; intents={', '.join(str(i) for i in intents)}"
                    chunks.append(
                        SchemaChunk(
                            source="intent_catalog",
                            copilot=str(copilot),
                            text=text,
                            relations=(),
                        )
                    )

    if contracts_path.exists():
        payload = json.loads(contracts_path.read_text(encoding="utf-8"))
        contracts = payload.get("contracts", []) if isinstance(payload, dict) else []
        for c in contracts:
            if not isinstance(c, dict):
                continue
            contract_id = str(c.get("contract_id") or "")
            relations_raw = c.get("preferred_relations") or []
            relations = tuple(str(r) for r in relations_raw if isinstance(r, str))
            if contract_id.startswith("sales_"):
                copilot = "sales"
            elif contract_id.startswith("inventory_"):
                copilot = "inventory"
            elif contract_id.startswith("contact_"):
                copilot = "customer"
            elif contract_id.startswith("artist_"):
                copilot = "artist"
            elif contract_id.startswith("vendor_"):
                copilot = "vendor"
            else:
                copilot = "sales"
            text = f"contract={contract_id}; relations={', '.join(relations)}"
            chunks.append(
                SchemaChunk(
                    source="contracts",
                    copilot=copilot,
                    text=text,
                    relations=relations,
                )
            )
    return chunks


def build_relation_registry() -> dict[str, set[str]]:
    registry: dict[str, set[str]] = {
        "sales": set(),
        "inventory": set(),
        "customer": set(),
        "artist": set(),
        "vendor": set(),
    }
    for chunk in build_schema_index():
        registry.setdefault(chunk.copilot, set()).update(chunk.relations)
    return registry
