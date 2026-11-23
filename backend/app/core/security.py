"""Authentification Bearer et autorisations RBAC de l'API (SA-28)."""
import hmac
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.auth import RoleRow, UserAuthSessionRow, UserRoleRow, UserRow
from app.services.authentication import hash_access_token

_bearer = HTTPBearer(auto_error=False)
_token_pattern = re.compile(r"^[A-Za-z0-9_-]{43}$")
_establishment_role_codes = {
    "responsable_iit": "IIT",
    "responsable_isb": "ISB",
    "responsable_isa": "ISA",
    "responsable_2i2s": "2I2S",
}


@dataclass(frozen=True)
class RoleGrant:
    role_code: str
    label: str
    scope: str
    scope_etablissement_id: str | None


@dataclass(frozen=True)
class AuthenticatedUser:
    user_id: int
    email: str
    full_name: str | None
    auth_session_id: UUID
    roles: tuple[RoleGrant, ...]

    def has_role(self, role_code: str) -> bool:
        return any(role.role_code == role_code for role in self.roles)


def _unauthorized() -> HTTPException:
    return HTTPException(
        status.HTTP_401_UNAUTHORIZED,
        "Authentification requise ou jeton invalide.",
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Security(_bearer),
    db: Session = Depends(get_db),
) -> AuthenticatedUser:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise _unauthorized()

    token = credentials.credentials
    if not _token_pattern.fullmatch(token):
        raise _unauthorized()

    token_hash = hash_access_token(token)
    result = db.execute(
        select(UserAuthSessionRow, UserRow)
        .join(UserRow, UserRow.user_id == UserAuthSessionRow.user_id)
        .where(
            UserAuthSessionRow.token_hash == token_hash,
            UserAuthSessionRow.revoked_at.is_(None),
            UserRow.is_active.is_(True),
        )
    ).first()
    if result is None:
        raise _unauthorized()

    auth_session, user = result
    expires_at = auth_session.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if expires_at <= datetime.now(UTC):
        raise _unauthorized()
    if not hmac.compare_digest(auth_session.token_hash, token_hash):
        raise _unauthorized()

    role_rows = db.execute(
        select(RoleRow.role_code, RoleRow.label, RoleRow.scope, UserRoleRow.scope_etablissement_id)
        .join(UserRoleRow, UserRoleRow.role_code == RoleRow.role_code)
        .where(UserRoleRow.user_id == user.user_id)
        .order_by(RoleRow.role_code, UserRoleRow.scope_etablissement_id)
    ).all()
    grants = tuple(RoleGrant(*row) for row in role_rows)
    return AuthenticatedUser(
        user_id=user.user_id,
        email=user.email,
        full_name=user.full_name,
        auth_session_id=auth_session.session_id,
        roles=grants,
    )


def require_roles(*role_codes: str):
    def dependency(user: AuthenticatedUser = Depends(get_current_user)) -> AuthenticatedUser:
        if not any(user.has_role(role_code) for role_code in role_codes):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Rôle insuffisant.")
        return user

    return dependency


def require_responsable(
    user: AuthenticatedUser = Depends(get_current_user),
) -> AuthenticatedUser:
    allowed = {"administrateur", *_establishment_role_codes}
    if not any(role.role_code in allowed for role in user.roles):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Un rôle de responsable est requis.")
    return user


def assert_establishment_permission(user: AuthenticatedUser, establishment_code: str) -> None:
    if user.has_role("administrateur"):
        return
    if any(
        role.role_code in _establishment_role_codes
        and _establishment_role_codes[role.role_code] == establishment_code
        and role.scope_etablissement_id == establishment_code
        for role in user.roles
    ):
        return
    raise HTTPException(status.HTTP_403_FORBIDDEN, "Ce rôle ne permet pas de gérer cet établissement.")
