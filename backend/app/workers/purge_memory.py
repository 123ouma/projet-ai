"""Purge des mémoires et sessions visiteur expirées (SA-25/SA-26).

À lancer périodiquement (cron, ou depuis le worker Python de l'architecture §4.6) :
    python -m app.workers.purge_memory
"""
from sqlalchemy import delete, func, or_, select

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.models import ConversationMemoryRow, VisitorSessionRow
from app.services.memory import _limits
from app.services.memory.postgres import PostgresConversationMemory


def main() -> None:
    with SessionLocal() as db:
        if get_settings().memory_backend == "postgres":
            removed = PostgresConversationMemory(db, _limits()).purge_expired()
        else:
            removed = 0
        expired_ids = db.scalars(
            select(VisitorSessionRow.session_id).where(
                or_(
                    VisitorSessionRow.expires_at <= func.now(),
                    VisitorSessionRow.ended_at.is_not(None),
                )
            )
        ).all()
        if expired_ids:
            removed += db.execute(
                delete(ConversationMemoryRow).where(
                    ConversationMemoryRow.session_id.in_(expired_ids)
                )
            ).rowcount or 0
            db.execute(
                delete(VisitorSessionRow).where(VisitorSessionRow.session_id.in_(expired_ids))
            )
            db.commit()
    print(f"{removed} message(s) expiré(s) et sessions terminées purgés.")


if __name__ == "__main__":
    main()
