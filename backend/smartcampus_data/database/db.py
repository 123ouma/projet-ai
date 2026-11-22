"""Connexion PostgreSQL configurée exclusivement via variables d'environnement / .env.

Aucun mot de passe n'est écrit dans le code. Le mot de passe, s'il est nécessaire,
provient de DATABASE_URL (ou DATABASE_URL_ADMIN pour la création de la base).
"""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

try:  # psycopg 3 est la dépendance attendue (psycopg[binary]).
    import psycopg
    from psycopg.rows import dict_row
except ImportError as exc:  # pragma: no cover - message explicite si dépendance absente
    raise RuntimeError(
        "Le pilote psycopg 3 est requis : pip install 'psycopg[binary]' python-dotenv"
    ) from exc


class ConfigError(RuntimeError):
    """Levée quand la configuration de connexion est absente ou invalide."""


def project_root() -> Path:
    """Racine du projet (dossier contenant database/, scripts/, data/)."""
    return Path(__file__).resolve().parent.parent


def _parse_dotenv(path: Path) -> dict[str, str]:
    """Analyse minimaliste KEY=VALUE, utilisée si python-dotenv est absent."""
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            values[key] = value
    return values


def load_env(env_path: Path | None = None) -> Path:
    """Charge le .env dans os.environ sans écraser les variables déjà définies.

    Les variables d'environnement du processus restent prioritaires : cela permet
    d'utiliser un cluster temporaire en CI sans modifier le .env du projet.
    """
    path = env_path or (project_root() / ".env")
    try:
        from dotenv import load_dotenv
    except ImportError:
        for key, value in _parse_dotenv(path).items():
            os.environ.setdefault(key, value)
    else:
        load_dotenv(dotenv_path=path, override=False)
    return path


def get_database_url(*, admin: bool = False) -> str:
    """Retourne DATABASE_URL, ou DATABASE_URL_ADMIN pour la base de maintenance.

    Si DATABASE_URL_ADMIN n'est pas définie et que admin=True, l'URL est dérivée
    en remplaçant uniquement le nom de base par « postgres ». Le mot de passe
    reste exactement le même et n'est jamais écrit dans le code.
    """
    load_env()
    if admin:
        explicit = os.environ.get("DATABASE_URL_ADMIN")
        if explicit:
            return explicit
        raw = os.environ.get("DATABASE_URL")
        if not raw:
            raise ConfigError(
                "DATABASE_URL est absente. Copiez .env.example vers .env et renseignez-la, "
                "ou définissez la variable d'environnement."
            )
        parts = urlsplit(raw)
        if parts.scheme not in {"postgresql", "postgres"}:
            raise ConfigError(f"Schéma d'URL PostgreSQL invalide : {parts.scheme!r}")
        return urlunsplit((parts.scheme, parts.netloc, "/postgres", "", ""))

    raw = os.environ.get("DATABASE_URL")
    if not raw:
        raise ConfigError(
            "DATABASE_URL est absente. Copiez .env.example vers .env et renseignez-la, "
            "ou définissez la variable d'environnement."
        )
    parts = urlsplit(raw)
    if parts.scheme not in {"postgresql", "postgres"}:
        raise ConfigError(f"Schéma d'URL PostgreSQL invalide : {parts.scheme!r}")
    if not parts.path.lstrip("/"):
        raise ConfigError("DATABASE_URL doit contenir un nom de base de données.")
    return raw


def database_name(url: str | None = None) -> str:
    """Extrait le nom de base d'une URL PostgreSQL (à des fins d'affichage)."""
    return urlsplit(url or get_database_url()).path.lstrip("/")


def connect(url: str | None = None, *, autocommit: bool = False):
    """Ouvre une connexion psycopg 3 avec des lignes sous forme de dictionnaires."""
    return psycopg.connect(url or get_database_url(), autocommit=autocommit, row_factory=dict_row)


def execute_sql_file(conn, path: Path) -> None:
    """Exécute un fichier SQL UTF-8 complet (BEGIN/COMMIT inclus dans le fichier)."""
    sql = Path(path).read_text(encoding="utf-8-sig")
    if not sql.strip():
        raise ValueError(f"Fichier SQL vide : {path}")
    with conn.cursor() as cur:
        cur.execute(sql)
