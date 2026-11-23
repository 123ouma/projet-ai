"""SA-36 : routes de l'assistant — connexion du backend au LLM.

Le LLM (Qwen3.5-9B, SA-33/SA-34) comprend la demande de l'étudiant et en extrait
intent, budget_dt et online. Il ne donne PAS de réponse factuelle sur les formations :
ce sera le rôle du RAG.
"""
from fastapi import APIRouter, Depends, HTTPException, status

from app.schemas.llm import LLMHealthOut, UnderstandIn, UnderstandOut
from app.services.llm import LLMBadResponseError, LLMClient, LLMUnavailableError, get_llm_client

router = APIRouter(prefix="/assistant", tags=["Assistant LLM (SA-36)"])


@router.post("/understand", response_model=UnderstandOut)
def understand(payload: UnderstandIn, llm: LLMClient = Depends(get_llm_client)):
    """Envoie le message au LLM et renvoie l'intention et les préférences extraites."""
    try:
        return llm.understand(payload.message, payload.language)
    except LLMUnavailableError as exc:
        # SA-4 §7.3 : message explicite, le catalogue reste accessible
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, f"Assistant indisponible : {exc}") from exc
    except LLMBadResponseError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Erreur de l'assistant : {exc}") from exc


@router.get("/health", response_model=LLMHealthOut)
def llm_health(llm: LLMClient = Depends(get_llm_client)):
    """Indique si le service LLM est joignable et s'il tourne en mode mock ou avec le vrai Qwen."""
    return llm.health()
