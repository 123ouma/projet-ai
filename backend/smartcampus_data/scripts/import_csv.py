"""Import relançable des CSV SA-18 vers PostgreSQL (SA-17).

Ordre de dépendance respecté :
  establishments → degree_levels / academic_years → formations →
  admission_requirements → academic_programs → tuition_fees →
  sources → documents → document_formations → document_versions.

Chaque fichier est importé dans sa propre transaction : une erreur annule
uniquement le fichier en cours. Toutes les écritures utilisent
INSERT ... ON CONFLICT : relancer le script ne crée aucun doublon et ne
supprime aucune donnée existante. Les cellules vides deviennent NULL.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import unicodedata
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

# Permet l'exécution directe : python scripts/import_csv.py
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database.db import ConfigError, connect, database_name, project_root  # noqa: E402

CSV_FILES = {
    "establishments": "etablissements.csv",
    "formations": "formations.csv",
    "admissions": "admissions.csv",
    "programmes": "programmes.csv",
    "tarifs": "tarifs.csv",
    "sources": "sources.csv",
    "documents": "documents.csv",
}

VERIFICATION_VALUES = {
    "collected_unverified", "verified", "derived_not_official_fact", "needs_review",
}
YEAR_RE = re.compile(r"^(\d{4})(?:[/−-](\d{4}))?$")
SLUG_RE = re.compile(r"[^a-z0-9]+")


class ImportErrorDetails(RuntimeError):
    """Erreur de données avec contexte lisible."""


# ---------------------------------------------------------------------------
# Helpers de transformation (aucune valeur inventée)
# ---------------------------------------------------------------------------

def text(value: str | None) -> str | None:
    """Chaîne nettoyée ; une cellule vide devient NULL."""
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def required_text(value: str | None, *, column: str, row_id: str) -> str:
    """Chaîne obligatoire : une valeur absente est une erreur, pas une invention."""
    result = text(value)
    if result is None:
        raise ImportErrorDetails(f"{row_id} : {column} est vide alors que la colonne est NOT NULL")
    return result


def integer(value: str | None, *, column: str, row_id: str) -> int | None:
    raw = text(value)
    if raw is None:
        return None
    try:
        return int(raw)
    except ValueError as exc:
        raise ImportErrorDetails(f"{row_id} : {column}={raw!r} n'est pas un entier") from exc


def decimal(value: str | None, *, column: str, row_id: str) -> Decimal | None:
    raw = text(value)
    if raw is None:
        return None
    try:
        return Decimal(raw)
    except InvalidOperation as exc:
        raise ImportErrorDetails(f"{row_id} : {column}={raw!r} n'est pas un nombre décimal") from exc


def timestamp(value: str | None, *, column: str, row_id: str) -> datetime | None:
    raw = text(value)
    if raw is None:
        return None
    try:
        return datetime.strptime(raw, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise ImportErrorDetails(
            f"{row_id} : {column}={raw!r} n'est pas au format ISO 8601 AAAA-MM-JJH:MM:SSZ"
        ) from exc


def slugify(label: str) -> str:
    """Clé technique dérivée d'un libellé officiel, sans donnée inventée."""
    ascii_label = unicodedata.normalize("NFKD", label).encode("ascii", "ignore").decode()
    slug = SLUG_RE.sub("-", ascii_label.lower()).strip("-")
    if not slug:  # cas théorique : on ne perd pas la valeur
        raise ImportErrorDetails(f"Impossible de dériver un code depuis {label!r}")
    return slug


def parse_academic_year(label: str | None) -> tuple[int, int | None] | None:
    """2026/2027 → (2026, 2027) ; 2025-2026 → (2025, 2026) ; 2026 → (2026, None)."""
    raw = text(label)
    if raw is None:
        return None
    match = YEAR_RE.fullmatch(raw)
    if not match:
        raise ImportErrorDetails(f"Année universitaire non reconnue : {raw!r}")
    start = int(match.group(1))
    end = int(match.group(2)) if match.group(2) else None
    if end is not None and end <= start:
        raise ImportErrorDetails(f"Année universitaire incohérente : {raw!r}")
    return start, end


def verification(value: str | None, *, row_id: str) -> str:
    raw = text(value)
    if raw is None:
        return "collected_unverified"
    if raw not in VERIFICATION_VALUES:
        raise ImportErrorDetails(f"{row_id} : statut de vérification inattendu {raw!r}")
    return raw


def read_csv(path: Path, key: str) -> list[dict[str, str]]:
    if not path.is_file():
        raise FileNotFoundError(f"CSV introuvable : {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ImportErrorDetails(f"{path.name} : aucun en-tête")
        rows = [dict(row) for row in reader]
    ids = [(row.get(key) or "").strip() for row in rows]
    empty = [i + 2 for i, value in enumerate(ids) if not value]
    if empty:
        raise ImportErrorDetails(f"{path.name} : {key} vide aux lignes {empty[:10]}")
    duplicates = sorted({value for value in ids if ids.count(value) > 1})
    if duplicates:
        raise ImportErrorDetails(f"{path.name} : {key} dupliqué : {duplicates[:10]}")
    return rows


# ---------------------------------------------------------------------------
# Génération SQL (les identifiants proviennent de constantes de ce module)
# ---------------------------------------------------------------------------

def upsert(table: str, columns: list[str], conflict: str, updatable: list[str]) -> str:
    inserts = ", ".join(columns)
    placeholders = ", ".join(f"%({name})s" for name in columns)
    assignments = ", ".join(f"{name} = EXCLUDED.{name}" for name in updatable)
    return (
        f"INSERT INTO {table} ({inserts}) VALUES ({placeholders}) "
        f"ON CONFLICT {conflict} DO UPDATE SET {assignments}"
    )


def insert_if_absent(table: str, columns: list[str], conflict: str) -> str:
    inserts = ", ".join(columns)
    placeholders = ", ".join(f"%({name})s" for name in columns)
    return (
        f"INSERT INTO {table} ({inserts}) VALUES ({placeholders}) "
        f"ON CONFLICT {conflict} DO NOTHING"
    )


def run_batch(cur, query: str, rows: list[dict], table: str) -> int:
    if not rows:
        return 0
    cur.executemany(query, rows)
    return len(rows)


# ---------------------------------------------------------------------------
# Contrôles avant import
# ---------------------------------------------------------------------------

def preflight(rows: dict[str, list[dict[str, str]]]) -> None:
    """Vérifie les références croisées dans les CSV avant toute écriture."""
    establishment_ids = {(r["etablissement_id"] or "").strip() for r in rows["establishments"]}
    formation_ids = {(r["formation_id"] or "").strip() for r in rows["formations"]}

    for name in CSV_FILES:
        for row in rows[name]:
            ref = (row.get("etablissement_id") or "").strip()
            if ref and ref not in establishment_ids:
                raise ImportErrorDetails(
                    f"{CSV_FILES[name]} : etablissement_id {ref!r} absent de etablissements.csv"
                )

    for name in ("admissions", "programmes", "tarifs", "sources", "documents"):
        for row in rows[name]:
            ref = (row.get("formation_id") or "").strip()
            if ref and ref not in formation_ids:
                raise ImportErrorDetails(
                    f"{CSV_FILES[name]} : formation_id {ref!r} absent de formations.csv"
                )


def reference_rows(rows: dict[str, list[dict[str, str]]]) -> tuple[list[dict], list[dict]]:
    """Construit degree_levels et academic_years à partir des valeurs publiées."""
    labels: dict[str, str] = {}
    for row in rows["formations"]:
        label = text(row.get("degree_type"))
        if label:
            labels[label] = slugify(label)

    degrees = [
        {"code": code, "label": label}
        for label, code in sorted(labels.items(), key=lambda item: item[1])
    ]

    years: dict[str, tuple[int, int | None]] = {}
    for name, column in (
        ("formations", "academic_year"),
        ("admissions", "admission_year"),
        ("tarifs", "fee_academic_year"),
    ):
        for row in rows[name]:
            label = text(row.get(column))
            if label and label not in years:
                years[label] = parse_academic_year(label)

    academic = [
        {"label": label, "start_year": start, "end_year": end}
        for label, (start, end) in sorted(years.items())
    ]
    return degrees, academic


# ---------------------------------------------------------------------------
# Importeurs (un par table)
# ---------------------------------------------------------------------------

def import_establishments(cur, rows: list[dict[str, str]]) -> int:
    columns = [
        "etablissement_id", "name", "short_name", "country", "city", "website_url",
        "official_name_source_url", "contact_email", "contact_phone", "campus_location",
        "collection_date", "document_language", "verification_status",
    ]
    query = upsert("establishments", columns, "(etablissement_id)", columns)
    data = []
    for row in rows:
        rid = row["etablissement_id"].strip()
        data.append({
            "etablissement_id": rid,
            "name": required_text(row.get("name"), column="name", row_id=rid),
            "short_name": text(row.get("short_name")),
            "country": text(row.get("country")),
            "city": text(row.get("city")),
            "website_url": text(row.get("website_url")),
            "official_name_source_url": text(row.get("official_name_source_url")),
            "contact_email": text(row.get("contact_email")),
            "contact_phone": text(row.get("contact_phone")),
            "campus_location": text(row.get("campus_location")),
            "collection_date": timestamp(row.get("collection_date"), column="collection_date", row_id=rid),
            "document_language": text(row.get("document_language")),
            "verification_status": verification(row.get("verification_status"), row_id=rid),
        })
    return run_batch(cur, query, data, "establishments")


def import_degree_levels(cur, degrees: list[dict]) -> int:
    query = upsert("degree_levels", ["code", "label"], "(code)", ["label"])
    return run_batch(cur, query, degrees, "degree_levels")


def import_academic_years(cur, years: list[dict]) -> int:
    query = upsert("academic_years", ["label", "start_year", "end_year"], "(label)",
                   ["start_year", "end_year"])
    return run_batch(cur, query, years, "academic_years")


def import_formations(cur, rows: list[dict[str, str]]) -> int:
    # academic_year est renommé en academic_year_label et degree_level_code est dérivé.
    columns = [
        "formation_id", "etablissement_id", "formation_name", "field", "speciality",
        "description", "duration_years", "language", "study_mode", "diploma_awarded",
        "career_opportunities", "further_studies", "career_field", "bridges",
        "recommended_profile", "interest_tags", "interest_tags_origin", "prerequisite_skills",
        "source_url", "source_title", "source_type", "collection_date", "last_verified_at",
        "degree_level_code", "academic_year_label", "verification_status", "document_language",
    ]
    query = upsert("formations", columns, "(formation_id)", columns)
    data = []
    for row in rows:
        rid = row["formation_id"].strip()
        degree = text(row.get("degree_type"))
        year_label = text(row.get("academic_year"))
        data.append({
            "formation_id": rid,
            "etablissement_id": row["etablissement_id"].strip(),
            "formation_name": required_text(row.get("formation_name"), column="formation_name", row_id=rid),
            "field": text(row.get("field")),
            "speciality": text(row.get("speciality")),
            "description": text(row.get("description")),
            "duration_years": decimal(row.get("duration_years"), column="duration_years", row_id=rid),
            "language": text(row.get("language")),
            "study_mode": text(row.get("study_mode")),
            "diploma_awarded": text(row.get("diploma_awarded")),
            "career_opportunities": text(row.get("career_opportunities")),
            "further_studies": text(row.get("further_studies")),
            "career_field": text(row.get("career_field")),
            "bridges": text(row.get("bridges")),
            "recommended_profile": text(row.get("recommended_profile")),
            "interest_tags": text(row.get("interest_tags")),
            "interest_tags_origin": text(row.get("interest_tags_origin")),
            "prerequisite_skills": text(row.get("prerequisite_skills")),
            "source_url": text(row.get("source_url")),
            "source_title": text(row.get("source_title")),
            "source_type": text(row.get("source_type")),
            "collection_date": timestamp(row.get("collection_date"), column="collection_date", row_id=rid),
            "last_verified_at": timestamp(row.get("last_verified_at"), column="last_verified_at", row_id=rid),
            "degree_level_code": slugify(degree) if degree else None,
            "academic_year_label": year_label,
            "verification_status": verification(row.get("verification_status"), row_id=rid),
            "document_language": text(row.get("document_language")),
        })
    return run_batch(cur, query, data, "formations")


def import_admissions(cur, rows: list[dict[str, str]]) -> int:
    columns = [
        "admission_id", "formation_id", "academic_year_label", "required_baccalaureate",
        "minimum_grade", "required_level", "admission_method", "required_documents",
        "registration_period", "special_conditions", "source_url", "source_title",
        "collection_date", "document_language", "verification_status",
    ]
    query = upsert("admission_requirements", columns, "(admission_id)", columns)
    data = []
    for row in rows:
        rid = row["admission_id"].strip()
        data.append({
            "admission_id": rid,
            "formation_id": row["formation_id"].strip(),
            "academic_year_label": text(row.get("admission_year")),
            "required_baccalaureate": text(row.get("required_baccalaureate")),
            "minimum_grade": decimal(row.get("minimum_grade"), column="minimum_grade", row_id=rid),
            "required_level": text(row.get("required_level")),
            "admission_method": text(row.get("admission_method")),
            "required_documents": text(row.get("required_documents")),
            "registration_period": text(row.get("registration_period")),
            "special_conditions": text(row.get("special_conditions")),
            "source_url": text(row.get("source_url")),
            "source_title": text(row.get("source_title")),
            "collection_date": timestamp(row.get("collection_date"), column="collection_date", row_id=rid),
            "document_language": text(row.get("document_language")),
            "verification_status": verification(row.get("verification_status"), row_id=rid),
        })
    return run_batch(cur, query, data, "admission_requirements")


def import_programmes(cur, rows: list[dict[str, str]]) -> int:
    columns = [
        "programme_id", "formation_id", "subjects", "modules", "semester_count",
        "internships", "projects", "specializations", "skills_acquired", "source_url",
        "source_title", "collection_date", "document_language", "verification_status",
    ]
    query = upsert("academic_programs", columns, "(programme_id)", columns)
    data = []
    for row in rows:
        rid = row["programme_id"].strip()
        data.append({
            "programme_id": rid,
            "formation_id": row["formation_id"].strip(),
            "subjects": text(row.get("subjects")),
            "modules": text(row.get("modules")),
            "semester_count": integer(row.get("semester_count"), column="semester_count", row_id=rid),
            "internships": text(row.get("internships")),
            "projects": text(row.get("projects")),
            "specializations": text(row.get("specializations")),
            "skills_acquired": text(row.get("skills_acquired")),
            "source_url": text(row.get("source_url")),
            "source_title": text(row.get("source_title")),
            "collection_date": timestamp(row.get("collection_date"), column="collection_date", row_id=rid),
            "document_language": text(row.get("document_language")),
            "verification_status": verification(row.get("verification_status"), row_id=rid),
        })
    return run_batch(cur, query, data, "academic_programs")


def import_tarifs(cur, rows: list[dict[str, str]]) -> int:
    columns = [
        "tarif_id", "formation_id", "academic_year_label", "fee_type", "fee_scope",
        "tuition_fee", "registration_fee", "other_fees", "fee_currency", "fee_period",
        "payment_terms", "campus_location", "contact_email", "contact_phone", "fee_status",
        "source_url", "source_title", "collection_date", "document_language",
        "verification_status",
    ]
    query = upsert("tuition_fees", columns, "(tarif_id)", columns)
    data = []
    for row in rows:
        rid = row["tarif_id"].strip()
        data.append({
            "tarif_id": rid,
            "formation_id": row["formation_id"].strip(),
            "academic_year_label": text(row.get("fee_academic_year")),
            "fee_type": required_text(row.get("fee_type"), column="fee_type", row_id=rid),
            "fee_scope": text(row.get("fee_scope")),
            "tuition_fee": decimal(row.get("tuition_fee"), column="tuition_fee", row_id=rid),
            "registration_fee": decimal(row.get("registration_fee"), column="registration_fee", row_id=rid),
            "other_fees": text(row.get("other_fees")),
            "fee_currency": text(row.get("fee_currency")),
            "fee_period": text(row.get("fee_period")),
            "payment_terms": text(row.get("payment_terms")),
            "campus_location": text(row.get("campus_location")),
            "contact_email": text(row.get("contact_email")),
            "contact_phone": text(row.get("contact_phone")),
            "fee_status": required_text(row.get("fee_status"), column="fee_status", row_id=rid),
            "source_url": text(row.get("source_url")),
            "source_title": text(row.get("source_title")),
            "collection_date": timestamp(row.get("collection_date"), column="collection_date", row_id=rid),
            "document_language": text(row.get("document_language")),
            "verification_status": verification(row.get("verification_status"), row_id=rid),
        })
    return run_batch(cur, query, data, "tuition_fees")


def import_sources(cur, rows: list[dict[str, str]]) -> int:
    columns = [
        "source_id", "etablissement_id", "formation_id", "source_url", "source_title",
        "source_type", "attribute", "value_excerpt", "raw_path", "value_origin",
        "document_language", "collection_date", "last_verified_at", "http_status",
        "verification_status", "evidence_excerpt",
    ]
    query = upsert("sources", columns, "(source_id)", columns)
    data = []
    for row in rows:
        rid = row["source_id"].strip()
        data.append({
            "source_id": rid,
            "etablissement_id": text(row.get("etablissement_id")),
            "formation_id": text(row.get("formation_id")),
            "source_url": required_text(row.get("source_url"), column="source_url", row_id=rid),
            "source_title": text(row.get("source_title")),
            "source_type": required_text(row.get("source_type"), column="source_type", row_id=rid),
            "attribute": text(row.get("attribute")),
            "value_excerpt": text(row.get("value_excerpt")),
            "raw_path": text(row.get("raw_path")),
            "value_origin": text(row.get("value_origin")),
            "document_language": text(row.get("document_language")),
            "collection_date": timestamp(row.get("collection_date"), column="collection_date", row_id=rid),
            "last_verified_at": timestamp(row.get("last_verified_at"), column="last_verified_at", row_id=rid),
            "http_status": integer(row.get("http_status"), column="http_status", row_id=rid),
            "verification_status": verification(row.get("verification_status"), row_id=rid),
            "evidence_excerpt": text(row.get("evidence_excerpt")),
        })
    return run_batch(cur, query, data, "sources")


def import_documents(cur, rows: list[dict[str, str]]) -> int:
    columns = [
        "document_id", "etablissement_id", "document_type", "title", "url", "parent_url",
        "raw_path", "metadata_path", "sha256", "byte_size", "http_status", "content_type",
        "language", "text_chars", "page_count", "collection_date", "sync_status",
        "last_error_message", "verification_status",
    ]
    query = upsert("documents", columns, "(document_id)", columns)
    data = []
    for row in rows:
        rid = row["document_id"].strip()
        sha = text(row.get("sha256"))
        if not sha or not re.fullmatch(r"[0-9a-f]{64}", sha):
            raise ImportErrorDetails(f"{rid} : sha256 manquant ou invalide : {sha!r}")
        data.append({
            "document_id": rid,
            "etablissement_id": text(row.get("etablissement_id")),
            "document_type": required_text(row.get("document_type"), column="document_type", row_id=rid),
            "title": text(row.get("title")),
            "url": required_text(row.get("url"), column="url", row_id=rid),
            "parent_url": text(row.get("parent_url")),
            "raw_path": required_text(row.get("raw_path"), column="raw_path", row_id=rid),
            "metadata_path": text(row.get("metadata_path")),
            "sha256": sha,
            "byte_size": integer(row.get("byte_size"), column="byte_size", row_id=rid),
            "http_status": integer(row.get("http_status"), column="http_status", row_id=rid),
            "content_type": text(row.get("content_type")),
            "language": text(row.get("language")),
            "text_chars": integer(row.get("text_chars"), column="text_chars", row_id=rid),
            "page_count": integer(row.get("page_count"), column="page_count", row_id=rid),
            "collection_date": timestamp(row.get("collection_date"), column="collection_date", row_id=rid),
            "sync_status": "collected",
            "last_error_message": text(row.get("error")),
            "verification_status": None,  # absent de documents.csv : NULL, pas de valeur supposée
        })
    return run_batch(cur, query, data, "documents")


def import_document_formations(cur, rows: list[dict[str, str]]) -> int:
    query = insert_if_absent(
        "document_formations", ["document_id", "formation_id"], "(document_id, formation_id)"
    )
    data = [
        {"document_id": row["document_id"].strip(), "formation_id": row["formation_id"].strip()}
        for row in rows
        if text(row.get("formation_id"))
    ]
    return run_batch(cur, query, data, "document_formations")


def import_document_versions(cur, rows: list[dict[str, str]]) -> int:
    columns = [
        "document_id", "version_number", "sha256", "raw_path", "byte_size",
        "collected_at", "is_current",
    ]
    query = insert_if_absent(
        "document_versions", columns, "(document_id, version_number)"
    )
    data = [
        {
            "document_id": row["document_id"].strip(),
            "version_number": 1,
            "sha256": row["sha256"].strip(),
            "raw_path": required_text(row.get("raw_path"), column="raw_path", row_id=row["document_id"]),
            "byte_size": integer(row.get("byte_size"), column="byte_size", row_id=row["document_id"]),
            "collected_at": timestamp(row.get("collection_date"), column="collection_date",
                                      row_id=row["document_id"]),
            "is_current": True,
        }
        for row in rows
    ]
    return run_batch(cur, query, data, "document_versions")


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def run_import(processed_dir: Path, url: str | None = None) -> dict:
    """Importe tous les CSV et retourne un rapport structuré.

    ``url`` permet aux tests de cibler une base dédiée sans modifier .env.
    """
    primary_keys = {
        "establishments": "etablissement_id",
        "formations": "formation_id",
        "admissions": "admission_id",
        "programmes": "programme_id",
        "tarifs": "tarif_id",
        "sources": "source_id",
        "documents": "document_id",
    }
    rows = {
        name: read_csv(processed_dir / filename, primary_keys[name])
        for name, filename in CSV_FILES.items()
    }
    preflight(rows)
    degrees, academic = reference_rows(rows)

    steps = [
        ("establishments", "etablissements.csv", lambda cur: import_establishments(cur, rows["establishments"])),
        ("degree_levels", "dérivé de formations.csv", lambda cur: import_degree_levels(cur, degrees)),
        ("academic_years", "dérivé de 3 CSV", lambda cur: import_academic_years(cur, academic)),
        ("formations", "formations.csv", lambda cur: import_formations(cur, rows["formations"])),
        ("admission_requirements", "admissions.csv", lambda cur: import_admissions(cur, rows["admissions"])),
        ("academic_programs", "programmes.csv", lambda cur: import_programmes(cur, rows["programmes"])),
        ("tuition_fees", "tarifs.csv", lambda cur: import_tarifs(cur, rows["tarifs"])),
        ("sources", "sources.csv", lambda cur: import_sources(cur, rows["sources"])),
        ("documents", "documents.csv", lambda cur: import_documents(cur, rows["documents"])),
        ("document_formations", "dérivé de documents.csv", lambda cur: import_document_formations(cur, rows["documents"])),
        ("document_versions", "dérivé de documents.csv", lambda cur: import_document_versions(cur, rows["documents"])),
    ]

    report_steps: list[dict] = []
    with connect(url) as conn:
        for table, origin, importer in steps:
            try:
                with conn.transaction():
                    with conn.cursor() as cur:
                        count = importer(cur)
            except Exception as exc:
                raise ImportErrorDetails(f"Échec de l'import de {table} ({origin}) : {exc}") from exc
            report_steps.append({"table": table, "origin": origin, "rows": count, "status": "ok"})
            print(f"  [OK] {table:<28} {count:>4} ligne(s)  <- {origin}")

    return {
        "status": "PASS",
        "database": database_name(url),
        "processed_dir": str(processed_dir),
        "steps": report_steps,
        "total_rows": sum(step["rows"] for step in report_steps),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--processed-dir",
        type=Path,
        default=project_root() / "data" / "processed",
        help="dossier contenant les 7 CSV SA-18",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=project_root() / "data" / "exports" / "import_report.json",
        help="chemin du rapport JSON produit",
    )
    args = parser.parse_args(argv)

    try:
        report = run_import(args.processed_dir)
    except (ConfigError, FileNotFoundError, ImportErrorDetails) as exc:
        print(f"[ERREUR] {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"[ERREUR] Import interrompu : {exc}", file=sys.stderr)
        return 1

    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"Import terminé : {report['total_rows']} ligne(s) traitée(s).")
    print(f"Rapport : {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
