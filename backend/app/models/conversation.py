"""Modèle ORM de la mémoire temporaire (SA-26). Reflète 003_conversation_memory.sql."""
import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ConversationMemoryRow(Base):
    __tablename__ = "conversation_memory"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    session_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    role: Mapped[str] = mapped_column(String(10))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
