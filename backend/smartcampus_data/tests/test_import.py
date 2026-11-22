"""Tests de l'import CSV : transformations pures et relance sur PostgreSQL."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from import_csv import (
    ImportErrorDetails,
    decimal as decimal_value,
    integer,
    parse_academic_year,
    read_csv,
    reference_rows,
    required_text,
    run_import,
    slugify,
    text,
    timestamp,
    upsert,
)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"


# ---------------------------------------------------------------------------
# Tests unitaires (aucune base requise)
# ---------------------------------------------------------------------------

def test_empty_cells_become_none() -> None:
    assert text("") is None
    assert text("   ") is None
    assert text("  IIT ") == "IIT"


def test_required_text_raises_on_missing_value() -> None:
    with pytest.raises(ImportErrorDetails):
        required_text("", column="name", row_id="IIT")


def test_numeric_and_timestamp_parsing() -> None:
    assert integer("42", column="n", row_id="r") == 42
    assert integer("", column="n", row_id="r") is None
    assert decimal_value("778.50", column="fee", row_id="r") == Decimal("778.50")
    assert timestamp("2026-11-21T23:26:39Z", column="d", row_id="r") == datetime(
        2026, 11, 21, 23, 26, 39, tzinfo=timezone.utc
    )
    with pytest.raises(ImportErrorDetails):
        integer("pas-un-entier", column="n", row_id="r")
    with pytest.raises(ImportErrorDetails):
        timestamp("21/11/2026", column="d", row_id="r")


def test_slugify_is_deterministic_and_distinct() -> None:
    assert slugify("Cycle ingénieur") == "cycle-ingenieur"
    assert slugify("Diplôme national d'architecte") == "diplome-national-d-architecte"
    assert slugify("Master") != slugify("Mastère")


def test_academic_year_derivation() -> None:
    assert parse_academic_year("2026/2027") == (2026, 2027)
    assert parse_academic_year("2025-2026") == (2025, 2026)
    assert parse_academic_year("2026") == (2026, None)
    assert parse_academic_year("") is None
    with pytest.raises(ImportErrorDetails):
        parse_academic_year("2027/2026")


def test_upsert_sql_contains_conflict_clause() -> None:
    query = upsert("formations", ["formation_id", "name"], "(formation_id)", ["name"])
    assert "INSERT INTO formations" in query
    assert "ON CONFLICT (formation_id) DO UPDATE SET name = EXCLUDED.name" in query


def test_reference_rows_from_real_csv() -> None:
    rows = {
        "formations": read_csv(PROCESSED_DIR / "formations.csv", "formation_id"),
        "admissions": read_csv(PROCESSED_DIR / "admissions.csv", "admission_id"),
        "tarifs": read_csv(PROCESSED_DIR / "tarifs.csv", "tarif_id"),
    }
    degrees, years = reference_rows(rows)
    assert len(degrees) == 7
    assert len({d["code"] for d in degrees}) == 7
    assert len(years) == 3
    assert {"2026/2027", "2025-2026", "2026"} <= {y["label"] for y in years}
    assert next(y for y in years if y["label"] == "2026")["end_year"] is None


def test_csv_readers_reject_duplicate_primary_keys() -> None:
    with pytest.raises(ImportErrorDetails):
        read_csv(PROCESSED_DIR / "formations.csv", "etablissement_id")  # clé non unique


# ---------------------------------------------------------------------------
# Tests d'intégration (base de test dédiée)
# ---------------------------------------------------------------------------

def test_import_is_relaunchable_without_duplicates(test_url: str, ensure_test_schema: None) -> None:
    first = run_import(PROCESSED_DIR, url=test_url)
    assert first["status"] == "PASS"

    from database.db import connect

    with connect(test_url) as conn:
        before = {
            table: conn.execute(f"SELECT count(*) AS n FROM {table}").fetchone()["n"]
            for table in (
                "establishments", "degree_levels", "academic_years", "formations",
                "admission_requirements", "academic_programs", "tuition_fees",
                "sources", "documents", "document_formations", "document_versions",
            )
        }

    second = run_import(PROCESSED_DIR, url=test_url)
    assert second["status"] == "PASS"

    with connect(test_url) as conn:
        after = {
            table: conn.execute(f"SELECT count(*) AS n FROM {table}").fetchone()["n"]
            for table in before
        }
    assert after == before


def test_imported_volumes_match_csv(test_url: str, ensure_test_schema: None) -> None:
    from database.db import connect

    expected = {
        "establishments": 4,
        "formations": 22,
        "admission_requirements": 22,
        "academic_programs": 22,
        "tuition_fees": 42,
        "sources": 329,
        "documents": 83,
        "degree_levels": 7,
        "academic_years": 3,
        "document_formations": 22,
        "document_versions": 83,
    }
    with connect(test_url) as conn:
        for table, count in expected.items():
            actual = conn.execute(f"SELECT count(*) AS n FROM {table}").fetchone()["n"]
            assert actual == count, f"{table} : {actual} au lieu de {count}"
