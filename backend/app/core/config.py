"""Configuration centralisée, lue depuis les variables d'environnement (.env).

Aucun secret n'est écrit en dur : voir .env.example à la racine du projet.
"""
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/core/config.py -> dossier backend/ (qui contient database/)
_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Application
    app_name: str = "SmartCampus AI API"
    environment: str = "development"
    api_prefix: str = "/api/v1"
    cors_origins: list[str] = ["http://localhost:3000"]

    # Base de données (SA-16)
    database_url: str = "postgresql+psycopg://smartcampus:smartcampus@localhost:5432/smartcampus"
    database_echo: bool = False
    migrations_dir: Path = _ROOT / "database" / "migrations"
    seeds_dir: Path = _ROOT / "database" / "seeds"

    # Catalogue (SA-20 / SA-21)
    annee_universitaire_courante: str = "2026-2027"

    # Authentification Bearer (SA-28)
    auth_token_ttl_minutes: int = Field(default=60, gt=0)

    # Mémoire temporaire des conversations (SA-26)
    memory_backend: str = "postgres"  # "postgres" ou "memory"
    memory_ttl_minutes: int = 60  # expiration après inactivité
    memory_max_messages: int = 20  # messages max envoyés au LLM
    memory_max_chars: int = 8000  # taille max du contexte envoyé au LLM
    memory_max_stored: int = 100  # messages max conservés par session
    visitor_session_ttl_minutes: int = Field(default=60, gt=0)  # expiration après inactivité


@lru_cache
def get_settings() -> Settings:
    return Settings()
