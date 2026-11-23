"""Schémas publics de la session visiteur (SA-25)."""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class VisitorSessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    session_id: UUID
    created_at: datetime
    expires_at: datetime
