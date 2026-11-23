"""Tests SA-36 : connexion backend ↔ service LLM, sans GPU ni base de données.

Le service LLM est simulé avec httpx.MockTransport : on vérifie l'envoi de la clé,
le format de la requête, la lecture du JSON et la gestion des erreurs.
    pytest tests/test_llm.py
"""
import httpx
import pytest

from app.services.llm import HttpLLMClient, LLMBadResponseError, LLMUnavailableError

KEY = "cle-de-test"


def reponse_llm(intent="orientation", budget=None, online=None, language="fr", mock=False):
    return {
        "intent": intent,
        "budget_dt": budget,
        "online": online,
        "normalized_message": "message",
        "language": language,
        "pipeline_version": "SA34-V3-normalization-V4-prompt" if language == "arabizi" else "SA34-raw-baseline-prompt",
        "model_id": "Qwen/Qwen3.5-9B",
        "mock": mock,
    }


def client_avec(handler, api_key=KEY):
    return HttpLLMClient("http://llm.test", api_key, transport=httpx.MockTransport(handler))


@pytest.mark.parametrize(
    ("language", "message", "attendu"),
    [
        ("fr", "Je veux une formation en IA à distance, budget 5000 dinars", reponse_llm("orientation", 5000, True, "fr")),
        ("en", "I want to register in computer science", reponse_llm("registration", None, None, "en")),
        ("arabizi", "Faskhouli demande préinscription mte3i.", reponse_llm("cancel", None, None, "arabizi")),
    ],
)
def test_understand_trois_langues(language, message, attendu):
    recu = {}

    def handler(request: httpx.Request):
        recu["url"] = str(request.url)
        recu["cle"] = request.headers.get("X-API-Key")
        recu["json"] = httpx.Response(200, content=request.content).json()
        return httpx.Response(200, json=attendu)

    resultat = client_avec(handler).understand(message, language)

    assert recu["url"] == "http://llm.test/v1/understand"
    assert recu["cle"] == KEY
    assert recu["json"] == {"message": message, "language": language}
    assert resultat.intent == attendu["intent"]
    assert resultat.budget_dt == attendu["budget_dt"]
    assert resultat.online == attendu["online"]
    assert resultat.mock is False


def test_mode_mock_signale():
    client = client_avec(lambda r: httpx.Response(200, json=reponse_llm("unclear", mock=True)))
    assert client.understand("Bonjour", "fr").mock is True


def test_cle_absente_dans_le_backend():
    client = client_avec(lambda r: httpx.Response(200, json=reponse_llm()), api_key=None)
    with pytest.raises(LLMUnavailableError):
        client.understand("Bonjour", "fr")


def test_service_injoignable():
    def handler(request):
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(LLMUnavailableError):
        client_avec(handler).understand("Bonjour", "fr")


def test_delai_depasse():
    def handler(request):
        raise httpx.ReadTimeout("timeout", request=request)

    with pytest.raises(LLMUnavailableError):
        client_avec(handler).understand("Bonjour", "fr")


def test_cle_refusee():
    client = client_avec(lambda r: httpx.Response(401, json={"detail": "Invalid API key"}))
    with pytest.raises(LLMBadResponseError):
        client.understand("Bonjour", "fr")


def test_inference_echouee():
    client = client_avec(lambda r: httpx.Response(502, json={"detail": "LLM inference failed"}))
    with pytest.raises(LLMBadResponseError):
        client.understand("Bonjour", "fr")


@pytest.mark.parametrize(
    "contenu",
    [
        {"intent": "inconnue", "budget_dt": None, "online": None},  # intention hors liste + champs manquants
        {**reponse_llm(), "budget_dt": "beaucoup"},  # budget non entier
    ],
)
def test_reponse_invalide(contenu):
    client = client_avec(lambda r: httpx.Response(200, json=contenu))
    with pytest.raises(LLMBadResponseError):
        client.understand("Bonjour", "fr")


def test_reponse_non_json():
    client = client_avec(lambda r: httpx.Response(200, text="pas du json"))
    with pytest.raises(LLMBadResponseError):
        client.understand("Bonjour", "fr")


def test_health():
    def handler(request):
        assert request.url.path == "/health"
        return httpx.Response(200, json={"status": "ok", "model": "Qwen/Qwen3.5-9B", "mock": True})

    sante = client_avec(handler).health()
    assert sante.reachable is True and sante.mock is True


def test_health_injoignable():
    def handler(request):
        raise httpx.ConnectError("refused", request=request)

    assert client_avec(handler).health().reachable is False


# ---------- SA-37 : champ history ----------
def test_history_envoye_si_present():
    recu = {}

    def handler(request):
        recu["json"] = httpx.Response(200, content=request.content).json()
        return httpx.Response(200, json=reponse_llm("confirm"))

    historique = [
        {"role": "user", "content": "Nheb préinscription fi licence info"},
        {"role": "assistant", "content": '{"intent": "registration", "budget_dt": null, "online": null}'},
    ]
    client_avec(handler).understand("Ey nconfirmi", "arabizi", history=historique)
    assert recu["json"] == {"message": "Ey nconfirmi", "language": "arabizi", "history": historique}


@pytest.mark.parametrize("historique", [None, []])
def test_history_absent_requete_identique_sa36(historique):
    recu = {}

    def handler(request):
        recu["json"] = httpx.Response(200, content=request.content).json()
        return httpx.Response(200, json=reponse_llm())

    client_avec(handler).understand("Bonjour", "fr", history=historique)
    assert recu["json"] == {"message": "Bonjour", "language": "fr"}  # pas de clé history
