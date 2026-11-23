"""Schémas de l'intégration LLM (SA-36).

Ils reprennent le contrat du service LLM d'Oumayma (SA-34, POST /v1/understand).
Si le modèle change (ex. Qwen fine-tuné QLoRA), ce contrat ne change pas.
"""
from typing import Literal

from pydantic import BaseModel, Field

Language = Literal["fr", "en", "arabizi", "tn"]
Intent = Literal["orientation", "information", "registration", "confirm", "reschedule", "cancel", "unclear"]


class UnderstandIn(BaseModel):
    message: str = Field(min_length=1, max_length=3000, description="Message de l'étudiant")
    language: Language = Field(
        default="fr",
        description="Langue du message : fr, en, arabizi ou tn (pas de détection automatique pour l'instant)",
    )


class UnderstandOut(BaseModel):
    """Résultat de la compréhension de la demande (extraction structurée, pas une réponse factuelle)."""

    intent: Intent
    budget_dt: int | None = Field(description="Budget en dinars tunisiens, sinon null")
    online: bool | None = Field(description="Préférence pour une formation en ligne, sinon null")
    normalized_message: str
    language: str
    pipeline_version: str
    model_id: str
    mock: bool = Field(description="true = réponse factice du mode mock, jamais une vraie inférence")


class LLMHealthOut(BaseModel):
    reachable: bool
    status: str | None = None
    model: str | None = None
    mock: bool | None = None


# ---------- SA-37 : dialogue avec historique ----------
class ProfilOut(BaseModel):
    """Profil cumulé sur toute la conversation : une valeur connue n'est pas oubliée
    si le message suivant ne la répète pas (ex. budget donné au premier message)."""

    intent: Intent | None = Field(description="Intention du dernier message")
    budget_dt: int | None = Field(description="Dernier budget connu dans la conversation")
    online: bool | None = Field(description="Dernière préférence en ligne connue")


class ChatOut(BaseModel):
    session_id: str
    understanding: UnderstandOut = Field(description="Ce que le LLM a compris du message actuel")
    profil: ProfilOut
    history_sent: int = Field(description="Nombre de messages précédents envoyés au LLM")
