# SmartCampus AI — Backend

Backend FastAPI + PostgreSQL du projet SmartCampus AI (orientation et préinscription NAU).
Structure conforme au document d'architecture SA-4 (§8).

## Tickets couverts dans cette contribution (Marwen)

| Ticket | Contenu | Fichiers principaux |
|---|---|---|
| SA-7  | Initialisation du backend : app FastAPI, config `.env`, CORS, `/health`, gestion des conflits (409), Dockerfile | `app/main.py`, `app/core/` |
| SA-16 | PostgreSQL : connexion SQLAlchemy, exécuteur de migrations SQL, docker-compose avec healthcheck | `app/core/database.py`, `app/db/migrate.py`, `database/migrations/001_init.sql`, `docker-compose.yml` |
| SA-20 | API des formations et des programmes (liste filtrée et paginée, détail, création, modification, archivage, programme par année/semestre) | `app/api/v1/formations.py` |
| SA-21 | API des tarifs et des conditions d'admission, consultation par budget, comparaison de 2 à 4 formations | `app/api/v1/admissions.py` |
| SA-26 | Mémoire temporaire des conversations : expiration après inactivité, fenêtre de contexte bornée pour le LLM, purge | `app/services/memory/`, `app/api/v1/conversations.py` |
| SA-28 | Comptes, authentification Argon2id/Bearer et rôles avec périmètre établissement | `app/api/v1/auth.py`, `app/core/security.py` |

## Démarrage

### Avec Docker (recommandé)
```bash
cd backend
cp .env.example .env          # puis changer POSTGRES_PASSWORD
docker compose up --build
docker compose exec backend python -m app.db.migrate --seed   # données de démo (facultatif)
```
Documentation interactive : http://localhost:8000/docs

### Sans Docker
```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows : .venv\Scripts\activate
pip install -r requirements-dev.txt
cp .env.example .env           # adapter DATABASE_URL
python -m app.db.migrate --seed
uvicorn app.main:app --reload
```

### Tests
```bash
cd backend
pytest                                  # tests unitaires et API sur SQLite isolé
TEST_DATABASE_URL=... pytest tests/test_api.py  # intégration PostgreSQL facultative
```
Les tests API locaux remplacent `get_db` par une base SQLite en mémoire et ne lisent
ni n'écrivent dans une base de développement ou de production. `tests/test_api.py`
nécessite une base PostgreSQL de test séparée, migrée et seedée.

## Endpoints (préfixe `/api/v1`)

La consultation du catalogue reste publique. Les écritures de formations, programmes,
tarifs et conditions exigent un compte authentifié avec le rôle correspondant à
l'établissement concerné, ou le rôle `administrateur`. L'inscription publique attribue
uniquement le rôle `candidat`.

| Méthode | Route | Ticket |
|---|---|---|
| GET | `/etablissements` | SA-20 |
| GET | `/formations?etablissement=&niveau=&domaine=&q=&limit=&offset=` | SA-20 |
| GET | `/formations/{id}` (avec programme) | SA-20 |
| POST / PATCH / DELETE* | `/formations`, `/formations/{id}` (*archivage) | SA-20 |
| GET / PUT | `/formations/{id}/programme` | SA-20 |
| GET | `/tarifs?annee=&etablissement=&niveau=&budget_max=` | SA-21 |
| GET | `/formations/{id}/tarifs?annee=` | SA-21 |
| PUT / DELETE | `/formations/{id}/tarifs/{2026-2027}` | SA-21 |
| GET / PUT | `/formations/{id}/conditions` | SA-21 |
| GET | `/formations/compare?ids=1,3&annee=` | SA-21 |
| POST | `/conversations/{session_id}/messages` | SA-26 |
| GET | `/conversations/{session_id}/messages` (historique) | SA-26 |
| GET | `/conversations/{session_id}/context` (fenêtre pour le LLM) | SA-26 |
| DELETE | `/conversations/{session_id}` | SA-26 |
| POST | `/visitor-sessions` | SA-25 |
| GET / DELETE | `/visitor-sessions/{session_id}` | SA-25 |
| POST | `/visitor-sessions/{session_id}/claim` | SA-29 |
| POST | `/auth/register` | SA-28 |
| POST | `/auth/login` | SA-28 |
| GET | `/auth/me` | SA-28 |
| POST | `/auth/logout` | SA-28 |

Les routes SA-25 créent un UUID côté serveur et placent le secret d'accès dans un cookie
`HttpOnly`, `SameSite=Lax` (et `Secure` en production). Seul son hash SHA-256 est stocké.
Avant le rattachement, les routes de conversation vérifient la propriété par ce cookie.
Un utilisateur authentifié peut appeler `/visitor-sessions/{session_id}/claim` : le cookie
prouve la propriété initiale, puis le compte devient propriétaire de la session sans déplacer
ni effacer l'historique. Après le rattachement, l'accès aux conversations et à la session
requiert le Bearer du même compte; le cookie seul ne suffit plus. Le rattachement est
idempotent pour ce compte et refusé si la session appartient déjà à un autre compte.
La déconnexion révoque le Bearer sans délier la session, et une session terminée ou expirée
reste inaccessible. La durée d'inactivité se configure avec `VISITOR_SESSION_TTL_MINUTES`
(60 par défaut). Terminer une session efface aussi sa mémoire SA-26. Le worker
`python -m app.workers.purge_memory` purge périodiquement les sessions terminées ou expirées.

Les comptes utilisent Argon2id pour les mots de passe et des jetons Bearer opaques,
aléatoires et révocables; seul leur hash SHA-256 est stocké. Les jetons expirent après
`AUTH_TOKEN_TTL_MINUTES` (60 par défaut). Le rôle public par défaut est `candidat`;
les rôles responsables et administrateur doivent être attribués par une procédure
administrative. Les rôles responsables sont limités à leur établissement.

## Migrations

Fichiers `database/migrations/NNN_nom.sql`, appliqués dans l'ordre et une seule fois
(table `schema_migrations`). Pour modifier le schéma : **ajouter** un nouveau fichier
(`006_...sql` après SA-28), ne jamais modifier une migration déjà appliquée.

```bash
python -m app.db.migrate --status
```

## Points à coordonner avec l'équipe

- **Islem (SA-12 / SA-17)** : `002_catalogue.sql` crée les tables du catalogue pour débloquer
  SA-20/21. À fusionner avec votre modèle : une seule version des tables doit rester.
- **Islem (SA-18)** : `database/seeds/001_catalogue_demo.sql` contient des données **fictives** ;
  à remplacer par les données collectées.
- **Fares (SA-25 / SA-29)** : la mémoire conserve le même UUID de session avant et après
  rattachement au compte authentifié.
- **Souhaila (SA-36 / SA-37)** : utiliser `memory.context_for_llm(session_id)` pour l'historique
  envoyé au LLM (voir `services/memory/__init__.py`).
- **Worker** : lancer `python -m app.workers.purge_memory` périodiquement.
