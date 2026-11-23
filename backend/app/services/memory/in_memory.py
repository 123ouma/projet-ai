"""Mémoire en RAM : pour les tests et le développement sans PostgreSQL.

Perdue au redémarrage et non partagée entre plusieurs processus : ne pas
utiliser en production (MEMORY_BACKEND=postgres par défaut).
"""
import threading
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from app.services.memory.base import ConversationMemory, MemoryLimits, MemoryMessage, Role


def _utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass
class _Session:
    messages: deque
    expires_at: datetime = field(default_factory=_utcnow)


class InMemoryConversationMemory(ConversationMemory):
    def __init__(self, limits: MemoryLimits, clock: Callable[[], datetime] = _utcnow):
        super().__init__(limits)
        self._clock = clock
        self._sessions: dict[str, _Session] = {}
        self._lock = threading.Lock()

    def _alive(self, session_id: str) -> _Session | None:
        session = self._sessions.get(session_id)
        if session is not None and session.expires_at <= self._clock():
            del self._sessions[session_id]
            return None
        return session

    def add(self, session_id: str, role: Role, content: str) -> MemoryMessage:
        content = self._validate(role, content)
        now = self._clock()
        with self._lock:
            session = self._alive(session_id)
            if session is None:
                session = _Session(messages=deque(maxlen=self.limits.max_stored))
                self._sessions[session_id] = session
            message = MemoryMessage(role=role, content=content, created_at=now)
            session.messages.append(message)
            session.expires_at = now + timedelta(minutes=self.limits.ttl_minutes)
            return message

    def history(self, session_id: str) -> list[MemoryMessage]:
        with self._lock:
            session = self._alive(session_id)
            return list(session.messages) if session else []

    def clear(self, session_id: str) -> int:
        with self._lock:
            session = self._sessions.pop(session_id, None)
            return len(session.messages) if session else 0

    def purge_expired(self) -> int:
        now = self._clock()
        with self._lock:
            expired = [sid for sid, s in self._sessions.items() if s.expires_at <= now]
            removed = sum(len(self._sessions.pop(sid).messages) for sid in expired)
            return removed
