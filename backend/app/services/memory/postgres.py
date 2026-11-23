"""Mémoire stockée dans PostgreSQL (table conversation_memory) : partagée entre l'API
et le worker, et conservée en cas de redémarrage."""
import uuid
from datetime import timedelta

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.models import ConversationMemoryRow
from app.services.memory.base import ConversationMemory, MemoryLimits, MemoryMessage, Role, trim_context


def _to_message(row: ConversationMemoryRow) -> MemoryMessage:
    return MemoryMessage(role=row.role, content=row.content, created_at=row.created_at)  # type: ignore[arg-type]


class PostgresConversationMemory(ConversationMemory):
    def __init__(self, db: Session, limits: MemoryLimits):
        super().__init__(limits)
        self.db = db

    @staticmethod
    def _sid(session_id: str) -> uuid.UUID:
        return uuid.UUID(str(session_id))

    def _ttl(self):
        return func.now() + timedelta(minutes=self.limits.ttl_minutes)

    def add(self, session_id: str, role: Role, content: str) -> MemoryMessage:
        content = self._validate(role, content)
        sid = self._sid(session_id)
        T = ConversationMemoryRow
        try:
            # 1. Session expirée -> on repart d'une mémoire vide
            self.db.execute(delete(T).where(T.session_id == sid, T.expires_at <= func.now()))
            # 2. Nouveau message
            row = T(session_id=sid, role=role, content=content, expires_at=self._ttl())
            self.db.add(row)
            self.db.flush()
            # 3. Fenêtre glissante : toute la session expire plus tard
            self.db.execute(update(T).where(T.session_id == sid).values(expires_at=self._ttl()))
            # 4. On ne garde que les max_stored derniers messages
            anciens = (
                select(T.id)
                .where(T.session_id == sid)
                .order_by(T.id.desc())
                .offset(self.limits.max_stored)
                .scalar_subquery()
            )
            self.db.execute(delete(T).where(T.id.in_(anciens)))
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        self.db.refresh(row)
        return _to_message(row)

    def history(self, session_id: str) -> list[MemoryMessage]:
        T = ConversationMemoryRow
        rows = self.db.scalars(
            select(T)
            .where(T.session_id == self._sid(session_id), T.expires_at > func.now())
            .order_by(T.id)
        ).all()
        return [_to_message(r) for r in rows]

    def context(self, session_id: str) -> list[MemoryMessage]:
        # On ne lit que les max_messages derniers en base, puis on borne en caractères.
        T = ConversationMemoryRow
        recents = (
            select(T)
            .where(T.session_id == self._sid(session_id), T.expires_at > func.now())
            .order_by(T.id.desc())
            .limit(self.limits.max_messages)
        )
        rows = list(reversed(self.db.scalars(recents).all()))
        return trim_context([_to_message(r) for r in rows], self.limits.max_messages, self.limits.max_chars)

    def clear(self, session_id: str) -> int:
        T = ConversationMemoryRow
        result = self.db.execute(delete(T).where(T.session_id == self._sid(session_id)))
        self.db.commit()
        return result.rowcount or 0

    def purge_expired(self) -> int:
        T = ConversationMemoryRow
        result = self.db.execute(delete(T).where(T.expires_at <= func.now()))
        self.db.commit()
        return result.rowcount or 0
