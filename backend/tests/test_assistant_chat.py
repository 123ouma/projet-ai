"""Tests SA-37 : dialogue multi-tours avec historique (sans GPU ni base de données).

LLM simulé + mémoire en RAM (SA-26).
    pytest tests/test_assistant_chat.py
"""
import uuid

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.schemas.llm import LLMHealthOut, UnderstandOut  # noqa: E402
from app.services.llm import LLMClient, LLMUnavailableError, get_llm_client  # noqa: E402
from app.services.memory import InMemoryConversationMemory, MemoryLimits, get_memory  # noqa: E402

API = "/api/v1/assistant/chat"


class ScriptedLLM(LLMClient):
    """Renvoie les réponses prévues dans l'ordre et garde les historiques reçus."""

    def __init__(self, reponses):
        self.reponses = list(reponses)
        self.historiques = []
        self.erreur = None

    def understand(self, message, language, history=None):
        if self.erreur:
            raise self.erreur
        self.historiques.append(history or [])
        intent, budget, online = self.reponses.pop(0)
        return UnderstandOut(
            intent=intent, budget_dt=budget, online=online, normalized_message=message,
            language=language, pipeline_version="test", model_id="fake", mock=True,
        )

    def health(self):
        return LLMHealthOut(reachable=True)


@pytest.fixture
def env():
    memoire = InMemoryConversationMemory(MemoryLimits())

    def installer(llm):
        app.dependency_overrides[get_llm_client] = lambda: llm
        app.dependency_overrides[get_memory] = lambda: memoire
        return TestClient(app)

    yield installer, memoire
    app.dependency_overrides.clear()


def test_premier_message_sans_historique(env):
    installer, _ = env
    llm = ScriptedLLM([("orientation", 4000, None)])
    sid = uuid.uuid4()
    r = installer(llm).post(f"{API}/{sid}", json={"message": "Nheb orientation fi IA, budget 4000 dt", "language": "arabizi"})
    assert r.status_code == 200
    body = r.json()
    assert body["history_sent"] == 0
    assert body["understanding"]["intent"] == "orientation"
    assert body["profil"] == {"intent": "orientation", "budget_dt": 4000, "online": None}
    assert llm.historiques == [[]]


def test_deuxieme_message_recoit_historique_et_profil_cumule(env):
    installer, _ = env
    llm = ScriptedLLM([("orientation", 4000, None), ("information", None, True)])
    client = installer(llm)
    sid = uuid.uuid4()
    client.post(f"{API}/{sid}", json={"message": "Nheb orientation fi IA, budget 4000 dt", "language": "arabizi"})
    r = client.post(f"{API}/{sid}", json={"message": "w online?", "language": "arabizi"})

    body = r.json()
    assert body["history_sent"] == 2
    # le LLM a reçu le message précédent de l'étudiant et sa propre réponse
    assert llm.historiques[1][0] == {"role": "user", "content": "Nheb orientation fi IA, budget 4000 dt"}
    assert llm.historiques[1][1]["role"] == "assistant"
    assert '"budget_dt": 4000' in llm.historiques[1][1]["content"]
    # le budget du 1er message n'est pas oublié, la préférence en ligne s'ajoute
    assert body["profil"] == {"intent": "information", "budget_dt": 4000, "online": True}


def test_sessions_separees(env):
    installer, _ = env
    llm = ScriptedLLM([("orientation", 4000, None), ("orientation", None, None)])
    client = installer(llm)
    client.post(f"{API}/{uuid.uuid4()}", json={"message": "budget 4000", "language": "fr"})
    r = client.post(f"{API}/{uuid.uuid4()}", json={"message": "bonjour", "language": "fr"})
    assert r.json()["history_sent"] == 0
    assert r.json()["profil"]["budget_dt"] is None


def test_erreur_llm_rien_enregistre(env):
    installer, memoire = env
    llm = ScriptedLLM([])
    llm.erreur = LLMUnavailableError("Le service LLM est injoignable.")
    sid = uuid.uuid4()
    r = installer(llm).post(f"{API}/{sid}", json={"message": "Bonjour", "language": "fr"})
    assert r.status_code == 503
    assert memoire.history(str(sid)) == []


def test_session_id_invalide(env):
    installer, _ = env
    r = installer(ScriptedLLM([])).post(f"{API}/pas-un-uuid", json={"message": "Bonjour"})
    assert r.status_code == 422


def test_historique_visible_dans_la_memoire_sa26(env):
    installer, _ = env
    client = installer(ScriptedLLM([("confirm", None, None)]))
    sid = uuid.uuid4()
    client.post(f"{API}/{sid}", json={"message": "Ey nconfirmi", "language": "arabizi"})
    r = client.get(f"/api/v1/conversations/{sid}/messages")
    assert r.status_code == 200
    assert [m["role"] for m in r.json()["messages"]] == ["user", "assistant"]
