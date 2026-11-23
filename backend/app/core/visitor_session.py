"""Authentification par cookie et contrôle de propriété des sessions visiteur."""
import hashlib
import hmac
import re
from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import Cookie, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import AuthenticatedUser, get_optional_current_user
from app.models.visitor_session import VisitorSessionRow
from app.services.memory import ConversationMemory, get_memory

VISITOR_SESSION_COOKIE = "smartcampus_visitor_session"
_TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9_-]{43}$")


def hash_visitor_token(token: str) -> str:
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def token_is_well_formed(token: str | None) -> bool:
    return bool(token and _TOKEN_PATTERN.fullmatch(token))


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def require_visitor_session(
    session_id: UUID,
    response: Response,
    visitor_token: str | None = Cookie(default=None, alias=VISITOR_SESSION_COOKIE),
    db: Session = Depends(get_db),
    memory: ConversationMemory = Depends(get_memory),
) -> VisitorSessionRow:
    if not token_is_well_formed(visitor_token):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session visiteur requise.")

    session = db.scalar(
        select(VisitorSessionRow)
        .where(VisitorSessionRow.session_id == session_id)
        .with_for_update()
    )
    if session is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session visiteur introuvable.")

    expected_hash = hash_visitor_token(visitor_token)
    if not hmac.compare_digest(session.token_hash, expected_hash):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Accès à cette session refusé.")

    now = datetime.now(UTC)
    if session.ended_at is not None or _as_utc(session.expires_at) <= now:
        memory.clear(str(session.session_id))
        raise HTTPException(status.HTTP_410_GONE, "Cette session visiteur a expiré ou est terminée.")

    session.expires_at = now + timedelta(minutes=get_settings().visitor_session_ttl_minutes)
    db.commit()
    db.refresh(session)
    settings = get_settings()
    response.set_cookie(
        key=VISITOR_SESSION_COOKIE,
        value=visitor_token,
        max_age=settings.visitor_session_ttl_minutes * 60,
        httponly=True,
        secure=settings.environment.lower() == "production",
        samesite="lax",
        path="/",
    )
    response.headers["Cache-Control"] = "no-store"
    return session


def require_session_access(
    session_id: UUID,
    response: Response,
    visitor_token: str | None = Cookie(default=None, alias=VISITOR_SESSION_COOKIE),
    current_user: AuthenticatedUser | None = Depends(get_optional_current_user),
    db: Session = Depends(get_db),
    memory: ConversationMemory = Depends(get_memory),
) -> VisitorSessionRow:
    """Authorise la session par cookie avant liaison, puis par compte après liaison."""
    if current_user is None and not token_is_well_formed(visitor_token):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session visiteur requise.")

    session = db.scalar(
        select(VisitorSessionRow)
        .where(VisitorSessionRow.session_id == session_id)
        .with_for_update()
    )
    if session is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session visiteur introuvable.")

    refresh_visitor_token: str | None = None
    if session.linked_user_id is None:
        if visitor_token is None or not token_is_well_formed(visitor_token):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session visiteur requise.")
        expected_hash = hash_visitor_token(visitor_token)
        if not hmac.compare_digest(session.token_hash, expected_hash):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Accès à cette session refusé.")
        refresh_visitor_token = visitor_token
    else:
        if current_user is None:
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED,
                "Authentification requise pour cette session liée.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        if current_user.user_id != session.linked_user_id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Accès à cette session refusé.")

    now = datetime.now(UTC)
    if session.ended_at is not None or _as_utc(session.expires_at) <= now:
        memory.clear(str(session.session_id))
        raise HTTPException(status.HTTP_410_GONE, "Cette session visiteur a expiré ou est terminée.")

    session.expires_at = now + timedelta(minutes=get_settings().visitor_session_ttl_minutes)
    db.commit()
    db.refresh(session)
    if refresh_visitor_token is not None:
        settings = get_settings()
        response.set_cookie(
            key=VISITOR_SESSION_COOKIE,
            value=refresh_visitor_token,
            max_age=settings.visitor_session_ttl_minutes * 60,
            httponly=True,
            secure=settings.environment.lower() == "production",
            samesite="lax",
            path="/",
        )
    response.headers["Cache-Control"] = "no-store"
    return session
