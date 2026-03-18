from __future__ import annotations

from ..memory.log_store import get_recent_events
from ..memory.vector_store import VectorMemoryStore
from ..models import MemoryContext


def fetch_memory_context(*, idcompany: int, question: str, limit: int = 6) -> MemoryContext:
    recent = get_recent_events(idcompany=idcompany, limit=limit, query=question)
    vector_store = VectorMemoryStore()
    vector_hits = vector_store.search(query=question, idcompany=idcompany, top_k=3)

    recent_questions = [str(r.get("question") or "") for r in recent if r.get("question")]
    recent_sql = [str(r.get("sql") or "") for r in recent if r.get("sql")]
    recent_questions.extend(str(v.payload.get("question") or "") for v in vector_hits if v.payload.get("question"))
    recent_sql.extend(str(v.payload.get("sql") or "") for v in vector_hits if v.payload.get("sql"))

    return MemoryContext(
        recent_questions=[q for q in recent_questions if q][:limit],
        recent_sql=[s for s in recent_sql if s][:limit],
        reused=bool(recent_questions or recent_sql),
    )
