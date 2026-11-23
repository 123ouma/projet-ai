"""Schémas d'entrée/sortie du catalogue (SA-20 / SA-21)."""
from decimal import Decimal
from typing import Annotated, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator, model_validator

Niveau = Literal["preparatoire", "licence", "ingenieur", "master", "autre"]
AnneeUniversitaire = Annotated[str, Field(pattern=r"^\d{4}-\d{4}$", examples=["2026-2027"])]
Montant = Annotated[Decimal, Field(ge=0, max_digits=10, decimal_places=3)]

T = TypeVar("T")


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Page(BaseModel, Generic[T]):
    total: int
    limit: int
    offset: int
    items: list[T]


def check_annee_suivante(value: str) -> str:
    debut, fin = (int(x) for x in value.split("-"))
    if fin != debut + 1:
        raise ValueError("L'année universitaire doit être de la forme AAAA-(AAAA+1), ex. 2026-2027.")
    return value


# ---------- Établissements ----------
class EtablissementOut(ORMModel):
    id: int
    code: str
    nom: str
    ville: str | None = None
    site_web: str | None = None


# ---------- Formations (SA-20) ----------
class FormationBase(BaseModel):
    code: str = Field(min_length=2, max_length=30)
    intitule: str = Field(min_length=3, max_length=300)
    niveau: Niveau
    domaine: str | None = Field(default=None, max_length=150)
    duree_annees: int = Field(ge=1, le=6)
    langue_enseignement: str = Field(default="français", max_length=50)
    description: str | None = Field(default=None, max_length=5000)


class FormationCreate(FormationBase):
    etablissement_code: str = Field(min_length=2, max_length=10, examples=["IIT"])


class FormationUpdate(BaseModel):
    """Mise à jour partielle : seuls les champs envoyés sont modifiés."""

    intitule: str | None = Field(default=None, min_length=3, max_length=300)
    niveau: Niveau | None = None
    domaine: str | None = Field(default=None, max_length=150)
    duree_annees: int | None = Field(default=None, ge=1, le=6)
    langue_enseignement: str | None = Field(default=None, max_length=50)
    description: str | None = Field(default=None, max_length=5000)
    actif: bool | None = None


class FormationSummary(ORMModel):
    id: int
    code: str
    intitule: str
    niveau: str
    domaine: str | None
    duree_annees: int
    langue_enseignement: str
    actif: bool
    etablissement: EtablissementOut


class ModuleIn(BaseModel):
    annee: int = Field(ge=1, le=6)
    semestre: Literal[1, 2]
    intitule: str = Field(min_length=2, max_length=300)
    credits: Decimal | None = Field(default=None, ge=0, max_digits=4, decimal_places=1)
    volume_horaire: int | None = Field(default=None, ge=0)
    ordre: int = Field(default=0, ge=0)


class ModuleOut(ORMModel, ModuleIn):
    id: int


class ProgrammeIn(BaseModel):
    modules: list[ModuleIn] = Field(max_length=200)


class ProgrammeOut(BaseModel):
    formation_id: int
    total_credits: Decimal
    modules: list[ModuleOut]


class FormationDetail(FormationSummary):
    description: str | None
    modules: list[ModuleOut]


# ---------- Tarifs (SA-21) ----------
class TarifIn(BaseModel):
    frais_inscription: Montant = Decimal("0")
    frais_scolarite: Montant
    devise: str = Field(default="TND", min_length=3, max_length=3)
    modalites_paiement: str | None = Field(default=None, max_length=2000)
    remarques: str | None = Field(default=None, max_length=2000)


class TarifOut(ORMModel):
    formation_id: int
    annee_universitaire: str
    frais_inscription: Decimal
    frais_scolarite: Decimal
    devise: str
    modalites_paiement: str | None
    remarques: str | None

    @computed_field
    @property
    def total_annuel(self) -> Decimal:
        return self.frais_inscription + self.frais_scolarite


class TarifAvecFormation(TarifOut):
    formation: FormationSummary


# ---------- Conditions d'admission (SA-21) ----------
class ConditionsIn(BaseModel):
    diplome_requis: str = Field(min_length=2, max_length=300)
    niveau_acces: str | None = Field(default=None, max_length=100)
    moyenne_minimale: Decimal | None = Field(default=None, ge=0, le=20, decimal_places=2)
    test_anglais_requis: bool = False
    entretien_requis: bool = True
    pieces_requises: list[Annotated[str, Field(min_length=2, max_length=200)]] = Field(
        default_factory=list, max_length=30
    )
    description: str | None = Field(default=None, max_length=5000)

    @field_validator("pieces_requises")
    @classmethod
    def sans_doublons(cls, v: list[str]) -> list[str]:
        vues: set[str] = set()
        resultat = []
        for piece in (p.strip() for p in v):
            if piece.lower() not in vues:
                vues.add(piece.lower())
                resultat.append(piece)
        return resultat


class ConditionsOut(ORMModel, ConditionsIn):
    formation_id: int


# ---------- Comparaison ----------
class FormationComparee(BaseModel):
    formation: FormationSummary
    tarif: TarifOut | None
    conditions: ConditionsOut | None


class Comparaison(BaseModel):
    annee_universitaire: str
    formations: list[FormationComparee]

    @model_validator(mode="after")
    def _au_moins_une(self):
        if not self.formations:
            raise ValueError("Aucune formation à comparer.")
        return self
