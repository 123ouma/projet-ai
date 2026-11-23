from fastapi import APIRouter

from app.api.v1 import admissions, conversations, formations

api_router = APIRouter()
# Ordre important : admissions contient /formations/compare, à déclarer avant /formations/{id}
api_router.include_router(admissions.router)
api_router.include_router(formations.router)
api_router.include_router(conversations.router)
