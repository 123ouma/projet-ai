"""Tests d'intégration de l'API (SA-20, SA-21, SA-26).

Nécessitent FastAPI installé ET une base PostgreSQL de test migrée + seedée :
    export TEST_DATABASE_URL=postgresql+psycopg://smartcampus:...@localhost:5432/smartcampus_test
    python -m app.db.migrate --seed     (avec DATABASE_URL=$TEST_DATABASE_URL)
    pytest tests/test_api.py
Sans TEST_DATABASE_URL, ces tests sont ignorés.
"""
import os
import uuid

import pytest

if not os.getenv("TEST_DATABASE_URL"):
    pytest.skip("TEST_DATABASE_URL non défini", allow_module_level=True)
pytest.importorskip("fastapi")

os.environ["DATABASE_URL"] = os.environ["TEST_DATABASE_URL"]
os.environ["ADMIN_API_TOKEN"] = "jeton-de-test"
os.environ["MEMORY_BACKEND"] = "postgres"

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

client = TestClient(app)
ADMIN = {"X-Admin-Token": "jeton-de-test"}
API = "/api/v1"


def test_health():
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/health/db").status_code == 200


# ---------- SA-20 ----------
def test_liste_et_filtres():
    r = client.get(f"{API}/formations", params={"etablissement": "iit"})
    assert r.status_code == 200
    body = r.json()
    assert body["total"] >= 1
    assert all(f["etablissement"]["code"] == "IIT" for f in body["items"])
    assert client.get(f"{API}/formations", params={"q": "génie"}).json()["total"] >= 1


def test_ecriture_protegee():
    payload = {"etablissement_code": "IIT", "code": "T-PROT", "intitule": "Test", "niveau": "licence", "duree_annees": 3}
    assert client.post(f"{API}/formations", json=payload).status_code == 401


def test_cycle_de_vie_formation():
    code = f"T-{uuid.uuid4().hex[:8]}"
    payload = {"etablissement_code": "IIT", "code": code, "intitule": "Formation de test", "niveau": "master", "duree_annees": 2}
    r = client.post(f"{API}/formations", json=payload, headers=ADMIN)
    assert r.status_code == 201, r.text
    fid = r.json()["id"]

    assert client.post(f"{API}/formations", json=payload, headers=ADMIN).status_code == 409  # doublon

    programme = {"modules": [
        {"annee": 1, "semestre": 1, "intitule": "Module A", "credits": "5"},
        {"annee": 2, "semestre": 2, "intitule": "Module B", "credits": "4.5"},
    ]}
    r = client.put(f"{API}/formations/{fid}/programme", json=programme, headers=ADMIN)
    assert r.status_code == 200, r.text
    assert r.json()["total_credits"] == "9.5"

    trop_loin = {"modules": [{"annee": 3, "semestre": 1, "intitule": "Hors durée"}]}
    assert client.put(f"{API}/formations/{fid}/programme", json=trop_loin, headers=ADMIN).status_code == 422
    assert client.patch(f"{API}/formations/{fid}", json={"duree_annees": 1}, headers=ADMIN).status_code == 422

    # ---------- SA-21 ----------
    tarif = {"frais_inscription": "300", "frais_scolarite": "4000.5"}
    r = client.put(f"{API}/formations/{fid}/tarifs/2026-2027", json=tarif, headers=ADMIN)
    assert r.status_code == 200, r.text
    assert r.json()["total_annuel"] == "4300.500"
    assert client.put(f"{API}/formations/{fid}/tarifs/2026-2028", json=tarif, headers=ADMIN).status_code == 422

    assert client.get(f"{API}/formations/{fid}/conditions").status_code == 404
    cond = {"diplome_requis": "Licence", "test_anglais_requis": False, "pieces_requises": ["CIN", "Diplôme"]}
    assert client.put(f"{API}/formations/{fid}/conditions", json=cond, headers=ADMIN).status_code == 200
    assert client.get(f"{API}/formations/{fid}/conditions").json()["pieces_requises"] == ["CIN", "Diplôme"]

    r = client.get(f"{API}/tarifs", params={"budget_max": "4300.5"})
    assert fid in [t["formation_id"] for t in r.json()["items"]]

    autre = client.get(f"{API}/formations").json()["items"][0]["id"]
    r = client.get(f"{API}/formations/compare", params={"ids": f"{fid},{autre}"})
    assert r.status_code == 200, r.text
    assert [f["formation"]["id"] for f in r.json()["formations"]] == [fid, autre]
    assert client.get(f"{API}/formations/compare", params={"ids": str(fid)}).status_code == 422

    assert client.delete(f"{API}/formations/{fid}", headers=ADMIN).status_code == 204
    ids = [f["id"] for f in client.get(f"{API}/formations", params={"limit": 100}).json()["items"]]
    assert fid not in ids


# ---------- SA-26 ----------
def test_memoire_conversation():
    created = client.post(f"{API}/visitor-sessions")
    assert created.status_code == 201, created.text
    sid = uuid.UUID(created.json()["session_id"])
    base = f"{API}/conversations/{sid}"
    assert client.post(f"{base}/messages", json={"role": "user", "content": "Quels masters à l'IIT ?"}).status_code == 201
    client.post(f"{base}/messages", json={"role": "assistant", "content": "Voici la liste..."})
    assert client.post(f"{base}/messages", json={"role": "system", "content": "x"}).status_code == 422

    r = client.get(f"{base}/messages").json()
    assert r["count"] == 2 and r["messages"][0]["role"] == "user"
    assert client.get(f"{base}/context").json()["count"] == 2

    assert client.delete(base).status_code == 204
    assert client.get(f"{base}/messages").json()["count"] == 0
    assert client.get(f"{API}/conversations/pas-un-uuid/messages").status_code == 422
    assert client.delete(f"{API}/visitor-sessions/{sid}").status_code == 204
