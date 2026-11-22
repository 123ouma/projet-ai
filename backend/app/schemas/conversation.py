"""Schémas de la mémoire temporaire (SA-26)."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class MessageIn(BaseModel):
    role: Literal["user", "assistant"] = Field(description="« system » est réservé au backend")
    content: str = Field(min_length=1, max_length=4000)


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    role: str
    content: str
    created_at: datetime


class ConversationMemoryOut(BaseModel):
    session_id: str
    count: int
    messages: list[MessageOut]
