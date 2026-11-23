"""SA-36 : connexion du backend au service LLM de compréhension.

Utilisation dans une route :

    from app.services.llm import LLMClient, get_llm_client
    def route(llm: LLMClient = Depends(get_llm_client)):
        resultat = llm.understand("Nheb orientation fi IA", "arabizi")
        resultat.intent, resultat.budget_dt, resultat.online
"""
from functools import lru_cache

from app.services.llm.base import LLMBadResponseError, LLMClient, LLMError, LLMUnavailableError
from app.services.llm.http_client import HttpLLMClient

__all__ = [
    "HttpLLMClient",
    "LLMBadResponseError",
    "LLMClient",
    "LLMError",
    "LLMUnavailableError",
    "get_llm_client",
]


@lru_cache
def get_llm_client() -> LLMClient:
    """Dépendance FastAPI : un seul client HTTP réutilisé (connexions gardées ouvertes)."""
    from app.core.config import get_settings

    s = get_settings()
    return HttpLLMClient(s.llm_api_url, s.llm_api_key, s.llm_timeout_seconds)
