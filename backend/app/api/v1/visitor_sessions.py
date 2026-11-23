"""SA-25 : création, consultation et fermeture des sessions visiteur."""
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import AuthenticatedUser, get_current_user
from app.core.visitor_session import (
    VISITOR_SESSION_COOKIE,
    hash_visitor_token,
    require_visitor_session,
    require_session_access,
)
from app.models.visitor_session import VisitorSessionRow
from app.schemas.visitor_session import VisitorSessionOut
from app.services.memory import ConversationMemory, get_memory

router = APIRouter(prefix="/visitor-sessions", tags=["Sessions visiteurs (SA-25)"])


def _set_cookie(response: Response, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        key=VISITOR_SESSION_COOKIE,
        value=token,
        max_age=settings.visitor_session_ttl_minutes * 60,
        httponly=True,
        secure=settings.environment.lower() == "production",
        samesite="lax",
        path="/",
    )
    response.headers["Cache-Control"] = "no-store"


def _clear_cookie(response: Response) -> None:
    response.delete_cookie(
        key=VISITOR_SESSION_COOKIE,
        path="/",
        httponly=True,
        secure=get_settings().environment.lower() == "production",
        samesite="lax",
    )
    response.headers["Cache-Control"] = "no-store"


@router.post(
    "",
    response_model=VisitorSessionOut,
    status_code=status.HTTP_201_CREATED,
    responses={201: {"description": "Session créée; le jeton d'accès est placé dans un cookie HttpOnly."}},
)
def create_visitor_session(
    response: Response,
    db: Session = Depends(get_db),
):
    """Crée une session. Le client ne choisit jamais son identifiant."""
    now = datetime.now(UTC)
    token = secrets.token_urlsafe(32)
    session = VisitorSessionRow(
        session_id=uuid.uuid4(),
        token_hash=hash_visitor_token(token),
        created_at=now,
        expires_at=now + timedelta(minutes=get_settings().visitor_session_ttl_minutes),
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    _set_cookie(response, token)
    return session


@router.post(
    "/{session_id}/claim",
    response_model=VisitorSessionOut,
    responses={
        401: {"description": "Authentification ou cookie visiteur requis."},
        403: {"description": "Le cookie ne correspond pas à cette session."},
        404: {"description": "Session inexistante."},
        409: {"description": "La session est déjà liée à un autre compte."},
        410: {"description": "Session expirée ou terminée."},
    },
)
def claim_visitor_session(
    session_id: uuid.UUID,
    response: Response,
    user: AuthenticatedUser = Depends(get_current_user),
    session: VisitorSessionRow = Depends(require_visitor_session),
    db: Session = Depends(get_db),
):
    """Lie au compte courant la session dont le cookie visiteur prouve la propriété."""
    now = datetime.now(UTC)
    result = db.execute(
        update(VisitorSessionRow)
        .where(
            VisitorSessionRow.session_id == session.session_id,
            VisitorSessionRow.token_hash == session.token_hash,
            VisitorSessionRow.ended_at.is_(None),
            or_(
                VisitorSessionRow.linked_user_id.is_(None),
                VisitorSessionRow.linked_user_id == user.user_id,
            ),
        )
        .values(linked_user_id=user.user_id)
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        current = db.scalar(
            select(VisitorSessionRow)
            .where(VisitorSessionRow.session_id == session_id)
            .execution_options(populate_existing=True)
        )
        if current is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Session visiteur introuvable.")
        expires_at = current.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        if current.ended_at is not None or expires_at <= now:
            raise HTTPException(status.HTTP_410_GONE, "Cette session visiteur a expiré ou est terminée.")
        if current.linked_user_id != user.user_id:
            raise HTTPException(status.HTTP_409_CONFLICT, "Cette session est liée à un autre compte.")
    db.commit()
    db.refresh(session)
    response.headers["Cache-Control"] = "no-store"
    return session


@router.get(
    "/{session_id}",
    response_model=VisitorSessionOut,
    responses={
        401: {"description": "Cookie visiteur ou authentification Bearer requis."},
        403: {"description": "La session appartient à un autre visiteur ou compte."},
        404: {"description": "Session inexistante."},
        410: {"description": "Session expirée ou terminée."},
    },
)
def get_visitor_session(
    response: Response,
    session: VisitorSessionRow = Depends(require_session_access),
):
    """Récupère uniquement la session liée au cookie du visiteur."""
    response.headers["Cache-Control"] = "no-store"
    return session


@router.delete(
    "/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        401: {"description": "Cookie visiteur ou authentification Bearer requis."},
        403: {"description": "La session appartient à un autre visiteur ou compte."},
        404: {"description": "Session inexistante."},
        410: {"description": "Session expirée ou déjà terminée."},
    },
)
def end_visitor_session(
    response: Response,
    session: VisitorSessionRow = Depends(require_session_access),
    db: Session = Depends(get_db),
    memory: ConversationMemory = Depends(get_memory),
) -> Response:
    """Termine la session et efface sa mémoire SA-26."""
    session.ended_at = datetime.now(UTC)
    db.commit()
    memory.clear(str(session.session_id))
    _clear_cookie(response)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response
