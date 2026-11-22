"""SA-26 : mémoire temporaire des conversations — interface commune.

Rôle : garder les derniers messages d'une session de chat pour que le LLM
comprenne la suite de la conversation (« et les frais ? » après une question sur une formation).

- Les messages expirent après MEMORY_TTL_MINUTES d'inactivité (fenêtre glissante).
- get_context() renvoie seulement la fin de la conversation, bornée en nombre de
  messages et en caractères, prête à être envoyée au LLM (SA-37, Souhaila).
- Ce module n'importe ni SQLAlchemy ni la configuration : testable seul.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Literal

Role = Literal["user", "assistant", "system"]
ROLES: tuple[str, ...] = ("user", "assistant", "system")


@dataclass(frozen=True)
class MemoryMessage:
    role: Role
    content: str
    created_at: datetime

    def to_llm(self) -> dict[str, str]:
        return {"role": self.role, "content": self.content}


@dataclass(frozen=True)
class MemoryLimits:
    ttl_minutes: int = 60
    max_messages: int = 20
    max_chars: int = 8000
    max_stored: int = 100

    def __post_init__(self) -> None:
        if min(self.ttl_minutes, self.max_messages, self.max_chars, self.max_stored) <= 0:
            raise ValueError("Les limites de la mémoire doivent être strictement positives.")


def trim_context(messages: list[MemoryMessage], max_messages: int, max_chars: int) -> list[MemoryMessage]:
    """Garde les messages les plus récents dans la limite de nombre et de caractères.

    On parcourt depuis la fin et on s'arrête au premier message qui ferait dépasser
    le budget (pas de « trou » dans la conversation). Si le dernier message dépasse
    à lui seul le budget, on garde sa fin.
    """
    selected: list[MemoryMessage] = []
    total = 0
    for msg in reversed(messages[-max_messages:]):
        size = len(msg.content)
        if not selected and size > max_chars:
            selected.append(replace(msg, content=msg.content[-max_chars:]))
            break
        if total + size > max_chars:
            break
        selected.append(msg)
        total += size
    selected.reverse()
    return selected


class ConversationMemory(ABC):
    def __init__(self, limits: MemoryLimits):
        self.limits = limits

    @abstractmethod
    def add(self, session_id: str, role: Role, content: str) -> MemoryMessage:
        """Ajoute un message et prolonge la durée de vie de la session."""

    @abstractmethod
    def history(self, session_id: str) -> list[MemoryMessage]:
        """Tous les messages encore valides de la session, du plus ancien au plus récent."""

    @abstractmethod
    def clear(self, session_id: str) -> int:
        """Efface la mémoire de la session. Renvoie le nombre de messages supprimés."""

    @abstractmethod
    def purge_expired(self) -> int:
        """Supprime toutes les sessions expirées (à appeler par le worker)."""

    def context(self, session_id: str) -> list[MemoryMessage]:
        return trim_context(self.history(session_id), self.limits.max_messages, self.limits.max_chars)

    def context_for_llm(self, session_id: str) -> list[dict[str, str]]:
        return [m.to_llm() for m in self.context(session_id)]

    @staticmethod
    def _validate(role: str, content: str) -> str:
        if role not in ROLES:
            raise ValueError(f"Rôle invalide : {role!r}.")
        content = content.strip()
        if not content:
            raise ValueError("Le message est vide.")
        return content
