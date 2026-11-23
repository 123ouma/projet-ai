"""SA-36 : client HTTP vers le service LLM d'Oumayma (POST /v1/understand, en-tête X-API-Key)."""
import logging

import httpx
from pydantic import ValidationError

from app.schemas.llm import Language, LLMHealthOut, UnderstandOut
from app.services.llm.base import LLMBadResponseError, LLMClient, LLMUnavailableError

logger = logging.getLogger("smartcampus.llm")


class HttpLLMClient(LLMClient):
    def __init__(
        self,
        base_url: str,
        api_key: str | None,
        timeout: float = 120.0,
        transport: httpx.BaseTransport | None = None,  # injecté dans les tests
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self._client = httpx.Client(base_url=self.base_url, timeout=timeout, transport=transport)

    def understand(
        self, message: str, language: Language, history: list[dict[str, str]] | None = None
    ) -> UnderstandOut:
        if not self.api_key:
            raise LLMUnavailableError("LLM_API_KEY n'est pas configurée dans le backend.")
        payload: dict = {"message": message, "language": language}
        if history:  # SA-37 : champ optionnel, omis si vide pour garder la requête SA-36 inchangée
            payload["history"] = history
        try:
            response = self._client.post(
                "/v1/understand",
                json=payload,
                headers={"X-API-Key": self.api_key},
            )
        except httpx.TimeoutException as exc:
            raise LLMUnavailableError("Le service LLM n'a pas répondu à temps.") from exc
        except httpx.HTTPError as exc:
            raise LLMUnavailableError("Le service LLM est injoignable.") from exc

        if response.status_code in (401, 403):
            # Ne jamais journaliser la clé elle-même
            logger.error("Clé X-API-Key refusée par le service LLM (HTTP %s).", response.status_code)
            raise LLMBadResponseError("Le service LLM refuse la clé API du backend.")
        if response.status_code == 503:
            raise LLMUnavailableError("Le service LLM n'est pas prêt.")
        if response.status_code >= 400:
            logger.warning("Le service LLM a répondu HTTP %s.", response.status_code)
            raise LLMBadResponseError("Le service LLM n'a pas pu analyser le message.")

        try:
            return UnderstandOut.model_validate(response.json())
        except (ValueError, ValidationError) as exc:
            raise LLMBadResponseError("Réponse du service LLM invalide.") from exc

    def health(self) -> LLMHealthOut:
        try:
            response = self._client.get("/health", timeout=5.0)
            response.raise_for_status()
            data = response.json()
        except (httpx.HTTPError, ValueError):
            return LLMHealthOut(reachable=False)
        return LLMHealthOut(reachable=True, status=data.get("status"), model=data.get("model"), mock=data.get("mock"))
