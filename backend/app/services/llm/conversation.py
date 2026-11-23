"""SA-37 : dialogue multi-tours — le LLM reçoit l'historique de la conversation.

Utilise la mémoire temporaire de Marwen (SA-26) :
  1. récupérer la fenêtre de contexte (context_for_llm, bornée en messages et caractères) ;
  2. l'envoyer au LLM avec le nouveau message (champ « history ») ;
  3. enregistrer le message de l'étudiant et la réponse du LLM dans la mémoire ;
  4. calculer le profil cumulé (intention, budget, préférence en ligne).
Si le LLM échoue, rien n'est enregistré : la conversation reste cohérente.
"""
import json

from app.schemas.llm import ChatOut, Language, ProfilOut, UnderstandOut
from app.services.llm.base import LLMClient
from app.services.memory import ConversationMemory, MemoryMessage


def serialiser_reponse(resultat: UnderstandOut) -> str:
    """Texte enregistré comme message « assistant » : compact et relisible par le LLM."""
    return json.dumps(
        {"intent": resultat.intent, "budget_dt": resultat.budget_dt, "online": resultat.online},
        ensure_ascii=False,
    )


def _lire_reponse(message: MemoryMessage) -> dict | None:
    if message.role != "assistant":
        return None
    try:
        data = json.loads(message.content)
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def calculer_profil(historique: list[MemoryMessage], dernier: UnderstandOut) -> ProfilOut:
    """Garde la dernière valeur connue de chaque champ sur toute la conversation."""
    budget, online = None, None
    for message in historique:
        data = _lire_reponse(message)
        if not data:
            continue
        if isinstance(data.get("budget_dt"), int) and not isinstance(data.get("budget_dt"), bool):
            budget = data["budget_dt"]
        if isinstance(data.get("online"), bool):
            online = data["online"]
    if dernier.budget_dt is not None:
        budget = dernier.budget_dt
    if dernier.online is not None:
        online = dernier.online
    return ProfilOut(intent=dernier.intent, budget_dt=budget, online=online)


def tour_de_dialogue(
    llm: LLMClient, memory: ConversationMemory, session_id: str, message: str, language: Language
) -> ChatOut:
    contexte = memory.context_for_llm(session_id)  # messages précédents, bornés (SA-26)
    resultat = llm.understand(message, language, history=contexte)  # peut lever LLMError

    memory.add(session_id, "user", message)
    memory.add(session_id, "assistant", serialiser_reponse(resultat))

    profil = calculer_profil(memory.history(session_id), resultat)
    return ChatOut(session_id=session_id, understanding=resultat, profil=profil, history_sent=len(contexte))
