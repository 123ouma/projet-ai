"""Fixtures partagées pour les tests PostgreSQL.

Les tests nécessitent une base dédiée définie par DATABASE_URL_TEST.
Sans cette variable, les tests SQL sont ignorés (les tests unitaires restent exécutés).
Chaque test annule ses écritures par un rollback : aucune donnée n'est laissée derrière.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from database.db import connect, execute_sql_file, load_env  # noqa: E402
from import_csv import run_import  # noqa: E402

MIGRATIONS = (
    "001_catalogue.sql",
    "002_users_candidatures.sql",
    "003_documents_sync.sql",
)


def get_test_url() -> str | None:
    load_env()
    return os.environ.get("DATABASE_URL_TEST")


@pytest.fixture(scope="session")
def test_url() -> str:
    url = get_test_url()
    if not url:
        pytest.skip(
            "DATABASE_URL_TEST n'est pas défini : copiez .env.example vers .env "
            "et renseignez une base de test dédiée."
        )
    return url


@pytest.fixture(scope="session")
def ensure_test_schema(test_url: str) -> None:
    """Applique les migrations et importe les CSV dans la base de test dédiée.

    Idempotent : aucune table ni donnée n'est supprimée. Cela rend les tests
    indépendants de l'ordre dans lequel ils sont exécutés.
    """
    with connect(test_url, autocommit=True) as conn:
        for filename in MIGRATIONS:
            execute_sql_file(conn, PROJECT_ROOT / "database" / "migrations" / filename)
    run_import(PROJECT_ROOT / "data" / "processed", url=test_url)


@pytest.fixture
def db(test_url: str, ensure_test_schema: None):
    conn = connect(test_url)
    try:
        yield conn
    finally:
        conn.rollback()
        conn.close()
