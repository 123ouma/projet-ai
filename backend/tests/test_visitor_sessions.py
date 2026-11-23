"""Tests API SA-25 et intégration des sessions avec la mémoire SA-26."""
from datetime import UTC, datetime, timedelta
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings
from app.core.database import get_db
from app.core.visitor_session import VISITOR_SESSION_COOKIE, hash_visitor_token
from app.main import app
from app.models.visitor_session import VisitorSessionRow
from app.services.memory import InMemoryConversationMemory, MemoryLimits, get_memory

API = "/api/v1"


@pytest.fixture
def api():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    VisitorSessionRow.__table__.create(engine)
    test_session = sessionmaker(bind=engine, expire_on_commit=False)

    def override_get_db():
        db = test_session()
        try:
            yield db
        finally:
            db.close()

    memory = InMemoryConversationMemory(
        MemoryLimits(ttl_minutes=30, max_messages=20, max_chars=8000, max_stored=100)
    )
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_memory] = lambda: memory
    settings = get_settings()
    previous_ttl = settings.visitor_session_ttl_minutes
    settings.visitor_session_ttl_minutes = 30

    client = TestClient(app)
    yield client, memory, test_session

    client.close()
    app.dependency_overrides.clear()
    settings.visitor_session_ttl_minutes = previous_ttl
    engine.dispose()


def create_session(client: TestClient) -> tuple[str, str]:
    response = client.post(f"{API}/visitor-sessions")
    assert response.status_code == 201, response.text
    session_id = response.json()["session_id"]
    token = client.cookies.get(VISITOR_SESSION_COOKIE)
    assert token
    return session_id, token


def test_create_session_generates_server_uuid_and_sets_only_hashed_secret(api):
    client, _, test_session = api
    requested_id = str(uuid.uuid4())

    response = client.post(f"{API}/visitor-sessions", json={"session_id": requested_id})

    assert response.status_code == 201
    session_id = response.json()["session_id"]
    uuid.UUID(session_id)
    assert session_id != requested_id
    assert VISITOR_SESSION_COOKIE not in response.json()
    cookie = response.headers["set-cookie"]
    assert "httponly" in cookie.lower()
    assert "samesite=lax" in cookie.lower()
    token = client.cookies.get(VISITOR_SESSION_COOKIE)
    assert token and token not in str(response.json())

    with test_session() as db:
        stored = db.get(VisitorSessionRow, uuid.UUID(session_id))
        assert stored is not None
        assert stored.token_hash == hash_visitor_token(token)
        assert len(stored.token_hash) == 64
        assert stored.linked_user_id is None


def test_retrieves_owned_session_and_refreshes_idle_expiration(api):
    client, _, _ = api
    session_id, _ = create_session(client)
    before = client.get(f"{API}/visitor-sessions/{session_id}").json()["expires_at"]

    response = client.get(f"{API}/visitor-sessions/{session_id}")

    assert response.status_code == 200
    assert response.json()["session_id"] == session_id
    assert response.json()["expires_at"] >= before
    assert response.headers["cache-control"] == "no-store"
    assert response.headers.get_list("set-cookie")[-1].startswith(f"{VISITOR_SESSION_COOKIE}=")


def test_creating_another_session_preserves_previous_history_and_owner(api):
    client, memory, test_session = api
    previous_id, previous_token = create_session(client)
    memory.add(previous_id, "user", "history from the previous session")

    new_id, _ = create_session(client)

    assert new_id != previous_id
    assert [message.content for message in memory.history(previous_id)] == [
        "history from the previous session"
    ]
    with test_session() as db:
        previous = db.get(VisitorSessionRow, uuid.UUID(previous_id))
        assert previous is not None
        assert previous.ended_at is None

    previous_owner = TestClient(app)
    previous_owner.cookies.set(VISITOR_SESSION_COOKIE, previous_token)
    response = previous_owner.get(f"{API}/visitor-sessions/{previous_id}")
    assert response.status_code == 200
    previous_owner.close()


def test_missing_invalid_and_nonexistent_session_responses(api):
    client, _, _ = api
    session_id = str(uuid.uuid4())

    assert client.get(f"{API}/visitor-sessions/{session_id}").status_code == 401
    assert client.get(
        f"{API}/visitor-sessions/{session_id}",
        headers={"Cookie": f"{VISITOR_SESSION_COOKIE}=invalid"},
    ).status_code == 401

    create_session(client)
    assert client.get(f"{API}/visitor-sessions/{session_id}").status_code == 404


def test_expired_session_is_gone_and_its_conversation_is_cleared(api):
    client, memory, test_session = api
    session_id, _ = create_session(client)
    memory.add(session_id, "user", "question conservée avant expiration")

    with test_session() as db:
        row = db.get(VisitorSessionRow, uuid.UUID(session_id))
        row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        db.commit()

    response = client.get(f"{API}/visitor-sessions/{session_id}")

    assert response.status_code == 410
    assert memory.history(session_id) == []
    assert client.get(f"{API}/conversations/{session_id}/messages").status_code == 410


def test_ending_session_clears_memory_and_revokes_access(api):
    client, memory, _ = api
    session_id, token = create_session(client)
    response = client.post(
        f"{API}/conversations/{session_id}/messages",
        json={"role": "user", "content": "message to clear when closed"},
    )
    assert response.status_code == 201

    response = client.delete(f"{API}/visitor-sessions/{session_id}")

    assert response.status_code == 204
    deleted_cookie = response.headers.get_list("set-cookie")[-1].lower()
    assert deleted_cookie.startswith(f"{VISITOR_SESSION_COOKIE}=")
    assert "max-age=0" in deleted_cookie
    assert memory.history(session_id) == []
    closed = TestClient(app)
    assert closed.get(
        f"{API}/visitor-sessions/{session_id}",
        headers={"Cookie": f"{VISITOR_SESSION_COOKIE}={token}"},
    ).status_code == 410
    closed.close()


def test_sessions_and_conversation_history_are_isolated_between_visitors(api):
    first_client, _, _ = api
    second_client = TestClient(app)
    first_id, _ = create_session(first_client)
    second_id, _ = create_session(second_client)

    assert first_client.post(
        f"{API}/conversations/{first_id}/messages",
        json={"role": "user", "content": "question privée A"},
    ).status_code == 201
    assert second_client.post(
        f"{API}/conversations/{second_id}/messages",
        json={"role": "user", "content": "question privée B"},
    ).status_code == 201
    assert first_client.get(f"{API}/visitor-sessions/{second_id}").status_code == 403
    assert first_client.get(f"{API}/conversations/{second_id}/messages").status_code == 403
    assert second_client.get(f"{API}/conversations/{second_id}/messages").json()["messages"][0]["content"] == (
        "question privée B"
    )
    assert first_client.get(f"{API}/conversations/{first_id}/messages").json()["messages"][0]["content"] == (
        "question privée A"
    )
    second_client.close()


def test_sa26_routes_keep_their_contract_but_require_an_owned_session(api):
    client, _, _ = api
    session_id = str(uuid.uuid4())
    base = f"{API}/conversations/{session_id}"
    assert client.post(
        f"{base}/messages",
        json={"role": "user", "content": "sans session"},
    ).status_code == 401

    session_id, _ = create_session(client)
    base = f"{API}/conversations/{session_id}"
    assert client.post(
        f"{base}/messages",
        json={"role": "user", "content": "question"},
    ).status_code == 201
    assert client.post(
        f"{base}/messages",
        json={"role": "assistant", "content": "réponse"},
    ).status_code == 201
    history = client.get(f"{base}/messages")
    assert history.status_code == 200
    assert history.json()["count"] == 2
    assert client.get(f"{base}/context").json()["count"] == 2
    assert client.delete(base).status_code == 204
    assert client.get(f"{base}/messages").json()["count"] == 0
    assert client.get(f"{API}/conversations/pas-un-uuid/messages").status_code == 422


def test_openapi_documents_session_access_errors_for_conversations(api):
    schema = app.openapi()
    expected = {"401", "403", "404", "410"}

    for path in (
        f"{API}/conversations/{{session_id}}/messages",
        f"{API}/conversations/{{session_id}}/context",
        f"{API}/conversations/{{session_id}}",
    ):
        for operation in schema["paths"][path].values():
            assert expected.issubset(operation["responses"])
