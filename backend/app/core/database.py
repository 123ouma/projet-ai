"""Connexion PostgreSQL (SA-16) : moteur SQLAlchemy, sessions et classe de base des modèles."""
from collections.abc import Iterator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings

settings = get_settings()

engine = create_engine(
    settings.database_url,
    echo=settings.database_echo,
    pool_pre_ping=True,  # reconnecte proprement si PostgreSQL a redémarré
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    """Classe mère de tous les modèles ORM."""


def get_db() -> Iterator[Session]:
    """Dépendance FastAPI : une session par requête, toujours refermée."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def check_database() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
