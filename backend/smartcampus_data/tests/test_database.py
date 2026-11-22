"""Tests PostgreSQL : connexion, schéma, contraintes et intégrité référentielle.

Tous les tests écrivent dans une transaction annulée à la fin : la base de test
reste inchangée. Aucun compte réel n'est créé. Les échecs attendus sont isolés
dans un savepoint afin de ne pas invalider la transaction du test.
"""

from __future__ import annotations

from contextlib import contextmanager

import pytest

from database.db import connect

DEMO_HASH = "demo-only-not-a-real-password-hash"


@contextmanager
def must_fail(conn):
    """Le bloc doit lever une erreur PostgreSQL ; le savepoint est restauré."""
    with pytest.raises(Exception):
        with conn.transaction():
            yield


def unique_email(label: str) -> str:
    # Domaine réservé .invalid : jamais une adresse réelle.
    return f"test-{label}@example.invalid"


def make_user(conn, email: str) -> int:
    return conn.execute(
        "INSERT INTO users (email, password_hash, full_name) VALUES (%s, %s, %s) RETURNING user_id",
        (email, DEMO_HASH, "Utilisateur de test"),
    ).fetchone()["user_id"]


def first_formation_id(conn) -> str:
    return conn.execute(
        "SELECT formation_id FROM formations ORDER BY formation_id LIMIT 1"
    ).fetchone()["formation_id"]


def test_connection_and_version(test_url: str) -> None:
    with connect(test_url) as conn:
        version = conn.execute("SELECT version() AS v").fetchone()["v"]
    assert "PostgreSQL" in version


def test_expected_tables_present(db) -> None:
    names = {
        row["table_name"]
        for row in db.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
        ).fetchall()
    }
    assert {
        "establishments", "degree_levels", "academic_years", "formations",
        "admission_requirements", "academic_programs", "tuition_fees",
        "roles", "users", "user_roles", "candidate_profiles", "candidatures",
        "candidature_status_history", "sources", "documents", "document_formations",
        "sync_history", "document_versions",
    } <= names


def test_insert_user_and_reject_duplicate_email(db) -> None:
    email = unique_email("duplicate")
    user_id = make_user(db, email)
    assert user_id > 0
    with must_fail(db):
        make_user(db, email)


def test_password_hash_cannot_be_empty(db) -> None:
    with must_fail(db):
        db.execute(
            "INSERT INTO users (email, password_hash) VALUES (%s, %s)",
            (unique_email("empty-hash"), ""),
        )


def test_no_plaintext_password_column(db) -> None:
    columns = {
        row["column_name"]
        for row in db.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'users' AND table_schema = 'public'"
        ).fetchall()
    }
    assert "password_hash" in columns
    assert "password" not in columns


def test_responsable_iit_requires_matching_scope(db) -> None:
    db.execute(
        "INSERT INTO roles (role_code, label, scope) VALUES "
        "('responsable_iit', 'Responsable IIT', 'establishment') "
        "ON CONFLICT (role_code) DO NOTHING"
    )
    user_id = make_user(db, unique_email("scope"))

    with must_fail(db):
        db.execute(
            "INSERT INTO user_roles (user_id, role_code, scope_etablissement_id) "
            "VALUES (%s, 'responsable_iit', NULL)",
            (user_id,),
        )
    with must_fail(db):
        db.execute(
            "INSERT INTO user_roles (user_id, role_code, scope_etablissement_id) "
            "VALUES (%s, 'responsable_iit', 'ISB')",
            (user_id,),
        )
    db.execute(
        "INSERT INTO user_roles (user_id, role_code, scope_etablissement_id) "
        "VALUES (%s, 'responsable_iit', 'IIT')",
        (user_id,),
    )


def test_duplicate_role_assignment_rejected(db) -> None:
    db.execute(
        "INSERT INTO roles (role_code, label, scope) VALUES "
        "('administrateur', 'Administrateur', 'global') "
        "ON CONFLICT (role_code) DO NOTHING"
    )
    user_id = make_user(db, unique_email("dup-role"))
    statement = (
        "INSERT INTO user_roles (user_id, role_code, scope_etablissement_id) "
        "VALUES (%s, 'administrateur', NULL)"
    )
    db.execute(statement, (user_id,))
    with must_fail(db):
        db.execute(statement, (user_id,))


def test_candidature_requires_existing_formation(db) -> None:
    user_id = make_user(db, unique_email("bad-formation"))
    with must_fail(db):
        db.execute(
            "INSERT INTO candidatures (candidate_user_id, formation_id, status) "
            "VALUES (%s, %s, 'draft')",
            (user_id, "formation-inexistante-test"),
        )


def test_submitted_candidature_requires_consent_and_date(db) -> None:
    user_id = make_user(db, unique_email("consent"))
    formation_id = first_formation_id(db)

    with must_fail(db):
        db.execute(
            "INSERT INTO candidatures "
            "(candidate_user_id, formation_id, status, consent_given, submitted_at) "
            "VALUES (%s, %s, 'submitted', false, now())",
            (user_id, formation_id),
        )
    with must_fail(db):
        db.execute(
            "INSERT INTO candidatures "
            "(candidate_user_id, formation_id, status, consent_given, submitted_at) "
            "VALUES (%s, %s, 'submitted', true, NULL)",
            (user_id, formation_id),
        )

    candidature_id = db.execute(
        "INSERT INTO candidatures "
        "(candidate_user_id, formation_id, status, consent_given, consent_given_at, submitted_at) "
        "VALUES (%s, %s, 'submitted', true, now(), now()) RETURNING candidature_id",
        (user_id, formation_id),
    ).fetchone()["candidature_id"]
    assert candidature_id > 0


def test_status_history_is_created_by_trigger(db) -> None:
    user_id = make_user(db, unique_email("history"))
    formation_id = first_formation_id(db)
    candidature_id = db.execute(
        "INSERT INTO candidatures (candidate_user_id, formation_id, status) "
        "VALUES (%s, %s, 'draft') RETURNING candidature_id",
        (user_id, formation_id),
    ).fetchone()["candidature_id"]

    first = db.execute(
        "SELECT from_status, to_status FROM candidature_status_history "
        "WHERE candidature_id = %s ORDER BY history_id",
        (candidature_id,),
    ).fetchone()
    assert first["from_status"] is None
    assert first["to_status"] == "draft"

    db.execute(
        "UPDATE candidatures SET status = 'submitted', consent_given = true, "
        "consent_given_at = now(), submitted_at = now() WHERE candidature_id = %s",
        (candidature_id,),
    )
    history = db.execute(
        "SELECT from_status, to_status FROM candidature_status_history "
        "WHERE candidature_id = %s ORDER BY history_id",
        (candidature_id,),
    ).fetchall()
    assert [(row["from_status"], row["to_status"]) for row in history] == [
        (None, "draft"), ("draft", "submitted")
    ]


def test_published_fee_requires_currency(db) -> None:
    formation_id = first_formation_id(db)
    with must_fail(db):
        db.execute(
            "INSERT INTO tuition_fees (tarif_id, formation_id, fee_type, fee_status, tuition_fee) "
            "VALUES (%s, %s, 'tuition', 'published', 100)",
            ("tarif-test-sans-devise", formation_id),
        )


def test_document_sha256_format_is_enforced(db) -> None:
    with must_fail(db):
        db.execute(
            "INSERT INTO documents (document_id, document_type, url, raw_path, sha256, collection_date) "
            "VALUES (%s, 'pdf', 'https://example.invalid/a.pdf', 'data/raw/a.pdf', %s, now())",
            ("doc-test-sha", "pas-un-sha256"),
        )


def test_single_current_document_version(db) -> None:
    document_id = "doc-test-version-unique"
    db.execute(
        "INSERT INTO documents (document_id, document_type, url, raw_path, sha256, collection_date) "
        "VALUES (%s, 'html', 'https://example.invalid/a.html', 'data/raw/a.html', %s, now())",
        (document_id, "a" * 64),
    )
    db.execute(
        "INSERT INTO document_versions (document_id, version_number, sha256, raw_path, is_current) "
        "VALUES (%s, 1, %s, 'data/raw/a.html', true)",
        (document_id, "b" * 64),
    )
    with must_fail(db):
        db.execute(
            "INSERT INTO document_versions (document_id, version_number, sha256, raw_path, is_current) "
            "VALUES (%s, 2, %s, 'data/raw/a.html', true)",
            (document_id, "c" * 64),
        )
