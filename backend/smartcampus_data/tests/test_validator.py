from processors.validator import validate_tables


def _minimal_tables():
    return {
        "etablissements": [
            {"etablissement_id": "IIT", "name": "IIT", "website_url": "https://iit.tn"}
        ],
        "formations": [
            {
                "formation_id": "IIT-big-data",
                "etablissement_id": "IIT",
                "formation_name": "Big Data",
                "source_url": "https://iit.tn/big-data/",
                "collection_date": "2026-11-21",
                "degree_type": "Licence",
                "description": "Formation officielle",
                "duration_years": 3,
                "language": "fr",
                "verification_status": "collected_unverified",
            }
        ],
        "admissions": [],
        "programmes": [],
        "tarifs": [],
        "sources": [],
        "documents": [],
    }


def test_valid_minimal_dataset_passes():
    report = validate_tables(_minimal_tables())
    assert report["passed"] is True
    assert report["summary"]["errors"] == 0


def test_duplicate_and_broken_relation_are_errors():
    tables = _minimal_tables()
    tables["formations"].append(dict(tables["formations"][0]))
    tables["admissions"].append(
        {"admission_id": "adm-1", "formation_id": "IIT-inconnue", "etablissement_id": "IIT"}
    )
    report = validate_tables(tables)
    codes = {item["code"] for item in report["errors"]}
    assert "DUPLICATE_ID" in codes
    assert "BROKEN_FORMATION_FK" in codes


def test_invalid_url_date_and_fee_are_detected():
    tables = _minimal_tables()
    tables["formations"][0]["source_url"] = "ftp://invalide"
    tables["formations"][0]["collection_date"] = "21/11/2026"
    tables["tarifs"].append(
        {
            "tarif_id": "tar-1",
            "formation_id": "IIT-big-data",
            "etablissement_id": "IIT",
            "fee_type": "tuition",
            "tuition_fee": "abc",
            "fee_currency": "DT",
            "fee_academic_year": "2026",
        }
    )
    report = validate_tables(tables)
    codes = {item["code"] for item in report["errors"]}
    assert {"INVALID_URL", "INVALID_DATE", "NON_NUMERIC_FEE"}.issubset(codes)


def test_iso_timestamps_are_valid_collection_dates():
    tables = _minimal_tables()
    tables["formations"][0]["collection_date"] = "2026-11-21T23:01:28Z"
    report = validate_tables(tables)
    assert not [e for e in report["errors"] if e["code"] == "INVALID_DATE"]


def test_missing_fields_are_reported_without_marking_verified():
    tables = _minimal_tables()
    tables["formations"][0]["description"] = ""
    report = validate_tables(tables)
    assert "formations.description" in report["missing_fields"]["IIT-big-data"]
    assert report["summary"]["incomplete_formations"] >= 1
