"""Modèles ORM du catalogue (SA-20 / SA-21). Reflètent database/migrations/002_catalogue.sql."""
from datetime import datetime
from decimal import Decimal

from sqlalchemy import ARRAY, Boolean, DateTime, ForeignKey, Integer, Numeric, SmallInteger, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Etablissement(Base):
    __tablename__ = "etablissements"

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    code: Mapped[str] = mapped_column(String(10), unique=True)
    nom: Mapped[str] = mapped_column(Text)
    ville: Mapped[str | None] = mapped_column(Text)
    site_web: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    formations: Mapped[list["Formation"]] = relationship(back_populates="etablissement")


class Formation(Base):
    __tablename__ = "formations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    etablissement_id: Mapped[int] = mapped_column(ForeignKey("etablissements.id"))
    code: Mapped[str] = mapped_column(String(30))
    intitule: Mapped[str] = mapped_column(Text)
    niveau: Mapped[str] = mapped_column(String(20))
    domaine: Mapped[str | None] = mapped_column(Text)
    duree_annees: Mapped[int] = mapped_column(SmallInteger)
    langue_enseignement: Mapped[str] = mapped_column(Text, server_default="français")
    description: Mapped[str | None] = mapped_column(Text)
    actif: Mapped[bool] = mapped_column(Boolean, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    etablissement: Mapped[Etablissement] = relationship(back_populates="formations", lazy="joined")
    modules: Mapped[list["ProgrammeModule"]] = relationship(
        back_populates="formation",
        cascade="all, delete-orphan",
        order_by=lambda: [ProgrammeModule.annee, ProgrammeModule.semestre, ProgrammeModule.ordre, ProgrammeModule.id],
    )
    tarifs: Mapped[list["Tarif"]] = relationship(
        back_populates="formation", cascade="all, delete-orphan", order_by=lambda: Tarif.annee_universitaire.desc()
    )
    conditions: Mapped["ConditionAdmission | None"] = relationship(
        back_populates="formation", cascade="all, delete-orphan", uselist=False
    )


class ProgrammeModule(Base):
    __tablename__ = "programme_modules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    formation_id: Mapped[int] = mapped_column(ForeignKey("formations.id", ondelete="CASCADE"))
    annee: Mapped[int] = mapped_column(SmallInteger)
    semestre: Mapped[int] = mapped_column(SmallInteger)
    intitule: Mapped[str] = mapped_column(Text)
    credits: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))
    volume_horaire: Mapped[int | None] = mapped_column(Integer)
    ordre: Mapped[int] = mapped_column(SmallInteger, server_default="0")

    formation: Mapped[Formation] = relationship(back_populates="modules")


class Tarif(Base):
    __tablename__ = "tarifs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    formation_id: Mapped[int] = mapped_column(ForeignKey("formations.id", ondelete="CASCADE"))
    annee_universitaire: Mapped[str] = mapped_column(String(9))
    frais_inscription: Mapped[Decimal] = mapped_column(Numeric(10, 3), server_default="0")
    frais_scolarite: Mapped[Decimal] = mapped_column(Numeric(10, 3))
    devise: Mapped[str] = mapped_column(String(3), server_default="TND")
    modalites_paiement: Mapped[str | None] = mapped_column(Text)
    remarques: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    formation: Mapped[Formation] = relationship(back_populates="tarifs")


class ConditionAdmission(Base):
    __tablename__ = "conditions_admission"

    formation_id: Mapped[int] = mapped_column(
        ForeignKey("formations.id", ondelete="CASCADE"), primary_key=True
    )
    diplome_requis: Mapped[str] = mapped_column(Text)
    niveau_acces: Mapped[str | None] = mapped_column(Text)
    moyenne_minimale: Mapped[Decimal | None] = mapped_column(Numeric(4, 2))
    test_anglais_requis: Mapped[bool] = mapped_column(Boolean, server_default="false")
    entretien_requis: Mapped[bool] = mapped_column(Boolean, server_default="true")
    pieces_requises: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default="{}")
    description: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    formation: Mapped[Formation] = relationship(back_populates="conditions")
