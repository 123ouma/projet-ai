"""Vérifie la base PostgreSQL après migration/import et génère un rapport.

Contrôles effectués (lecture seule) :
  - connexion et version PostgreSQL ;
  - présence des 18 tables attendues ;
  - présence des clés primaires et étrangères ;
  - intégrité référentielle (aucun orphelin) ;
  - unicité et domaines des valeurs ;
  - correspondance des volumes avec les CSV SA-18 ;
  - absence d'embeddings / de chat (Périmètre SA-14 respecté).

Usage : python scripts/verify_database.py [--report-dir data/exports]
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database.db import ConfigError, connect, database_name, project_root  # noqa: E402

EXPECTED_TABLES = {
    "establishments", "degree_levels", "academic_years", "formations",
    "admission_requirements", "academic_programs", "tuition_fees",
    "roles", "users", "user_roles", "candidate_profiles", "candidatures",
    "candidature_status_history", "sources", "documents", "document_formations",
    "sync_history", "document_versions",
}

EXPECTED_COUNTS = {
    "establishments": ("etablissements.csv", 4),
    "formations": ("formations.csv", 22),
    "admission_requirements": ("admissions.csv", 22),
    "academic_programs": ("programmes.csv", 22),
    "tuition_fees": ("tarifs.csv", 42),
    "sources": ("sources.csv", 329),
    "documents": ("documents.csv", 83),
    "degree_levels": (None, 7),
    "academic_years": (None, 3),
    "document_formations": (None, 22),
    "document_versions": (None, 83),
    "roles": (None, 8),
    "sync_history": (None, 0),
}

INTEGRITY_CHECKS = {
    "formations_orphans": (
        "SELECT count(*) AS n FROM formations f "
        "LEFT JOIN establishments e ON e.etablissement_id = f.etablissement_id "
        "WHERE e.etablissement_id IS NULL"
    ),
    "admission_orphans": (
        "SELECT count(*) AS n FROM admission_requirements a "
        "LEFT JOIN formations f ON f.formation_id = a.formation_id WHERE f.formation_id IS NULL"
    ),
    "program_orphans": (
        "SELECT count(*) AS n FROM academic_programs p "
        "LEFT JOIN formations f ON f.formation_id = p.formation_id WHERE f.formation_id IS NULL"
    ),
    "tuition_orphans": (
        "SELECT count(*) AS n FROM tuition_fees t "
        "LEFT JOIN formations f ON f.formation_id = t.formation_id WHERE f.formation_id IS NULL"
    ),
    "sources_formation_orphans": (
        "SELECT count(*) AS n FROM sources s "
        "LEFT JOIN formations f ON f.formation_id = s.formation_id "
        "WHERE s.formation_id IS NOT NULL AND f.formation_id IS NULL"
    ),
    "document_formations_orphans": (
        "SELECT count(*) AS n FROM document_formations df "
        "LEFT JOIN documents d ON d.document_id = df.document_id "
        "LEFT JOIN formations f ON f.formation_id = df.formation_id "
        "WHERE d.document_id IS NULL OR f.formation_id IS NULL"
    ),
    "document_versions_orphans": (
        "SELECT count(*) AS n FROM document_versions v "
        "LEFT JOIN documents d ON d.document_id = v.document_id WHERE d.document_id IS NULL"
    ),
    "published_fees_without_currency": (
        "SELECT count(*) AS n FROM tuition_fees "
        "WHERE fee_status = 'published' AND fee_currency IS NULL"
    ),
    "invalid_document_sha256": (
        "SELECT count(*) AS n FROM documents WHERE sha256 !~ '^[0-9a-f]{64}$'"
    ),
    "documents_without_local_path": (
        "SELECT count(*) AS n FROM documents WHERE raw_path IS NULL OR raw_path = ''"
    ),
    "unknown_verification_status": (
        "SELECT count(*) AS n FROM ("
        "SELECT verification_status FROM establishments UNION ALL "
        "SELECT verification_status FROM formations UNION ALL "
        "SELECT verification_status FROM admission_requirements UNION ALL "
        "SELECT verification_status FROM academic_programs UNION ALL "
        "SELECT verification_status FROM tuition_fees UNION ALL "
        "SELECT verification_status FROM sources"
        ") s WHERE verification_status NOT IN "
        "('collected_unverified', 'verified', 'derived_not_official_fact', 'needs_review')"
    ),
    "indexed_documents": (
        "SELECT count(*) AS n FROM documents WHERE rag_index_status = 'indexed'"
    ),
    "multiple_current_versions": (
        "SELECT count(*) AS n FROM ("
        "SELECT document_id FROM document_versions WHERE is_current "
        "GROUP BY document_id HAVING count(*) > 1) q"
    ),
}

UNIQUENESS_CHECKS = {
    "duplicates_formation_id": "SELECT count(*) AS n FROM (SELECT formation_id FROM formations GROUP BY formation_id HAVING count(*) > 1) q",
    "duplicates_formation_name": (
        "SELECT count(*) AS n FROM (SELECT etablissement_id, formation_name FROM formations "
        "GROUP BY etablissement_id, formation_name HAVING count(*) > 1) q"
    ),
    "duplicates_tarif_key": (
        "SELECT count(*) AS n FROM (SELECT formation_id, fee_type, fee_scope, academic_year_label "
        "FROM tuition_fees GROUP BY 1,2,3,4 HAVING count(*) > 1) q"
    ),
    "duplicates_document_url": (
        "SELECT count(*) AS n FROM (SELECT etablissement_id, url FROM documents "
        "GROUP BY 1,2 HAVING count(*) > 1) q"
    ),
    "duplicates_user_email": "SELECT count(*) AS n FROM (SELECT email FROM users GROUP BY email HAVING count(*) > 1) q",
}


def check(conn, name: str, condition: bool, details: str) -> dict:
    return {
        "name": name,
        "status": "PASS" if condition else "FAIL",
        "details": details,
    }


def count_csv_rows(path: Path | None) -> int | None:
    if path is None or not path.is_file():
        return None
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return sum(1 for _ in csv.DictReader(handle))


def verify(data_dir: Path) -> dict:
    results: list[dict] = []

    with connect() as conn:
        version = conn.execute("SELECT version() AS v").fetchone()["v"]
        results.append(check(conn, "postgresql_connection", True, version))

        present = {
            row["table_name"]
            for row in conn.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public'"
            ).fetchall()
        }
        missing = sorted(EXPECTED_TABLES - present)
        results.append(check(
            conn, "expected_tables", not missing,
            f"{len(EXPECTED_TABLES) - len(missing)}/{len(EXPECTED_TABLES)} présentes"
            + (f" ; manquantes : {missing}" if missing else ""),
        ))

        pk_rows = conn.execute(
            "SELECT tc.table_name, count(*) AS n FROM information_schema.table_constraints tc "
            "WHERE tc.constraint_type = 'PRIMARY KEY' AND tc.table_schema = 'public' "
            "GROUP BY tc.table_name"
        ).fetchall()
        pk_ok = {r["table_name"] for r in pk_rows if r["n"] >= 1}
        missing_pk = sorted(EXPECTED_TABLES - pk_ok)
        results.append(check(
            conn, "primary_keys", not missing_pk,
            f"{len(pk_ok)}/{len(EXPECTED_TABLES)} tables ont une PK"
            + (f" ; sans PK : {missing_pk}" if missing_pk else ""),
        ))

        fk_count = conn.execute(
            "SELECT count(*) AS n FROM information_schema.table_constraints "
            "WHERE constraint_type = 'FOREIGN KEY' AND table_schema = 'public'"
        ).fetchone()["n"]
        results.append(check(conn, "foreign_keys", fk_count >= 20,
                             f"{fk_count} contraintes de clé étrangère"))

        for table in sorted(EXPECTED_TABLES):
            if table not in present:
                continue
            actual = conn.execute(f"SELECT count(*) AS n FROM {table}").fetchone()["n"]
            csv_name, expected = EXPECTED_COUNTS.get(table, (None, None))
            csv_count = count_csv_rows(data_dir / csv_name) if csv_name else None
            target = csv_count if csv_count is not None else expected
            if target is None:
                continue
            results.append(check(
                conn, f"row_count_{table}", actual == target,
                f"{actual} ligne(s) en base ; attendu {target}"
                + (f" ({csv_name})" if csv_name else " (valeur de référence documentée)"),
            ))

        for name, query in INTEGRITY_CHECKS.items():
            value = conn.execute(query).fetchone()["n"]
            results.append(check(conn, name, value == 0, f"{value} ligne(s) invalide(s)"))

        for name, query in UNIQUENESS_CHECKS.items():
            value = conn.execute(query).fetchone()["n"]
            results.append(check(conn, name, value == 0, f"{value} doublon(s)"))

        vector_tables = conn.execute(
            "SELECT count(*) AS n FROM information_schema.tables "
            "WHERE table_schema = 'public' AND (table_name ILIKE '%embedding%' OR table_name ILIKE '%vector%')"
        ).fetchone()["n"]
        results.append(check(conn, "no_embedding_table", vector_tables == 0,
                             f"{vector_tables} table(s) d'embedding/vecteur"))

    failures = [r for r in results if r["status"] == "FAIL"]
    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "database": database_name(),
        "status": "PASS" if not failures else "FAIL",
        "checks": results,
        "summary": {
            "total": len(results),
            "passed": len(results) - len(failures),
            "failed": len(failures),
        },
    }


def render_markdown(report: dict) -> str:
    lines = [
        "# Rapport de validation PostgreSQL — SmartCampus AI",
        "",
        f"- Généré le : {report['generated_at']}",
        f"- Base : `{report['database']}`",
        f"- Résultat : **{report['status']}**",
        f"- Contrôles : {report['summary']['passed']}/{report['summary']['total']} réussis",
        "",
        "| Contrôle | Résultat | Détail |",
        "|---|---|---|",
    ]
    for item in report["checks"]:
        lines.append(
            f"| `{item['name']}` | {item['status']} | {item['details']} |"
        )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--report-dir", type=Path, default=project_root() / "data" / "exports",
        help="dossier où écrire verification_report_db.json / .md",
    )
    args = parser.parse_args(argv)

    try:
        report = verify(project_root() / "data" / "processed")
    except (ConfigError, OSError) as exc:
        print(f"[ERREUR] {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"[ERREUR] Validation interrompue : {exc}", file=sys.stderr)
        return 1

    args.report_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.report_dir / "verification_report_db.json"
    md_path = args.report_dir / "verification_report_db.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")

    print(f"Validation : {report['status']} "
          f"({report['summary']['passed']}/{report['summary']['total']} contrôles)")
    for item in report["checks"]:
        if item["status"] == "FAIL":
            print(f"  [FAIL] {item['name']} : {item['details']}")
    print(f"Rapports : {json_path} ; {md_path}")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
