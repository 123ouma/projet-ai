"""SA-20 : API de gestion des formations et des programmes.

Consultation publique ; écriture réservée au responsable NAU (voir core/security.py).
"""
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, contains_eager, selectinload

from app.core.database import get_db
from app.core.security import AuthenticatedUser, assert_establishment_permission, require_responsable
from app.models import Etablissement, Formation, ProgrammeModule
from app.schemas.catalog import (
    EtablissementOut,
    FormationCreate,
    FormationDetail,
    FormationSummary,
    FormationUpdate,
    Niveau,
    Page,
    ProgrammeIn,
    ProgrammeOut,
)

router = APIRouter(tags=["Formations et programmes (SA-20)"])


def get_formation_or_404(db: Session, formation_id: int, *, inclure_inactive: bool = True) -> Formation:
    formation = db.get(Formation, formation_id)
    if formation is None or (not inclure_inactive and not formation.actif):
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Formation {formation_id} introuvable.")
    return formation


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


# ---------- Établissements ----------
@router.get("/etablissements", response_model=list[EtablissementOut])
def list_etablissements(db: Session = Depends(get_db)):
    return db.scalars(select(Etablissement).order_by(Etablissement.code)).all()


# ---------- Formations ----------
@router.get("/formations", response_model=Page[FormationSummary])
def list_formations(
    etablissement: str | None = Query(None, description="Code établissement : IIT, ISB, ISA, 2i2s"),
    niveau: Niveau | None = None,
    domaine: str | None = None,
    q: str | None = Query(None, min_length=2, max_length=100, description="Recherche texte libre"),
    inclure_inactives: bool = False,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    stmt = select(Formation).join(Formation.etablissement)
    if not inclure_inactives:
        stmt = stmt.where(Formation.actif.is_(True))
    if etablissement:
        stmt = stmt.where(func.lower(Etablissement.code) == etablissement.lower())
    if niveau:
        stmt = stmt.where(Formation.niveau == niveau)
    if domaine:
        stmt = stmt.where(Formation.domaine.ilike(f"%{_escape_like(domaine)}%", escape="\\"))
    if q:
        motif = f"%{_escape_like(q)}%"
        stmt = stmt.where(
            or_(
                Formation.intitule.ilike(motif, escape="\\"),
                Formation.code.ilike(motif, escape="\\"),
                Formation.domaine.ilike(motif, escape="\\"),
                Formation.description.ilike(motif, escape="\\"),
            )
        )

    total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery()))
    items = db.scalars(
        stmt.options(contains_eager(Formation.etablissement))
        .order_by(Etablissement.code, Formation.intitule)
        .limit(limit)
        .offset(offset)
    ).all()
    return Page(total=total or 0, limit=limit, offset=offset, items=items)


@router.get("/formations/{formation_id}", response_model=FormationDetail)
def get_formation(formation_id: int, db: Session = Depends(get_db)):
    formation = db.scalar(
        select(Formation).options(selectinload(Formation.modules)).where(Formation.id == formation_id)
    )
    if formation is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Formation {formation_id} introuvable.")
    return formation


@router.post(
    "/formations",
    response_model=FormationDetail,
    status_code=status.HTTP_201_CREATED,
)
def create_formation(
    payload: FormationCreate,
    user: AuthenticatedUser = Depends(require_responsable),
    db: Session = Depends(get_db),
):
    etab = db.scalar(select(Etablissement).where(func.lower(Etablissement.code) == payload.etablissement_code.lower()))
    if etab is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Établissement « {payload.etablissement_code} » inconnu.")
    assert_establishment_permission(user, etab.code)
    formation = Formation(etablissement_id=etab.id, **payload.model_dump(exclude={"etablissement_code"}))
    db.add(formation)
    db.commit()  # un doublon (établissement, code) lève IntegrityError -> 409 (main.py)
    db.refresh(formation)
    return formation


@router.patch("/formations/{formation_id}", response_model=FormationDetail)
def update_formation(
    formation_id: int,
    payload: FormationUpdate,
    user: AuthenticatedUser = Depends(require_responsable),
    db: Session = Depends(get_db),
):
    formation = get_formation_or_404(db, formation_id)
    assert_establishment_permission(user, formation.etablissement.code)
    changes = payload.model_dump(exclude_unset=True)
    obligatoires = {"intitule", "niveau", "duree_annees", "langue_enseignement", "actif"}
    nuls = sorted(k for k, v in changes.items() if v is None and k in obligatoires)
    if nuls:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Champs obligatoires, ne peuvent pas être null : {nuls}.")
    if "duree_annees" in changes:
        max_annee = max((m.annee for m in formation.modules), default=0)
        if changes["duree_annees"] < max_annee:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                f"Le programme contient des modules en année {max_annee} : durée trop courte.",
            )
    for field, value in changes.items():
        setattr(formation, field, value)
    db.commit()
    db.refresh(formation)
    return formation


@router.delete(
    "/formations/{formation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def archive_formation(
    formation_id: int,
    user: AuthenticatedUser = Depends(require_responsable),
    db: Session = Depends(get_db),
):
    """Archivage (actif = false) plutôt que suppression : les candidatures existantes restent valides."""
    formation = get_formation_or_404(db, formation_id)
    assert_establishment_permission(user, formation.etablissement.code)
    formation.actif = False
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------- Programme d'études ----------
def _programme_out(formation: Formation) -> ProgrammeOut:
    total = sum((m.credits or Decimal("0") for m in formation.modules), Decimal("0"))
    return ProgrammeOut(formation_id=formation.id, total_credits=total, modules=formation.modules)


@router.get("/formations/{formation_id}/programme", response_model=ProgrammeOut)
def get_programme(formation_id: int, db: Session = Depends(get_db)):
    return _programme_out(get_formation_or_404(db, formation_id))


@router.put(
    "/formations/{formation_id}/programme",
    response_model=ProgrammeOut,
)
def replace_programme(
    formation_id: int,
    payload: ProgrammeIn,
    user: AuthenticatedUser = Depends(require_responsable),
    db: Session = Depends(get_db),
):
    """Remplace tout le programme en une transaction."""
    formation = get_formation_or_404(db, formation_id)
    assert_establishment_permission(user, formation.etablissement.code)
    trop_loin = [m.annee for m in payload.modules if m.annee > formation.duree_annees]
    if trop_loin:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"Années {sorted(set(trop_loin))} hors de la durée de la formation ({formation.duree_annees} ans).",
        )
    formation.modules.clear()  # delete-orphan supprime les anciens modules
    db.flush()
    formation.modules.extend(ProgrammeModule(**m.model_dump()) for m in payload.modules)
    db.commit()
    db.refresh(formation)
    return _programme_out(formation)
