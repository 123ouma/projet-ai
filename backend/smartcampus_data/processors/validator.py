"""Quality control for the processed CSV dataset."""

from __future__ import annotations

import csv
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Iterable

from config.settings import CORE_COMPLETENESS_FIELDS, EXPORTS_DIR, PROCESSED_DIR, REQUIRED_FORMATION_FIELDS

TABLE_NAMES = (
    "etablissements",
    "formations",
    "admissions",
    "programmes",
    "tarifs",
    "sources",
    "documents",
)

DATE_COLUMNS = {"collection_date", "last_verified_at"}
YEAR_COLUMNS = {"academic_year", "admission_year", "fee_academic_year"}

REQUIRED_COLUMNS: dict[str, list[str]] = {
    "etablissements": ["etablissement_id", "name", "website_url"],
    "formations": ["formation_id", "etablissement_id", "formation_name", "source_url"],
    "admissions": ["admission_id", "formation_id", "etablissement_id"],
    "programmes": ["programme_id", "formation_id", "etablissement_id"],
    "tarifs": ["tarif_id", "formation_id", "etablissement_id", "fee_currency"],
    "sources": ["source_id", "etablissement_id", "source_url", "attribute"],
    "documents": ["document_id", "etablissement_id", "url", "raw_path"],
}


def _is_empty(value: object | None) -> bool:
    return value is None or str(value).strip() == "" or str(value).strip().lower() in {"nan", "none", "null"}


def _is_number(value: object | None) -> bool:
    if _is_empty(value):
        return True
    try:
        float(str(value).replace(",", "."))
        return True
    except (TypeError, ValueError):
        return False


def _valid_date(value: object | None) -> bool:
    """Accept ISO dates and ISO 8601 timestamps (the collector's DATE_FORMAT)."""
    if _is_empty(value):
        return True
    text = str(value).strip()
    if re.fullmatch(r"\d{4}(-\d{2}(-\d{2})?)?", text):
        return True
    return bool(
        re.fullmatch(
            r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?",
            text,
        )
    )


def _valid_year(value: object | None) -> bool:
    if _is_empty(value):
        return True
    return bool(re.fullmatch(r"20\d{2}([-/]20\d{2})?", str(value).strip()))


def _valid_url(value: object | None) -> bool:
    if _is_empty(value):
        return True
    text = str(value).strip()
    return bool(re.match(r"^https?://[^/\s]+(?:/[^\s]*)?$", text, re.I))


def _duplicates(values: Iterable[object]) -> list[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        if _is_empty(value):
            continue
        key = str(value).strip().casefold()
        if key in seen:
            duplicates.add(str(value).strip())
        seen.add(key)
    return sorted(duplicates)


def validate_tables(tables: dict[str, list[dict]]) -> dict:
    """Validate in-memory tables and return a structured report."""
    errors: list[dict] = []
    warnings: list[dict] = []
    missing_fields: dict[str, list[str]] = defaultdict(list)
    counts: dict[str, int] = {}

    def add(level: str, code: str, message: str, **context: object) -> None:
        target = errors if level == "error" else warnings
        target.append({"code": code, "message": message, **context})

    for name in TABLE_NAMES:
        rows = tables.get(name, [])
        counts[name] = len(rows)
        if not rows:
            add("warning", "EMPTY_TABLE", f"La table {name}.csv est vide.", table=name)
            continue
        missing_columns = [column for column in REQUIRED_COLUMNS[name] if column not in rows[0]]
        if missing_columns:
            add("error", "MISSING_COLUMN", f"Colonnes absentes dans {name}.csv.", table=name, columns=missing_columns)
            continue

    etabs = tables.get("etablissements", [])
    formations = tables.get("formations", [])
    etab_ids = {str(row.get("etablissement_id")) for row in etabs if not _is_empty(row.get("etablissement_id"))}
    formation_ids = {str(row.get("formation_id")) for row in formations if not _is_empty(row.get("formation_id"))}

    for row in formations:
        fid = str(row.get("formation_id") or "<sans id>")
        for field in REQUIRED_FORMATION_FIELDS:
            if _is_empty(row.get(field)):
                add("error", "FORMATION_FIELD_MISSING", f"Champ obligatoire manquant pour {fid}.", formation_id=fid, field=field)
        if not _valid_url(row.get("source_url")):
            add("error", "INVALID_URL", f"URL source invalide pour {fid}.", formation_id=fid, value=row.get("source_url"))
        if _is_empty(row.get("formation_name")):
            add("error", "NAME_MISSING", "Nom de formation absent.", formation_id=fid)

    for table in TABLE_NAMES:
        rows = tables.get(table, [])
        id_column = {
            "etablissements": "etablissement_id",
            "formations": "formation_id",
            "admissions": "admission_id",
            "programmes": "programme_id",
            "tarifs": "tarif_id",
            "sources": "source_id",
            "documents": "document_id",
        }[table]
        for value in _duplicates(row.get(id_column) for row in rows):
            add("error", "DUPLICATE_ID", f"Identifiant dupliqué dans {table}.csv.", table=table, value=value)
        if table == "formations":
            for value in _duplicates(row.get("formation_name") for row in rows):
                add("error", "DUPLICATE_NAME", "Nom de formation dupliqué.", table=table, value=value)

        for row in rows:
            context = {"table": table, "id": row.get(id_column)}
            if "formation_id" in row and not _is_empty(row.get("formation_id")) and str(row.get("formation_id")) not in formation_ids:
                add("error", "BROKEN_FORMATION_FK", "formation_id absent de formations.csv.", formation_id=row.get("formation_id"), **context)
            if "etablissement_id" in row and not _is_empty(row.get("etablissement_id")) and str(row.get("etablissement_id")) not in etab_ids:
                add("error", "BROKEN_ETABLISSEMENT_FK", "etablissement_id absent de etablissements.csv.", etablissement_id=row.get("etablissement_id"), **context)
            for column, value in row.items():
                if column in DATE_COLUMNS and not _valid_date(value):
                    add("error", "INVALID_DATE", f"Format de date invalide: {column}.", column=column, value=value, **context)
                if column in YEAR_COLUMNS and not _valid_year(value):
                    add("error", "INVALID_YEAR", f"Format d'année invalide: {column}.", column=column, value=value, **context)
                if column in {"source_url", "url", "website_url", "official_name_source_url"} and not _valid_url(value):
                    add("error", "INVALID_URL", f"URL invalide: {column}.", column=column, value=value, **context)

    for row in tables.get("tarifs", []):
        fid = str(row.get("formation_id") or "<sans id>")
        for column in ("tuition_fee", "registration_fee"):
            if not _is_number(row.get(column)):
                add("error", "NON_NUMERIC_FEE", f"Tarif publié non numérique: {column}.", formation_id=fid, column=column, value=row.get(column))
        for column in ("tuition_fee", "registration_fee"):
            if not _is_empty(row.get(column)) and _is_empty(row.get("fee_currency")):
                add("error", "MISSING_CURRENCY", "Devise absente pour un tarif publié.", formation_id=fid, column=column)

    sources_by_formation: dict[str, int] = defaultdict(int)
    for row in tables.get("sources", []):
        fid = str(row.get("formation_id") or "")
        if fid:
            sources_by_formation[fid] += 1

    for row in formations:
        fid = str(row.get("formation_id") or "<sans id>")
        empty_core = [f"formations.{field}" for field in CORE_COMPLETENESS_FIELDS if _is_empty(row.get(field))]
        related_empty: list[str] = []
        for table, fields in {
            "admissions": ("required_baccalaureate", "admission_method", "required_documents"),
            "programmes": ("subjects", "skills_acquired"),
            "tarifs": ("tuition_fee", "registration_fee", "fee_currency"),
        }.items():
            related = [item for item in tables.get(table, []) if str(item.get("formation_id")) == fid]
            if not related:
                related_empty.extend([f"{table}.{field}" for field in fields])
            else:
                for field in fields:
                    if all(_is_empty(item.get(field)) for item in related):
                        related_empty.append(f"{table}.{field}")
        missing_fields[fid] = sorted(set(empty_core + related_empty))
        if len(missing_fields[fid]) >= 4:
            warnings.append(
                {
                    "code": "INCOMPLETE_FORMATION",
                    "message": f"Formation incomplète: {row.get('formation_name') or fid}.",
                    "formation_id": fid,
                    "missing_count": len(missing_fields[fid]),
                }
            )
        if str(row.get("verification_status", "")).lower() in {"verified", "vérifié", "verifiee"} and sources_by_formation.get(fid, 0) < 2:
            add(
                "warning",
                "UNSUPPORTED_VERIFICATION",
                "Statut 'verified' non justifié par au moins deux sources.",
                formation_id=fid,
            )

    incomplete = [item for item in warnings if item.get("code") == "INCOMPLETE_FORMATION"]
    passed = len(errors) == 0
    return {
        "passed": passed,
        "summary": {
            "counts": counts,
            "errors": len(errors),
            "warnings": len(warnings),
            "incomplete_formations": len(incomplete),
            "formations_with_sources": len(sources_by_formation),
        },
        "errors": errors,
        "warnings": warnings,
        "missing_fields": dict(sorted(missing_fields.items())),
        "incomplete_formations": incomplete,
    }


def read_csv_tables(processed_dir: Path = PROCESSED_DIR) -> dict[str, list[dict]]:
    tables: dict[str, list[dict]] = {}
    for name in TABLE_NAMES:
        path = processed_dir / f"{name}.csv"
        # Exporters write utf-8-sig for Excel compatibility; utf-8-sig decoding
        # also handles plain UTF-8, so it strips the BOM from the first header.
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            tables[name] = list(csv.DictReader(handle))
    return tables


def write_validation_report(report: dict, exports_dir: Path = EXPORTS_DIR) -> tuple[Path, Path]:
    exports_dir.mkdir(parents=True, exist_ok=True)
    json_path = exports_dir / "validation_report.json"
    md_path = exports_dir / "validation_report.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    summary = report["summary"]
    lines = [
        "# Rapport de validation — SmartCampus_Data",
        "",
        f"**Résultat :** {'PASS' if report['passed'] else 'FAIL'}",
        "",
        "## Comptages",
        "",
        "| Table | Lignes |",
        "|---|---:|",
    ]
    lines.extend(f"| {name}.csv | {count} |" for name, count in summary["counts"].items())
    lines.extend(
        [
            "",
            f"- Erreurs : {summary['errors']}",
            f"- Avertissements : {summary['warnings']}",
            f"- Formations incomplètes : {summary['incomplete_formations']}",
            "",
            "## Erreurs",
            "",
        ]
    )
    if report["errors"]:
        lines.extend(f"- `{item['code']}` — {item['message']}" for item in report["errors"][:200])
    else:
        lines.append("- Aucune.")
    lines.extend(["", "## Avertissements", ""])
    if report["warnings"]:
        lines.extend(f"- `{item['code']}` — {item['message']}" for item in report["warnings"][:200])
    else:
        lines.append("- Aucun.")
    lines.extend(["", "## Champs manquants par formation", ""])
    if report["missing_fields"]:
        for fid, fields in report["missing_fields"].items():
            lines.append(f"- **{fid}** : {', '.join(fields) if fields else 'aucun'}")
    else:
        lines.append("- Aucune formation analysée.")
    lines.extend(
        [
            "",
            "> Une formation n'est marquée `collected_unverified` que lorsque ses champs sont extraits de sources officielles. "
            "La présence d'un nom sur une page officielle ne suffit pas à la considérer comme vérifiée.",
            "",
        ]
    )
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return json_path, md_path


def validate_dataset(processed_dir: Path = PROCESSED_DIR, exports_dir: Path = EXPORTS_DIR) -> dict:
    tables = read_csv_tables(processed_dir)
    report = validate_tables(tables)
    write_validation_report(report, exports_dir)
    return report
