"""SA-26 : mémoire temporaire des conversations.

Utilisation côté chatbot (SA-36 / SA-37) :

    from app.services.memory import get_memory
    memory.add(session_id, "user", question)
    historique = memory.context_for_llm(session_id)   # [{"role": ..., "content": ...}, ...]
    ... appel au LLM ...
    memory.add(session_id, "assistant", reponse)
"""
from collections.abc import Iterator
from functools import lru_cache

from app.services.memory.base import ConversationMemory, MemoryLimits, MemoryMessage, trim_context
from app.services.memory.in_memory import InMemoryConversationMemory

__all__ = [
    "ConversationMemory",
    "InMemoryConversationMemory",
    "MemoryLimits",
    "MemoryMessage",
    "get_memory",
    "trim_context",
]


def _limits() -> MemoryLimits:
    from app.core.config import get_settings

    s = get_settings()
    return MemoryLimits(
        ttl_minutes=s.memory_ttl_minutes,
        max_messages=s.memory_max_messages,
        max_chars=s.memory_max_chars,
        max_stored=s.memory_max_stored,
    )


@lru_cache
def _in_memory_singleton() -> InMemoryConversationMemory:
    return InMemoryConversationMemory(_limits())


def get_memory() -> Iterator[ConversationMemory]:
    """Dépendance FastAPI : renvoie l'implémentation choisie par MEMORY_BACKEND."""
    from app.core.config import get_settings

    if get_settings().memory_backend == "memory":
        yield _in_memory_singleton()
        return

    from app.core.database import SessionLocal
    from app.services.memory.postgres import PostgresConversationMemory

    db = SessionLocal()
    try:
        yield PostgresConversationMemory(db, _limits())
    finally:
        db.close()
