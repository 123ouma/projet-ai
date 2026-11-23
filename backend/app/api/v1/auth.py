"""Authentification et consultation des rôles (SA-28)."""
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import AuthenticatedUser, RoleGrant, get_current_user
from app.models.auth import RoleRow, UserAuthSessionRow, UserRoleRow, UserRow
from app.schemas.auth import AuthTokenOut, LoginIn, RegisterIn, RoleOut, UserOut
from app.services.authentication import issue_access_token
from app.services.passwords import (
    DUMMY_PASSWORD_HASH,
    hash_password,
    password_hash_needs_rehash,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["Authentification (SA-28)"])


def _user_out(
    *,
    user_id: int,
    email: str,
    full_name: str | None,
    roles: tuple[RoleGrant, ...],
) -> UserOut:
    return UserOut(
        user_id=user_id,
        email=email,
        full_name=full_name,
        roles=[
            RoleOut(
                role_code=role.role_code,
                label=role.label,
                scope=role.scope,
                scope_etablissement_id=role.scope_etablissement_id,
            )
            for role in roles
        ],
    )


def _load_role_grants(db: Session, user_id: int) -> tuple[RoleGrant, ...]:
    rows = db.execute(
        select(RoleRow.role_code, RoleRow.label, RoleRow.scope, UserRoleRow.scope_etablissement_id)
        .join(UserRoleRow, UserRoleRow.role_code == RoleRow.role_code)
        .where(UserRoleRow.user_id == user_id)
        .order_by(RoleRow.role_code, UserRoleRow.scope_etablissement_id)
    ).all()
    return tuple(RoleGrant(*row) for row in rows)


def _auth_response(
    *,
    user_id: int,
    email: str,
    full_name: str | None,
    roles: tuple[RoleGrant, ...],
    access_token: str,
    expires_at: datetime,
) -> AuthTokenOut:
    return AuthTokenOut(
        access_token=access_token,
        expires_at=expires_at,
        user=_user_out(user_id=user_id, email=email, full_name=full_name, roles=roles),
    )


@router.post(
    "/register",
    response_model=AuthTokenOut,
    status_code=status.HTTP_201_CREATED,
    responses={409: {"description": "Un compte utilise déjà cette adresse."}},
)
def register(
    payload: RegisterIn,
    response: Response,
    db: Session = Depends(get_db),
) -> AuthTokenOut:
    """Crée un compte candidat; les rôles privilégiés ne sont jamais auto-attribués."""
    candidate_role = db.get(RoleRow, "candidat")
    if candidate_role is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Les rôles ne sont pas initialisés; appliquer les migrations.",
        )

    user = UserRow(
        email=payload.email,
        password_hash=hash_password(payload.password),
        full_name=payload.full_name,
    )
    db.add(user)
    db.flush()
    db.add(UserRoleRow(user_id=user.user_id, role_code="candidat"))
    access_token, expires_at = issue_access_token(db, user.user_id)
    db.commit()
    db.refresh(user)
    response.headers["Cache-Control"] = "no-store"
    return _auth_response(
        user_id=user.user_id,
        email=user.email,
        full_name=user.full_name,
        roles=_load_role_grants(db, user.user_id),
        access_token=access_token,
        expires_at=expires_at,
    )


@router.post(
    "/login",
    response_model=AuthTokenOut,
    responses={401: {"description": "Identifiants invalides ou compte désactivé."}},
)
def login(
    payload: LoginIn,
    response: Response,
    db: Session = Depends(get_db),
) -> AuthTokenOut:
    """Vérifie les identifiants et émet un jeton Bearer révocable à durée limitée."""
    user = db.scalar(select(UserRow).where(UserRow.email == payload.email))
    stored_hash = user.password_hash if user is not None else DUMMY_PASSWORD_HASH
    password_valid = verify_password(payload.password, stored_hash)
    if user is None or not user.is_active or not password_valid:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Identifiants invalides.")

    if password_hash_needs_rehash(user.password_hash):
        user.password_hash = hash_password(payload.password)
    user.last_login_at = datetime.now(UTC)
    access_token, expires_at = issue_access_token(db, user.user_id)
    db.commit()
    response.headers["Cache-Control"] = "no-store"
    return _auth_response(
        user_id=user.user_id,
        email=user.email,
        full_name=user.full_name,
        roles=_load_role_grants(db, user.user_id),
        access_token=access_token,
        expires_at=expires_at,
    )


@router.get(
    "/me",
    response_model=UserOut,
    responses={401: {"description": "Authentification absente, invalide ou expirée."}},
)
def me(user: AuthenticatedUser = Depends(get_current_user)) -> UserOut:
    return _user_out(
        user_id=user.user_id,
        email=user.email,
        full_name=user.full_name,
        roles=user.roles,
    )


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={401: {"description": "Authentification absente, invalide ou expirée."}},
)
def logout(
    response: Response,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    session = db.get(UserAuthSessionRow, user.auth_session_id)
    if session is not None and session.revoked_at is None:
        session.revoked_at = datetime.now(UTC)
        db.commit()
    response.headers["Cache-Control"] = "no-store"
    response.status_code = status.HTTP_204_NO_CONTENT
    return response
