"""SA-26 : purge des mémoires de conversation expirées.

À lancer périodiquement (cron, ou depuis le worker Python de l'architecture §4.6) :
    python -m app.workers.purge_memory
"""
from app.core.config import get_settings
from app.core.database import SessionLocal
from app.services.memory import _limits
from app.services.memory.postgres import PostgresConversationMemory


def main() -> None:
    if get_settings().memory_backend != "postgres":
        print("MEMORY_BACKEND n'est pas « postgres » : rien à purger.")
        return
    with SessionLocal() as db:
        removed = PostgresConversationMemory(db, _limits()).purge_expired()
    print(f"{removed} message(s) expiré(s) supprimé(s).")


if __name__ == "__main__":
    main()
