"""SA-21 : API de consultation des tarifs et des conditions d'admission.

Inclut la comparaison de formations (architecture §4.1 : « consultation et comparaison »).
Ce routeur est inclus AVANT celui des formations pour que /formations/compare
ne soit pas capturé par /formations/{formation_id}.
"""
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, contains_eager

from app.api.v1.formations import get_formation_or_404
from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import AuthenticatedUser, assert_establishment_permission, require_responsable
from app.models import ConditionAdmission, Etablissement, Formation, Tarif
from app.schemas.catalog import (
    Comparaison,
    ConditionsIn,
    ConditionsOut,
    FormationComparee,
    Niveau,
    Page,
    TarifAvecFormation,
    TarifIn,
    TarifOut,
    check_annee_suivante,
)

router = APIRouter(tags=["Tarifs et conditions d'admission (SA-21)"])

AnneePath = Annotated[str, Path(pattern=r"^\d{4}-\d{4}$", examples=["2026-2027"])]


def _annee(value: str | None) -> str:
    annee = value or get_settings().annee_universitaire_courante
    try:
        return check_annee_suivante(annee)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc


# ---------- Consultation globale des tarifs ----------
@router.get("/tarifs", response_model=Page[TarifAvecFormation])
def list_tarifs(
    annee: str | None = Query(None, pattern=r"^\d{4}-\d{4}$", description="Par défaut : année en cours"),
    etablissement: str | None = None,
    niveau: Niveau | None = None,
    budget_max: Decimal | None = Query(None, ge=0, description="Total annuel maximum (inscription + scolarité)"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    stmt = (
        select(Tarif)
        .join(Tarif.formation)
        .join(Formation.etablissement)
        .where(Tarif.annee_universitaire == _annee(annee), Formation.actif.is_(True))
    )
    if etablissement:
        stmt = stmt.where(func.lower(Etablissement.code) == etablissement.lower())
    if niveau:
        stmt = stmt.where(Formation.niveau == niveau)
    if budget_max is not None:
        stmt = stmt.where(Tarif.frais_inscription + Tarif.frais_scolarite <= budget_max)

    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    items = db.scalars(
        stmt.options(contains_eager(Tarif.formation).contains_eager(Formation.etablissement))
        .order_by(Tarif.frais_inscription + Tarif.frais_scolarite, Formation.intitule)
        .limit(limit)
        .offset(offset)
    ).all()
    return Page(total=total or 0, limit=limit, offset=offset, items=items)


# ---------- Comparaison ----------
@router.get("/formations/compare", response_model=Comparaison)
def compare_formations(
    ids: str = Query(..., description="2 à 4 identifiants séparés par des virgules, ex. 1,3"),
    annee: str | None = Query(None, pattern=r"^\d{4}-\d{4}$"),
    db: Session = Depends(get_db),
):
    try:
        id_list = list(dict.fromkeys(int(x) for x in ids.split(",") if x.strip()))
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "ids doit contenir des entiers.") from exc
    if not 2 <= len(id_list) <= 4:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Comparer entre 2 et 4 formations distinctes.")

    annee_cible = _annee(annee)
    formations = {f.id: f for f in db.scalars(select(Formation).where(Formation.id.in_(id_list))).all()}
    manquantes = [i for i in id_list if i not in formations]
    if manquantes:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Formation(s) introuvable(s) : {manquantes}.")

    tarifs = {
        t.formation_id: t
        for t in db.scalars(
            select(Tarif).where(Tarif.formation_id.in_(id_list), Tarif.annee_universitaire == annee_cible)
        ).all()
    }
    conditions = {
        c.formation_id: c
        for c in db.scalars(select(ConditionAdmission).where(ConditionAdmission.formation_id.in_(id_list))).all()
    }
    return Comparaison(
        annee_universitaire=annee_cible,
        formations=[
            FormationComparee(
                formation=formations[i],
                tarif=tarifs.get(i),
                conditions=conditions.get(i),
            )
            for i in id_list
        ],
    )


# ---------- Tarifs d'une formation ----------
@router.get("/formations/{formation_id}/tarifs", response_model=list[TarifOut])
def get_tarifs(
    formation_id: int,
    annee: str | None = Query(None, pattern=r"^\d{4}-\d{4}$", description="Vide = toutes les années"),
    db: Session = Depends(get_db),
):
    formation = get_formation_or_404(db, formation_id)
    tarifs = formation.tarifs
    if annee:
        tarifs = [t for t in tarifs if t.annee_universitaire == annee]
    return tarifs


@router.put(
    "/formations/{formation_id}/tarifs/{annee}",
    response_model=TarifOut,
)
def upsert_tarif(
    formation_id: int,
    annee: AnneePath,
    payload: TarifIn,
    user: AuthenticatedUser = Depends(require_responsable),
    db: Session = Depends(get_db),
):
    """Crée ou remplace le tarif d'une formation pour une année universitaire."""
    annee = _annee(annee)
    formation = get_formation_or_404(db, formation_id)
    assert_establishment_permission(user, formation.etablissement.code)
    tarif = db.scalar(select(Tarif).where(Tarif.formation_id == formation_id, Tarif.annee_universitaire == annee))
    data = payload.model_dump()
    data["devise"] = data["devise"].upper()
    if tarif is None:
        tarif = Tarif(formation_id=formation_id, annee_universitaire=annee, **data)
        db.add(tarif)
    else:
        for field, value in data.items():
            setattr(tarif, field, value)
    db.commit()
    db.refresh(tarif)
    return tarif


@router.delete(
    "/formations/{formation_id}/tarifs/{annee}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_tarif(
    formation_id: int,
    annee: AnneePath,
    user: AuthenticatedUser = Depends(require_responsable),
    db: Session = Depends(get_db),
):
    formation = get_formation_or_404(db, formation_id)
    assert_establishment_permission(user, formation.etablissement.code)
    tarif = db.scalar(select(Tarif).where(Tarif.formation_id == formation_id, Tarif.annee_universitaire == annee))
    if tarif is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tarif introuvable pour cette année.")
    db.delete(tarif)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------- Conditions d'admission ----------
@router.get("/formations/{formation_id}/conditions", response_model=ConditionsOut)
def get_conditions(formation_id: int, db: Session = Depends(get_db)):
    formation = get_formation_or_404(db, formation_id)
    if formation.conditions is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conditions d'admission non renseignées pour cette formation.")
    return formation.conditions


@router.put(
    "/formations/{formation_id}/conditions",
    response_model=ConditionsOut,
)
def upsert_conditions(
    formation_id: int,
    payload: ConditionsIn,
    user: AuthenticatedUser = Depends(require_responsable),
    db: Session = Depends(get_db),
):
    formation = get_formation_or_404(db, formation_id)
    assert_establishment_permission(user, formation.etablissement.code)
    if formation.conditions is None:
        formation.conditions = ConditionAdmission(**payload.model_dump())
    else:
        for field, value in payload.model_dump().items():
            setattr(formation.conditions, field, value)
    db.commit()
    db.refresh(formation.conditions)
    return formation.conditions
