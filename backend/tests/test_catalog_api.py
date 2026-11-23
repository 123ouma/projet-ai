"""Tests API isolés SA-20/SA-21 avec une base SQLite en mémoire."""
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import JSON, create_engine, event, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import app
from app.models import (
    ConditionAdmission,
    Etablissement,
    Formation,
    ProgrammeModule,
    Tarif,
)
from app.models.auth import RoleRow, UserAuthSessionRow, UserRoleRow, UserRow

API = "/api/v1"


@pytest.fixture
def api():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _):
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    # PostgreSQL ARRAY is represented as JSON only in this SQLite test database.
    pieces_type = ConditionAdmission.__table__.c.pieces_requises.type
    ConditionAdmission.__table__.c.pieces_requises.type = JSON()

    def apply_sqlite_boolean_default(_, __, formation):
        if formation.actif is None:
            formation.actif = True

    event.listen(Formation, "before_insert", apply_sqlite_boolean_default)
    tables = [
        Etablissement.__table__,
        Formation.__table__,
        ProgrammeModule.__table__,
        Tarif.__table__,
        ConditionAdmission.__table__,
        RoleRow.__table__,
        UserRow.__table__,
        UserRoleRow.__table__,
        UserAuthSessionRow.__table__,
    ]
    Base.metadata.create_all(engine, tables=tables)
    test_sessions = sessionmaker(bind=engine, expire_on_commit=False)

    with test_sessions() as db:
        db.add_all(
            [
                Etablissement(id=1, code="IIT", nom="Institut International de Technologie"),
                Etablissement(id=2, code="ISB", nom="International School of Business"),
                RoleRow(role_code="candidat", label="Candidat", scope="global"),
                RoleRow(role_code="responsable_iit", label="Responsable IIT", scope="establishment"),
                RoleRow(role_code="responsable_isb", label="Responsable ISB", scope="establishment"),
            ]
        )
        db.flush()
        iit = db.scalar(select(Etablissement).where(Etablissement.code == "IIT"))
        isb = db.scalar(select(Etablissement).where(Etablissement.code == "ISB"))
        formation_iit = Formation(
            etablissement_id=iit.id,
            code="LIC-GL",
            intitule="Licence en génie logiciel",
            niveau="licence",
            domaine="informatique",
            duree_annees=3,
            description="Formation de test IIT",
            actif=True,
        )
        formation_iit_2 = Formation(
            etablissement_id=iit.id,
            code="ING-DATA",
            intitule="Ingénierie des données",
            niveau="ingenieur",
            domaine="informatique",
            duree_annees=3,
            description="Formation de test IIT",
            actif=True,
        )
        formation_isb = Formation(
            etablissement_id=isb.id,
            code="BBA",
            intitule="Bachelor of Business Administration",
            niveau="licence",
            domaine="gestion",
            duree_annees=3,
            description="Formation de test ISB",
            actif=True,
        )
        db.add_all([formation_iit, formation_iit_2, formation_isb])
        db.flush()
        db.add_all(
            [
                ProgrammeModule(
                    formation_id=formation_iit.id,
                    annee=1,
                    semestre=1,
                    intitule="Algorithmique",
                    credits=Decimal("5.0"),
                ),
                ProgrammeModule(
                    formation_id=formation_iit.id,
                    annee=1,
                    semestre=2,
                    intitule="Bases de données",
                    credits=Decimal("4.5"),
                ),
                Tarif(
                    formation_id=formation_iit.id,
                    annee_universitaire="2026-2027",
                    frais_inscription=Decimal("300"),
                    frais_scolarite=Decimal("4000"),
                    devise="TND",
                ),
            ]
        )
        db.commit()
        ids = {
            "iit": formation_iit.id,
            "iit_2": formation_iit_2.id,
            "isb": formation_isb.id,
        }

    def override_get_db():
        with test_sessions() as db:
            yield db

    previous_overrides = app.dependency_overrides.copy()
    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as client:
            yield client, test_sessions, ids
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous_overrides)
        engine.dispose()
        event.remove(Formation, "before_insert", apply_sqlite_boolean_default)
        ConditionAdmission.__table__.c.pieces_requises.type = pieces_type


def register_responsable(
    client: TestClient,
    test_sessions,
    establishment: str = "IIT",
) -> dict[str, str]:
    email = f"{uuid4().hex}@example.test"
    response = client.post(
        f"{API}/auth/register",
        json={"email": email, "password": "un-mot-de-passe-solide"},
    )
    assert response.status_code == 201, response.text
    user_id = response.json()["user"]["user_id"]
    with test_sessions() as db:
        db.add(
            UserRoleRow(
                user_id=user_id,
                role_code=f"responsable_{establishment.lower()}",
                scope_etablissement_id=establishment,
            )
        )
        db.commit()
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_public_formation_search_details_and_validation(api):
    client, _, ids = api
    assert client.get(f"{API}/etablissements").status_code == 200

    response = client.get(
        f"{API}/formations",
        params={"etablissement": "iit", "niveau": "licence", "q": "génie"},
    )
    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["id"] == ids["iit"]

    detail = client.get(f"{API}/formations/{ids['iit']}")
    assert detail.status_code == 200
    assert [module["intitule"] for module in detail.json()["modules"]] == [
        "Algorithmique",
        "Bases de données",
    ]
    assert client.get(f"{API}/formations/999999").status_code == 404
    assert client.get(f"{API}/formations", params={"q": "a"}).status_code == 422
    assert client.get(f"{API}/formations", params={"niveau": "doctorat"}).status_code == 422
    assert client.get(f"{API}/formations", params={"limit": 0}).status_code == 422


def test_formation_updates_archive_scope_and_validate_payload(api):
    client, test_sessions, ids = api
    iit_headers = register_responsable(client, test_sessions, "IIT")
    assert client.patch(
        f"{API}/formations/{ids['iit']}",
        json={"intitule": "Non autorisé"},
    ).status_code == 401

    candidate = client.post(
        f"{API}/auth/register",
        json={"email": f"{uuid4().hex}@example.test", "password": "un-mot-de-passe-solide"},
    ).json()
    candidate_headers = {"Authorization": f"Bearer {candidate['access_token']}"}
    assert client.patch(
        f"{API}/formations/{ids['isb']}",
        json={"intitule": "Modification interdite"},
        headers=iit_headers,
    ).status_code == 403
    assert client.patch(
        f"{API}/formations/{ids['iit']}",
        json={"intitule": "Modification interdite"},
        headers=candidate_headers,
    ).status_code == 403
    assert client.patch(
        f"{API}/formations/{ids['iit']}",
        json={"niveau": "doctorat"},
        headers=iit_headers,
    ).status_code == 422
    assert client.patch(
        f"{API}/formations/{ids['iit']}",
        json={"intitule": None},
        headers=iit_headers,
    ).status_code == 422

    updated = client.patch(
        f"{API}/formations/{ids['iit']}",
        json={"intitule": "Intitulé modifié"},
        headers=iit_headers,
    )
    assert updated.status_code == 200
    assert updated.json()["intitule"] == "Intitulé modifié"
    invalid_create = client.post(
        f"{API}/formations",
        json={
            "etablissement_code": "IIT",
            "code": "TEST-BAD",
            "intitule": "Invalid",
            "niveau": "doctorat",
            "duree_annees": 3,
        },
        headers=iit_headers,
    )
    assert invalid_create.status_code == 422
    assert client.delete(f"{API}/formations/{ids['iit']}", headers=iit_headers).status_code == 204
    assert client.get(f"{API}/formations/{ids['iit']}").status_code == 200
    assert client.get(f"{API}/formations", params={"etablissement": "IIT"}).json()["total"] == 1
    assert client.get(
        f"{API}/formations",
        params={"etablissement": "IIT", "inclure_inactives": "true"},
    ).json()["total"] == 2


def test_programme_endpoint_replaces_modules_and_checks_duration(api):
    client, test_sessions, ids = api
    headers = register_responsable(client, test_sessions)
    base = f"{API}/formations/{ids['iit']}/programme"
    assert client.put(base, json={"modules": []}).status_code == 401

    payload = {
        "modules": [
            {"annee": 2, "semestre": 1, "intitule": "Module nouveau", "credits": "6.0"},
            {"annee": 3, "semestre": 2, "intitule": "Projet", "credits": "3.5"},
        ]
    }
    response = client.put(base, json=payload, headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["total_credits"] == "9.5"
    assert response.json()["modules"][0]["intitule"] == "Module nouveau"

    too_long = {"modules": [{"annee": 4, "semestre": 1, "intitule": "Hors programme"}]}
    assert client.put(base, json=too_long, headers=headers).status_code == 422
    invalid_semester = {"modules": [{"annee": 1, "semestre": 3, "intitule": "Semestre invalide"}]}
    assert client.put(base, json=invalid_semester, headers=headers).status_code == 422
    assert client.get(f"{API}/formations/999999/programme").status_code == 404


def test_tariff_admission_and_comparison_endpoints(api):
    client, test_sessions, ids = api
    iit_headers = register_responsable(client, test_sessions, "IIT")
    isb_headers = register_responsable(client, test_sessions, "ISB")

    prices = client.get(
        f"{API}/tarifs",
        params={"etablissement": "IIT", "niveau": "licence", "budget_max": "5000", "annee": "2026-2027"},
    )
    assert prices.status_code == 200
    assert prices.json()["total"] == 1
    assert prices.json()["items"][0]["formation"]["id"] == ids["iit"]
    assert client.get(f"{API}/formations/{ids['iit']}/tarifs").json()[0]["total_annuel"] == "4300.000"
    assert client.get(f"{API}/formations/999999/tarifs").status_code == 404

    tariff_url = f"{API}/formations/{ids['iit_2']}/tarifs/2026-2027"
    assert client.put(
        tariff_url,
        json={"frais_scolarite": "3000"},
    ).status_code == 401
    assert client.put(
        tariff_url,
        json={"frais_scolarite": "3000"},
        headers=isb_headers,
    ).status_code == 403
    tariff = client.put(
        tariff_url,
        json={"frais_inscription": "250", "frais_scolarite": "3000", "devise": "tnd"},
        headers=iit_headers,
    )
    assert tariff.status_code == 200, tariff.text
    assert tariff.json()["total_annuel"] == "3250.000"
    assert client.put(
        f"{API}/formations/{ids['iit_2']}/tarifs/2026-2028",
        json={"frais_scolarite": "3000"},
        headers=iit_headers,
    ).status_code == 422
    assert client.put(
        tariff_url,
        json={"frais_scolarite": "-1"},
        headers=iit_headers,
    ).status_code == 422

    condition_url = f"{API}/formations/{ids['iit']}/conditions"
    assert client.get(condition_url).status_code == 404
    assert client.put(
        condition_url,
        json={"diplome_requis": "Baccalauréat"},
    ).status_code == 401
    condition = client.put(
        condition_url,
        json={
            "diplome_requis": "Baccalauréat",
            "moyenne_minimale": "12.50",
            "pieces_requises": ["CIN", " cin ", "Relevé de notes"],
        },
        headers=iit_headers,
    )
    assert condition.status_code == 200, condition.text
    assert condition.json()["pieces_requises"] == ["CIN", "Relevé de notes"]
    assert client.get(condition_url).status_code == 200
    assert client.put(
        f"{API}/formations/{ids['iit']}/conditions",
        json={"diplome_requis": "Baccalauréat", "moyenne_minimale": "22"},
        headers=iit_headers,
    ).status_code == 422
    assert client.get(f"{API}/formations/999999/conditions").status_code == 404

    comparison = client.get(
        f"{API}/formations/compare",
        params={"ids": f"{ids['iit']},{ids['iit_2']}", "annee": "2026-2027"},
    )
    assert comparison.status_code == 200
    assert [entry["formation"]["id"] for entry in comparison.json()["formations"]] == [
        ids["iit"],
        ids["iit_2"],
    ]
    assert comparison.json()["formations"][0]["conditions"]["pieces_requises"] == [
        "CIN",
        "Relevé de notes",
    ]
    assert client.get(f"{API}/formations/compare", params={"ids": "not-an-id,2"}).status_code == 422
    assert client.get(f"{API}/formations/compare", params={"ids": f"{ids['iit']},999999"}).status_code == 404
    assert client.delete(
        f"{API}/formations/{ids['iit_2']}/tarifs/2026-2027",
        headers=iit_headers,
    ).status_code == 204
    assert client.delete(
        f"{API}/formations/{ids['iit_2']}/tarifs/2026-2027",
        headers=iit_headers,
    ).status_code == 404
