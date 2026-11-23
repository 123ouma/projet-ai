"""SA-36 : interface commune pour le LLM de compréhension.

Le backend ne dépend que de cette interface. Remplacer Qwen par une version
fine-tunée (QLoRA) se fait côté service LLM, sans toucher aux routes du backend.
"""
from abc import ABC, abstractmethod

from app.schemas.llm import Language, LLMHealthOut, UnderstandOut


class LLMError(Exception):
    """Erreur générique du LLM."""


class LLMUnavailableError(LLMError):
    """Service injoignable, délai dépassé ou clé non configurée → 503 côté backend."""


class LLMBadResponseError(LLMError):
    """Le service a répondu, mais avec une erreur ou un contenu invalide → 502 côté backend."""


class LLMClient(ABC):
    @abstractmethod
    def understand(
        self, message: str, language: Language, history: list[dict[str, str]] | None = None
    ) -> UnderstandOut:
        """Analyse un message et renvoie intent, budget_dt et online.

        history (SA-37) : messages précédents [{"role": "user"|"assistant", "content": ...}],
        du plus ancien au plus récent. Absent ou vide = requête identique à SA-36.
        """

    @abstractmethod
    def health(self) -> LLMHealthOut:
        """État du service LLM (dont le mode mock)."""
