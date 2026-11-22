"""Protection PROVISOIRE des routes d'écriture du catalogue.

À remplacer par la vérification du rôle « responsable NAU » de SA-28 (Fares).
En attendant, les routes POST/PUT/PATCH/DELETE exigent l'en-tête X-Admin-Token.
La consultation reste publique (architecture §7.1).
"""
import secrets

from fastapi import Header, HTTPException, status

from app.core.config import get_settings


def require_responsable(x_admin_token: str | None = Header(default=None)) -> None:
    expected = get_settings().admin_api_token
    if not expected:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Écriture désactivée : ADMIN_API_TOKEN n'est pas configuré.",
        )
    if not x_admin_token or not secrets.compare_digest(x_admin_token, expected):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Jeton administrateur invalide.")
