"""SA-26 : routes de la mémoire temporaire des conversations.

session_id = identifiant (UUID) de la session visiteur créée par SA-25 (Fares).
TODO SA-25/SA-29 : vérifier que la session appartient bien à l'appelant
(cookie/jeton de session) avant de lire ou d'écrire.
"""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.core.visitor_session import require_visitor_session
from app.models.visitor_session import VisitorSessionRow
from app.schemas.conversation import ConversationMemoryOut, MessageIn, MessageOut
from app.services.memory import ConversationMemory, get_memory

router = APIRouter(prefix="/conversations", tags=["Mémoire des conversations (SA-26)"])

_SESSION_ACCESS_RESPONSES = {
    401: {"description": "Cookie de session absent ou invalide."},
    403: {"description": "La session appartient à un autre visiteur."},
    404: {"description": "Session inexistante."},
    410: {"description": "Session expirée ou terminée."},
}

@router.post(
    "/{session_id}/messages",
    response_model=MessageOut,
    status_code=status.HTTP_201_CREATED,
    responses=_SESSION_ACCESS_RESPONSES,
)
def add_message(
    session_id: UUID,
    payload: MessageIn,
    memory: ConversationMemory = Depends(get_memory),
    _: VisitorSessionRow = Depends(require_visitor_session),
):
    try:
        return memory.add(str(session_id), payload.role, payload.content)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc


@router.get(
    "/{session_id}/messages",
    response_model=ConversationMemoryOut,
    responses=_SESSION_ACCESS_RESPONSES,
)
def get_history(
    session_id: UUID,
    memory: ConversationMemory = Depends(get_memory),
    _: VisitorSessionRow = Depends(require_visitor_session),
):
    """Historique complet encore en mémoire (affichage du chat)."""
    messages = memory.history(str(session_id))
    return ConversationMemoryOut(session_id=str(session_id), count=len(messages), messages=messages)


@router.get(
    "/{session_id}/context",
    response_model=ConversationMemoryOut,
    responses=_SESSION_ACCESS_RESPONSES,
)
def get_context(
    session_id: UUID,
    memory: ConversationMemory = Depends(get_memory),
    _: VisitorSessionRow = Depends(require_visitor_session),
):
    """Fenêtre réduite à envoyer au LLM (bornée en messages et en caractères)."""
    messages = memory.context(str(session_id))
    return ConversationMemoryOut(session_id=str(session_id), count=len(messages), messages=messages)


@router.delete(
    "/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=_SESSION_ACCESS_RESPONSES,
)
def clear_memory(
    session_id: UUID,
    response: Response,
    memory: ConversationMemory = Depends(get_memory),
    _: VisitorSessionRow = Depends(require_visitor_session),
):
    """« Nouvelle conversation » : efface la mémoire de la session."""
    memory.clear(str(session_id))
    response.status_code = status.HTTP_204_NO_CONTENT
    return response
