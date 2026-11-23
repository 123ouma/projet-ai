"""Comptes, rôles et jetons d'authentification (SA-28)."""
import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

_SQLITE_BIGINT = BigInteger().with_variant(Integer, "sqlite")


class RoleRow(Base):
    __tablename__ = "roles"

    role_code: Mapped[str] = mapped_column(String(40), primary_key=True)
    label: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    scope: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class UserRow(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("email = lower(email)", name="users_email_lower_chk"),
        CheckConstraint("length(password_hash) > 0", name="users_password_hash_not_empty_chk"),
    )

    user_id: Mapped[int] = mapped_column(_SQLITE_BIGINT, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(120))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class UserRoleRow(Base):
    __tablename__ = "user_roles"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "role_code",
            "scope_etablissement_id",
            name="user_roles_natural_key",
            postgresql_nulls_not_distinct=True,
        ),
        CheckConstraint(
            "role_code NOT IN ('responsable_iit', 'responsable_isb', "
            "'responsable_isa', 'responsable_2i2s') OR scope_etablissement_id IS NOT NULL",
            name="user_roles_scope_required_chk",
        ),
        CheckConstraint(
            "(role_code = 'responsable_iit' AND scope_etablissement_id = 'IIT') OR "
            "(role_code = 'responsable_isb' AND scope_etablissement_id = 'ISB') OR "
            "(role_code = 'responsable_isa' AND scope_etablissement_id = 'ISA') OR "
            "(role_code = 'responsable_2i2s' AND scope_etablissement_id = '2I2S') OR "
            "(role_code NOT IN ('responsable_iit', 'responsable_isb', "
            "'responsable_isa', 'responsable_2i2s') AND scope_etablissement_id IS NULL)",
            name="user_roles_scope_chk",
        ),
        Index("ix_user_roles_user", "user_id"),
        Index("ix_user_roles_role", "role_code"),
    )

    user_role_id: Mapped[int] = mapped_column(_SQLITE_BIGINT, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        _SQLITE_BIGINT, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False
    )
    role_code: Mapped[str] = mapped_column(
        String(40), ForeignKey("roles.role_code", ondelete="RESTRICT"), nullable=False
    )
    scope_etablissement_id: Mapped[str | None] = mapped_column(
        String(10), ForeignKey("etablissements.code", ondelete="RESTRICT")
    )
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    assigned_by: Mapped[int | None] = mapped_column(
        _SQLITE_BIGINT, ForeignKey("users.user_id", ondelete="SET NULL")
    )


class UserAuthSessionRow(Base):
    __tablename__ = "user_auth_sessions"
    __table_args__ = (
        Index("ix_user_auth_sessions_user", "user_id"),
        Index("ix_user_auth_sessions_expires", "expires_at"),
    )

    session_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        _SQLITE_BIGINT, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
