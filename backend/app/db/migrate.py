"""Exécuteur de migrations SQL (SA-16).

Applique dans l'ordre les fichiers database/migrations/NNN_nom.sql non encore appliqués
et les note dans la table schema_migrations. Chaque fichier s'exécute dans une transaction.

    python -m app.db.migrate            # applique les migrations
    python -m app.db.migrate --seed     # + données de démonstration (database/seeds)
    python -m app.db.migrate --status   # liste l'état des migrations
"""
import argparse
import sys
from pathlib import Path

from sqlalchemy import text

from app.core.config import get_settings
from app.core.database import engine

CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version    TEXT PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
)
"""


def _sql_files(directory: Path) -> list[Path]:
    return sorted(p for p in directory.glob("*.sql") if p.is_file())


def applied_versions() -> set[str]:
    with engine.begin() as conn:
        conn.execute(text(CREATE_TABLE))
        return {row[0] for row in conn.execute(text("SELECT version FROM schema_migrations"))}


def migrate() -> list[str]:
    done = applied_versions()
    applied: list[str] = []
    for path in _sql_files(get_settings().migrations_dir):
        if path.stem in done:
            continue
        print(f"-> migration {path.name}")
        with engine.begin() as conn:  # transaction : tout ou rien
            conn.exec_driver_sql(path.read_text(encoding="utf-8"))
            conn.execute(text("INSERT INTO schema_migrations (version) VALUES (:v)"), {"v": path.stem})
        applied.append(path.stem)
    print(f"{len(applied)} migration(s) appliquée(s).")
    return applied


def seed() -> None:
    for path in _sql_files(get_settings().seeds_dir):
        print(f"-> seed {path.name}")
        with engine.begin() as conn:
            conn.exec_driver_sql(path.read_text(encoding="utf-8"))


def status() -> None:
    done = applied_versions()
    for path in _sql_files(get_settings().migrations_dir):
        print(f"[{'x' if path.stem in done else ' '}] {path.name}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Migrations SmartCampus AI")
    parser.add_argument("--seed", action="store_true", help="charger les données de démonstration")
    parser.add_argument("--status", action="store_true", help="afficher l'état sans rien appliquer")
    args = parser.parse_args(argv)
    if args.status:
        status()
        return 0
    migrate()
    if args.seed:
        seed()
    return 0


if __name__ == "__main__":
    sys.exit(main())
