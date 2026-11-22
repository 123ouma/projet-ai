"""Tests de validation des schémas du catalogue (SA-20 / SA-21), sans base de données."""
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.schemas.catalog import ConditionsIn, FormationCreate, ModuleIn, TarifIn, TarifOut, check_annee_suivante


def test_formation_valide():
    f = FormationCreate(etablissement_code="IIT", code="ING-GL", intitule="Génie logiciel", niveau="ingenieur", duree_annees=3)
    assert f.langue_enseignement == "français"


@pytest.mark.parametrize("champ,valeur", [("niveau", "doctorat"), ("duree_annees", 0), ("duree_annees", 9), ("code", "x")])
def test_formation_invalide(champ, valeur):
    data = dict(etablissement_code="IIT", code="ING-GL", intitule="Génie logiciel", niveau="ingenieur", duree_annees=3)
    data[champ] = valeur
    with pytest.raises(ValidationError):
        FormationCreate(**data)


def test_module_semestre():
    with pytest.raises(ValidationError):
        ModuleIn(annee=1, semestre=3, intitule="Maths")


def test_tarif_negatif_refuse():
    with pytest.raises(ValidationError):
        TarifIn(frais_scolarite=Decimal("-1"))


def test_tarif_total_annuel():
    t = TarifOut(
        formation_id=1, annee_universitaire="2026-2027", frais_inscription=Decimal("500.000"),
        frais_scolarite=Decimal("6000.500"), devise="TND", modalites_paiement=None, remarques=None,
    )
    assert t.total_annuel == Decimal("6500.500")
    assert t.model_dump()["total_annuel"] == Decimal("6500.500")


def test_annee_universitaire():
    assert check_annee_suivante("2026-2027") == "2026-2027"
    with pytest.raises(ValueError):
        check_annee_suivante("2026-2028")


def test_pieces_requises_dedoublonnees():
    c = ConditionsIn(diplome_requis="Baccalauréat", pieces_requises=["CIN", " cin ", "Relevé de notes"])
    assert c.pieces_requises == ["CIN", "Relevé de notes"]
