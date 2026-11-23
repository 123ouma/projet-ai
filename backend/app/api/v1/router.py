from fastapi import APIRouter

from app.api.v1 import admissions, auth, conversations, formations, visitor_sessions

api_router = APIRouter()
# Ordre important : admissions contient /formations/compare, à déclarer avant /formations/{id}
api_router.include_router(admissions.router)
api_router.include_router(formations.router)
api_router.include_router(auth.router)
api_router.include_router(conversations.router)
api_router.include_router(visitor_sessions.router)
