"""Tests de rattachement des sessions visiteurs à un compte (SA-29)."""
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.core.visitor_session import VISITOR_SESSION_COOKIE
from app.main import app
from app.models import Etablissement
from app.models.auth import RoleRow, UserAuthSessionRow, UserRoleRow, UserRow
from app.models.visitor_session import VisitorSessionRow
from app.services.memory import InMemoryConversationMemory, MemoryLimits, get_memory


@pytest.fixture
def api():
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
            VisitorSessionRow.__table__,
        ],
    )
    test_sessions = sessionmaker(bind=engine, expire_on_commit=False)
    with test_sessions() as db:
        db.add_all(
            [
                Etablissement(id=1, code="IIT", nom="IIT"),
                RoleRow(role_code="candidat", label="Candidat", scope="global"),
            ]
        )
        db.commit()
    memory = InMemoryConversationMemory(MemoryLimits())

    def override_get_db():
        with test_sessions() as db:
            yield db

    def override_get_memory():
        yield memory

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_memory] = override_get_memory
    with TestClient(app) as client:
        yield client, test_sessions, memory
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_memory, None)
    engine.dispose()


def register(client: TestClient, email: str | None = None) -> tuple[int, str]:
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": email or f"{uuid4().hex}@example.test",
            "password": "un-mot-de-passe-solide",
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    return body["user"]["user_id"], body["access_token"]


def create_visitor_session(client: TestClient) -> UUID:
    response = client.post("/api/v1/visitor-sessions")
    assert response.status_code == 201, response.text
    return UUID(response.json()["session_id"])


def test_claim_preserves_history_and_allows_owner_bearer_access(api):
    client, test_sessions, memory = api
    session_id = create_visitor_session(client)
    base = f"/api/v1/conversations/{session_id}"
    assert client.post(
        f"{base}/messages",
        json={"role": "user", "content": "Ma conversation avant connexion"},
    ).status_code == 201
    user_id, token = register(client)
    headers = {"Authorization": f"Bearer {token}"}

    claim = client.post(f"/api/v1/visitor-sessions/{session_id}/claim", headers=headers)
    assert claim.status_code == 200, claim.text
    assert client.post(f"/api/v1/visitor-sessions/{session_id}/claim", headers=headers).status_code == 200
    with test_sessions() as db:
        visitor_session = db.get(VisitorSessionRow, session_id)
        assert visitor_session is not None
        assert visitor_session.linked_user_id == user_id

    client.cookies.clear()
    history = client.get(f"{base}/messages", headers=headers)
    assert history.status_code == 200, history.text
    assert history.json()["count"] == 1
    assert history.json()["messages"][0]["content"] == "Ma conversation avant connexion"
    assert memory.history(str(session_id))[0].content == "Ma conversation avant connexion"
    assert client.get(f"{base}/messages").status_code == 401


def test_claim_requires_the_visitors_own_cookie(api):
    client, _, _ = api
    session_id = create_visitor_session(client)
    _, token = register(client)
    headers = {"Authorization": f"Bearer {token}"}

    stranger = TestClient(app)
    try:
        assert stranger.post(
            f"/api/v1/visitor-sessions/{session_id}/claim",
            headers=headers,
        ).status_code == 401
        # A well-formed but unrelated cookie must not be accepted as proof of ownership.
        stranger.cookies.set(VISITOR_SESSION_COOKIE, "B" * 43)
        assert stranger.post(
            f"/api/v1/visitor-sessions/{session_id}/claim",
            headers=headers,
        ).status_code == 403
    finally:
        stranger.close()


def test_claim_conflict_does_not_transfer_another_accounts_session(api):
    client, test_sessions, _ = api
    session_id = create_visitor_session(client)
    owner_id, owner_token = register(client)
    url = f"/api/v1/visitor-sessions/{session_id}/claim"
    assert client.post(url, headers={"Authorization": f"Bearer {owner_token}"}).status_code == 200

    _, other_token = register(client)
    conflict = client.post(url, headers={"Authorization": f"Bearer {other_token}"})
    assert conflict.status_code == 409
    with test_sessions() as db:
        visitor_session = db.get(VisitorSessionRow, session_id)
        assert visitor_session is not None
        assert visitor_session.linked_user_id == owner_id


def test_logout_and_another_account_cannot_access_linked_session(api):
    client, _, _ = api
    session_id = create_visitor_session(client)
    _, token = register(client)
    headers = {"Authorization": f"Bearer {token}"}
    claim_url = f"/api/v1/visitor-sessions/{session_id}/claim"
    base = f"/api/v1/conversations/{session_id}"
    assert client.post(claim_url, headers=headers).status_code == 200

    assert client.post("/api/v1/auth/logout", headers=headers).status_code == 204
    assert client.get(f"{base}/messages", headers=headers).status_code == 401
    assert client.get(f"{base}/messages").status_code == 401

    _, fresh_token = register(client)
    fresh_headers = {"Authorization": f"Bearer {fresh_token}"}
    # The second account cannot use the already-linked visitor session.
    assert client.get(f"{base}/messages", headers=fresh_headers).status_code == 403


def test_expired_linked_session_cannot_be_accessed(api):
    client, test_sessions, _ = api
    session_id = create_visitor_session(client)
    user_id, token = register(client)
    headers = {"Authorization": f"Bearer {token}"}
    url = f"/api/v1/visitor-sessions/{session_id}/claim"
    assert client.post(url, headers=headers).status_code == 200
    with test_sessions() as db:
        visitor_session = db.get(VisitorSessionRow, session_id)
        assert visitor_session is not None
        visitor_session.expires_at = datetime.now(UTC) - timedelta(minutes=1)
        db.commit()

    response = client.get(f"/api/v1/conversations/{session_id}/messages", headers=headers)
    assert response.status_code == 410
