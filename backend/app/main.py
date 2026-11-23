"""Point d'entrée de l'API SmartCampus AI (SA-7).

Lancer en local :  uvicorn app.main:app --reload   (depuis le dossier backend/)
Documentation :    http://localhost:8000/docs
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.database import check_database

settings = get_settings()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("smartcampus")


@asynccontextmanager
async def lifespan(_: FastAPI):
    logger.info("Démarrage %s (%s)", settings.app_name, settings.environment)
    if not check_database():
        logger.warning("PostgreSQL injoignable au démarrage : vérifier DATABASE_URL.")
    yield


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(IntegrityError)
async def integrity_error_handler(_: Request, exc: IntegrityError):
    # Doublon (contrainte UNIQUE) ou référence invalide (clé étrangère)
    logger.info("Conflit d'intégrité : %s", exc.orig)
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={"detail": "Conflit avec les données existantes (doublon ou référence invalide)."},
    )


@app.get("/health", tags=["Santé"])
def health():
    return {"status": "ok"}


@app.get("/health/db", tags=["Santé"])
def health_db():
    ok = check_database()
    return JSONResponse(
        status_code=200 if ok else 503,
        content={"status": "ok" if ok else "indisponible", "database": ok},
    )


app.include_router(api_router, prefix=settings.api_prefix)
