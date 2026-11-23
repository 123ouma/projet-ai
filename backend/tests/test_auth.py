"""Tests locaux d'authentification SA-28 sans PostgreSQL."""
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import app
from app.models import Etablissement, Formation, ProgrammeModule
from app.models.auth import RoleRow, UserAuthSessionRow, UserRoleRow, UserRow
from app.services.passwords import verify_password


@pytest.fixture
def client():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        engine,
        tables=[
            Etablissement.__table__,
            RoleRow.__table__,
            UserRow.__table__,
            UserRoleRow.__table__,
            UserAuthSessionRow.__table__,
            Formation.__table__,
            ProgrammeModule.__table__,
        ],
    )
    test_sessions = sessionmaker(bind=engine, expire_on_commit=False)
    with test_sessions() as db:
        db.add_all(
            [
                Etablissement(id=1, code="IIT", nom="IIT"),
                Etablissement(id=2, code="ISB", nom="ISB"),
            ]
        )
        db.add_all(
            [
                RoleRow(role_code="candidat", label="Candidat", scope="global"),
                RoleRow(role_code="responsable_iit", label="Responsable IIT", scope="establishment"),
                RoleRow(role_code="responsable_isb", label="Responsable ISB", scope="establishment"),
                RoleRow(role_code="administrateur", label="Administrateur", scope="global"),
            ]
        )
        db.commit()

    def override_get_db():
        with test_sessions() as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client, test_sessions
    app.dependency_overrides.pop(get_db, None)
    engine.dispose()


def register(client: TestClient, email: str | None = None) -> dict:
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": email or f"{uuid4().hex}@example.test",
            "password": "un-mot-de-passe-solide",
            "full_name": "Étudiant test",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_registration_hashes_password_and_only_grants_candidate(client):
    test_client, test_sessions = client
    account = register(test_client, "Student@Example.test")
    assert account["user"]["email"] == "student@example.test"
    assert [role["role_code"] for role in account["user"]["roles"]] == ["candidat"]
    assert test_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {account['access_token']}"},
    ).status_code == 200

    with test_sessions() as db:
        user = db.scalar(select(UserRow).where(UserRow.email == "student@example.test"))
        stored_session = db.scalar(select(UserAuthSessionRow))
        assert user is not None
        assert user.password_hash.startswith("$argon2id$")
        assert verify_password("un-mot-de-passe-solide", user.password_hash)
        assert stored_session is not None
        assert stored_session.token_hash != account["access_token"]

    assert test_client.post(
        "/api/v1/auth/register",
        json={
            "email": "privileged@example.test",
            "password": "un-mot-de-passe-solide",
            "role_code": "administrateur",
        },
    ).status_code == 422


def test_login_logout_and_invalid_credentials(client):
    test_client, _ = client
    email = f"{uuid4().hex}@example.test"
    register(test_client, email)
    assert test_client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "mauvais-mot-de-passe"},
    ).status_code == 401

    login = test_client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "un-mot-de-passe-solide"},
    )
    assert login.status_code == 200
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    assert test_client.post("/api/v1/auth/logout", headers=headers).status_code == 204
    assert test_client.get("/api/v1/auth/me", headers=headers).status_code == 401


def test_missing_or_malformed_bearer_token_is_rejected(client):
    test_client, _ = client
    assert test_client.get("/api/v1/auth/me").status_code == 401
    invalid = test_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer not-a-valid-token"},
    )
    assert invalid.status_code == 401
    assert invalid.headers["www-authenticate"] == "Bearer"


def test_expired_bearer_token_is_rejected(client):
    test_client, test_sessions = client
    account = register(test_client)
    with test_sessions() as db:
        auth_session = db.scalar(select(UserAuthSessionRow))
        assert auth_session is not None
        auth_session.expires_at = datetime.now(UTC) - timedelta(minutes=1)
        db.commit()

    response = test_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {account['access_token']}"},
    )
    assert response.status_code == 401


def test_responsible_role_is_limited_to_its_establishment(client):
    test_client, test_sessions = client
    account = register(test_client)
    headers = {"Authorization": f"Bearer {account['access_token']}"}
    payload = {
        "etablissement_code": "IIT",
        "code": "TEST-IIT",
        "intitule": "Formation de test",
        "niveau": "licence",
        "duree_annees": 3,
    }
    assert test_client.post("/api/v1/formations", json=payload, headers=headers).status_code == 403

    with test_sessions() as db:
        db.add(
            UserRoleRow(
                user_id=account["user"]["user_id"],
                role_code="responsable_iit",
                scope_etablissement_id="IIT",
            )
        )
        db.commit()
    allowed = test_client.post("/api/v1/formations", json=payload, headers=headers)
    assert allowed.status_code == 201, allowed.text
    payload["etablissement_code"] = "ISB"
    denied = test_client.post("/api/v1/formations", json=payload, headers=headers)
    assert denied.status_code == 403
