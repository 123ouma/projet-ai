"""Crée la base si nécessaire et applique les migrations SA-12/SA-13/SA-14.

Usage :
    python scripts/create_database.py
    python scripts/create_database.py --migrations-only   # ne tente pas CREATE DATABASE

La connexion est lue depuis .env (DATABASE_URL / DATABASE_URL_ADMIN). Aucun
mot de passe n'est présent dans ce fichier. Les migrations sont idempotentes :
le script peut être relancé sans supprimer la moindre donnée.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from psycopg import sql

# Permet l'exécution directe : python scripts/create_database.py
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database.db import (  # noqa: E402
    ConfigError,
    connect,
    database_name,
    execute_sql_file,
    get_database_url,
    project_root,
)

MIGRATIONS = (
    "001_catalogue.sql",
    "002_users_candidatures.sql",
    "003_documents_sync.sql",
)


def ensure_database(db_name: str) -> bool:
    """Crée la base si elle n'existe pas. Retourne True si elle a été créée."""
    with connect(get_database_url(admin=True), autocommit=True) as admin:
        exists = admin.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s", (db_name,)
        ).fetchone()
        if exists:
            return False
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(db_name)))
        return True


def apply_migrations() -> list[str]:
    """Applique les migrations dans l'ordre, chacune dans sa propre transaction."""
    applied: list[str] = []
    migrations_dir = project_root() / "database" / "migrations"
    with connect(autocommit=True) as conn:
        for filename in MIGRATIONS:
            path = migrations_dir / filename
            if not path.is_file():
                raise FileNotFoundError(f"Migration introuvable : {path}")
            execute_sql_file(conn, path)
            applied.append(filename)
    return applied


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--migrations-only",
        action="store_true",
        help="n'appelle pas CREATE DATABASE (utile si l'utilisateur n'a pas les droits)",
    )
    args = parser.parse_args(argv)

    try:
        target_url = get_database_url()
        db_name = database_name(target_url)
        if args.migrations_only:
            print(f"Base cible : {db_name} (création ignorée)")
        else:
            created = ensure_database(db_name)
            print(f"Base cible : {db_name} ({'créée' if created else 'existante'})")

        applied = apply_migrations()
        for name in applied:
            print(f"  [OK] migration {name}")
        print(f"Migrations appliquées : {len(applied)}/{len(MIGRATIONS)}")
        return 0
    except (ConfigError, FileNotFoundError) as exc:
        print(f"[ERREUR] {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # erreur PostgreSQL ou SQL
        print(f"[ERREUR] Échec des migrations : {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
