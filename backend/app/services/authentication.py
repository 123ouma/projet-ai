"""Création et empreinte des jetons Bearer (SA-28)."""
import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.auth import UserAuthSessionRow


def hash_access_token(token: str) -> str:
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def issue_access_token(db: Session, user_id: int) -> tuple[str, datetime]:
    token = secrets.token_urlsafe(32)
    now = datetime.now(UTC)
    expires_at = now + timedelta(minutes=get_settings().auth_token_ttl_minutes)
    db.add(
        UserAuthSessionRow(
            session_id=uuid.uuid4(),
            user_id=user_id,
            token_hash=hash_access_token(token),
            created_at=now,
            expires_at=expires_at,
        )
    )
    return token, expires_at
