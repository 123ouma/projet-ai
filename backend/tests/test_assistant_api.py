"""Tests SA-36 des routes /api/v1/assistant (sans GPU ni base de données).

Le client LLM est remplacé par un faux client grâce à dependency_overrides.
    pytest tests/test_assistant_api.py
"""
import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.schemas.llm import LLMHealthOut, UnderstandOut  # noqa: E402
from app.services.llm import LLMBadResponseError, LLMClient, LLMUnavailableError, get_llm_client  # noqa: E402

API = "/api/v1/assistant"


class FakeLLM(LLMClient):
    def __init__(self, erreur: Exception | None = None):
        self.erreur = erreur
        self.appels = []

    def understand(self, message, language):
        self.appels.append((message, language))
        if self.erreur:
            raise self.erreur
        return UnderstandOut(
            intent="cancel" if language == "arabizi" else "orientation",
            budget_dt=None,
            online=None,
            normalized_message=message,
            language=language,
            pipeline_version="test",
            model_id="fake",
            mock=True,
        )

    def health(self):
        return LLMHealthOut(reachable=True, status="ok", model="fake", mock=True)


@pytest.fixture
def client():
    def utiliser(fake: FakeLLM) -> TestClient:
        app.dependency_overrides[get_llm_client] = lambda: fake
        return TestClient(app)

    yield utiliser
    app.dependency_overrides.clear()


def test_understand_ok(client):
    fake = FakeLLM()
    r = client(fake).post(f"{API}/understand", json={"message": "Faskhouli demande préinscription mte3i.", "language": "arabizi"})
    assert r.status_code == 200
    assert r.json()["intent"] == "cancel"
    assert fake.appels == [("Faskhouli demande préinscription mte3i.", "arabizi")]


def test_langue_par_defaut_fr(client):
    fake = FakeLLM()
    client(fake).post(f"{API}/understand", json={"message": "Bonjour"})
    assert fake.appels[0][1] == "fr"


@pytest.mark.parametrize("payload", [{"message": ""}, {"message": "Hi", "language": "de"}, {}])
def test_requete_invalide(client, payload):
    assert client(FakeLLM()).post(f"{API}/understand", json=payload).status_code == 422


def test_llm_indisponible_503(client):
    r = client(FakeLLM(LLMUnavailableError("Le service LLM est injoignable."))).post(f"{API}/understand", json={"message": "Bonjour"})
    assert r.status_code == 503
    assert "indisponible" in r.json()["detail"]


def test_llm_reponse_invalide_502(client):
    r = client(FakeLLM(LLMBadResponseError("Réponse du service LLM invalide."))).post(f"{API}/understand", json={"message": "Bonjour"})
    assert r.status_code == 502


def test_health(client):
    r = client(FakeLLM()).get(f"{API}/health")
    assert r.status_code == 200 and r.json()["mock"] is True
